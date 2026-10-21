import datetime
import logging
import re
import zoneinfo

import anthropic

import actions
import config

log = logging.getLogger("agent")
_client = None

MAX_STEPS = 4
KEEP_MESSAGES = 30

TOOLS = [
    {
        "name": "send_sms",
        "description": "מכין שליחת הודעת SMS. הפעולה לא מתבצעת עד שהמשתמש מאשר בקול.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "שם איש קשר מהרשימה, או מספר טלפון"},
                "message": {"type": "string", "description": "תוכן ההודעה"},
            },
            "required": ["to", "message"],
        },
    },
    {
        "name": "call_me_and_connect",
        "description": "מחייג אל המשתמש ואחרי שהוא עונה מחבר אותו אל הנמען. דורש אישור קולי.",
        "input_schema": {
            "type": "object",
            "properties": {"to": {"type": "string", "description": "שם איש קשר או מספר טלפון"}},
            "required": ["to"],
        },
    },
    {
        "name": "end_call",
        "description": "מסיים את השיחה הנוכחית. לקרוא רק כשהמשתמש מבקש לסיים או להתראות.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _system_prompt() -> str:
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M")
    names = ", ".join(actions.load_contacts()) or "אין"
    return (
        "אתה עוזר אישי בשיחת טלפון עם הבעלים שלך. הכול מוקרא בקול, לכן:\n"
        "- ענה בעברית, במשפט עד שלושה משפטים קצרים.\n"
        "- בלי רשימות, כוכביות, כותרות, אימוג'ים או סימנים מיוחדים, ובלי נקודה באמצע מספרים.\n"
        "- התמלול של דיבור המשתמש עלול להכיל טעויות. אם משהו לא ברור, שאל.\n"
        "- לפני שליחת הודעה או חיוג הפעל את הכלי המתאים. הוא יכין את הפעולה והמשתמש יתבקש לאשר בקול. "
        "אחרי הפעלת הכלי הקרא למשתמש מה יתבצע ובקש שיאמר כן.\n"
        "- אל תגיד שפעולה בוצעה עד שקיבלת הודעת מערכת שמאשרת זאת.\n"
        "- כשהמשתמש מבקש לסיים, קרא ל-end_call ואמור שלום קצר.\n"
        f"אנשי קשר ידועים: {names}.\n"
        f"התאריך והשעה עכשיו בישראל: {now}."
    )


def _client_instance():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=25.0, max_retries=1)
    return _client


def _run_tool(st, name: str, args: dict) -> str:
    if name == "send_sms":
        return actions.stage_sms(st, args.get("to", ""), args.get("message", ""))
    if name == "call_me_and_connect":
        return actions.stage_bridge(st, args.get("to", ""))
    if name == "end_call":
        st.ended = True
        return "השיחה תיסגר אחרי המשפט הבא שלך"
    return "כלי לא מוכר"


def _trim(messages: list) -> list:
    """חותך רק בתחילת תור משתמש אמיתי, כדי לא לשבור זוגות tool_use/tool_result."""
    if len(messages) <= KEEP_MESSAGES:
        return messages
    for i in range(len(messages) - KEEP_MESSAGES, len(messages)):
        if messages[i]["role"] == "user" and isinstance(messages[i]["content"], str):
            return messages[i:]
    return messages


def _user_content(text: str) -> str:
    if text.startswith("Digits-"):
        return f"[המשתמש הקיש במקשים: {text[7:]}]"
    return text


def chat(st, user_text: str) -> tuple[str, bool]:
    """מחזיר (טקסט להקראה, האם לסיים את השיחה)."""
    system_note = actions.resolve_pending(st, user_text)
    content = _user_content(user_text)
    if system_note:
        content = f"{system_note}\nהמשתמש אמר: {content}"

    messages = st.history + [{"role": "user", "content": content}]
    text = ""
    for _ in range(MAX_STEPS):
        resp = _client_instance().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=400,
            system=_system_prompt(), tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason != "tool_use":
            break
        results = [{"type": "tool_result", "tool_use_id": b.id,
                    "content": _run_tool(st, b.name, b.input)}
                   for b in resp.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    st.history = _trim(messages)
    return text or "בסדר", st.ended
