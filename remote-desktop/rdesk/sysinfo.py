"""זהות מקומית (שם משתמש + שם מחשב) - בדיוק כמו ב-AnyDesk: מוצגת גם על
"המחשב הזה" בצד המארח (אצלם "Logged in as") וגם בבקשת חיבור נכנסת, כדי
שאפשר יהיה לזהות מי מתחבר לא רק לפי מזהה אלא גם לפי שם המשתמש/המחשב.

מדווח-עצמי מהצד שמתחבר, לא מאומת קריפטוגרפית - בדיוק כמו כתובת ה-IP
שכבר מוצגת: אינדיקציה נוספת ל"האם זה נראה מוכר", לא בקרת גישה. צד זדוני
יכול תאורטית לדווח שם שקרי - בדיוק כמו שאפשר תאורטית לזייף את זה ב-AnyDesk
עצמו; זה לא שונה מכל שדה מדווח-עצמי אחר בפרוטוקולים מהסוג הזה."""
from __future__ import annotations

import getpass
import socket


def local_identity() -> dict:
    try:
        username = getpass.getuser()
    except Exception:
        username = ""
    try:
        computer = socket.gethostname()
    except Exception:
        computer = ""
    return {"username": username, "computer": computer}
