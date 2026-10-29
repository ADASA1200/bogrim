# מדריך מלא, שלב אחר שלב: קו טלפון בימות המשיח שמדבר עם Gemini Live

מדריך זה מלווה אותך מאפס עד שיחה עובדת. אפשר לעקוב אחריו בלי ידע קודם.
בכל שלב יש **בדיקת ביניים** שאומרת מה אמור להופיע. אל תעבור לשלב הבא לפני שהבדיקה עברה.

## מה בונים

```
מתקשר ──► ימות המשיח ──(SIP + אודיו RTP על UDP)──► שרת Oracle ──(WebSocket מוצפן)──► Gemini Live
            שלוחה 1522        חשבון SIP             קובץ sip_ai.py              (כולל חיפוש גוגל)
```

- **ימות המשיח** מחייגת לשרת שלך דרך חשבון SIP (מעין "שלוחת טלפון באינטרנט").
- **השרת** הוא מחשב קטן באינטרנט שרץ עליו קובץ פייתון אחד, `sip_ai.py`. הוא מקבל את השיחה, ממיר את האודיו ומעביר אותו ל־Gemini ובחזרה.
- **Gemini** מקשיב, חושב (ומחפש בגוגל לפי הצורך), ועונה בקול.

### חוקי ברזל
1. **שירות אחד בלבד** על חשבון SIP אחד. שני שירותים שנרשמים עם אותו חשבון מפילים זה את זה.
2. **הסודות** (סיסמת SIP, מפתח Gemini, טוקן ימות) לא נשלחים לאף אחד ולא עולים ל־GitHub. הם נשארים רק בקובץ ששמור אצלך ובשרת.
3. בכל הפקודות כאן, מה שבתוך `<...>` צריך להחליף בערך שלך (כולל הסוגריים).
4. כל פקודה כאן היא **שורה אחת**. העתק את כולה, הדבק ב־PowerShell ולחץ Enter.

---

## שלב 0 | הכנות: מה צריך שיהיה בידך

| פריט | איפה משיגים | בדיקה |
|---|---|---|
| מחשב Windows עם PowerShell | קיים | חפש "PowerShell" בתפריט התחל |
| לקוח SSH | מובנה ב־Windows 10/11 | הרץ `ssh -V`, אמורה להופיע גרסה |
| חשבון Oracle Cloud | cloud.oracle.com | אפשר להיכנס לקונסולה |
| מערכת ימות המשיח | קיימת | אפשר להיכנס לניהול |
| מפתח Gemini API (פרויקט עם חיוב) | aistudio.google.com ← Get API key | מפתח שמתחיל ב־`AIza` |
| קובץ `sip_ai_template.py` | מהמאגר (בלי פרטים אישיים) | הקובץ אצלך בהורדות |

```powershell
ssh -V
```

---

## שלב 1 | יצירת שרת ב־Oracle Cloud

אם כבר יש לך שרת Ubuntu, דלג ל**בדיקת הביניים** שבסוף השלב.

1. היכנס לקונסולה: cloud.oracle.com ← **Sign in**.
2. תפריט ☰ ← **Compute** ← **Instances** ← **Create instance**.
3. **Name:** כל שם, למשל `sip-ai`.
4. **Image:** לחץ **Change image** ← **Ubuntu** ← **Canonical Ubuntu 24.04** (או 22.04). חשוב: לא 25.x ולא גרסה שמגיעה עם פייתון 3.13, כי הקוד זקוק לפייתון 3.11 או 3.12.
5. **Shape:** אפשר מכונה קטנה מקבוצת Always Free. הקוד קל.
6. **Networking:** השאר "Create new VCN" או בחר VCN קיים, ו־**Assign a public IPv4 address**.
7. **Add SSH keys:** בחר **Generate a key pair for me** והורד את **Save private key** (קובץ `.key`). **שמור אותו, אי אפשר להוריד שוב.**
8. **Create** וחכה שהסטטוס יהפוך ל־**Running** (דקה–שתיים).
9. בעמוד המכונה רשום את **Public IP address**. זו `<כתובת-השרת>`.

**למה לקבע את הכתובת:** כתובת ציבורית רגילה יכולה להשתנות כשהמכונה נעצרת. כדי שלא תצטרך לעדכן את ימות בכל פעם: ☰ ← **Networking** ← **IP management** ← **Reserved public IPs** ← **Reserve public IP address** ושייך אותה למכונה (בעמוד ה־VNIC של המכונה).

**בדיקת ביניים:** יש לך כתובת IP ציבורית וקובץ `.key` בתיקיית ההורדות.

---

## שלב 2 | התחברות לשרת מ־PowerShell

1. הגדר שני משתנים (עדכן את שם הקובץ ואת הכתובת):

```powershell
$key = "$env:USERPROFILE\Downloads\<שם-קובץ-המפתח>.key"; $srv = "ubuntu@<כתובת-השרת>"
```

2. אם SSH מתלונן ש"הרשאות הקובץ פתוחות מדי" (WARNING: UNPROTECTED PRIVATE KEY FILE), הרץ פעם אחת:

```powershell
icacls $key /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

3. התחבר:

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv
```

בפעם הראשונה תישאל `Are you sure you want to continue connecting?` ← הקלד `yes`.

**בדיקת ביניים:** מופיע שורת פקודה כמו `ubuntu@sip-ai:~$`. בדוק גם את גרסת פייתון:

```bash
python3 --version
```

צריך `3.11.x` או `3.12.x`. כדי לצאת מהשרת: `exit`.

> **טיפ:** המשתנים `$key` ו־`$srv` נמחקים כשסוגרים את חלון PowerShell. בכל חלון חדש הרץ שוב את הפקודה בסעיף 1.

---

## שלב 3 | פתיחת הרשת ב־Oracle (השלב שבו הכי הרבה נתקעים)

בענן Oracle יש **שני** חומות אש: אחת בקונסולה (Security List) ואחת בתוך השרת (iptables). צריך לפתוח את שתיהן. כאן הראשונה.

1. בקונסולה: ☰ ← **Networking** ← **Virtual cloud networks** ← לחץ על ה־VCN של המכונה.
2. **Subnets** ← לחץ על ה־Subnet של המכונה.
3. **Security Lists** ← לחץ על ה־Security List (בדרך כלל `Default Security List for ...`).
4. **Add Ingress Rules** והוסף **שלושה חוקים**. בכולם: Stateless **לא מסומן** (Stateful), IP Protocol **UDP**.

| Source CIDR | Source port range | Destination port range | למה |
|---|---|---|---|
| `0.0.0.0/0` | (ריק) | `5060` | הודעות SIP |
| `0.0.0.0/0` | (ריק) | `10000-10199` | אודיו (RTP) |
| `147.236.157.20/32` | (ריק) | **(ריק, כל הפורטים)** | **חיוני.** הודעת ההזמנה (INVITE) של ימות גדולה ומגיעה בחלקים. Oracle זורק את החלקים הנוספים אם אין חוק UDP בלי הגבלת פורט מהכתובת של ימות |

5. לחץ **Add Ingress Rules**.

**בדיקת ביניים:** ברשימת ה־Ingress Rules מופיעים שלושת החוקים. אם יש חוק קיים ל־TCP 22 (SSH), השאר אותו.

---

## שלב 4 | פתיחת חומת האש בתוך השרת

מחשב ה־Ubuntu של Oracle חוסם כברירת מחדל בעזרת iptables. הפקודה הבאה פותחת את הפורטים וגם שומרת את החוקים לאחר הפעלה מחדש (היא עוברת באופן אוטומטי ב־`ssh`):

```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo iptables -I INPUT 1 -p udp --dport 5060 -j ACCEPT && sudo iptables -I INPUT 1 -p udp --dport 10000:10199 -j ACCEPT && sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save"
```

אם מופיע מסך כחול של `iptables-persistent` עם שאלות Yes/No, בחר **Yes** בשתיהן.

**בדיקת ביניים:**

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo iptables -L INPUT -n --line-numbers | head -8"
```

צריך לראות שתי שורות `ACCEPT udp ... dpt:5060` ו־`dpts:10000:10199`.

---

## שלב 5 | חשבון SIP בימות המשיח

חשבון SIP הוא ה"זהות" שהשרת שלך יציג לימות כדי לקבל שיחות.

### 5.1 הכנת טוקן API
באתר ימות: **חומת אש** ← **API KEY** (טוקן ניהול). העתק אותו. אל תשלח אותו לאף אחד.

הכנס אותו למשתנה בחלון PowerShell (הוא יישאל ולא יוצג בהיסטוריה):

```powershell
$tok = Read-Host "Yemot API token"
```

### 5.2 בדיקה אם כבר יש חשבונות SIP
```powershell
(Invoke-RestMethod -Method Post -Uri "https://www.call2all.co.il/ym/api/GetSipAccountsInCustomer" -Headers @{authorization=$tok} -ContentType "application/json" -Body "{}").accounts | Format-Table id,accountNumber,extensionNote,transport
```

- **`id`** הוא שם המשתמש של ה־SIP (ה־`SIP_USERNAME` בקוד).
- **`accountNumber`** הוא המספר הפנימי שבו השלוחה מפנה לחשבון (לא תמיד זהה ל־`id`).
- אם `transport` כבר UDP, מצוין.

### 5.3 יצירת חשבון חדש (רק אם אין)
```powershell
$r = Invoke-RestMethod -Method Post -Uri "https://www.call2all.co.il/ym/api/CreateSipAccount" -Headers @{authorization=$tok} -ContentType "application/json" -Body '{"extensionNote":"gemini-bridge"}'; $r | Format-List accountNumber,accountID,PASS
```

רשום בצד בבטחה: `accountID` (שם משתמש) ו־`PASS` (סיסמה), וגם `accountNumber`.

### 5.4 העברת החשבון ל־UDP
```powershell
Invoke-RestMethod -Method Post -Uri "https://www.call2all.co.il/ym/api/SipToUdp" -Headers @{authorization=$tok} -ContentType "application/json" -Body '{"accountNumber":"<accountNumber>"}'
```

אם חוזרת הודעה בסגנון "לא בוצע שינוי", זה תקין: החשבון כבר UDP.

> **אזהרה:** ימות חוסמת IP אחרי **5 בקשות שגויות ברצף**. אם נתקעת עם שגיאת הרשאה, אל תנסה שוב ושוב. חכה, ובדוק את הטוקן.

**בדיקת ביניים:** הפקודה בסעיף 5.2 מציגה חשבון עם `transport` שמכיל `udp`.

---

## שלב 6 | שלוחה 1522 בימות

1. באתר ימות היכנס לעריכת המערכת (עץ השלוחות) וצור שלוחה בשם **1522** אם אין.
2. הגדרות השלוחה (קובץ `ext.ini`):

```
type=sip
account_dial_number=<accountNumber>
sip_timeout=30
```

3. **או** בשורה אחת דרך ה־API (מבצע את אותו הדבר ויוצר את השלוחה אם אין):

```powershell
Invoke-RestMethod -Method Post -Uri "https://www.call2all.co.il/ym/api/UpdateExtension" -Headers @{authorization=$tok} -ContentType "application/json" -Body '{"path":"1522","type":"sip","account_dial_number":"<accountNumber>","sip_timeout":30,"title":"Gemini"}'
```

**בדיקת ביניים:** התשובה כוללת `responseStatus : OK`. אם יש שלוחה 1522 קיימת עם תוכן אחר, ההגדרה מחליפה אותה: וודא קודם שזה מה שאתה רוצה.

---

## שלב 7 | הכנת קובץ הפייתון

1. הורד את `sip_ai_template.py` ושנה את שמו ל־`sip_ai.py` (עותק פרטי, שלא יעלה ל־GitHub).
2. פתח אותו בעורך טקסט (Notepad++ או VS Code) ועדכן את ארבעת הקבועים בראש הקובץ (בין המרכאות בלבד):

| קבוע | מה לשים |
|---|---|
| `SIP_USERNAME` | ה־`id` / `accountID` של חשבון ה־SIP |
| `SIP_PASSWORD` | סיסמת החשבון (`PASS`) |
| `PUBLIC_IP` | `<כתובת-השרת>` |
| `GEMINI_API_KEY` | מפתח ה־Gemini |

3. את השאר השאר כמו שהוא: `SIP_SERVER = "sip.yemot.co.il"`, `SIP_PORT = 5060`, `RTP_PORT_LOW = 10000`, `RTP_PORT_HIGH = 10199`, `LIVE_MODEL = "gemini-3.8-live"`.
4. שמור.

**בדיקת ביניים:** חפש בקובץ את הטקסט `YOUR_` — לא אמורה להישאר שום תוצאה.

---

## שלב 8 | העלאה והתקנה בשרת

### 8.1 העלאה
```powershell
scp -o ServerAliveInterval=20 -i $key "$env:USERPROFILE\Downloads\sip_ai.py" "${srv}:/home/ubuntu/sip_ai.py"
```

### 8.2 התקנה כשירות
הפקודה יוצרת סביבת פייתון, מתקינה את התלויות (`pyVoIP`, `google-genai`, `numpy`...), יוצרת שירות `sip-ai` ומפעילה אותו. ההתקנה לוקחת כמה דקות.

```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo python3 /home/ubuntu/sip_ai.py --install-service"
```

### 8.3 בדיקות עצמיות (לא נרשמות ל־SIP)
בדיקת הקוד עצמו:

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo /opt/sip-ai/venv/bin/python /opt/sip-ai/sip_ai.py --self-test 2>&1 | tail -4"
```

אמורה להופיע `OK`. בדיקת מפתח Gemini:

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo /opt/sip-ai/venv/bin/python /opt/sip-ai/sip_ai.py --check-api 2>&1 | tail -6"
```

אם נכשל כאן: המפתח שגוי, או שאין לפרויקט חיוב.

**בדיקת ביניים:**

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "systemctl is-active sip-ai; sudo journalctl -u sip-ai -n 25 --no-pager -o cat"
```

צריך לראות `active`, ובלוג הודעת `200 OK` על `REGISTER`. פירוש: ימות קיבלה את השרת שלך.

---

## שלב 9 | שיחת בדיקה ראשונה

1. פתח את הלוג החי (והשאר אותו פתוח):

```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo journalctl -u sip-ai -f -o cat"
```

2. מטלפון חייג למספר הקו של המערכת, ועבור לשלוחה **1522**.
3. אמור להופיע בלוג, לפי הסדר:
   - `SIP RX INVITE ...`
   - `Call ... incoming`
   - `Call ... answered; codec=PCMA` (או PCMU)
   - שורות `media: ... packets=N` שבהן N עולה — האודיו מגיע
4. שמע את הברכה, דבר משפט ברור ושאל שאלה כמו "מה מזג האוויר בתל אביב?". בלוג תופיע `received Google Search grounding` כשהמודל מחפש.
5. לניתוק: לחץ `#` בטלפון (או נתק).
6. עצור את הלוג ב־`Ctrl+C`.

### מה כל שורה אומרת

| בלוג | משמעות |
|---|---|
| אין `INVITE` בכלל | הודעת החיוג לא מגיעה: שלב 3 (חוק הפיצול) או שלב 4 |
| `INVITE` אבל אין `answered` | בעיית SDP/קודק: שלח לי את הלוג |
| `answered` אבל `packets=0` | האודיו לא מגיע: פורטים 10000–10199 סגורים (שלב 3 או 4) |
| `packets` עולה, ואין קול | ראה "כוונון איכות" למטה |

---

## שלב 10 | תקלות נפוצות

| סימפטום | סיבה | פתרון |
|---|---|---|
| `REGISTER` נדחה שוב ושוב (401/403) | שם משתמש/סיסמה שגויים, או חשבון לא UDP | תקן קבועים, העלה מחדש, הרץ שוב `SipToUdp` |
| נרשם אבל החיוג מתנתק מייד | שני שירותים רשומים עם אותו חשבון | ראה למטה "זיהוי שירותים כפולים" |
| הצלצול נשמע ואין ענות | חסר חוק הפיצול (שלב 3) | הוסף את החוק השלישי |
| הניתוק אחרי 10 שניות | אין אודיו נכנס (`NO_RTP_TIMEOUT`) | וודא פורטים 10000–10199 פתוחים בשני המקומות |
| `quota` / `403` מ־Gemini | אין חיוב / מפתח לא תקין | `--check-api` ובדוק חיוב ב־Google AI Studio |
| ימות לא מצלצלת אל השרת בכלל | IP נחסם אצל ימות (5 בקשות שגויות) | המתן, ופנה לתמיכת ימות אם נשאר חסום |

### זיהוי שירותים כפולים
```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "systemctl list-units --type=service --state=running | grep -iE 'sip|yemot|gemini|bridge|smsbot'"
```

השאר רק את `sip-ai`. כדי לעצור שירות אחר (שנה את השם):

```powershell
ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo systemctl stop <שם-שירות> && sudo systemctl disable <שם-שירות>"
```

אם SMSBOTAI רץ על שרת אחר עם אותו חשבון, כבה אותו שם. אפשר ליצור חשבון SIP נפרד לכל מערכת (שלב 5.3).

---

## שלב 11 | כוונון איכות

כל ההגדרות הן קבועים בראש `sip_ai.py`. אחרי שינוי: **העלה מחדש (8.1)** ואז התקן וטען:

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "sudo install -o root -g sipai -m 640 /home/ubuntu/sip_ai.py /opt/sip-ai/sip_ai.py && sudo systemctl restart sip-ai; sleep 8; systemctl is-active sip-ai"
```

> אם הפקודה מלינה על `sipai`: הרץ `ls -ld /opt/sip-ai /opt/sip-ai/sip_ai.py` וקרא את שם הקבוצה בעמודה השלישית/רביעית; השתמש בה במקום `sipai`.

| קבוע | ברירת מחדל | מה משנים אם... |
|---|---|---|
| `NOISE_GATE_RMS` | `200` | המודל לא שומע אותך או מזהה גרוע: הורד ל־`100` או `60`. אם הוא "שומע" רעש רקע: העלה |
| `OUTPUT_VOLUME` | `0.4` | קול המודל חלש מדי (העלה ל־`0.6`) או מעוות (הורד) |
| `VOICE` | `Charon` | רוצה קול אחר |
| `SYSTEM_INSTRUCTION` | הנחיה בעברית | רוצה לשנות את האישיות או הידע של העוזר |
| `ENABLE_GOOGLE_SEARCH` | `True` | `False` כדי לכבות חיפוש |
| `MAX_CALLS` | `10` | כמה שיחות בו־זמנית |
| `USER_SILENCE_TIMEOUT` | `30` | כמה שניות שקט עד שהמערכת מנתקת |

### אבחון עומק (כשהמודל לא עונה או לא שומע)
בקובץ יש `MEDIA_DIAGNOSTICS`. כשהוא `True` הלוג מדפיס כל 5 שניות:

```
media: packets=… | caller frames=… voiced=… rms_max=… | model chunks=… bytes=… played=… interrupts=…
```

איך לקרוא:
- `voiced` נשאר קרוב ל־0 והעוצמה (`rms_max`) נמוכה: שער הרעש חותך אותך. הורד את `NOISE_GATE_RMS`.
- `model bytes` עולה אבל `played` נשאר 0: אודיו המודל לא מושמע לטלפון.
- `interrupts` עולה מהר: המודל נקטע שוב ושוב (הוא "שומע" את עצמו או רעש). נדרש כוונון רגישות הזיהוי.
- `model chunks` נשאר 0: המודל לא מייצר קול כלל.

---

## שלב 12 | תחזוקה שוטפת

| מה | פקודה |
|---|---|
| סטטוס | `ssh -o ServerAliveInterval=20 -i $key $srv "systemctl is-active sip-ai"` |
| 50 שורות אחרונות | `ssh -o ServerAliveInterval=20 -i $key $srv "sudo journalctl -u sip-ai -n 50 --no-pager -o cat"` |
| הפעלה מחדש | `ssh -o ServerAliveInterval=20 -i $key $srv "sudo systemctl restart sip-ai"` |
| עצירה | `ssh -o ServerAliveInterval=20 -i $key $srv "sudo systemctl stop sip-ai"` |
| עדכון חבילות מערכת | `ssh -t -o ServerAliveInterval=20 -i $key $srv "sudo apt-get update && sudo apt-get -y upgrade"` |

השירות מוגדר לעלות מחדש מעצמו אחרי קריסה או אתחול השרת.

---

## שלב 13 | ניקיון ואבטחה

1. מחק מהשרת את העותק עם הסודות: 

```powershell
ssh -o ServerAliveInterval=20 -i $key $srv "shred -u /home/ubuntu/sip_ai.py"
```

(הקובץ שמותקן ב־`/opt/sip-ai` נשאר ופעיל.)
2. מחק מתיקיית ההורדות ב־Windows קבצים שמכילים סיסמאות, וקובץ `.key` שמור במקום פרטי.
3. אם הסודות נחשפו אי פעם (בצ'אט, בצילום מסך, ב־GitHub): החלף אותם. מפתח Gemini ב־Google AI Studio; סיסמת SIP ביצירת חשבון חדש; טוקן ימות במסך חומת האש.
4. גבה את `sip_ai.py` הפרטי במקום מוגן.
5. הגבל גישת SSH ב־Security List ל־IP שלך בלבד (במקום `0.0.0.0/0`) אם הכתובת שלך קבועה.
