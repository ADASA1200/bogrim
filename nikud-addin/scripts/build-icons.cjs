// מצייר את סמלי רצועת הכלים ב-Chromium (כדי שהניקוד ימוקם נכון) ושומר ל-assets/ribbon.
// הרצה: node scripts/build-icons.cjs   (דורש Playwright)
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const { COMMANDS, TOOLS, ALL_MARKS } = await import('./ribbon.mjs');
  const out = path.join(__dirname, '..', 'assets', 'ribbon');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(`<html><body style="margin:0;background:transparent"><div id="i"></div></body></html>`);
  const font = `"FreeSerif","DejaVu Serif","DejaVu Sans",serif`;

  async function render(file, size, html) {
    await page.evaluate(({ html, size }) => {
      const el = document.getElementById('i');
      el.style.cssText = `width:${size}px;height:${size}px;position:relative;`;
      el.innerHTML = html;
    }, { html, size });
    await page.locator('#i').screenshot({ path: path.join(out, file), omitBackground: true });
  }

  const actionHtml = (icon, s) => {
    const r = Math.round(s * 0.18);
    const fs = icon.small ? s * 0.38 : s * 0.72;
    const badge = icon.badge
      ? `<div style="position:absolute;left:${-s * 0.02}px;bottom:${-s * 0.02}px;width:${s * 0.46}px;height:${s * 0.46}px;border-radius:50%;background:#f2a33a;color:#1b1b1b;font:700 ${s * 0.32}px 'DejaVu Sans',sans-serif;display:flex;align-items:center;justify-content:center;border:${Math.max(1, s * 0.03)}px solid #fff;box-sizing:border-box">${icon.badge}</div>`
      : '';
    return `<div style="position:absolute;inset:${s * 0.02}px;border-radius:${r}px;background:${icon.bg};color:#fff;display:flex;align-items:center;justify-content:center;font:700 ${fs}px/1 ${font};padding-bottom:${s * 0.08}px;box-sizing:border-box" dir="rtl">${icon.glyph}</div>${badge}`;
  };

  const markHtml = (m, s) => {
    const glyph = m.standalone ? m.mark : (m.mark.startsWith('‍') ? 'ו' : '◌') + m.mark;
    return `<div style="position:absolute;inset:${s * 0.03}px;border-radius:${s * 0.14}px;background:#fff;border:${Math.max(1, s * 0.04)}px solid #8a939c;color:#111;display:flex;align-items:center;justify-content:center;font:${s * 0.78}px/1 ${font};box-sizing:border-box" dir="rtl">${glyph}</div>`;
  };

  for (const s of [16, 32, 80]) {
    for (const c of [...COMMANDS, ...TOOLS]) await render(`${c.id}-${s}.png`, s, actionHtml(c.icon, s));
    for (const m of ALL_MARKS) await render(`${m.id}-${s}.png`, s, markHtml(m, s));
  }
  await browser.close();
  console.log(`icons: ${fs.readdirSync(out).length} files`);
})();
