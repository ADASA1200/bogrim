"""הגדרות מקומיות ב-~/.rdesk/config.json (הרשאות 0600)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import protocol as P

CONFIG_DIR = Path(os.environ.get("RDESK_HOME", Path.home() / ".rdesk"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def load() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(CONFIG_FILE)


def host_identity(cfg: dict) -> str:
    """מזהה קבוע (נוצר פעם אחת ונשמר)."""
    if not cfg.get("id"):
        cfg["id"] = P.new_id()
        save(cfg)
    return cfg["id"]


def viewer_identity(cfg: dict) -> str:
    """מזהה פנימי קבוע לצופה הזה (לא המזהה החיוג - זה רק למארחים לזהות
    "אותו מכשיר" בין התחברויות, כדי ש"אמון תמידי" יעבוד בכלל). נוצר פעם אחת ונשמר,
    בניגוד למזהה אקראי-חדש-בכל-חיבור."""
    if not cfg.get("viewer_id"):
        cfg["viewer_id"] = "v" + P.new_nonce()[:12]
        save(cfg)
    return cfg["viewer_id"]


# ---- גישה ללא נוכחות -------------------------------------------------
MIN_UNATTENDED_LEN = 8


def get_unattended(cfg: dict) -> tuple[bytes | None, P.Permissions]:
    u = cfg.get("unattended") or {}
    perms = P.Permissions(**{k: bool(v) for k, v in (u.get("perms") or {}).items()
                             if k in P.Permissions.__dataclass_fields__})
    try:
        key = bytes.fromhex(u["key"]) if u.get("key") else None
    except ValueError:
        key = None
    return key, perms


def set_unattended(cfg: dict, password: str | None, perms: P.Permissions) -> bytes | None:
    """שומר מפתח נגזר (לא את הסיסמה עצמה). password=None משאיר את הסיסמה הקיימת ומעדכן הרשאות."""
    u = cfg.setdefault("unattended", {})
    if password is not None:
        if len(password) < MIN_UNATTENDED_LEN:
            raise ValueError("password too short")
        u["key"] = P.derive_key(password).hex()
    u["perms"] = perms.to_json()
    save(cfg)
    return get_unattended(cfg)[0]


def clear_unattended(cfg: dict) -> None:
    cfg.pop("unattended", None)
    save(cfg)


def server_url(arg: str | None = None) -> str:
    """עדיפות: פרמטר מפורש > הגדרות משתמש > ברירת המחדל."""
    return arg or load().get("server") or P.DEFAULT_SERVER


# ---- מצב "המחשב הזה הוא גם השרת" (בלי שרת איתות נפרד) --------------------
DEFAULT_EMBEDDED_PORT = 8765


def get_embedded(cfg: dict) -> tuple[bool, int]:
    e = cfg.get("embedded_server") or {}
    port = e.get("port", DEFAULT_EMBEDDED_PORT)
    if not isinstance(port, int) or not (1 <= port <= 65535):
        port = DEFAULT_EMBEDDED_PORT
    return bool(e.get("enabled", False)), port


def set_embedded(cfg: dict, enabled: bool, port: int = DEFAULT_EMBEDDED_PORT) -> None:
    cfg["embedded_server"] = {"enabled": bool(enabled), "port": int(port)}
    save(cfg)


# ---- פרופילי הרשאה שמורים (אמון תמידי למזהה ספציפי) ---------------------
def get_trusted(cfg: dict, peer: str) -> P.Permissions | None:
    """הרשאות שמורות עבור מזהה ספציפי - מדלג על בקשת האישור הרגילה, בלי צורך בסיסמה גלובלית."""
    t = (cfg.get("trusted") or {}).get(peer)
    if t is None:
        return None
    return P.Permissions(**{k: bool(v) for k, v in t.items() if k in P.Permissions.__dataclass_fields__})


def list_trusted(cfg: dict) -> dict[str, dict]:
    return dict(cfg.get("trusted") or {})


def set_trusted(cfg: dict, peer: str, perms: P.Permissions) -> None:
    cfg.setdefault("trusted", {})[peer] = perms.to_json()
    save(cfg)


def remove_trusted(cfg: dict, peer: str) -> None:
    (cfg.get("trusted") or {}).pop(peer, None)
    save(cfg)


# ---- בקרת גישה: רשימת IP מורשים + אימות דו-שלבי (TOTP) ------------------
def get_ip_whitelist(cfg: dict) -> list[str]:
    return list(cfg.get("ip_whitelist") or [])


def set_ip_whitelist(cfg: dict, entries: list[str]) -> None:
    cfg["ip_whitelist"] = [str(e).strip() for e in entries if str(e).strip()]
    save(cfg)


def get_totp_secret(cfg: dict) -> str | None:
    """קוד דו-שלבי נוסף על סיסמת הגישה ללא-נוכחות (לא רלוונטי לחיבור אינטראקטיבי,
    שכבר דורש אישור אנושי חי - זה מחזק בדיוק את המקרה שאין בו נוכחות)."""
    return (cfg.get("unattended") or {}).get("totp_secret")


def set_totp_secret(cfg: dict, secret: str | None) -> None:
    u = cfg.setdefault("unattended", {})
    if secret:
        u["totp_secret"] = secret
    else:
        u.pop("totp_secret", None)
    save(cfg)


# ---- מצב בקשת-אישור לחיבור אינטראקטיבי (כמו Interactive Access ב-AnyDesk) --
INTERACTIVE_ALWAYS = "always"          # תמיד לשאול (ברירת מחדל, המצב הקיים)
INTERACTIVE_WINDOW_OPEN = "window_open"  # לשאול רק כשהחלון פתוח (לא מוסתר למגש)
INTERACTIVE_NEVER = "never"            # לעולם לא - רק גישה ללא-נוכחות עם סיסמה
_INTERACTIVE_MODES = (INTERACTIVE_ALWAYS, INTERACTIVE_WINDOW_OPEN, INTERACTIVE_NEVER)


def get_interactive_mode(cfg: dict) -> str:
    m = cfg.get("interactive_mode")
    return m if m in _INTERACTIVE_MODES else INTERACTIVE_ALWAYS


def set_interactive_mode(cfg: dict, mode: str) -> None:
    if mode not in _INTERACTIVE_MODES:
        raise ValueError("bad interactive mode")
    cfg["interactive_mode"] = mode
    save(cfg)


# ---- Wake-on-LAN: כתובת MAC שמורה למזהה מרוחק ספציפי ---------------------
def get_wol_mac(cfg: dict, host_id: str) -> str | None:
    return (cfg.get("wol") or {}).get(host_id)


def set_wol_mac(cfg: dict, host_id: str, mac: str | None) -> None:
    w = cfg.setdefault("wol", {})
    if mac:
        w[host_id] = mac
    else:
        w.pop(host_id, None)
    save(cfg)
