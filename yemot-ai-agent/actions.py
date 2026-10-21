"""פעולות עם תופעות לוואי. כל פעולה מוכנה (pending) ומבוצעת רק אחרי אישור קולי,
וההחלטה אם התקבל אישור נעשית בקוד כאן, לא במודל."""
import json
import logging
import os
import re

import config
import yemot_client

log = logging.getLogger("actions")

_YES = re.compile(r"^(כן|בטח|אישור|מאשר|מאשרת|אשר|שלח|תשלח|חייג|תחייג|בסדר|סבבה|יאללה|אוקיי|אוקי|ok|yes)\b", re.I)
_NO = re.compile(r"(^|\s)(לא|בטל|ביטול|עצור|עזוב|אל)(\s|$)")


def normalize_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("00972"):
        d = d[5:]
    elif d.startswith("972"):
        d = d[3:]
    if d and not d.startswith("0"):
        d = "0" + d
    return d


def valid_phone(p: str) -> bool:
    return bool(re.fullmatch(r"0\d{8,9}", p))


def load_contacts() -> dict:
    try:
        with open(config.CONTACTS_FILE, encoding="utf-8") as f:
            return {name: normalize_phone(num) for name, num in json.load(f).items()}
    except FileNotFoundError:
        return {}
    except Exception:
        log.exception("contacts file unreadable")
        return {}


def resolve_target(to: str) -> tuple[str | None, str]:
    """שם איש קשר או מספר -> (מספר, שם להקראה)."""
    contacts = load_contacts()
    to = (to or "").strip()
    if to in contacts:
        return contacts[to], to
    for name, num in contacts.items():
        if to and (to in name or name in to):
            return num, name
    p = normalize_phone(to)
    return (p, p) if valid_phone(p) else (None, to)


def classify_confirmation(text: str) -> str:
    """'yes' / 'no' / 'other'. הקשה 1 = כן, 2 = לא."""
    t = (text or "").strip().rstrip(".,!?").strip()
    if t in ("Digits-1", "1"):
        return "yes"
    if t in ("Digits-2", "2"):
        return "no"
    if _NO.search(t):
        return "no"
    if _YES.match(t):
        return "yes"
    return "other"


# --- הכנת פעולות (נקראות על ידי כלי המודל) ---

def stage_sms(st, to: str, message: str) -> str:
    phone, label = resolve_target(to)
    if not phone:
        return "שגיאה: לא נמצא איש קשר או מספר תקין. בקש מהמשתמש לחזור על השם או המספר."
    if not message.strip():
        return "שגיאה: תוכן ההודעה ריק."
    st.pending = {"kind": "sms", "phone": phone, "message": message.strip(),
                  "say": f"לשלוח הודעה ל{label}: {message.strip()}"}
    return "ממתין לאישור קולי של המשתמש. הקרא לו בקצרה מה יישלח ובקש שיאמר כן לאישור."


def stage_bridge(st, to: str) -> str:
    phone, label = resolve_target(to)
    if not phone:
        return "שגיאה: לא נמצא איש קשר או מספר תקין. בקש מהמשתמש לחזור על השם או המספר."
    st.pending = {"kind": "bridge", "phone": phone,
                  "say": f"לחייג אליך ולחבר אותך ל{label}"}
    return "ממתין לאישור קולי של המשתמש. הקרא לו בקצרה מה יקרה ובקש שיאמר כן לאישור."


def execute_pending(pending: dict) -> str:
    try:
        if pending["kind"] == "sms":
            yemot_client.send_sms(pending["phone"], pending["message"])
            return "ההודעה נשלחה"
        if pending["kind"] == "bridge":
            yemot_client.bridge_call(config.OWNER_PHONE, pending["phone"])
            return "החיוג הופעל, הטלפון שלך יצלצל בעוד רגע"
        return "פעולה לא מוכרת"
    except Exception as e:
        log.exception("execute failed")
        return f"הפעולה נכשלה: {e}"


def resolve_pending(st, user_text: str) -> str | None:
    """אם יש פעולה ממתינה: מבצע או מבטל לפי התשובה, ומחזיר הודעת מערכת למודל."""
    if not st.pending:
        return None
    pending, st.pending = st.pending, None
    verdict = classify_confirmation(user_text)
    if verdict == "yes":
        return f"[הודעת מערכת: המשתמש אישר. תוצאה: {execute_pending(pending)}]"
    return "[הודעת מערכת: הפעולה הממתינה בוטלה כי המשתמש לא אישר]"
