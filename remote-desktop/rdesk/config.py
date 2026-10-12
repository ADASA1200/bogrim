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
