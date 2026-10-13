"""הרמת הרשאות מנהל (UAC) מרחוק - כמו "Request Administrative Rights" של
AnyDesk. UAC אמיתי לא ניתן לעקוף בתוכנה: המשתמש הפיזי שיושב מול המחשב
המארח חייב ללחוץ "כן" על חלון ה-UAC האמיתי של Windows - שום קוד לא יכול
לאשר את עצמו, וזו בדיוק הנקודה של UAC. מה שבונים כאן הוא בקשה מהצופה ->
אישור/דחייה אצל המארח (כמו בקשת חיבור רגילה) -> אם אושר, מנסים להרים
הרשאות עם ShellExecute("runas", ...) שמציג את חלון ה-UAC האמיתי.

היקף גרסה זו: בקשה/אישור/הרמת-הרשאות בלבד. בלי גישור מלא שמעביר את זרם
הקלט (עכבר/מקלדת) של הסשן הקיים לתהליך מורם - UIPI של Windows חוסם שליחת
קלט מתהליך רגיל לחלונות שרצים כמנהל, ופתרון מלא לזה דורש להעביר את כל
שרשרת ה-capture/injection לתהליך מורם נפרד עם IPC משלו; זו הרחבה נפרדת
ומשמעותית, לא משהו שנבנה "בדרך". ראו README.

לא מאומת על Windows אמיתי - כמו שאר הפיצ'רים הספציפיים ל-Windows בפרויקט
הזה; ה-CI/בדיקה ידנית על Windows אמיתי הם הבדיקה האמיתית."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger("rdesk.uac")


def is_elevated() -> bool:
    """בודק אם התהליך הנוכחי כבר רץ בהרשאות מנהל."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_elevation(args: list[str] | None = None) -> bool:
    """מציג את חלון ה-UAC האמיתי של Windows ומריץ עותק מורם של עצמנו.
    מחזיר True אם ה-OS *הציג* את הבקשה בהצלחה - לא אם המשתמש אישר אותה
    (ShellExecute רק משגר את הבקשה; אין דרך סינכרונית לדעת את ההחלטה)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        params = " ".join(args or [])
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return int(result) > 32
    except Exception:
        log.exception("UAC elevation request failed")
        return False
