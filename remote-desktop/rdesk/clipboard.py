"""גישה ללוח הגזירים (pyperclip) בצורה בטוחה לחריגות."""
from __future__ import annotations


class Clipboard:
    def __init__(self) -> None:
        try:
            import pyperclip
            self._p = pyperclip
        except Exception:
            self._p = None

    def get(self) -> str | None:
        if not self._p:
            return None
        try:
            return self._p.paste()
        except Exception:
            return None

    def set(self, text: str) -> None:
        if not self._p:
            return
        try:
            self._p.copy(text)
        except Exception:
            pass


class MemoryClipboard:
    """לוח בזיכרון לבדיקות."""

    def __init__(self, text: str = "") -> None:
        self.text = text

    def get(self) -> str | None: return self.text
    def set(self, text: str) -> None: self.text = text
