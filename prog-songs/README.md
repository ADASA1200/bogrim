# prog-songs

שירים חדשים מהאשכול "הסינגלים והקליפים החדשים" ב-prog.co.il -> כרטיס ב-Google Chat
(שם, אמן, קרדיטים, כפתורי האזנה/הורדה, YouTube והפוסט).

כל הלוגיקה ב-Apps Script (`Code.gs`): פענוח הדף, מניעת כפילויות (Script Properties), בניית הכרטיס, שליחה וטריגר.

## הקמה
1. **Chat:** בחדר Google Chat: *Apps & integrations > Webhooks* > צור webhook והעתק את הכתובת.
2. **Apps Script:** פרויקט חדש. הדבק את `Code.gs`. ב-*Project Settings* הפעל "Show appsscript.json" והדבק את `appsscript.json`.
3. **Project Settings > Script properties:**
   - `CHAT_WEBHOOK_URL` = כתובת ה-webhook
   - `SECRET` = מחרוזת אקראית ארוכה
4. הרץ `testChat` (פעם ראשונה תתבקש הרשאה). אמורה להופיע הודעת בדיקה בחדר.
5. **Deploy > New deployment > Web app:** Execute as *Me*, Who has access *Anyone*. העתק את כתובת ה-`/exec`.

## מקור הנתונים
- **שליפה ישירה:** הרץ `installTrigger` (בודק כל 10 דקות). בבדיקה שלנו Cloudflare החזיר 403 לשרתי גוגל,
  ואז `checkNewSongs` רק רושם ליומן שהבקשה נחסמה.
- **גשר דפדפן** (כשהשליפה הישירה חסומה): התקן את `bridge.user.js` ב-Tampermonkey, פתח את האשכול
  (`https://www.prog.co.il/threads/387726/latest`), ובתפריט Tampermonkey בחר *הגדר Web App URL + SECRET*.
  הגשר רק מעביר את ה-HTML ל-`doPost`; הכל השאר קורה ב-Apps Script. אפשר להפעיל "רענון אוטומטי" ולהשאיר את הלשונית פתוחה.

## הגדרות (`CONFIG` ב-`Code.gs`)
`ONLY_AUTHORS` (סינון מחברים), `SEND_WITHOUT_AUDIO` (פוסט בלי mp3 כמו #27,424), `MAX_PER_RUN`, `TRIGGER_MINUTES`.

## הערות
- הכפתור "האזנה / הורדה" מצביע על קובץ ה-mp3 ב-`s3.prog.co.il`; הוא נפתח בדפדפן שלך.
  Apps Script לא מעתיק את הקבצים (גם הם חסומים לו), ולכן אין עותק ב-Drive.
- פוסט בלי אודיו לא מסומן כ"נשלח", כך שאם יתווסף לו קובץ בעריכה הוא יישלח בריצה הבאה.
