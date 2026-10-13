// ==UserScript==
// @name         prog-songs bridge
// @namespace    bogrim.prog-songs
// @version      1.0.0
// @description  צינור דק: מעביר את ה-HTML של עמוד האשכול (ושל העמוד הקודם) ל-Apps Script. כל הלוגיקה שם.
// @match        https://www.prog.co.il/threads/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      script.google.com
// @connect      script.googleusercontent.com
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';
  var THREAD_ID = '387726';
  if (location.pathname.indexOf('.' + THREAD_ID) < 0) return;

  var REFRESH_MIN = 10; // רענון אוטומטי כשהמצב פעיל

  GM_registerMenuCommand('הגדר Web App URL + SECRET', function () {
    var url = prompt('כתובת ה-Web App (מסתיימת ב-/exec):', GM_getValue('url', ''));
    if (url === null) return;
    var secret = prompt('SECRET (כמו ב-Script Properties):', GM_getValue('secret', ''));
    if (secret === null) return;
    GM_setValue('url', url.trim());
    GM_setValue('secret', secret.trim());
    run();
  });
  GM_registerMenuCommand('שלח עכשיו', run);
  GM_registerMenuCommand('רענון אוטומטי: ' + (GM_getValue('auto', false) ? 'פעיל (לחץ לכיבוי)' : 'כבוי (לחץ להפעלה)'), function () {
    GM_setValue('auto', !GM_getValue('auto', false));
    location.reload();
  });

  function toast(msg, isError) {
    var el = document.getElementById('ps-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'ps-toast';
      el.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:99999;padding:8px 12px;border-radius:6px;' +
        'font:13px sans-serif;color:#fff;direction:rtl;max-width:340px;box-shadow:0 2px 8px rgba(0,0,0,.3)';
      document.body.appendChild(el);
    }
    el.style.background = isError ? '#b3261e' : '#1b6b3a';
    el.textContent = msg;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.remove(); }, 8000);
  }

  function getText(url) {
    // אותו מקור, עם העוגיות שלך: ה-HTML הגולמי כפי שהשרת שולח (זה מה שהפענוח ב-Apps Script נבדק מולו)
    return fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url);
      return r.text();
    });
  }

  function post(url, payload) {
    return new Promise(function (resolve, reject) {
      GM_xmlhttpRequest({
        method: 'POST', url: url, data: JSON.stringify(payload),
        headers: { 'Content-Type': 'text/plain;charset=utf-8' }, // בלי preflight
        timeout: 120000,
        onload: function (r) {
          try { resolve(JSON.parse(r.responseText)); }
          catch (e) { reject(new Error('תשובה לא צפויה מה-Web App (HTTP ' + r.status + '). בדוק שהפריסה היא Anyone.')); }
        },
        onerror: function () { reject(new Error('שגיאת רשת מול Apps Script')); },
        ontimeout: function () { reject(new Error('תם הזמן מול Apps Script')); }
      });
    });
  }

  function run() {
    var url = GM_getValue('url', ''), secret = GM_getValue('secret', '');
    if (!url || !secret) { toast('חסרה הגדרה: תפריט Tampermonkey > הגדר Web App URL + SECRET', true); return; }

    var prev = document.querySelector('link[rel="prev"]');
    var urls = [location.href];
    if (prev) urls.push(new URL(prev.getAttribute('href'), location.href).href);

    Promise.all(urls.map(getText))
      .then(function (pages) { return post(url, { token: secret, action: 'ingest', pages: pages }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error);
        var r = res.result;
        toast('נשלחו ' + r.sent.length + ' | כבר נשלחו ' + r.alreadySent + ' | בלי אודיו ' + r.noAudio +
          (r.failed.length ? ' | נכשלו ' + r.failed.length : ''), r.failed.length > 0);
      })
      .catch(function (err) { toast('שגיאה: ' + err.message, true); });
  }

  run();

  if (GM_getValue('auto', false)) {
    setTimeout(function () {
      // נוצר עמוד חדש? עוברים לסוף האשכול, אחרת מרעננים
      if (document.querySelector('link[rel="next"]')) location.href = location.origin + '/threads/' + THREAD_ID + '/latest';
      else location.reload();
    }, REFRESH_MIN * 60 * 1000);
  }
})();
