"""חשבון + פנקס כתובות משותף (בצד שרת האיתות): גרסה מצומצמת ועצמאית
ל-host-it-yourself, לא שירות בענן בתשלום כמו my.anydesk.com - בלי חיוב,
בלי ניהול ארגון, בלי התקנת-מרחוק. בחשבון יש שם משתמש+סיסמה ורשימת אנשי
קשר (id + תווית), ששמורה בקובץ JSON בצד השרת ומסונכרנת בין כל המכשירים
שמתחברים לאותו שרת עם אותו חשבון.

הסיסמה נשמרת כ-hash מסוג PBKDF2 עם salt אקראי לכל חשבון - בדיוק כמו
derive_key ב-protocol.py, רק עם salt נפרד כדי ששני חשבונות עם סיסמה
זהה לא ייראו זהים בקובץ."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LEN = 8


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


class AccountStore:
    """אחסון חשבונות ופנקסי כתובות בקובץ JSON יחיד. בטוח לקריאה/כתיבה
    חוזרת תוך כדי ריצת השרת - כל פעולה טוענת וכותבת את הקובץ בשלמותו
    (מספיק לנפח נתונים כזה; בלי DB חיצוני כדי לא להוסיף תלות)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    def register(self, username: str, password: str) -> None:
        if not _USERNAME_RE.match(username or ""):
            raise ValueError("bad_username")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError("password_too_short")
        data = self._load()
        if username in data:
            raise ValueError("username_taken")
        salt = os.urandom(16)
        data[username] = {
            "salt": salt.hex(),
            "hash": _hash_password(password, salt).hex(),
            "contacts": [],
        }
        self._save(data)

    def verify(self, username: str, password: str) -> bool:
        data = self._load()
        acct = data.get(username)
        if not acct:
            return False
        try:
            salt = bytes.fromhex(acct["salt"])
            expected = bytes.fromhex(acct["hash"])
        except (KeyError, ValueError):
            return False
        return hmac.compare_digest(_hash_password(password, salt), expected)

    def get_contacts(self, username: str) -> list[dict]:
        data = self._load()
        acct = data.get(username)
        return list(acct.get("contacts", [])) if acct else []

    def set_contacts(self, username: str, contacts: list[dict]) -> None:
        data = self._load()
        if username not in data:
            raise ValueError("no_such_account")
        cleaned = []
        for c in contacts[:200]:
            if not isinstance(c, dict):
                continue
            cid = re.sub(r"\D", "", str(c.get("id", "")))[:32]
            label = str(c.get("label", ""))[:80]
            if cid:
                cleaned.append({"id": cid, "label": label})
        data[username]["contacts"] = cleaned
        self._save(data)
