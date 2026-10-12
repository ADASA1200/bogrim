"""עיצוב מודרני (Sun Valley - בסגנון Windows 11) לממשקי ה-tkinter.

tkinter עם ה-theme המובנה נראה כמו Windows מלפני עשרים שנה. sv_ttk מחליף רק
את עיצוב ווידג'טי ה-ttk (כפתור, שדה, Notebook וכו'); וידג'טים "קלאסיים" כמו
ScrolledText/Canvas לא מושפעים ממנו וצריך לצבוע אותם ידנית כדי שיתאימו.

הערכה חלה על כל ה-interpreter של Tcl, כלומר על כל Toplevel שנפתח מתחת
ל-root - לכן צריך להפעיל את apply() פעם אחת בלבד, על ה-tk.Tk() האמיתי.
"""
from __future__ import annotations

import tkinter

try:
    import sv_ttk
except ImportError:  # pragma: no cover - חייב להיות מותקן; זה רק רשת ביטחון
    sv_ttk = None

# מהצבעים של ערכת הנושא הכהה של sv_ttk (theme/dark.tcl), כדי שווידג'טים
# קלאסיים ייראו זהים לווידג'טי ה-ttk שסביבם.
BG = "#1c1c1c"
FG = "#fafafa"
MUTED = "#9a9a9a"
ACCENT = "#57c8ff"
SELECT_BG = "#2f60d8"

_applied_roots: set[int] = set()


def apply(root: tkinter.Tk) -> None:
    """מפעיל את ערכת הנושא הכהה. root חייב להיות tk.Tk() אמיתי, לא Toplevel.

    בטוח לקרוא יותר מפעם אחת על אותו root. אם root הוא Toplevel - פשוט לא
    עושה כלום, כי הוא כבר יורש את העיצוב מה-root האמיתי של התוכנה.
    """
    if sv_ttk is None or not isinstance(root, tkinter.Tk):
        return
    if id(root) in _applied_roots:
        return
    sv_ttk.set_theme("dark", root=root)
    _applied_roots.add(id(root))


def style_classic(widget, **extra) -> None:
    """צובע ווידג'ט קלאסי (Text/ScrolledText/Listbox...) כדי שיתאים לערכה הכהה."""
    opts = dict(
        background=BG, foreground=FG, insertbackground=FG,
        selectbackground=SELECT_BG, selectforeground=FG,
        highlightthickness=0, relief="flat", borderwidth=0,
    )
    opts.update(extra)
    try:
        widget.configure(**opts)
    except tkinter.TclError:
        pass


def style_toplevel(win) -> None:
    """צובע את רקע החלון (Toplevel) עצמו, כדי שלא יציץ רקע לא-ערוך בשוליים."""
    try:
        win.configure(bg=BG)
    except tkinter.TclError:
        pass
