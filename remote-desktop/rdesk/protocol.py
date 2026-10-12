"""קבועים, אימות סיסמה והודעות משותפים ל-host, viewer ולשרת האיתות."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, asdict

DEFAULT_SERVER = "ws://127.0.0.1:8765"
MAX_SIGNAL_BYTES = 256 * 1024       # גודל מקסימלי להודעת איתות (SDP בלבד)
MAX_CLIPBOARD_BYTES = 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
FILE_CHUNK = 16 * 1024
MAX_AUTH_ATTEMPTS = 5               # ניסיונות סיסמה שגויים לפני חסימה זמנית
BLOCK_SECONDS = 60


def new_id() -> str:
    """מזהה בן 9 ספרות, בסגנון AnyDesk."""
    return "".join(str(secrets.randbelow(10)) for _ in range(9))


def format_id(raw: str) -> str:
    raw = "".join(c for c in raw if c.isdigit())
    return " ".join(raw[i:i + 3] for i in range(0, len(raw), 3))


def clean_id(raw: str) -> str:
    return "".join(c for c in raw if c.isdigit())


def new_password(length: int = 10) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXYZ2346789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def new_nonce() -> str:
    return secrets.token_hex(16)


def auth_tag(password: str, nonce: str, role: str, sdp: str) -> str:
    """חתימה על ה-SDP (כולל טביעת האצבע של DTLS) באמצעות הסיסמה.

    כך גם שרת איתות עוין לא יכול לבצע MITM: בלי הסיסמה הוא לא יכול לזייף
    offer / answer עם טביעת אצבע משלו.
    """
    key = hashlib.sha256(("rdesk-v1:" + password).encode()).digest()
    msg = f"{role}\n{nonce}\n{sdp}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_tag(password: str, nonce: str, role: str, sdp: str, tag: str) -> bool:
    return hmac.compare_digest(auth_tag(password, nonce, role, sdp), tag or "")


@dataclass
class Permissions:
    """הרשאות שהמארח מעניק לצופה בסשן."""
    control: bool = True      # עכבר ומקלדת
    clipboard: bool = True
    files: bool = True
    chat: bool = True

    def to_json(self) -> dict:
        return asdict(self)


def dumps(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def loads(text) -> dict:
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj
