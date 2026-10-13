"""בקרת גישה: רשימת IP מורשים (ACL) ואימות דו-שלבי (TOTP, RFC 6238) לגישה
ללא-נוכחות - כמו ה-Access Control List והאימות הדו-שלבי של AnyDesk.

TOTP מיושם כאן ישירות (hashlib/hmac סטנדרטיים) בלי תלות חדשה, ותואם כל
אפליקציית אימות רגילה (Google Authenticator וכו') שמקבלת מפתח Base32."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import struct
import time


def ip_allowed(ip: str | None, whitelist: list[str]) -> bool:
    """רשימה ריקה = בלי הגבלה (ברירת המחדל). כל רשומה היא IP בודד או רשת CIDR."""
    if not whitelist:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in whitelist:
        entry = entry.strip()
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def totp_new_secret() -> str:
    return base64.b32encode(os.urandom(10)).decode("ascii")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    padded = secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_code(secret_b32: str, t: float | None = None, step: int = 30) -> str:
    return _hotp(secret_b32, int((t if t is not None else time.time()) // step))


def totp_verify(secret_b32: str, code: str, t: float | None = None, step: int = 30, window: int = 1) -> bool:
    """window=1 סולח על הפרש של עד צעד זמן אחד (שעונים לא מסונכרנים בול)."""
    if not secret_b32 or not code:
        return False
    now = t if t is not None else time.time()
    try:
        for drift in range(-window, window + 1):
            if hmac.compare_digest(totp_code(secret_b32, now + drift * step, step), code.strip()):
                return True
    except Exception:   # מפתח/קוד לא תקינים - נכשל בבטחה, בלי להעלות חריגה
        return False
    return False
