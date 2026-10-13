"""קבועים, אימות סיסמה והודעות משותפים ל-host, viewer ולשרת האיתות."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import urllib.parse
from dataclasses import dataclass, asdict

import os

# כתובת שרת האיתות. אפשר לשנות כאן לפני בניית ה-EXE, או במשתנה סביבה / בהגדרות התוכנה.
DEFAULT_SERVER = os.environ.get("RDESK_SERVER", "ws://127.0.0.1:8765")
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


def derive_key(password: str) -> bytes:
    """מפתח משותף מהסיסמה (PBKDF2). אפשר לשמור אותו בדיסק במקום הסיסמה עצמה."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"rdesk-v1", 200_000)


def auth_tag(key: bytes, nonce: str, role: str, sdp: str) -> str:
    """חתימה על ה-SDP (כולל טביעת האצבע של DTLS) באמצעות מפתח הסיסמה.

    כך גם שרת איתות עוין לא יכול לבצע MITM: בלי הסיסמה הוא לא יכול לזייף
    offer / answer עם טביעת אצבע משלו.
    """
    msg = f"{role}\n{nonce}\n{sdp}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_tag(key: bytes, nonce: str, role: str, sdp: str, tag: str) -> bool:
    return hmac.compare_digest(auth_tag(key, nonce, role, sdp), tag or "")


def _fingerprint(sdp: str) -> str:
    m = re.search(r"a=fingerprint:sha-256 ([0-9A-Fa-f:]+)", sdp)
    return m.group(1).upper() if m else ""


def session_code(offer_sdp: str, answer_sdp: str) -> str:
    """קוד בן 6 ספרות שנגזר מטביעות האצבע של שני הצדדים.

    שני הצדדים מחשבים אותו בנפרד ממה שהם ראו. אם שרת איתות עוין החליף SDP
    (MITM) - הקודים יהיו שונים. אפשר להשוות אותם בעל-פה.
    """
    h = hashlib.sha256((_fingerprint(offer_sdp) + "|" + _fingerprint(answer_sdp)).encode()).digest()
    n = int.from_bytes(h[:4], "big") % 1_000_000
    return f"{n:06d}"[:3] + " " + f"{n:06d}"[3:]


INVITE_SCHEME = "rdesk"


def make_invite_url(host_id: str, token: str, server: str) -> str:
    """קישור הזמנה לסשן (כמו Session Invitation של AnyDesk): פתיחתו מתחברת
    אוטומטית, חד-פעמית, בלי להקליד שום דבר. ה-token נבדק/נצרך בצד המארח."""
    return f"{INVITE_SCHEME}://connect/{clean_id(host_id)}/{token}?server={urllib.parse.quote(server, safe='')}"


def parse_invite_url(url: str) -> dict | None:
    try:
        parsed = urllib.parse.urlparse((url or "").strip())
    except ValueError:
        return None
    if parsed.scheme != INVITE_SCHEME or parsed.netloc != "connect":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2:
        return None
    host_id, token = clean_id(parts[0]), parts[1]
    if not host_id or not token:
        return None
    server = urllib.parse.parse_qs(parsed.query).get("server", [""])[0]
    return {"id": host_id, "token": token, "server": server or None}


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
