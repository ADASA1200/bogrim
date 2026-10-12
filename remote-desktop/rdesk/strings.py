"""כל הטקסטים הגלויים למשתמש - בעברית. מקום אחד לתרגום ולעריכה."""
from __future__ import annotations

import sys

try:                      # ב-Linux ל-Tk אין תמיכה ב-bidi; ב-Windows/macOS יש
    from bidi.algorithm import get_display as _bidi
except Exception:         # pragma: no cover
    _bidi = None


def rtl(text: str) -> str:
    """מסדר טקסט עברי לתצוגה נכונה בסביבות ש-Tk בהן לא תומך ב-RTL (Linux)."""
    if _bidi and sys.platform.startswith("linux"):
        return "\n".join(_bidi(line) for line in text.split("\n"))
    return text


APP = "RDesk"

# ---- הודעות שגיאה (קודים פנימיים -> עברית) ----
REASONS = {
    "bad password": "הסיסמה שגויה",
    "declined": "המשתמש במחשב המרוחק דחה את החיבור",
    "busy": "המחשב המרוחק עסוק בסשן אחר",
    "blocked": "נחסמת זמנית עקב ניסיונות סיסמה שגויים. נסו שוב בעוד דקה",
    "no session": "הבקשה פגה. נסו להתחבר שוב",
    "internal error": "שגיאה פנימית במחשב המרוחק",
    "host not found / offline": "המזהה לא נמצא או שהמחשב המרוחק לא מחובר",
    "host authentication failed": "אימות המחשב המרוחק נכשל (ייתכן ניסיון התחזות)",
    "timed out waiting for host": "המחשב המרוחק לא הגיב בזמן",
    "id in use": "המזהה כבר בשימוש במחשב אחר",
    "bad id": "מזהה לא תקין",
    "protocol error": "שגיאת פרוטוקול",
    "host ended the session": "המחשב המרוחק סיים את הסשן",
    "disconnected": "התנתקת מהסשן",
    "connection lost": "החיבור אבד",
    "incomplete": "הקובץ לא התקבל במלואו",
    "file transfer not allowed": "העברת קבצים לא מורשית במחשב המרוחק",
    "bad size": "גודל קובץ לא תקין",
    "file larger than announced": "הקובץ גדול ממה שהוצהר",
}


def reason(code) -> str:
    code = str(code)
    return REASONS.get(code, code)


# ---- מארח ----
H_TITLE = "RDesk - מארח"
H_TITLE_ACTIVE = "RDesk - ⚠ סשן פעיל במחשב שלך"
H_MY_PC = "המחשב הזה"
H_YOUR_ID = "המזהה שלך:"
H_PASSWORD = "סיסמה זמנית:"
H_COPY = "העתק"
H_NEW_PW = "סיסמה חדשה"
H_CONNECTING = "⏳ מתחבר לשרת..."
H_ONLINE = "🟢 מחובר לשרת - מוכן לקבל חיבורים"
H_OFFLINE = "🔴 אין חיבור לשרת, מנסה שוב..."
H_TEMP_NOTE = "חיבור עם הסיסמה הזמנית דורש את אישורך בכל פעם."

H_TAB_MAIN = "ראשי"
H_TAB_SETTINGS = "הגדרות"
H_CONNECT_BOX = "התחברות למחשב אחר"
H_SELF = "לא ניתן להתחבר למחשב הזה עצמו."
H_SERVER_BOX = "שרת"
H_SERVER_LABEL = "כתובת שרת האיתות:"
H_SERVER_SAVE = "שמור"
H_SERVER_SAVED = "הכתובת נשמרה. היא תיכנס לתוקף אחרי הפעלה מחדש של התוכנה."

H_EMBED_BOX = "המחשב הזה כשרת (בלי שרת נפרד)"
H_EMBED_ENABLE = "הפוך את המחשב הזה גם לשרת האיתות"
H_EMBED_PORT = "פורט:"
H_EMBED_SAVE = "שמור"
H_EMBED_SAVED = "ההגדרה נשמרה. היא תיכנס לתוקף אחרי הפעלה מחדש של התוכנה."
H_EMBED_BAD_PORT = "הפורט צריך להיות מספר בין 1 ל-65535."
H_EMBED_HELP = ("כשזה מופעל, אין צורך בשרת נפרד: המחשב הזה משמש גם כנקודת ההכרות בין שני הצדדים.\n"
                "החיבור עצמו (וידאו, קלט, קבצים) תמיד ישיר ומוצפן בין שני המחשבים.\n"
                "לחיבור באותה רשת (בית/משרד) זה עובד מיד. לחיבור מהאינטרנט צריך להגדיר הפניית פורט "
                "(Port Forwarding) בנתב של המחשב הזה אל הפורט שלמעלה, ולתת לצד השני את ה-IP הציבורי.")
H_EMBED_STARTING = "⏳ מפעיל שרת מוטבע..."
H_EMBED_RUNNING = "🟢 שרת מוטבע רץ בפורט {port}"
H_EMBED_LAN = "ברשת המקומית: ws://{ip}:{port}"
H_EMBED_PUBLIC = "מהאינטרנט (דורש הפניית פורט בנתב): ws://{ip}:{port}"
H_EMBED_NO_PUBLIC = "לא הצליח לזהות IP ציבורי (ייתכן שאין חיבור לאינטרנט)"
H_EMBED_COPY_LAN = "העתק כתובת רשת מקומית"
H_EMBED_COPY_PUBLIC = "העתק כתובת אינטרנט"

H_UNATT_BOX = "גישה ללא נוכחות (חיבור בלי אישור)"
H_UNATT_ENABLE = "אפשר חיבור ללא אישור באמצעות סיסמה קבועה"
H_UNATT_PW = "סיסמה קבועה:"
H_UNATT_PW_HINT = "(לפחות 8 תווים; השאירו ריק כדי לא לשנות)"
H_UNATT_SAVE = "שמור"
H_UNATT_SAVED = "ההגדרות נשמרו."
H_UNATT_TOO_SHORT = "הסיסמה הקבועה חייבת להכיל לפחות 8 תווים."
H_UNATT_NEED_PW = "כדי להפעיל גישה ללא נוכחות יש להגדיר סיסמה קבועה."
H_UNATT_WARN = ("מי שיודע את המזהה ואת הסיסמה הקבועה יוכל להתחבר למחשב הזה בלי אישור.\n"
                "השתמשו בסיסמה ארוכה וייחודית, ושתפו אותה רק עם מי שבוטחים בו.")
H_UNATT_CONFIRM_TITLE = "אישור הפעלת גישה ללא נוכחות"
H_UNATT_CONFIRM = H_UNATT_WARN + "\n\nלהפעיל?"

H_SESSION_BOX = "סשן פעיל"
H_NO_SESSION = "אין חיבור פעיל"
H_SESSION_ON = "🔴 מישהו מחובר למחשב שלך כרגע"
H_SESSION_ON_UNATT = "🔴 מישהו מחובר למחשב שלך כרגע (ללא אישור, גישה קבועה)"
H_PERM_CONTROL = "שליטה"
H_PERM_CLIP = "לוח"
H_PERM_FILES = "קבצים"
H_SEND_FILE = "שלח קובץ"
H_DISCONNECT = "נתק"
H_ME = "אני: "
H_VIEWER = "צופה: "
H_FILE_IN = "📥 התקבל קובץ: "
H_FILE_OUT = "📤 נשלח: "
H_FILE_ERR = "⚠ שגיאת קובץ: "

H_ASK_TITLE = "בקשת חיבור"
H_ASK_TEXT = "מישהו מבקש להתחבר למחשב שלך.\nלאפשר?"
H_ASK_CONTROL = "אפשר שליטה (עכבר ומקלדת)"
H_ASK_CLIP = "אפשר סנכרון לוח"
H_ASK_FILES = "אפשר העברת קבצים"
H_ASK_OK = "אשר"
H_ASK_NO = "דחה"

H_ALERT_TITLE = "אבטחה"
H_ALERT_BLOCKED = "זוהו יותר מדי ניסיונות סיסמה שגויים. החיבורים נחסמו זמנית."
H_ALERT_SPAM = "נדחו מספר בקשות חיבור ברצף. בקשות חדשות נחסמו לדקה."
H_CODE = "קוד אבטחה: {code}  (ודאו שהוא זהה למה שהצופה רואה)"
V_CODE = "קוד אבטחה: {code}"

# ---- צופה ----
V_TITLE = "RDesk - צופה"
V_HEADER = "חיבור למחשב מרוחק"
V_ID = "מזהה:"
V_PASSWORD = "סיסמה (אופציונלי):"
V_PW_HINT = "בלי סיסמה - המשתמש במחשב המרוחק יתבקש לאשר את החיבור.\nעם סיסמת גישה ללא נוכחות (אם הוגדרה שם) - החיבור יתבצע בלי אישור."
V_SERVER = "שרת:"
V_CONNECT = "התחבר"
V_NEED_FIELDS = "יש להזין את המזהה של המחשב המרוחק"
V_CONNECTING = "מתחבר..."
V_WAIT_APPROVAL = "ממתין לאישור המשתמש במחשב המרוחק..."
V_FAILED = "החיבור נכשל: "
V_VIEW_ONLY = "צפייה בלבד"
V_MONITOR = "צג {i} ({w}x{h})"
V_QUALITY = "איכות:"
V_Q_HIGH, V_Q_MID, V_Q_LOW = "גבוהה", "בינונית", "נמוכה"
V_SEND_FILE = "שלח קובץ"
V_CHAT = "צ'אט"
V_FULLSCREEN = "מסך מלא"
V_DISCONNECT = "נתק"
V_CHAT_TITLE = "צ'אט"
V_ME = "אני: "
V_HOST = "מארח: "
V_CLOSED_TITLE = "RDesk"
V_CLOSED = "הסשן נסגר: "
V_FILE_IN = "התקבל קובץ:\n"
V_FILE_ERR = "שגיאת העברת קובץ: "

# ---- שורת פקודה ----
CLI_DESC = "RDesk - שליטה מרחוק"
CLI_APP = "האפליקציה המלאה (ברירת מחדל): מארח + התחברות למחשבים אחרים"
CLI_SERVER = "שרת איתות"
CLI_HOST = "המחשב שנשלט"
CLI_VIEWER = "המחשב ששולט"
CLI_HEADLESS = "בלי ממשק גרפי"
CLI_TURN = "url,username,credential לשרת TURN"
CLI_SETPW = "הגדרת סיסמה קבועה לגישה ללא נוכחות"
CLI_SERVE_SIGNALING = "הפעלת שרת איתות מוטבע במחשב הזה (בלי שרת נפרד); אפשר לציין פורט"
CLI_EMBED_STARTING = "שרת מוטבע רץ בפורט {port}"
CLI_EMBED_LAN = "ברשת המקומית: ws://{ip}:{port}"
CLI_EMBED_PUBLIC = "מהאינטרנט (דורש הפניית פורט בנתב): ws://{ip}:{port}"
CLI_EMBED_NO_PUBLIC = "לא זוהה IP ציבורי (ייתכן שאין חיבור לאינטרנט)"
CLI_CLEARPW = "כיבוי גישה ללא נוכחות"
CLI_ID_LINE = "המזהה שלך: {id}"
CLI_UNATT_ON = "גישה ללא נוכחות: מופעלת (חיבור עם הסיסמה הקבועה לא יבקש אישור)"
CLI_UNATT_OFF = "גישה ללא נוכחות: כבויה (כל חיבור ידרוש אישור)"
CLI_ASK = "\n>> בקשת חיבור מ-{peer}. לאשר? [כ/ל] "
CLI_YES = {"כ", "כן", "y", "yes"}
CLI_PW_PROMPT = "סיסמה קבועה חדשה (לפחות 8 תווים): "
CLI_PW_AGAIN = "הקלידו שוב: "
CLI_PW_MISMATCH = "הסיסמאות לא זהות."
CLI_PW_SHORT = "הסיסמה קצרה מדי (מינימום 8 תווים)."
CLI_PW_SET = "הסיסמה הקבועה נשמרה. גישה ללא נוכחות מופעלת."
CLI_PW_CLEARED = "גישה ללא נוכחות כובתה."
EV = {
    "session_start": "החיבור התחיל",
    "session_end": "הסשן הסתיים",
    "chat": "הודעה",
    "file_received": "התקבל קובץ",
    "file_sent": "נשלח קובץ",
    "file_error": "שגיאת קובץ",
    "alert": "התראת אבטחה",
    "status": "מצב",
    "error": "שגיאה",
}
