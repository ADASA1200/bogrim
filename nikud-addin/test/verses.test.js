import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { skeleton, gematria, splitVerse, VerseIndex } from '../src/core/verses.js';
import { normalizeMarks } from '../src/core/hebrew.js';

const data = JSON.parse(readFileSync(new URL('../data/tanach.json', import.meta.url), 'utf8'));
const idx = new VerseIndex(data);
const n = normalizeMarks;

test('גימטריה', () => {
  assert.equal(gematria(1), 'א');
  assert.equal(gematria(15), 'טו');
  assert.equal(gematria(16), 'טז');
  assert.equal(gematria(119), 'קיט');
  assert.equal(gematria(150), 'קנ');
});

test('שלד: כתיב מלא וחסר, סופיות ושמות', () => {
  assert.equal(skeleton('מצוות').skel, skeleton('מִצְוֺת').skel);
  assert.equal(skeleton('אלקים').skel, skeleton('אֱלֹהִים').skel);
  assert.ok(skeleton('אלקים').substitute);
  assert.ok(!skeleton('אֱלֹהִים').substitute);
  assert.equal(skeleton("ה'").skel, skeleton('יְהֹוָה').skel);
  assert.equal(skeleton("וה'").skel, skeleton('וַיהֹוָה').skel);
  assert.equal(skeleton('יי').skel, '#');
});

test('פירוק פסוק עם מקף', () => {
  assert.deepEqual(splitVerse('עַל־פְּנֵי הַמָּיִם'), [
    { text: 'עַל', sep: '־' }, { text: 'פְּנֵי', sep: ' ' }, { text: 'הַמָּיִם', sep: '' },
  ]);
});

test('האינדקס כולל את כל התנ"ך', () => {
  assert.equal(idx.size, 23206);
  assert.equal(idx.refText(0), 'בראשית א, א');
});

test('חיפוש בכתיב מלא מוצא את הפסוק', () => {
  const words = ['בראשית', 'ברא', 'אלוקים'];
  const res = idx.search(words);
  assert.equal(idx.refText(res[0].id), 'בראשית א, א');
  // הכינוי "אלוקים" נשאר כמו שנכתב
  assert.equal(idx.render(res[0], { userWords: words }), n('בְּרֵאשִׁית בָּרָא') + ' אלוקים');
});

test('שמע ישראל, עם ה\'', () => {
  const words = ['שמע', 'ישראל', "ה'", 'אלקינו'];
  const res = idx.search(words);
  assert.ok(res.some((r) => idx.refText(r.id) === 'דברים ו, ד'));
  const m = res.find((r) => idx.refText(r.id) === 'דברים ו, ד');
  assert.equal(idx.render(m, { userWords: words }), n('שְׁמַע יִשְׂרָאֵל') + " ה' אלקינו");
  const full = idx.render(m, { full: true, userWords: words });
  assert.ok(full.endsWith(n('אֶחָד')), full);
});

test('מקף נשמר, טעמים רק לפי בקשה', () => {
  const res = idx.search(['על', 'פני', 'המים']);
  const m = res.find((r) => idx.refText(r.id) === 'בראשית א, ב');
  assert.ok(m);
  assert.equal(idx.render(m), n('עַל־פְּנֵי הַמָּיִם'));
  assert.notEqual(idx.render(m, { taamim: true }), idx.render(m));
  assert.equal(idx.render(m, { nikud: false, userWords: ['על', 'פני', 'המים'] }), 'על־פני המים');
});

test('מילה שלא בתנ"ך: אין תוצאות', () => {
  assert.deepEqual(idx.search(['מחשב', 'נייד']), []);
});
