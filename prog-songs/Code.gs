/**
 * prog-songs: שירים חדשים מאשכול "הסינגלים והקליפים החדשים" ב-prog.co.il -> כרטיס ב-Google Chat.
 *
 * כל הלוגיקה כאן: פענוח הדף, מניעת כפילויות, בניית הכרטיס, שליחה לצ'אט וטריגר אוטומטי.
 * מקור הדף יכול להיות:
 *   1. שליפה ישירה (checkNewSongs) - עובד רק אם Cloudflare לא חוסם את שרתי גוגל.
 *   2. doPost עם { action: 'ingest', pages: [html...] } - הדפדפן מעביר את ה-HTML (bridge.user.js).
 *
 * Script Properties (Project Settings): SECRET, CHAT_WEBHOOK_URL
 */

var THREAD_ID = '387726';
var THREAD_URL = 'https://www.prog.co.il/threads/' + THREAD_ID + '/';
var SITE = 'https://www.prog.co.il';

var CONFIG = {
  MAX_PER_RUN: 10,           // מקסימום כרטיסים בריצה אחת
  ONLY_AUTHORS: [],          // למשל ['עקיבא60']; ריק = כל המחברים
  SEND_WITHOUT_AUDIO: false, // פוסט בלי mp3 (רק YouTube): false = מדלגים ובודקים שוב בריצה הבאה
  TRIGGER_MINUTES: 10        // 1, 5, 10, 15 או 30
};

/* ------------------------------ נקודות כניסה ------------------------------ */

function doGet() {
  return json_({ ok: true, service: 'prog-songs' });
}

function doPost(e) {
  try {
    var req = JSON.parse(e.postData.contents);
    var secret = prop_('SECRET');
    if (!secret || req.token !== secret) return json_({ ok: false, error: 'unauthorized' });
    if (req.action === 'ingest') {
      if (!Array.isArray(req.pages) || !req.pages.length) return json_({ ok: false, error: 'no pages' });
      return json_({ ok: true, result: processPages_(req.pages) });
    }
    return json_({ ok: false, error: 'unknown action' });
  } catch (err) {
    return json_({ ok: false, error: String(err && err.message || err) });
  }
}

/** שליפה ישירה מהאתר + שליחה. מיועד לטריגר. */
function checkNewSongs() {
  var pages;
  try {
    pages = fetchLatestPages_();
  } catch (err) {
    console.error(err.message);
    return { ok: false, error: err.message };
  }
  var result = processPages_(pages);
  console.log(JSON.stringify(result));
  return result;
}

function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'checkNewSongs') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('checkNewSongs').timeBased().everyMinutes(CONFIG.TRIGGER_MINUTES).create();
}

/** בדיקת חיבור ל-Chat. */
function testChat() {
  postToChat_({
    postId: '0', title: 'בדיקה - שיר לדוגמה', artist: 'בדיקה', song: 'שיר לדוגמה',
    credits: ['לחן: פלוני.', 'עיבוד: אלמוני.'], audioUrl: SITE, youtube: 'https://www.youtube.com/',
    postUrl: THREAD_URL
  });
}

/* ------------------------------ שליפה ישירה ------------------------------ */

function fetchPage_(url) {
  var r = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: true,
    headers: { 'Accept-Language': 'he,en;q=0.8' }
  });
  var code = r.getResponseCode();
  var body = r.getContentText();
  if (code !== 200 || /<title>\s*(Just a moment|Attention Required)/i.test(body)) {
    throw new Error('prog.co.il חסם את הבקשה (HTTP ' + code + ', Cloudflare). השתמש ב-bridge.user.js.');
  }
  return body;
}

function fetchLatestPages_() {
  var last = fetchPage_(THREAD_URL + 'latest');
  var pages = [last];
  var m = last.match(/<link rel="prev" href="([^"]+)"/);
  if (m) pages.push(fetchPage_(SITE + decodeEntities_(m[1])));
  return pages;
}

/* ------------------------------ עיבוד ושליחה ------------------------------ */

function processPages_(htmls) {
  var byId = {};
  htmls.forEach(function (h) {
    parseThreadHtml_(h).forEach(function (s) { byId[s.postId] = s; });
  });
  var songs = Object.keys(byId).map(function (k) { return byId[k]; })
    .sort(function (a, b) { return Number(a.postId) - Number(b.postId); });

  var res = { found: songs.length, sent: [], alreadySent: 0, noAudio: 0, otherAuthor: 0, failed: [] };
  var props = PropertiesService.getScriptProperties();
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    songs.forEach(function (s) {
      if (CONFIG.ONLY_AUTHORS.length && CONFIG.ONLY_AUTHORS.indexOf(s.author) < 0) { res.otherAuthor++; return; }
      if (!s.audioUrl && !CONFIG.SEND_WITHOUT_AUDIO) { res.noAudio++; return; }
      if (props.getProperty('sent:' + s.postId)) { res.alreadySent++; return; }
      if (res.sent.length >= CONFIG.MAX_PER_RUN) return;
      try {
        postToChat_(s);
        props.setProperty('sent:' + s.postId, String(Date.now()));
        res.sent.push(s.postId + ' ' + s.title);
        Utilities.sleep(1100); // מגבלת קצב של webhook
      } catch (err) {
        res.failed.push(s.postId + ': ' + err.message);
      }
    });
  } finally {
    lock.releaseLock();
  }
  return res;
}

function postToChat_(s) {
  var url = prop_('CHAT_WEBHOOK_URL');
  if (!url) throw new Error('חסר CHAT_WEBHOOK_URL ב-Script Properties');
  var r = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json; charset=UTF-8',
    payload: JSON.stringify(buildMessage_(s)),
    muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 200) {
    throw new Error('Chat HTTP ' + r.getResponseCode() + ' ' + r.getContentText().slice(0, 200));
  }
}

function buildMessage_(s) {
  var widgets = [];
  if (s.credits && s.credits.length) {
    widgets.push({ textParagraph: { text: s.credits.map(escapeHtml_).join('<br>') } });
  }
  var buttons = [];
  if (s.audioUrl) buttons.push(button_('▶ האזנה / הורדה', s.audioUrl));
  if (s.youtube) buttons.push(button_('YouTube', s.youtube));
  buttons.push(button_('לפוסט', s.postUrl));
  widgets.push({ buttonList: { buttons: buttons } });

  var header = { title: s.song || s.title };
  if (s.artist) header.subtitle = s.artist;
  return {
    text: '🎵 ' + s.title,
    cardsV2: [{ cardId: 'post-' + s.postId, card: { header: header, sections: [{ widgets: widgets }] } }]
  };
}

function button_(text, url) {
  return { text: text, onClick: { openLink: { url: url } } };
}

/* ------------------------------ פענוח ה-HTML ------------------------------ */

/**
 * מקבל HTML של עמוד באשכול ומחזיר מערך שירים:
 * { postId, number, author, time, postUrl, title, artist, song, credits[], audioUrl, audioName, coverUrl, youtube }
 * (פונקציה טהורה, ללא תלות ב-API של Apps Script, כדי שאפשר יהיה לבדוק אותה גם ב-Node.)
 */
function parseThreadHtml_(html) {
  var out = [];
  var startRe = /<article class="message message--post js-post[^>]*?data-content="post-(\d+)"/g;
  var anyPostRe = /<article class="message message--post/g;
  var starts = [], m;
  while ((m = startRe.exec(html))) starts.push({ idx: m.index, id: m[1] });

  starts.forEach(function (st) {
    // מסיימים בפוסט/מודעה הבאים, אחרת היינו שואבים את הפרסומות שאחרי הפוסט האחרון
    anyPostRe.lastIndex = st.idx + 10;
    var next = anyPostRe.exec(html);
    var chunk = html.slice(st.idx, next ? next.index : html.length);
    out.push(parsePost_(st.id, chunk));
  });
  return out;
}

function parsePost_(postId, chunk) {
  var author = (chunk.match(/data-author="([^"]*)"/) || [])[1] || '';
  var number = (chunk.match(/message-attribution-opposite[\s\S]*?#([\d,]+)\s*<\/a>/) || [])[1] || '';
  var time = (chunk.match(/data-time="(\d+)"/) || [])[1] || '';

  var body = (chunk.match(/<div class="bbWrapper">([\s\S]*?)<div class="js-selectToQuoteEnd">/) || [])[1] || '';
  var head = parseHead_(body);

  // mp3: קודם הקובץ המצורף (יש לו שם), אחרת נגן ה-audio
  var audioUrl = '', audioName = '';
  var att = chunk.match(/<a class="file-preview" href="([^"]+\.(?:mp3|m4a|aac|wav|ogg|flac))"/i);
  if (att) {
    audioUrl = decodeEntities_(att[1]);
    var nm = chunk.match(/class="file-name" title="([^"]*)"/);
    if (nm) audioName = decodeEntities_(nm[1]);
  } else {
    var au = body.match(/<audio[\s\S]*?<source src="([^"]+)"/);
    if (au) audioUrl = decodeEntities_(au[1]);
  }

  // תמונת עטיפה (הראשונה בגוף הפוסט)
  var coverUrl = '';
  var img = body.match(/<img[^>]*class="bbImage"[^>]*>/);
  if (img) {
    var src = img[0].match(/\ssrc="([^"]+)"/);
    if (src) coverUrl = decodeEntities_(src[1]);
  }

  // YouTube מתוך תצוגת הקישור המקדימה. (קישור ה-Drive זהה בכל פוסט, לכן מתעלמים ממנו.)
  var yt = body.match(/data-url="(https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/[^"]+)"/);

  var t = splitTitle_(head.title);
  return {
    postId: postId, number: number, author: author, time: time,
    postUrl: SITE + '/posts/' + postId + '/',
    title: head.title, artist: t.artist, song: t.song, credits: head.credits,
    audioUrl: audioUrl, audioName: audioName, coverUrl: coverUrl,
    youtube: yt ? decodeEntities_(yt[1]) : ''
  };
}

/** שורה ראשונה = "אמן - שם"; השורות הבאות עד שורה ריקה = קרדיטים. */
function parseHead_(bodyHtml) {
  var head = bodyHtml.split(/<(?:div|script|table|blockquote|ul|ol)\b/i)[0];
  var lines = head.split(/<br\s*\/?>/i).map(function (l) {
    return decodeEntities_(l.replace(/<[^>]*>/g, '')).replace(/[‎‏‪-‮ ]/g, ' ').trim();
  });
  var i = 0;
  while (i < lines.length && !lines[i]) i++;
  var title = collapse_(lines[i] || '');
  var credits = [];
  for (i = i + 1; i < lines.length && lines[i]; i++) {
    lines[i].split(/\s{2,}/).forEach(function (part) {
      part = collapse_(part);
      if (part) credits.push(part);
    });
  }
  return { title: title, credits: credits };
}

function splitTitle_(title) {
  var m = title.match(/^(.*?)\s+[-–—]\s+(.+)$/);
  return m ? { artist: m[1], song: m[2] } : { artist: '', song: title };
}

/* ------------------------------ עזרים ------------------------------ */

function collapse_(s) { return s.replace(/\s+/g, ' ').trim(); }

function decodeEntities_(s) {
  return String(s).replace(/&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos|nbsp);/g, function (m, g) {
    switch (g) {
      case 'amp': return '&';
      case 'lt': return '<';
      case 'gt': return '>';
      case 'quot': return '"';
      case 'apos': return "'";
      case 'nbsp': return ' ';
    }
    var code = g.charAt(1) === 'x' ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10);
    return isNaN(code) ? m : String.fromCodePoint(code);
  });
}

function escapeHtml_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
