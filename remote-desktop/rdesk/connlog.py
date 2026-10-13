"""יומן חיבורים: מי התחבר, מתי, כמה זמן ובאיזה מצב - קובץ נפרד מ-config.json
(כדי לא להעמיס עליו) בתיקיית ההגדרות, עם שמירה אטומית ו-0600 כמוהו."""
from __future__ import annotations

import json
import os
import time

from . import config

LOG_FILE = config.CONFIG_DIR / "connections.json"
MAX_ENTRIES = 200


def _load() -> list[dict]:
    try:
        data = json.loads(LOG_FILE.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(entries: list[dict]) -> None:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LOG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), "utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(LOG_FILE)


def start_entry(peer: str, mode: str, perms: dict) -> None:
    entries = _load()
    entries.append({"peer": peer, "mode": mode, "perms": perms, "startedAt": time.time(), "endedAt": None})
    if len(entries) > MAX_ENTRIES:
        del entries[: len(entries) - MAX_ENTRIES]
    _save(entries)


def end_last(peer: str) -> None:
    """מסמן את הרשומה הפתוחה האחרונה של peer זה כסגורה (לפי שעת סיום)."""
    entries = _load()
    for e in reversed(entries):
        if e.get("peer") == peer and e.get("endedAt") is None:
            e["endedAt"] = time.time()
            break
    _save(entries)


def recent(limit: int = 50) -> list[dict]:
    return list(reversed(_load()))[:limit]


def clear() -> None:
    _save([])
