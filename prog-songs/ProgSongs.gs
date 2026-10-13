/**
 * פרוג סינגלים — שירים חדשים מאשכול "הסינגלים והקליפים החדשים" ב-prog.co.il -> העלאה ישירה ל-Google Chat.
 * קובץ נוסף בפרויקט "מיוזיק". הוא משתמש בפונקציות/קבועים הקיימים שם ואינו מגדיר אותם מחדש:
 *   SPREADSHEET_ID, SPACE_ID, TIME_ZONE, APPS_SCRIPT_DIRECT_UPLOAD_LIMIT_MB, logMusic,
 *   uploadBlobToChatRequest, createChatMessage, convertToHebrewDate,
 *   findID3v2Header, findAPICFrame, determineMimeType.
 *
 * הפעלה ראשית: runProgSongs (אפשר גם לקרוא לה מתוך runAllMonitors). התקנת טריגר: installProgTrigger.
 * בדיקה בלי שליחה/כתיבה: inspectProgSongs. בדיקת גישה לאתר: diagnoseProgAccess.
 *
 * לוגיקת עמודים: נשמר מספר העמוד האחרון (Script Property PROG_LAST_PAGE). בכל ריצה בודקים אם קיים
 * עמוד הבא; אם כן מתקדמים אליו (וסורקים גם את העמודים שדילגנו עליהם), ואם לא נוצר עמוד חדש חוזרים
 * לסרוק את שני העמודים האחרונים.
 */
const PROG_THREAD_ID = '387726';
const PROG_SITE = 'https://www.prog.co.il';
const PROG_THREAD_BASE = PROG_SITE + '/threads/%D7%94%D7%A1%D7%99%D7%A0%D7%92%D7%9C%D7%99%D7%9D-%D7%95%D7%94%D7%A7%D7%9C%D7%99%D7%A4%D7%99%D7%9D-%D7%94%D7%97%D7%93%D7%A9%D7%99%D7%9D.' + PROG_THREAD_ID + '/';
const PROG_SHEET_NAME = 'פרוג';

// משנים כאן בלבד.
const PROG_START_PAGE = 1372;       // עמוד התחלה; בהמשך נשמר ב-Script Property PROG_LAST_PAGE
const PROG_MIN_POST_ID = 17057764;  // לא שולחים פוסטים ישנים יותר (מונע הצפה בהרצה הראשונה)
const PROG_ONLY_AUTHORS = [];       // למשל ['עקיבא60']; ריק = כל המחברים
const PROG_MAX_PER_RUN = 6;
const PROG_MAX_PAGE_ADVANCE = 5;    // כמה עמודים חדשים מתקדמים בריצה אחת
const PROG_MAX_ATTEMPTS = 5;        // אחרי כמה כישלונות הפוסט מסומן FAILED (דורש טיפול ידני)
const PROG_BUDGET_MS = 240000;
const PROG_MIN_TIME_TO_START_MS = 45000; // הורדה + העלאה של שיר של ~15MB
const PROG_VERSION = 'progSongsV1';

// עמודות: A-C תאריך/קישור/שם כמו בגיליונות האחרים.
const PROG_HEADERS = [
  'תאריך שליחה', 'קישור לפוסט', 'שם', 'מזהה פוסט', 'מספר פוסט', 'מחבר',
  'קישור mp3', 'עמוד', 'מצב', 'ניסיונות', 'שגיאה אחרונה', 'הודעות JSON', 'עדכון אחרון'
];

/* ------------------------------ נקודות כניסה ------------------------------ */

function runProgSongs() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) { logMusic('פרוג: הרצה אחרת פעילה; מדלג'); return; }
  const deadline = Date.now() + PROG_BUDGET_MS;
  try {
    const props = PropertiesService.getScriptProperties();
    const startPage = Number(props.getProperty('PROG_LAST_PAGE')) || PROG_START_PAGE;
    const scan = progCollectPages_(startPage);
    logMusic('פרוג: עמוד אחרון ' + scan.lastPage + ' | נסרקו עמודים ' + Object.keys(scan.pages).join(', '));

    const tracker = progOpenTracker_(true);
    const queue = progPendingSongs_(scan.pages, tracker);
    logMusic('פרוג: ' + queue.length + ' שירים ממתינים לשליחה');

    let failures = 0, sent = 0;
    for (const item of queue.slice(0, PROG_MAX_PER_RUN)) {
      if (Date.now() + PROG_MIN_TIME_TO_START_MS >= deadline) { logMusic('פרוג: הזמן הסתיים; ההמשך בהרצה הבאה'); failures++; break; }
      if (progProcessSong_(tracker, item.song, item.page, deadline)) sent++; else failures++;
    }
    if (queue.length > PROG_MAX_PER_RUN) failures++; // נשארו שירים: לא מקדמים את העמוד עד שהתור ריק
    // מקדמים את העמוד השמור רק אם הכל הושלם; אחרת בריצה הבאה נסרוק שוב את אותם עמודים.
    if (!failures) props.setProperty('PROG_LAST_PAGE', String(scan.lastPage));
    logMusic('פרוג: נשלחו ' + sent + ' | כשלונות/ממתינים ' + failures);
  } catch (e) {
    logMusic('פרוג: הריצה נכשלה: ' + e);
  } finally {
    lock.releaseLock();
  }
}

function installProgTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => { if (t.getHandlerFunction() === 'runProgSongs') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('runProgSongs').timeBased().everyMinutes(10).create();
}

/** קריאה בלבד: מה היה נשלח. אין שליחה ל-Chat ואין כתיבה בגיליון/Properties. */
function inspectProgSongs() {
  const startPage = Number(PropertiesService.getScriptProperties().getProperty('PROG_LAST_PAGE')) || PROG_START_PAGE;
  const scan = progCollectPages_(startPage);
  logMusic('פרוג: עמוד אחרון ' + scan.lastPage + ' | נסרקו ' + Object.keys(scan.pages).join(', '));
  const tracker = progOpenTracker_(false);
  const pending = new Set(progPendingSongs_(scan.pages, tracker).map(i => i.song.postId));
  Object.keys(scan.pages).forEach(page => {
    progParseThread_(scan.pages[page]).forEach(s => {
      logMusic('עמוד ' + page + ' | #' + s.number + ' ' + s.postId + ' | ' + s.author + ' | ' + s.title +
        ' | אודיו: ' + (s.audioUrl ? (s.audioSizeMB || '?') + 'MB' : 'אין') + ' | ' + (pending.has(s.postId) ? 'יישלח' : 'לא יישלח'));
    });
  });
}

/** האם Cloudflare חוסם את Apps Script? מדפיס קוד/סוג/כותרת לכל אחד מהמשאבים. */
function diagnoseProgAccess() {
  const page = progFetchPage_(Number(PropertiesService.getScriptProperties().getProperty('PROG_LAST_PAGE')) || PROG_START_PAGE, true);
  const songs = page && page.html ? progParseThread_(page.html).filter(s => s.audioUrl) : [];
  const probe = (label, url, headers) => {
    const r = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: headers });
    const h = r.getHeaders();
    const title = (r.getContentText().match(/<title>([^<]*)<\/title>/i) || [])[1] || '';
    logMusic('diagnose ' + label + ' -> HTTP ' + r.getResponseCode() + ' | ' + (h['Content-Type'] || h['content-type']) + (title ? ' | title: ' + title : ''));
  };
  if (!songs.length) { logMusic('diagnose: לא נמצא שיר לבדיקה (העמוד עצמו נחסם?)'); return; }
  const s = songs[songs.length - 1];
  probe('mp3', s.audioUrl, { Range: 'bytes=0-1023', Referer: PROG_SITE + '/' });
  if (s.coverUrl) probe('cover', s.coverUrl, { Referer: PROG_SITE + '/' });
}

/* ------------------------------ עמודים ------------------------------ */

/**
 * מביא עמוד. מחזיר { page, html } לפי ה-canonical (XenForo מפנה עמוד מעבר לאחרון לעמוד האחרון),
 * או null אם העמוד לא קיים (404). נחסם ע"י Cloudflare => זורק שגיאה.
 */
function progFetchPage_(page, soft) {
  const url = PROG_THREAD_BASE + (page > 1 ? 'page-' + page : '');
  const r = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true, headers: { 'Accept-Language': 'he,en;q=0.8' } });
  const code = r.getResponseCode();
  const html = r.getContentText();
  if (/<title>\s*(Just a moment|Attention Required)/i.test(html)) {
    if (soft) { logMusic('diagnose עמוד ' + page + ' -> HTTP ' + code + ' | Cloudflare חסם'); return null; }
    throw new Error('prog.co.il חסם את הבקשה (HTTP ' + code + ', Cloudflare)');
  }
  if (code === 404) return null;
  if (code !== 200) throw new Error('prog.co.il החזיר HTTP ' + code + ' לעמוד ' + page);
  const m = html.match(new RegExp('<link rel="canonical" href="[^"]*?\\.' + PROG_THREAD_ID + '/(?:page-(\\d+))?"'));
  if (!m) throw new Error('לא נמצא canonical בעמוד ' + page + ' (מבנה העמוד השתנה?)');
  return { page: m[1] ? Number(m[1]) : 1, html: html };
}

/**
 * מתחילים מהעמוד השמור, מתקדמים כל עוד קיים עמוד הבא. אם לא נוצר עמוד חדש מוסיפים את העמוד שלפניו,
 * כך שתמיד נסרקים לפחות שני עמודים אחרונים.
 */
function progCollectPages_(startPage) {
  const first = progFetchPage_(startPage);
  if (!first) throw new Error('עמוד ' + startPage + ' לא קיים');
  const pages = {};
  let current = first.page;
  pages[current] = first.html;
  for (let i = 0; i < PROG_MAX_PAGE_ADVANCE; i++) {
    const next = progFetchPage_(current + 1);
    if (!next || next.page !== current + 1) break; // לא נוצר עמוד חדש (או הפניה חזרה לאחרון)
    current = next.page;
    pages[current] = next.html;
  }
  if (current > 1 && !pages[current - 1]) {
    const prev = progFetchPage_(current - 1);
    if (prev && prev.page === current - 1) pages[current - 1] = prev.html;
  }
  return { lastPage: current, pages: pages };
}

/* ------------------------------ מעקב בגיליון ------------------------------ */

function progOpenTracker_(createIfMissing) {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = spreadsheet.getSheetByName(PROG_SHEET_NAME);
  if (!sheet) {
    if (!createIfMissing) return { sheet: null, byPost: new Map() };
    sheet = spreadsheet.insertSheet(PROG_SHEET_NAME);
  }
  if (!sheet.getLastRow()) sheet.appendRow(PROG_HEADERS);
  const rows = sheet.getLastRow() > 1 ? sheet.getRange(2, 1, sheet.getLastRow() - 1, PROG_HEADERS.length).getValues() : [];
  const byPost = new Map();
  rows.forEach((values, i) => { if (values[3] !== '') byPost.set(String(values[3]), { row: i + 2, values: values }); });
  return { sheet: sheet, byPost: byPost };
}

function progSave_(tracker, record) {
  record.values[12] = new Date();
  tracker.sheet.getRange(record.row, 1, 1, PROG_HEADERS.length).setValues([record.values]);
  SpreadsheetApp.flush();
}

function progAddRecord_(tracker, song, page) {
  const values = [
    '', song.postUrl, song.title, song.postId, song.number, song.author,
    song.audioUrl, page, 'NEW', 0, '', '', new Date()
  ];
  tracker.sheet.appendRow(values);
  const record = { row: tracker.sheet.getLastRow(), values: values };
  tracker.byPost.set(song.postId, record);
  return record;
}

/** שירים עם אודיו שעדיין לא נשלחו, מהישן לחדש. */
function progPendingSongs_(pages, tracker) {
  const byId = {};
  Object.keys(pages).forEach(page => {
    progParseThread_(pages[page]).forEach(s => { byId[s.postId] = { song: s, page: Number(page) }; });
  });
  return Object.keys(byId).map(k => byId[k])
    .filter(({ song }) => {
      if (Number(song.postId) < PROG_MIN_POST_ID) return false;
      if (PROG_ONLY_AUTHORS.length && PROG_ONLY_AUTHORS.indexOf(song.author) < 0) return false;
      if (!song.audioUrl) return false; // פוסט בלי אודיו: לא נרשם, ייבדק שוב בסריקה הבאה
      const rec = tracker.byPost.get(song.postId);
      return !rec || (rec.values[8] !== 'SENT' && rec.values[8] !== 'FAILED');
    })
    .sort((a, b) => Number(a.song.postId) - Number(b.song.postId));
}

/* ------------------------------ שליחה ------------------------------ */

function progProcessSong_(tracker, song, page, deadline) {
  const record = tracker.byPost.get(song.postId) || progAddRecord_(tracker, song, page);
  const v = record.values;
  v[9] = Number(v[9] || 0) + 1;
  v[8] = 'SENDING';
  progSave_(tracker, record);
  try {
    logMusic('פרוג: מטפל ב-' + song.title + ' | פוסט ' + song.postId);
    const names = progSendSong_(song, deadline);
    v[0] = new Date();
    v[8] = 'SENT';
    v[10] = '';
    v[11] = JSON.stringify({ version: PROG_VERSION, messages: names });
    progSave_(tracker, record);
    logMusic('פרוג: הושלם ' + song.title);
    return true;
  } catch (e) {
    v[8] = v[9] >= PROG_MAX_ATTEMPTS ? 'FAILED' : 'RETRY';
    v[10] = String(e).slice(0, 2000);
    try { progSave_(tracker, record); } catch (writeError) { logMusic('פרוג: שמירת השגיאה נכשלה: ' + writeError); }
    logMusic('פרוג: לא הושלם (' + v[8] + '): ' + song.title + ' | ' + e);
    return false;
  }
}

function progSendSong_(song, deadline) {
  const tooBig = song.audioSizeMB && song.audioSizeMB > APPS_SCRIPT_DIRECT_UPLOAD_LIMIT_MB;
  let audioBlob = null, bytes = null;
  if (!tooBig) {
    audioBlob = progDownload_(song.audioUrl, 'audio', /^audio\/|octet-stream/i);
    audioBlob.setName(song.audioName || (song.title + '.mp3'));
    if (/octet-stream/i.test(audioBlob.getContentType() || '') && /\.mp3$/i.test(audioBlob.getName())) audioBlob.setContentType('audio/mpeg');
    bytes = audioBlob.getBytes();
  }
  const sizeMB = bytes ? bytes.length / (1024 * 1024) : (song.audioSizeMB || 0);

  // עטיפה: קודם התמונה מהפוסט, ואם אי אפשר - תמונת האלבום מתוך ה-ID3 של הקובץ
  let coverBlob = null;
  if (song.coverUrl) {
    try { coverBlob = progDownload_(song.coverUrl, 'cover', /^image\//i); }
    catch (e) { logMusic('פרוג: העטיפה מהפוסט לא ירדה; מנסים ID3: ' + e.message); }
  }
  if (coverBlob) coverBlob.setName('cover.' + (/png/i.test(coverBlob.getContentType()) ? 'png' : /webp/i.test(coverBlob.getContentType()) ? 'webp' : 'jpg'));
  else if (bytes) coverBlob = progAlbumArtFromBytes_(bytes);

  let fileToken = null, artToken = null;
  if (audioBlob) fileToken = uploadBlobToChatRequest(audioBlob, audioBlob.getName());
  if (coverBlob) {
    try { artToken = uploadBlobToChatRequest(coverBlob, coverBlob.getName()); }
    catch (e) { logMusic('פרוג: העלאת העטיפה נכשלה; ממשיכים בלעדיה: ' + e.message); }
  }

  const text = progMessageText_(song, sizeMB, !audioBlob);
  const parts = [];
  if (fileToken && artToken) {
    parts.push({ suffix: 'art', payload: { text: text, attachment: [{ attachmentDataRef: artToken }] } });
    parts.push({ suffix: 'file', payload: { attachment: [{ attachmentDataRef: fileToken }] } });
  } else {
    const payload = { text: text };
    const token = artToken || fileToken;
    if (token) payload.attachment = [{ attachmentDataRef: token }];
    parts.push({ suffix: 'single', payload: payload });
  }
  // messageId קבוע לכל פוסט: ניסיון חוזר לא יוצר הודעה כפולה (ראו createChatMessage).
  return parts.map(p => createChatMessage(p.payload, song.title + ' ' + p.suffix,
    PROG_VERSION + ':' + SPACE_ID + ':' + song.postId + ':' + p.suffix, deadline));
}

function progMessageText_(song, sizeMB, linkOnly) {
  const size = !sizeMB ? '' : sizeMB < 1000 ? sizeMB.toFixed(2) + ' MB' : (sizeMB / 1024).toFixed(2) + ' GB';
  let date = 'תאריך לא זמין';
  if (song.time) date = convertToHebrewDate(new Date(Number(song.time) * 1000));
  let text = '🎵 *שם:* ' + song.title + '\n';
  if (song.credits.length) text += '🎼 *קרדיטים:* ' + song.credits.join(' | ').slice(0, 2500) + '\n';
  if (size) text += '⚖️ *גודל:* ' + size + '\n';
  text += '📅 *תאריך:* ' + date + '\n';
  if (linkOnly) text += '⚠️ _הקובץ גדול מדי לצירוף ישיר; זמין בקישור_\n';
  text += '\n<' + song.postUrl + '|📝 לפוסט>';
  if (song.youtube) text += ' | <' + song.youtube + '|▶ YouTube>';
  if (linkOnly) text += ' | <' + song.audioUrl + '|📥 הורדה>';
  return text;
}

/** מוריד קובץ ומוודא שלא קיבלנו דף חסימה/התחברות במקום הקובץ. */
function progDownload_(url, kind, typeRe) {
  const r = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: { Referer: PROG_SITE + '/' } });
  const code = r.getResponseCode();
  const headers = r.getHeaders();
  const type = String(headers['Content-Type'] || headers['content-type'] || '');
  if (code !== 200) throw new Error(kind + ' HTTP ' + code + (/text\/html/i.test(type) ? ' (דף HTML - חסימה?)' : ''));
  if (!typeRe.test(type)) throw new Error(kind + ': סוג תוכן לא צפוי ' + type);
  return r.getBlob();
}

/** תמונת אלבום מתוך תגית ID3 של הקובץ שכבר ירד (אותן פונקציות פענוח שכבר קיימות בפרויקט). */
function progAlbumArtFromBytes_(bytes) {
  try {
    const id3 = findID3v2Header(bytes);
    if (!id3) return null;
    const apic = findAPICFrame(bytes, id3.tagStart, id3.tagSize, id3.majorVersion);
    if (!apic) return null;
    const image = bytes.slice(apic.dataStart, apic.dataStart + apic.dataSize);
    const mime = determineMimeType(image);
    const ext = mime === 'image/png' ? 'png' : mime === 'image/webp' ? 'webp' : 'jpg';
    return Utilities.newBlob(image, mime, 'cover.' + ext);
  } catch (e) {
    logMusic('פרוג: חילוץ תמונת אלבום נכשל: ' + e.message);
    return null;
  }
}

/* ------------------------------ פענוח ה-HTML ------------------------------ */

/**
 * מקבל HTML של עמוד באשכול ומחזיר מערך שירים:
 * { postId, number, author, time, postUrl, title, artist, song, credits[], audioUrl, audioName, audioSizeMB, coverUrl, youtube }
 */
function progParseThread_(html) {
  const out = [];
  const startRe = /<article class="message message--post js-post[^>]*?data-content="post-(\d+)"/g;
  const anyPostRe = /<article class="message message--post/g;
  const starts = [];
  let m;
  while ((m = startRe.exec(html))) starts.push({ idx: m.index, id: m[1] });
  starts.forEach(st => {
    // עד הפוסט/המודעה הבאים, כדי לא לשאוב את הפרסומות שאחרי הפוסט האחרון
    anyPostRe.lastIndex = st.idx + 10;
    const next = anyPostRe.exec(html);
    out.push(progParsePost_(st.id, html.slice(st.idx, next ? next.index : html.length)));
  });
  return out;
}

function progParsePost_(postId, chunk) {
  const author = (chunk.match(/data-author="([^"]*)"/) || [])[1] || '';
  const number = (chunk.match(/message-attribution-opposite[\s\S]*?#([\d,]+)\s*<\/a>/) || [])[1] || '';
  const time = (chunk.match(/data-time="(\d+)"/) || [])[1] || '';
  const body = (chunk.match(/<div class="bbWrapper">([\s\S]*?)<div class="js-selectToQuoteEnd">/) || [])[1] || '';
  const head = progParseHead_(body);

  // mp3: קודם הקובץ המצורף (יש לו שם וגודל), אחרת נגן ה-audio
  let audioUrl = '', audioName = '', audioSizeMB = 0;
  const att = chunk.match(/<a class="file-preview" href="([^"]+\.(?:mp3|m4a|aac|wav|ogg|flac))"/i);
  if (att) {
    audioUrl = progDecode_(att[1]);
    const nm = chunk.match(/class="file-name" title="([^"]*)"/);
    if (nm) audioName = progDecode_(nm[1]);
    const sz = chunk.match(/class="file-meta">\s*([\d.,]+)\s*(KB|MB|GB)/i);
    if (sz) {
      const n = parseFloat(sz[1].replace(',', ''));
      audioSizeMB = sz[2].toUpperCase() === 'GB' ? n * 1024 : sz[2].toUpperCase() === 'KB' ? n / 1024 : n;
    }
  } else {
    const au = body.match(/<audio[\s\S]*?<source src="([^"]+)"/);
    if (au) audioUrl = progDecode_(au[1]);
  }

  let coverUrl = '';
  const img = body.match(/<img[^>]*class="bbImage"[^>]*>/);
  if (img) {
    const src = img[0].match(/\ssrc="([^"]+)"/);
    if (src) coverUrl = progDecode_(src[1]);
  }

  // YouTube מהתצוגה המקדימה. קישור ה-Drive זהה בכל פוסט (תיקייה כללית), לכן לא נשלח.
  const yt = body.match(/data-url="(https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/[^"]+)"/);

  const t = progSplitTitle_(head.title);
  return {
    postId: postId, number: number, author: author, time: time,
    postUrl: PROG_SITE + '/posts/' + postId + '/',
    title: head.title, artist: t.artist, song: t.song, credits: head.credits,
    audioUrl: audioUrl, audioName: audioName, audioSizeMB: audioSizeMB,
    coverUrl: coverUrl, youtube: yt ? progDecode_(yt[1]) : ''
  };
}

/** שורה ראשונה = "אמן - שם"; השורות הבאות עד שורה ריקה = קרדיטים. */
function progParseHead_(bodyHtml) {
  const head = bodyHtml.split(/<(?:div|script|table|blockquote|ul|ol)\b/i)[0];
  const lines = head.split(/<br\s*\/?>/i).map(l =>
    progDecode_(l.replace(/<[^>]*>/g, '')).replace(/[‎‏‪-‮ ]/g, ' ').trim());
  let i = 0;
  while (i < lines.length && !lines[i]) i++;
  const title = progCollapse_(lines[i] || '');
  const credits = [];
  for (i = i + 1; i < lines.length && lines[i]; i++) {
    lines[i].split(/\s{2,}/).forEach(part => { part = progCollapse_(part); if (part) credits.push(part); });
  }
  return { title: title, credits: credits };
}

function progSplitTitle_(title) {
  const m = title.match(/^(.*?)\s+[-–—]\s+(.+)$/);
  return m ? { artist: m[1], song: m[2] } : { artist: '', song: title };
}

function progCollapse_(s) { return s.replace(/\s+/g, ' ').trim(); }

function progDecode_(s) {
  return String(s).replace(/&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos|nbsp);/g, (m, g) => {
    switch (g) {
      case 'amp': return '&';
      case 'lt': return '<';
      case 'gt': return '>';
      case 'quot': return '"';
      case 'apos': return "'";
      case 'nbsp': return ' ';
    }
    const code = g.charAt(1) === 'x' ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10);
    return isNaN(code) ? m : String.fromCodePoint(code);
  });
}
