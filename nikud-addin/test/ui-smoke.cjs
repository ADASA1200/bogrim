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
