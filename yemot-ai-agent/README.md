# עוזר קולי אישי על ימות המשיח

חיוג לשלוחה בימות → שרת פייתון → Claude → תשובה מוקראת. אפשר גם לבקש ממנו לשלוח SMS ולחייג אליך ולחבר אותך למישהו.

```
אתה מחייג ─► שלוחת type=api בימות ─► השרת שלך (/yemot)
             (מקליטה + מתמללת בעצמה)      ├─ בודק מספר מתקשר + סוד + קוד אישי
                                          ├─ Claude (עם כלים)
                                          └─ API הניהול של ימות (SMS, גישור שיחות)
```

## מה בפנים

| קובץ | תפקיד |
|---|---|
| `server.py` | הפרוטוקול מול ימות: אימות, קוד אישי, שאלה ותשובה (`read=...`), ניתוק |
| `agent.py` | לולאת Claude עם הכלים `send_sms`, `call_me_and_connect`, `end_call` |
| `actions.py` | הכנת פעולות ואישור קולי. ההחלטה אם המשתמש אישר נעשית בקוד, לא במודל |
| `yemot_client.py` | `SendSms`, `CreateBridgeCall` |
| `simulate.py` | בדיקה מהמחשב בלי טלפון |
| `test_server.py` | בדיקות אוטומטיות (`pytest`) |

## אבטחה

השרת מקבל הוראות בקול, ולכן יש כמה שכבות:
1. `URL_SECRET`: ימות מצרפת אותו לכל בקשה (`api_add_0`). בקשה בלעדיו נדחית.
2. `ApiPhone` חייב להיות הטלפון שלך. הערה: זיהוי מתקשר אפשר לזייף, ולכן יש גם:
3. קוד אישי (`PIN`) בתחילת כל שיחה, עם נעילה אחרי 5 ניסיונות כושלים בתוך 15 דקות.
4. כל SMS או חיוג דורש אישור קולי ("כן") או הקשה 1.
5. הטוקן של ימות ומפתח Claude נשארים רק בשרת, בקובץ `.env`.

## התקנה על שרת האורקל

1. **שרת:** VM עם Ubuntu. פתח את פורטים 80 ו-443 בשני מקומות:
   - ב-OCI: Networking → VCN → Security List → Ingress Rules
   - בתוך השרת (ב-Ubuntu של אורקל יש כללי iptables חוסמים):
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save
     ```
2. **כתובת עם HTTPS:** שם חינמי ב-duckdns.org שמצביע ל-IP של השרת, ו-Caddy לתעודה אוטומטית:
   ```bash
   sudo apt install -y caddy python3-venv
   # /etc/caddy/Caddyfile
   YOURNAME.duckdns.org {
       reverse_proxy 127.0.0.1:8080
   }
   sudo systemctl reload caddy
   ```
3. **הקוד:**
   ```bash
   cd ~ && git clone <הריפו> && cd <הריפו>/yemot-ai-agent
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env && nano .env            # למלא את הכול
   cp contacts.example.json contacts.json && nano contacts.json
   ```
   ל-`URL_SECRET` אפשר לייצר ערך כך: `openssl rand -hex 24`
4. **שירות שרץ תמיד** (`/etc/systemd/system/yemot-ai.service`):
   ```ini
   [Unit]
   Description=Yemot AI assistant
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/<הריפו>/yemot-ai-agent
   EnvironmentFile=/home/ubuntu/<הריפו>/yemot-ai-agent/.env
   # worker אחד בלבד: מצב השיחות נשמר בזיכרון
   ExecStart=/home/ubuntu/<הריפו>/yemot-ai-agent/.venv/bin/gunicorn -w 1 --threads 8 -b 127.0.0.1:8080 --timeout 60 "server:create_app()"
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl enable --now yemot-ai
   curl https://YOURNAME.duckdns.org/healthz      # אמור להחזיר ok
   ```

## הגדרת השלוחה בימות

בשלוחה חדשה (למשל `/9`) צור את הקובץ `ext.ini` לפי `ext.ini.example`, עם הכתובת והסוד שלך:

```
type=api
api_link=https://YOURNAME.duckdns.org/yemot
api_url_post=yes
api_add_0=k=<URL_SECRET>
api_wait_answer_music_on_hold=yes
```

`api_url_post=yes` חשוב: ב-GET כל תור מוסיף לכתובת את כל מה שנאמר עד עכשיו, והיא עלולה לחרוג מהמגבלה.

## בדיקות לפני שמסתמכים על זה

1. **בלי טלפון:** `source .env` (או `set -a; . ./.env`) ואז `python simulate.py https://YOURNAME.duckdns.org/yemot` ושיחה בהקלדה.
2. **מהטלפון שלך:** שיחה רגילה, ואז ניסוי של: קוד שגוי; שתיקה; ניתוק באמצע; מתקשר ממספר אחר (חייב להידחות).
3. **פעולות:** "שלח הודעה ל... " ← "כן" ← בדוק שהגיעה. ואז שוב ← "לא" ← בדוק שלא נשלחה. אחר כך "תחבר אותי ל...".

## דברים שלא אומתו מול מערכת חיה

הקוד נבנה לפי התיעוד, אבל לא נוסה מול הקו שלך. אלה הנקודות לבדוק בשיחה הראשונה:
- **הניתוק:** `id_list_message=...&go_to_folder=hangup`. אם השיחה לא נסגרת, זה המקום לתקן (`server.py`, פונקציה `_end`).
- **הקלטה ארוכה:** המנוע `record` (שקט 3 שניות, עד 30 שניות) מוגדר ב-`config.py`. אפשר לכוון.
- **דיוק התמלול בעברית** על קו טלפון משתנה. אם הוא חלש, אפשר לעבור להקלטה (`record`) ולתמלל בשרת עם שירות חיצוני.
- **שבת ויום טוב:** לפי התיעוד, ימות חוסמת חיוג יוצא של קמפיינים בשבת וביום טוב. ייתכן שהגישור (`CreateBridgeCall`) מושפע באופן דומה. אם הוא נכשל, השרת יאמר לך שהפעולה נכשלה.
- **עלויות:** `SendSms` ו-`CreateBridgeCall` מחויבות ביחידות מהמערכת שלך (ראה בתיעוד של כל פקודה).

## מה אפשר להוסיף אחר כך

- **וואטסאפ:** כלי נוסף ב-`agent.py` שקורא לספק (WhatsApp Cloud API או ספק מתווך). קבלת הודעות נכנסות: webhook לשרת, שמירה, והקראה בשיחה הבאה.
- **ועידה:** הפעלת `confbridge` או פעולות `CallAction` על חדר.
- **חיוג אליך ביוזמת העוזר** (תזכורות): `RunCampaign` עם הודעת TTS.
