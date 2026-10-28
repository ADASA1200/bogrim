מארז התקנה - גשר ימות המשיח <-> Gemini Live
===========================================

המארז כולל את הקוד, קובץ הגדרות מוכן (.env) עם המפתחות, וטוקן הניהול של ימות.
הסיסמה של חשבון ה-SIP לא נשמרת במארז: הסקריפט שולף אותה ישירות מימות.

שלבים
-----
1. מ-PowerShell, להעלות את הקובץ לשרת (החלף את שם הקובץ אם הוא שונה):

   scp -o ServerAliveInterval=20 -i "$env:USERPROFILE\Downloads\ssh-key-2026-09-01.key" "$env:USERPROFILE\Downloads\yemot-gemini-bundle.zip" ubuntu@129.159.157.8:/home/ubuntu/bundle.zip

2. להתחבר לשרת:

   ssh -o ServerAliveInterval=20 -o ServerAliveCountMax=6 -i "$env:USERPROFILE\Downloads\ssh-key-2026-09-01.key" ubuntu@129.159.157.8

3. בשרת:

   sudo apt-get install -y unzip
   rm -rf ~/yemot-gemini-bundle && unzip -q ~/bundle.zip -d ~
   cd ~/yemot-gemini-bundle
   bash install_all.sh

4. ב-Oracle Console להוסיף כללי כניסה (Ingress Rules) מסוג UDP: פורט 5060 וטווח 10000-10199.

5. להתקשר למערכת ולחייג לשלוחה (מספר השלוחה כתוב ב-bundle.conf, כרגע 1522).

אם שלוחה 1522 כבר קיימת בימות, הסקריפט לא ישנה אותה. כדי להפוך אותה בכל זאת:
   USE_EXISTING=1 bash install_all.sh

אם השלב של ימות נכשל בשליפת הסיסמה (למשל למפתח ה-API אין הרשאה), אפשר להשלים ידנית:
   sudo nano /opt/yemot-gemini-bridge/.env
והוסף שלוש שורות (הסיסמה - בלחיצה על "העתק" באתר ימות, בלשונית "מרכזיה עסקית"):
   YEMOT_REGISTER_HOST=sip.yemot.co.il
   YEMOT_SIP_USER=086693864
   YEMOT_SIP_PASSWORD=הסיסמה
ואז: sudo systemctl restart yemot-gemini-bridge
(אם הרישום נדחה, אל תנסה שוב ושוב: ימות חוסמת כתובת אחרי 5 ניסיונות שגויים.)

צפייה בלוג:   sudo journalctl -u yemot-gemini-bridge -f
בדיקת Gemini בלי ימות:
   cd /opt/yemot-gemini-bridge && ./venv/bin/python -m bridge.probe 127.0.0.1 --token "$(sudo grep ^ACCESS_TOKEN= .env | cut -d= -f2)"

אחרי שהכל עובד: למחוק את המארז מהשרת וממחשב ה-Windows (הוא מכיל מפתחות), ולהחליף את המפתחות שהודבקו בצ'אט.
