"""הגדרות רשת גלובליות: אמון בחנות התעודות של מערכת ההפעלה.

ברירת המחדל של Python משתמשת ברשימת אמון פנימית קבועה (certifi) ולא במה
שהמשתמש/מנהל המכשיר התקינו במערכת ההפעלה (למשל root CA של תוכנת סינון/
אבטחה ארגונית). דפדפנים קוראים את חנות האמון של המערכת ולכן "סתם עובדים";
כדי ש-RDesk יתנהג אותו דבר לגבי חיבור ה-wss:// לשרת האיתות, מפעילים כאן
את truststore שמחליף את ה-SSLContext הגלובלי ב-Python לכזה שקורא ישירות
ממערכת ההפעלה (Windows: CryptoAPI, macOS: Security framework, Linux:
ברירת המחדל כבר כך לרוב).

זה *לא* משבית אימות תעודות ולא מוסיף אמון לשום דבר בעצמו - הוא רק מחליף
את המקור לרשימת האמון שכבר מוגדרת במערכת ההפעלה. חיבור WebRTC עצמו
(וידאו/קלט/קבצים) הוא P2P על DTLS-SRTP ואינו עובר דרך שום proxy מסוג הזה.
"""
from __future__ import annotations

import logging

log = logging.getLogger("rdesk.net")
_installed = False


def use_system_trust_store() -> bool:
    """מפעיל פעם אחת. מחזיר True אם הופעל בהצלחה."""
    global _installed
    if _installed:
        return True
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        log.info("truststore not installed - using the default certifi trust store")
        return False
    except Exception:
        log.exception("failed to enable the OS trust store; keeping the default")
        return False
    _installed = True
    log.info("TLS connections now trust the operating system's certificate store")
    return True
