# מדריך: קו טלפון בימות המשיח שמדבר עם Gemini Live (שרת Oracle + קובץ פייתון אחד)

המדריך מתאר את המערכת שרצה אצלך: קובץ אחד, `sip_ai.py`, שרץ כשירות `sip-ai` על שרת Oracle. השיחה עוברת מימות המשיח לשרת, והשרת מעביר אותה ל־Gemini.

```
מתקשר ── ימות המשיח ──SIP/RTP (UDP)──► שרת Oracle (sip_ai.py) ──WebSocket──► Gemini Live
                            שלוחה 1522                               חיפוש גוגל מובנה
```

**חוקי ברזל**
- שירות אחד בלבד על חשבון SIP אחד. אם שני שירותים (למשל SMSBOTAI ו־`sip-ai`) נרשמים עם אותו חשבון, הם מפילים זה את זה.
- כל הפקודות כאן הן שורה אחת, ל־PowerShell.
- המפתחות והסיסמאות נמצאים בראש `sip_ai.py` (קבועים). אל תעלה את הקובץ הזה ל־GitHub ואל תשלח אותו לאף אחד.

---

## 0. מה צריך מראש
| פריט | מאיפה |
|---|---|
| שרת Oracle עם Ubuntu 22.04/24.04 (Python 3.11 או 3.12, **לא** 3.13), כתובת IP ציבורית קבועה | קונסולת Oracle |
| קובץ מפתח SSH (`.key`) לשרת | נוצר עם השרת |
| מפתח Gemini API מפרויקט עם חיוב | aistudio.google.com |
| מערכת בימות המשיח עם שלוחה ראשית | ימות |
| טוקן API של ימות (`call2all`) | ניהול המערכת ← הגדרות ← API |

## 1. חשבון SIP בימות המשיח
1. באתר ימות: **מרכזייה עסקית ← חשבונות SIP ← יצירת חשבון**. אפשר גם דרך ה־API (`CreateSipAccount`).
2. רשום את **מספר החשבון** (למשל `<מספר-חשבון>`) ואת **הסיסמה**.
3. ודא שהחשבון בפרוטוקול **UDP** (ה־API: `SipToUdp`). ההודעה "already UDP" אומרת שהכול בסדר.
4. שרת ה־SIP הוא `sip.yemot.co.il`, פורט 5060.

## 2. שלוחה 1522 בימות
1. ב־`IVR` צור את השלוחה `1522` אם אין (או עריכת `ext.ini` של השלוחה).
2. הגדרות השלוחה:
```
type=sip
account_dial_number=<מספר חשבון ה-SIP שיצרת>
sip_timeout=30
```
3. אפשר גם בשורת API אחת (`UpdateExtension` עם `path=1522`, `type=sip`, `account_dial_number=...`).
4. **חשוב:** ימות חוסם IP אחרי 5 בקשות שגויות ברצף. אל תנסה פעמים רבות ברצף עם סיסמה שגויה.

## 3. חיבור לשרת
```powershell
$key = "$env:USERPROFILE\Downloads\<שם-קובץ-המפתח>.key"; $srv = "ubuntu@<כתובת-השרת>"
```
```powershell
ssh -o ServerAliveInterval=20 -i $key $srv
```
אם מופיעה שגיאת הרשאות על קובץ המפתח, הרץ פעם אחת:
```powershell
icacls $key /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

## 4. פתיחת הרשת ב־Oracle (המקום הכי נפוץ לכשלון)
בקונסולה: **Networking ← Virtual Cloud Networks ← ה־VCN שלך ← Subnet ← Security List ← Add Ingress Rules**. הוסף שלוש חוקים (Stateful):

| Source CIDR | פרוטוקול | פורט יעד | הערה |
|---|---|---|---|
| `0.0.0.0/0` | UDP | `5060` | SIP |
| `0.0.0.0/0` | UDP | `10000-10199` | אודיו (RTP) |
| **`147.236.157.20/32`** | **UDP** | **ללא הגבלת פורט (כל הפורטים)** | **קריטי: חבילות SIP גדולות מגיעות מפוצלות ואורקל זורק את החלקים בלי החוק הזה** |

החוק השלישי הוא שפתר את בעיית ה־INVITE שלא נקלט. חסר אצלך אותו = השיחה לא תיענה.

## 5. התקנת הקובץ
1. ערוך את הקבועים בראש `sip_ai.py`: `SIP_USERNAME`, `SIP_PASSWORD`, `PUBLIC_IP` (כתובת השרת), `GEMINI_API_KEY`. השאר ללא שינוי: `SIP_SERVER = "sip.yemot.co.il"`, `RTP_PORT_LOW/HIGH = 10000/10199`.
2. העלה לשרת:
```powershell
scp -o ServerAliveInterval=20 -i $key "$env:USERPROFILE\Downloads\sip_ai.py" "${srv}:/home/ubuntu/sip_ai.py"
```
3. התקנה כשירות (יוצר venv, יחידת systemd, ומפעיל):
```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo python3 /home/ubuntu/sip_ai.py --install-service"
```
4. בדיקות לפני רישום (לא נרשמות ל־SIP):
```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo -u sipai /opt/sip-ai/venv/bin/python /opt/sip-ai/sip_ai.py --self-test; sudo -u sipai /opt/sip-ai/venv/bin/python /opt/sip-ai/sip_ai.py --check-api"
```
> אם הפקודה של `-u sipai` נכשלת על שם המשתמש, הרץ `ls -l /opt/sip-ai` כדי לראות מי הבעלים, והחלף.

## 6. חומת האש בשרת עצמו
אורקל Ubuntu חוסמת בדרך כלל עם iptables. הוסף כללי פתיחה (חד־פעמי):
```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo iptables -I INPUT 1 -p udp --dport 5060 -j ACCEPT && sudo iptables -I INPUT 1 -p udp --dport 10000:10199 -j ACCEPT && sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save"
```

## 7. בדיקה שהכול חי
```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "systemctl is-active sip-ai; sudo journalctl -u sip-ai -n 30 --no-pager -o cat"
```
צריך לראות `active` ובלוג הודעת רישום מוצלח (`200 OK ... REGISTER`).

לוג חי בזמן שיחה:
```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo journalctl -u sip-ai -f -o cat"
```
חייג ל־`1522`. בלוג אמורות להופיע השורות: `SIP RX INVITE` ← `Call ... incoming` ← `answered; codec=PCMA` ← `media: ... packets=...`.

## 8. טבלת תקלות
| סימפטום | סיבה סבירה | מה לעשות |
|---|---|---|
| השיחה לא נענית, אין `INVITE` בלוג | חסר חוק הפיצול ב־Oracle (סעיף 4) או חומת אש | להוסיף חוק UDP לכל הפורטים מ־`147.236.157.20/32`; לבדוק `iptables -L INPUT -n -v` |
| `REGISTER` נדחה שוב ושוב | סיסמה/מספר חשבון שגויים, או חשבון לא UDP, או שני שירותים עם אותו חשבון | לתקן קבועים; לוודא ש־SMSBOTAI כבוי; להמתין כמה דקות (חסימת IP) |
| השיחה נענית אבל שקט | RTP לא מגיע (`packets=0`) | לפתוח UDP 10000-10199 ב־Oracle וב־iptables; לבדוק `PUBLIC_IP` |
| הברכה נשמעת אבל המודל לא מגיב | מפתח Gemini/חיוב, או רגישות הזיהוי | `--check-api`; ראה סעיף 9 |
| הניתוק אחרי 10 שניות | `NO_RTP_TIMEOUT` | בדוק זרימת RTP |
| כמה שירותים רצים | התנגשות | `systemctl list-units --type=service \| grep -iE "sip\|yemot\|gemini\|bridge"` ולהשאיר רק `sip-ai` |

## 9. כוונון איכות
הקבועים שבראש הקובץ, בלי פרוייקטים נוספים:
- `NOISE_GATE_RMS = 200`: פריימים חלשים יותר מוחלפים בשקט. אם הזיהוי חלש, הורד ל־`80`–`120`.
- `OUTPUT_VOLUME = 0.4`: עוצמת קול המודל בטלפון.
- `VOICE = "Charon"`: קול המודל. `SYSTEM_INSTRUCTION`: ההנחיה בעברית שמגדירה את אופי העוזר.
- `ENABLE_GOOGLE_SEARCH = True`: חיפוש גוגל. לא כולל ניווט מפות.

אחרי כל שינוי: העלה מחדש (סעיף 5.2), ואז:
```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo install -o root -g sipai -m 640 /home/ubuntu/sip_ai.py /opt/sip-ai/sip_ai.py && sudo systemctl restart sip-ai; sleep 8; systemctl is-active sip-ai"
```

**מצב ידוע:** אצלך כרגע ההתחברות והברכה עובדות, אבל התשובה של המודל לא נשמעת והזיהוי חלש. הקובץ `sip_ai_diag.py` מוסיף לוג מפורט (כמה אודיו מגיע מהמתקשר, כמה המודל שולח וכמה מושמע). הרץ אותו וישלח לי את הלוג כדי לתקן.

## 10. ניקיון ואבטחה (בסוף)
- מחק עותקי קבצים שיש בהם סיסמאות: `ls ~ ` בשרת, וגם ב־Downloads בווינדוס.
- אם מפתח Gemini או סיסמת ה־SIP נחשפו בשיחות, החלף אותם והכנס את החדשים לקבועים.
- שמור גיבוי של `sip_ai.py` במקום פרטי.
