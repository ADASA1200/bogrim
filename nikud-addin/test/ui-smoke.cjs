// בדיקת עשן לחלונית בדפדפן, מול Word מדומה (test/fake-word.js).
// הרצה: node test/ui-smoke.cjs   (דורש Playwright מותקן)
const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };

function serve() {
  const server = http.createServer((req, res) => {
    const file = path.join(root, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { 'Content-Type': (types[path.extname(file)] ?? 'application/octet-stream') + '; charset=utf-8' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((r) => server.listen(0, () => r(server)));
}

const n = (s) => s.normalize('NFC');

function assertEq(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`);
  }
  console.log('ok -', msg);
}

(async () => {
  const server = await serve();
  const port = server.address().port;
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  await page.route('https://appsforoffice.microsoft.com/**', (r) => r.fulfill({ body: '', contentType: 'text/javascript' }));

  const docText = 'משה למד (ספר) ולנתנאל שולחן, ע"ה.\rדוד';
  await page.addInitScript(`window.__FAKE_DOC_TEXT__ = ${JSON.stringify(docText)};`);
  await page.addInitScript({ path: path.join(__dirname, 'fake-word.js') });
  await page.goto(`http://localhost:${port}/src/taskpane.html`);
  await page.waitForFunction(() => /במילון \d+/.test(document.getElementById('dict-size').textContent));

  const original = () => page.textContent('#original');
  const options = () => page.$$eval('#options li[role=option] span:first-child', (els) => els.map((e) => e.textContent));
  const doc = () => page.evaluate(() => window.__fakeDoc.text);

  await page.click('#btn-start');
  // משה: אפשרות אחת, מנוקדת אוטומטית. העצירה הראשונה היא "למד".
  await page.waitForFunction(() => document.getElementById('original').textContent === 'למד');
  assertEq((await options()).length, 2, 'למד: שתי אפשרויות');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter'); // לִמֵּד

  await page.waitForFunction(() => document.getElementById('original').textContent === 'ספר');
  await page.keyboard.press('ArrowLeft'); // דלג

  await page.waitForFunction(() => document.getElementById('original').textContent === 'ולנתנאל');
  const pre = await page.$$eval('#options li .tag', (els) => els.map((e) => e.textContent));
  assertEq(pre.every((t) => t === '+'), true, 'ולנתנאל: הצעות מסומנות +');
  await page.keyboard.press('Enter');

  await page.waitForFunction(() => document.getElementById('original').textContent === 'שולחן');
  assertEq(await page.evaluate(() => document.activeElement.id), 'manual-input', 'מילה חסרה: המיקוד עובר לניקוד ידני');
  await page.fill('#manual-input', 'שֻׁלְחָן');
  await page.keyboard.press('Enter'); // הוסף והמשך

  await page.waitForFunction(() => document.getElementById('original').textContent === 'ע"ה');
  await page.keyboard.press('Control+z'); // ביטול: חוזר ל"שולחן"
  await page.waitForFunction(() => document.getElementById('original').textContent === 'שולחן');
  assertEq((await doc()).includes('שולחן,'), true, 'ביטול החזיר את המילה המקורית');
  assertEq(n((await options())[0]), n('שֻׁלְחָן'), 'שולחן נשמר במילון');
  await page.focus('#options');
  await page.keyboard.press('Enter');

  await page.waitForFunction(() => document.getElementById('original').textContent === 'ע"ה');
  await page.keyboard.press('Alt+Enter'); // פתיחת ר"ת, עם $$ לבדיקה

  // דוד: אפשרות אחת, ואז סוף המסמך
  await page.waitForFunction(() => !document.getElementById('idle').hidden);

  const finalText = await doc();
  console.log('document:', finalText.replace('\r', ' ¶ '));
  for (const w of ['מֹשֶׁה', 'לִמֵּד', '(ספר)', 'שֻׁלְחָן,', '$$עָלָיו הַשָּׁלוֹם.', 'דָּוִד']) {
    assertEq(n(finalText).includes(n(w)), true, `המסמך מכיל ${w}`);
  }
  const vlan = finalText.split(' ')[3];
  assertEq(vlan.replace(/[֑-ׇ]/g, ''), 'ולנתנאל', 'אותיות "ולנתנאל" נשמרו');

  // לשונית המילון
  await page.click('[data-tab=dictionary]');
  await page.fill('#dict-search', 'שולחן');
  await page.waitForSelector('#dict-values li');
  assertEq(n(await page.textContent('#dict-values li')), n('שֻׁלְחָן'), 'המילון מציג את המילה שנוספה');

  // הגדרות נשמרות
  await page.click('[data-tab=settings]');
  await page.click('[data-preset=run]');
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('nikud-kal.settings')).whenMultiple);
  assertEq(saved, 'first', 'הרצת ניקוד נשמרה בהגדרות');

  // ---------- ניקוד פסוקים ----------
  assertEq(await page.evaluate(() => ['autoNikud', 'verseNikud', 'mark_5B0', 'mark_591'].every((k) => k in window.__actions)), true, 'פקודות רצועת הכלים נרשמו');

  // בתוך תהליך הניקוד: Ctrl+↑ על "בראשית"
  await page.evaluate(() => {
    window.__fakeDoc.text = "כמו שכתוב בראשית ברא אלקים, וזהו.";
    window.__fakeDoc.selStart = window.__fakeDoc.selEnd = 0;
  });
  await page.click('[data-tab=settings]');
  await page.click('[data-preset=default]');
  await page.click('[data-tab=nikud]');
  await page.click('#btn-start');
  await page.waitForFunction(() => document.getElementById('original').textContent === 'כמו');
  await page.keyboard.press('Control+ArrowLeft'); // המילה לא במילון: המיקוד בשדה הידני
  await page.waitForFunction(() => document.getElementById('original').textContent === 'שכתוב');
  await page.keyboard.press('Control+ArrowLeft');
  await page.waitForFunction(() => document.getElementById('original').textContent === 'בראשית');
  await page.keyboard.press('Control+ArrowUp');
  await page.waitForFunction(() => document.activeElement.id === 'verse' && document.querySelectorAll('#verse-words span').length === 2, null, { timeout: 15000 });
  await page.keyboard.press(' '); // מילה שלישית
  await page.waitForFunction(() => document.querySelectorAll('#verse-words span').length === 3);
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelectorAll('#verse-results li[role=option]').length > 0, null, { timeout: 15000 });
  assertEq(await page.textContent('#verse-results li .ref'), 'בראשית א, א', 'נמצא בראשית א, א');
  await page.check('#verse-quotes');
  await page.focus('#verse-results');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.getElementById('original').textContent === 'וזהו');
  let t = n(await doc());
  assertEq(t, n('כמו שכתוב "בְּרֵאשִׁית בָּרָא אלקים" (בראשית א, א), וזהו.'), 'הפסוק נוקד, עם מירכאות ומקור, והכינוי נשמר');

  // ביטול מחזיר את המילים, והתהליך ממשיך (בשדה הידני Ctrl+Z מבטל סימן, לכן הכפתור)
  await page.click('#btn-undo');
  await page.waitForFunction(() => document.getElementById('original').textContent === 'בראשית');
  assertEq(await doc(), 'כמו שכתוב בראשית ברא אלקים, וזהו.', 'ביטול הפסוק החזיר את הטקסט');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.getElementById('idle').hidden);

  // בלי תהליך: בחירה של פסוק והקשה על "ניקוד פסוקים"
  await page.evaluate(() => {
    window.__fakeDoc.text = "ונאמר שמע ישראל ה' אלקינו ה' אחד";
    window.__fakeDoc.selStart = 6;
    window.__fakeDoc.selEnd = window.__fakeDoc.text.length;
  });
  await page.uncheck('#verse-quotes').catch(() => {});
  await page.evaluate(() => window.__actions.verseNikud({ completed() {} }));
  await page.waitForFunction(() => document.querySelectorAll('#verse-results li[role=option]').length > 0, null, { timeout: 15000 });
  const refs = await page.$$eval('#verse-results li .ref', (els) => els.map((e) => e.textContent));
  assertEq(refs.includes('דברים ו, ד'), true, 'שמע ישראל נמצא, גם עם כינויים');
  const k = refs.indexOf('דברים ו, ד');
  await page.focus('#verse-results');
  for (let i = 0; i < k; i++) await page.keyboard.press('ArrowDown');
  await page.uncheck('#verse-quotes');
  await page.focus('#verse-results');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.getElementById('idle').hidden);
  t = n(await doc());
  assertEq(t, n("ונאמר שְׁמַע יִשְׂרָאֵל ה' אלקינו ה' אֶחָד (דברים ו, ד)"), 'פסוק מבחירה, עם מקור');

  // ניקוד ידני: כל מילה נעצרת בחלון הידני
  await page.evaluate(() => {
    window.__fakeDoc.text = 'משה דוד';
    window.__fakeDoc.selStart = window.__fakeDoc.selEnd = 0;
  });
  await page.click('#btn-manual');
  await page.waitForFunction(() => document.getElementById('original').textContent === 'משה');
  assertEq(await page.evaluate(() => document.activeElement.id), 'manual-input', 'ניקוד ידני: המיקוד בשדה הידני');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.getElementById('idle').hidden);

  await page.setViewportSize({ width: 340, height: 900 });
  await page.click('[data-tab=nikud]');
  fs.mkdirSync(path.join(root, 'test', 'out'), { recursive: true });
  await page.screenshot({ path: path.join(root, 'test', 'out', 'taskpane.png'), fullPage: true });

  assertEq(errors.length, 0, `אין שגיאות JavaScript ${errors.join(' | ')}`);
  await browser.close();
  server.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
