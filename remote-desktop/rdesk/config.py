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


def host_identity(cfg: dict) -> tuple[str, str]:
    """מזהה קבוע; סיסמה קבועה אם הוגדרה, אחרת חדשה בכל הפעלה."""
    changed = False
    if not cfg.get("id"):
        cfg["id"] = P.new_id(); changed = True
    if changed:
        save(cfg)
    return cfg["id"], cfg.get("password") or P.new_password()
