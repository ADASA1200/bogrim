"""מצב פרטיות (כמו Privacy Mode של AnyDesk): בזמן סשן, חוסם את הקלט הפיזי
המקומי במחשב המארח (כך שמי שיושב שם לא יכול להתערב) ומציג שכבת-כיסוי שחורה
על הצג הפיזי - בלי להשפיע על מה שהצופה המרוחק רואה ושולט בו.

הסתרת המסך הפיזי מהצופה-על-הכתף אבל לא מהצופה המרוחק עצמו דורשת טריק
ספציפי ל-Windows: SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
(Windows 10 2004+) - API מתועד של מיקרוסופט בדיוק למטרה הזו (למשל מנהלי
סיסמאות משתמשים בו כדי להסתיר חלונות מתוכנות הקלטת-מסך): החלון מוסתר מכל
API לכידת-מסך (כולל mss, שה-capture שלנו עצמו משתמש בו) אבל ממשיך
להיצבע כרגיל ע"י ה-GPU על הצג הפיזי. בלינוקס/מק אין כאן API מקביל נגיש,
אז שם המצב חוסם רק קלט מקומי, בלי הסתרת מסך (וזה מתועד ב-README).

Tcl/Tk לא בטוח לשימוש מכמה thread-ים, וגם לא ליצירת כמה אובייקטי ``Tk()``
ברצף (גם ברצף, לא רק בו-זמנית) - זה קורס בפועל עם
"Tcl_AsyncDelete: async handler deleted by the wrong thread". אז יוצרים
thread ייעודי יחיד לכל חיי התהליך, עם ``Tk()`` אחד שנשאר קיים ומוצג/מוסתר
(withdraw/deiconify) במקום להיווצר מחדש בכל enable().

לא מאומת על Windows אמיתי - כמו שאר הפיצ'רים הספציפיים ל-Windows בפרויקט
הזה; ה-CI הוא הבדיקה האמיתית."""
from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger("rdesk.privacy")

_ui_lock = threading.Lock()
_ui_thread: threading.Thread | None = None
_ui_root = None
_ui_available = False
_ui_ready = threading.Event()


def _ensure_ui_thread() -> bool:
    global _ui_thread
    with _ui_lock:
        if _ui_thread is not None:
            return _ui_available
        try:
            import tkinter  # noqa: F401
        except Exception:
            log.warning("tkinter unavailable - privacy mode will not blank the local screen")
            _ui_thread = threading.main_thread()   # placeholder שמסמן "לא ננסה שוב"
            return False
        _ui_thread = threading.Thread(target=_ui_main, daemon=True, name="rdesk-privacy-ui")
        _ui_thread.start()
        _ui_ready.wait(timeout=5)
        return _ui_available


def _ui_main() -> None:
    global _ui_root, _ui_available
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.configure(bg="black")
        root.attributes("-topmost", True)
        root.overrideredirect(True)
        _ui_root = root
        _ui_available = True
    finally:
        _ui_ready.set()
    if _ui_root is not None:
        _ui_root.mainloop()


def _virtual_screen_bounds(root) -> tuple[int, int, int, int]:
    """שטח כל הצגים יחד (לא רק הראשי) - ב-Windows יש API ייעודי לזה."""
    if sys.platform == "win32":
        try:
            import ctypes
            u32 = ctypes.windll.user32
            x, y = u32.GetSystemMetrics(76), u32.GetSystemMetrics(77)
            w, h = u32.GetSystemMetrics(78), u32.GetSystemMetrics(79)
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def _exclude_from_capture(root) -> None:
    try:
        import ctypes
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        hwnd = root.winfo_id()
        ctypes.windll.user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        log.exception("SetWindowDisplayAffinity failed - overlay will be visible to screen capture too")


class PrivacyGuard:
    """``listener_factory`` מאפשר הזרקת listeners מזויפים לבדיקות - ברירת
    המחדל (None) משתמשת ב-pynput האמיתי, שתופס קלט פיזי בפועל ולכן לא
    מתאים להרצה בתוך בדיקה אוטומטית."""

    def __init__(self, listener_factory=None) -> None:
        self._listener_factory = listener_factory or self._real_listeners
        self._active = False
        self._kb = None
        self._mouse = None

    @property
    def active(self) -> bool:
        return self._active

    def enable(self) -> None:
        if self._active:
            return
        self._active = True
        self._kb, self._mouse = self._listener_factory()
        for listener in (self._kb, self._mouse):
            if listener is not None:
                listener.start()
        self._show_overlay()

    def disable(self) -> None:
        if not self._active:
            return
        self._active = False
        for listener in (self._kb, self._mouse):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._kb = self._mouse = None
        self._hide_overlay()

    @staticmethod
    def _real_listeners():
        try:
            from pynput import keyboard, mouse
        except Exception:
            log.warning("pynput unavailable - privacy mode will not block local input")
            return None, None
        kb = keyboard.Listener(on_press=lambda k: None, suppress=True)
        ms = mouse.Listener(on_move=lambda x, y: None, on_click=lambda *a: None,
                            on_scroll=lambda *a: None, suppress=True)
        return kb, ms

    # ---------------------------------------------------------------- מסך
    def _show_overlay(self) -> None:
        if not _ensure_ui_thread():
            return

        def do_show():
            x, y, w, h = _virtual_screen_bounds(_ui_root)
            _ui_root.geometry(f"{w}x{h}+{x}+{y}")
            if sys.platform == "win32":
                _exclude_from_capture(_ui_root)
            _ui_root.deiconify()
            _ui_root.lift()

        try:
            _ui_root.after(0, do_show)
        except Exception:
            log.exception("failed to show privacy overlay")

    def _hide_overlay(self) -> None:
        if _ui_root is not None:
            try:
                _ui_root.after(0, _ui_root.withdraw)
            except Exception:
                pass
