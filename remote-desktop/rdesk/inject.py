"""הזרקת עכבר ומקלדת בצד המארח (pynput), עם ולידציה קפדנית של הקלט."""
from __future__ import annotations

import sys

# שמות מקשים מותרים (תואמים ל-pynput.keyboard.Key)
NAMED_KEYS = {
    "enter", "tab", "space", "backspace", "delete", "esc", "home", "end",
    "page_up", "page_down", "up", "down", "left", "right", "insert",
    "shift", "ctrl", "alt", "cmd", "caps_lock", "menu", "print_screen",
    "pause", "num_lock", "scroll_lock",
    *(f"f{i}" for i in range(1, 25)),
}
BUTTONS = {"left", "right", "middle"}


def _clamp01(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, v))


class NullInjector:
    """מתעד אירועים בלי להזריק אותם (בדיקות / מצב צפייה בלבד)."""

    def __init__(self) -> None:
        self.events: list[tuple] = []

    def mouse_move(self, x: int, y: int) -> None: self.events.append(("move", x, y))
    def mouse_button(self, b: str, down: bool) -> None: self.events.append(("button", b, down))
    def scroll(self, dx: int, dy: int) -> None: self.events.append(("scroll", dx, dy))
    def key(self, name: str, down: bool) -> None: self.events.append(("key", name, down))
    def release_all(self) -> None: self.events.append(("release_all",))


class PynputInjector:
    def __init__(self) -> None:
        if sys.platform == "win32":
            try:  # קואורדינטות פיזיות בלי קנה מידה של DPI
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass
        from pynput import keyboard, mouse
        self._kb, self._ms = keyboard, mouse
        self.kb = keyboard.Controller()
        self.ms = mouse.Controller()
        self._buttons = {"left": mouse.Button.left, "right": mouse.Button.right,
                         "middle": mouse.Button.middle}
        self._down_keys: set = set()
        self._down_buttons: set[str] = set()

    def mouse_move(self, x: int, y: int) -> None:
        self.ms.position = (x, y)

    def mouse_button(self, b: str, down: bool) -> None:
        btn = self._buttons[b]
        if down:
            self.ms.press(btn); self._down_buttons.add(b)
        else:
            self.ms.release(btn); self._down_buttons.discard(b)

    def scroll(self, dx: int, dy: int) -> None:
        self.ms.scroll(dx, dy)

    def _resolve(self, name: str):
        if name in NAMED_KEYS:
            return getattr(self._kb.Key, name, None)
        if len(name) == 1:
            return name
        return None

    def key(self, name: str, down: bool) -> None:
        k = self._resolve(name)
        if k is None:
            return
        if down:
            self.kb.press(k); self._down_keys.add(k)
        else:
            self.kb.release(k); self._down_keys.discard(k)

    def release_all(self) -> None:
        """משחרר מקשים/כפתורים תקועים כשהסשן נסגר."""
        for k in list(self._down_keys):
            try: self.kb.release(k)
            except Exception: pass
        for b in list(self._down_buttons):
            try: self.ms.release(self._buttons[b])
            except Exception: pass
        self._down_keys.clear(); self._down_buttons.clear()


def apply_event(inj, ev: dict, geom: dict) -> None:
    """מיישם אירוע קלט מהצופה. קואורדינטות מנורמלות (0..1) לצג הנבחר."""
    t = ev.get("t")
    if t in ("mm", "md", "mu"):
        x = geom["left"] + int(_clamp01(ev.get("x")) * (geom["width"] - 1))
        y = geom["top"] + int(_clamp01(ev.get("y")) * (geom["height"] - 1))
        inj.mouse_move(x, y)
        b = ev.get("b", "left")
        if t in ("md", "mu") and b in BUTTONS:
            inj.mouse_button(b, t == "md")
    elif t == "ms":
        dx = max(-20, min(20, int(ev.get("dx", 0) or 0)))
        dy = max(-20, min(20, int(ev.get("dy", 0) or 0)))
        inj.scroll(dx, dy)
    elif t in ("kd", "ku"):
        name = ev.get("k")
        if isinstance(name, str) and (name in NAMED_KEYS or len(name) == 1):
            inj.key(name, t == "kd")
