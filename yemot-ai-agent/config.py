import os


def _get(name, default=""):
    return os.environ.get(name, default).strip()


YEMOT_TOKEN = _get("YEMOT_TOKEN")
OWNER_PHONE = _get("OWNER_PHONE")
PIN = _get("PIN")
URL_SECRET = _get("URL_SECRET")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-sonnet-5-5")
CONTACTS_FILE = _get("CONTACTS_FILE", "contacts.json")

# הקלטת דיבור: שניות שקט לסיום, ואורך הקלטה מקסימלי
SILENCE_SECONDS = 3
MAX_RECORD_SECONDS = 30

MAX_REPLY_CHARS = 500
PIN_ATTEMPTS_PER_CALL = 3
LOCKOUT_FAILS = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60


def validate():
    missing = [n for n in ("YEMOT_TOKEN", "OWNER_PHONE", "PIN", "URL_SECRET", "ANTHROPIC_API_KEY")
               if not globals()[n]]
    if missing:
        raise RuntimeError("חסרים משתני סביבה: " + ", ".join(missing))
    if len(URL_SECRET) < 16:
        raise RuntimeError("URL_SECRET קצר מדי (לפחות 16 תווים)")
    if not PIN.isdigit() or not 4 <= len(PIN) <= 8:
        raise RuntimeError("PIN חייב להיות 4-8 ספרות")
