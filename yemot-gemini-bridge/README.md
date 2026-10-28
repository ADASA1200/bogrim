# גשר ימות המשיח ⇄ Gemini Live (`gemini-3.8-live`)

שרת שמקבל שיחת SIP מימות המשיח ומחבר אותה בזמן אמת למודל הקולי של Google.
המתקשר מדבר, המודל עונה בקול, ויש לו כלים: חיפוש ברשת, קריאת דפי אינטרנט, תאריך ושעה כולל תאריך עברי, ניתוק שיחה.

```
מתקשר ──PSTN──▶ ימות המשיח ──SIP/UDP + RTP (G.711, 8kHz)──▶ הגשר (השרת שלכם) ──WebSocket──▶ Gemini Live
                  שלוחה routing_ip                        PCMA/PCMU ⇄ PCM 16kHz / 24kHz
```

## מה צריך

1. שרת עם **כתובת IPv4 ציבורית קבועה** (VPS, ענן או שרת ביתי עם כתובת קבועה).
2. פורטים פתוחים ל־**UDP** מהאינטרנט: `5060` (SIP) וטווח `10000-10199` (RTP, שני פורטים לכל שיחה בו־זמנית).
3. מפתח Gemini API מפרויקט **עם חיוב פעיל** ([AI Studio](https://aistudio.google.com/apikey)).
4. Docker, או Python 3.12 ומעלה.

> **חשוב:** הקוד רץ אצלכם, לא בסביבת העבודה שבה נכתב. לשם שרת "שרץ תמיד" צריך להעלות אותו לשרת משלכם.

## התקנה

```bash
cd yemot-gemini-bridge
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # זה ה-ACCESS_TOKEN
nano .env                                                       # GEMINI_API_KEY, PUBLIC_IP, ACCESS_TOKEN
docker compose up -d --build
docker compose logs -f
```

בלי Docker:

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
set -a; . ./.env; set +a; ./venv/bin/python -m bridge.main
```

להרצה קבועה בלי Docker יש קובץ `deploy/yemot-gemini-bridge.service` ל־systemd.

## הגדרה בימות המשיח

### דרך א׳ (מומלצת): ניתוב שיחה ל־IP — `type=routing_ip`

בשלוחה שתרצו שתדבר עם Gemini, בקובץ `ext.ini`:

```
type=routing_ip
routing_ip=203.0.113.7
routing_ip_port=5060
routing_extension=<הערך של ACCESS_TOKEN>
routing_ip_dial_time=25
routing_ip_cancel_star_next=yes
;routing_ip_end_goto=/8
;routing_ip_record=yes
```

- `routing_ip`: ה־`PUBLIC_IP` של השרת (כתובת IP, לא שם דומיין).
- `routing_extension`: ימות שולחת אותו כחלק המשתמש בכתובת ה־SIP (`sip:<טוקן>@כתובת`). **הוא משמש כטוקן** והגשר דוחה כל שיחה שלא נושאת אותו. ימות אוסרת בו את התווים `@` `&` `:`, ולכן הטוקן מוגבל ל־`A-Za-z0-9_.-`.
- `routing_ip_dial_time`: זמן החיוג. הגשר מתחבר ל־Gemini לפני שהוא עונה (בדרך כלל פחות משניה), לכן ברירת המחדל של 23 שניות מספיקה.
- `routing_ip_cancel_star_next=yes`: בלי זה הקשת `*` מנתקת את השיחה וחוזרת למערכת הבסיס.
- אחרי הניתוק, ההמשך נקבע לפי `routing_ip_end_goto`.

מקור: [ניתובי שיחה למענה אנושי, ניתוב שיחה ל־IP](https://f2.freeivr.co.il/topic/218).

### דרך ב׳: חשבון SIP רשום — `type=sip`

מתאים כשאין IP ציבורי לשרת (למשל מאחורי NAT). הגשר נרשם אל ימות כמו טלפון משרדי:

1. יוצרים חשבון עם הפקודה `CreateSipAccount` של ה־API (או בלשונית "מרכזיה עסקית"), ושומרים את `accountID` ואת `PASS`.
2. מגדירים ב־`.env`: `YEMOT_REGISTER_HOST`, `YEMOT_SIP_USER`, `YEMOT_SIP_PASSWORD`. את כתובת שרת ה־SIP של המערכת שלכם מקבלים מימות.
3. בשלוחה: `type=sip` ו־`account_dial_number=<מספר החשבון>`.

הגשר מקבל רק שיחות שמגיעות מכתובת שרת הרישום. הרישום נעשה ב־UDP, ולכן גם בדרך הזאת צריך להיות פתוח טווח ה־RTP. תעבורת WSS של ימות מיועדת ל־WebRTC (DTLS-SRTP) ואינה נתמכת כאן.

## התאמות SIP ואודיו לימות

| נושא | ערך | הערה |
|---|---|---|
| תעבורת SIP | UDP, פורט 5060 | ברירת המחדל של `routing_ip` ושל חשבונות UDP |
| מדיה | RTP/AVP פשוט, ללא SRTP | הצעה עם `RTP/SAVP` נדחית ב־`488` |
| קודק | G.711: **PCMA** (A-law) מועדף, **PCMU** כגיבוי | לפי מה שימות מציעה, ובסדר `CODEC_PREFERENCE` |
| קצב דגימה בקו | 8 kHz, חבילות של 20 מילישניות (160 דגימות) | RTP רציף עם שקט בין דיבורים, כדי שהנתבים לא יסגרו את הנתיב |
| DTMF | RFC 2833 (`telephone-event`) ו־SIP INFO | הספרה מועברת למודל כטקסט `[DTMF: 5]` |
| כיוון מתקשר → מודל | PCM 16 קילו־הרץ, 16 ביט | המרה מ־8 kHz בזמן אמת (כ־26 מילישניות עיכוב) |
| כיוון מודל → מתקשר | PCM 24 קילו־הרץ | המרה ל־8 kHz (כ־21 מילישניות עיכוב) |
| כתובת ה־RTP | מה שמופיע ב־`PUBLIC_IP`, ו־RTP סימטרי | הגשר לומד את כתובת המקור של החבילה הראשונה |
| כותרות ימות | `X-Yemot-CallID`, `X-Yemot-Path` נקראות | המזהה זמין לכלי `get_caller_info` |
| מזהה מתקשר | `P-Asserted-Identity` / `Remote-Party-ID` / `From` | במספר המופיע בלוגים רק 4 ספרות אחרונות |

## כלים שהמודל מקבל

- **חיפוש ברשת:** Google Search grounding מובנה (`ENABLE_GOOGLE_SEARCH`).
- `get_datetime`: תאריך, שעה, יום בשבוע ותאריך עברי.
- `fetch_url`: קריאת דף אינטרנט ציבורי. חסום לכתובות פנימיות, מותר רק `http`/`https` בפורטים 80/443, יש בדיקה גם בזמן ההתחברות מול התקפות DNS rebinding, ומוחזרים עד 6000 תווים.
- `get_caller_info`: מספר המתקשר ומזהה השיחה בימות.
- `end_call`: ניתוק השיחה. המודל נדרש להיפרד קודם, והגשר מחכה שהפרידה תושמע עד הסוף.

להוספת כלי חדש: פונקציה אסינכרונית ב־`bridge/tools.py` ורישום ב־`build_registry`. כך אפשר לחבר, למשל, קריאות ל־API של ימות (`SendSms`, `RunTzintuk`) או למערכת שלכם. כלים שמבצעים פעולות עם עלות או השפעה (שליחת הודעות, שינויים) צריכים הגנות משלהם, כי המודל מקבל קלט מהמתקשר ומהרשת.

## התאמת ההתנהגות

- פרומפט המערכת (עברית, בהתאמה לשיחת טלפון) נמצא ב־`bridge/config.py`. להרחבה: `SYSTEM_PROMPT_EXTRA`, להחלפה מלאה: `SYSTEM_PROMPT_FILE`.
- קול: `GEMINI_VOICE` (למשל `Kore`, `Puck`). רגישות לסיום משפט: `VAD_SILENCE_MS`.
- הגשר מפעיל דחיסת הקשר וחידוש סשן, כך ששיחה לא מוגבלת ל־15 דקות. ניתוק אחרי `MAX_CALL_SECONDS`.

## בדיקה לפני החיבור לימות

```bash
python3 -m bridge.probe YOUR_PUBLIC_IP                      # הפורט פתוח והגשר חי? (SIP OPTIONS)
python3 -m bridge.probe YOUR_PUBLIC_IP --token <ACCESS_TOKEN>   # שיחת ניסוי: אמורה לשמוע ברכה מהמודל
```

בדיקת ה־`--token` משמיעה שקט ומדווחת אם חזר דיבור מהמודל. מומלץ להריץ אותה ממחשב אחר, כך שגם הפורטים והחומת אש נבדקים.
`GET /healthz` (ללא הרשאה) ו־`GET /status` (עם `Authorization: Bearer <STATUS_TOKEN>`) זמינים כש־`STATUS_PORT` מוגדר.

הרצת הבדיקות האוטומטיות: `pip install -r requirements-dev.txt && pytest`.

## אבטחה

- כל INVITE נבדק מול `ACCESS_TOKEN` בהשוואה בזמן קבוע; שיחה בלי הטוקן מקבלת `404`, עם הגבלת קצב לכל כתובת.
- ה־SIP ב־UDP אינו מוצפן, ולכן הטוקן עובר בגלוי בין ימות לשרת. אם ימות מפרסמת טווח כתובות קבוע, הגדירו `ALLOWED_SOURCE_NETWORKS` או חוק בחומת האש כשכבה שנייה.
- הטוקן ומפתח ה־Gemini לא נכתבים ללוגים. תמלולי שיחות כבויים כברירת מחדל (`LOG_TRANSCRIPTS=false`), והפעלתם דורשת שיקול פרטיות.
- `MAX_CALLS` מגביל שיחות במקביל, ולכן גם הוצאות ל־Gemini.
- מפתח ה־API של Google שייך לחשבון המחויב. אל תכניסו אותו לריפו.

## עלויות

- Gemini Live מחויב לפי טוקנים של אודיו, ושיחה פתוחה צורכת גם כשהמתקשר שותק. מחירי הצד השלישי שפורסמו הם כ־$0.75 למיליון טוקני קלט ו־$4.50 למיליון טוקני פלט; **יש לאמת מול [דף המודל](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live) ודף התמחור של Google**.
- חיוב בימות על ניתוב ל־IP ועל שיחות נכנסות לפי תנאי המערכת שלכם. התיעוד שנבדק אינו מפרט את זה, ולכן יש לאמת מול ימות.

## מגבלות ידועות

- **לא נבדק מול שרת ימות אמיתי.** הבדיקות האוטומטיות (41 בדיקות) מדמות את ימות ואת Gemini, ובכללן שיחה מלאה עם DTMF, קריאות כלים, ניתוק על ידי המודל, חידוש חיבור, ביטול שיחה (CANCEL) ורישום עם אימות Digest. יש לבצע שיחת ניסוי ראשונה ולעקוב אחרי הלוגים. אם הבקשה נדחית, הלוג מציג את אורך שם המשתמש בכתובת, כדי לאבחן שימות שולחת את הטוקן כפי שהוגדר.
- הקודקים שימות מציעה ב־INVITE אינם מתועדים בחומר שנבדק. הגשר תומך ב־PCMA וב־PCMU בלבד (לא G.729, Opus או SRTP).
- ללא ג׳יטר־באפר וללא הסתרת אובדן חבילות. ברשת יציבה זה לא מורגש; ברשת עמוסה עשוי להישמע קטיעה.
- ללא העברת שיחה (REFER) ולא TLS ל־SIP.
- נבדק מול גרסת ה־SDK `google-genai` 2.33. המנוע של Google עדיין משתנה (למשל שדות שנתמכו במודלים קודמים כמו `thinking_level` אינם נתמכים ב־3.8); אם שדה נדחה בהתחברות, הלוג יציג את שגיאת השרת.

## מבנה הקוד

| קובץ | תפקיד |
|---|---|
| `bridge/sip.py` | סוכן SIP מעל UDP: INVITE/ACK/BYE/CANCEL/OPTIONS/INFO, שידור חוזר, רישום עם Digest |
| `bridge/sdp.py`, `bridge/rtp.py`, `bridge/audio.py` | משא ומתן על SDP, RTP עם מד־זמן של 20 מילישניות, G.711 והמרת קצבים |
| `bridge/gemini_live.py` | סשן Gemini Live לכל שיחה: אודיו, כלים, חידוש חיבור |
| `bridge/tools.py` | הכלים של המודל |
| `bridge/call.py` | מחזור חיי שיחה, אימות, הגבלות |
| `bridge/main.py`, `bridge/config.py`, `bridge/probe.py` | הפעלה, הגדרות, כלי בדיקה |
