import { test } from 'node:test';
import assert from 'node:assert/strict';

import { stripMarks, hasNikud, normalizeMarks, makeKey, MARKS } from '../src/core/hebrew.js';
import { Dictionary } from '../src/core/dictionary.js';
import {
  tokenize, extractCore, isAbbreviation, vocalizePrefix, isValidPrefixSequence,
  prefixedCandidates, defectiveVariants, suggest, decide, updateBrackets, newBracketState,
} from '../src/core/analyzer.js';
import { DEFAULT_SETTINGS, RUN_PRESET, sanitizeSettings } from '../src/core/settings.js';

const S = DEFAULT_SETTINGS;

test('הסרת ניקוד ובדיקת ניקוד', () => {
  assert.equal(stripMarks('מֹשֶׁה'), 'משה');
  assert.equal(stripMarks('בְּרֵאשִׁ֖ית'), 'בראשית');
  assert.equal(stripMarks('בְּרֵאשִׁ֖ית', { keepTaamim: true }), 'בראש\u0596ית');
  assert.ok(hasNikud('מֹשֶׁה'));
  assert.ok(!hasNikud('משה'));
});

test('סדר הסימנים אחיד', () => {
  // שׁ עם קמץ ודגש, בשני סדרים שונים
  const a = 'ש' + MARKS.QAMATS + MARKS.DAGESH + MARKS.SHIN_DOT;
  const b = 'ש' + MARKS.SHIN_DOT + MARKS.DAGESH + MARKS.QAMATS;
  assert.equal(normalizeMarks(a), normalizeMarks(b));
  assert.equal(normalizeMarks(a), b);
});

test('מפתח מאחד גרשיים', () => {
  assert.equal(makeKey('ר״ת'), 'ר"ת');
  assert.equal(makeKey('א׳'), "א'");
});

test('פירוק לטוקנים לפי רווח ומקף', () => {
  const t = tokenize('אף־על־גב בית-ספר  שלום').map((x) => x.text);
  assert.deepEqual(t, ['אף', 'על', 'גב', 'בית', 'ספר', 'שלום']);
});

test('הפרדת גרעין המילה', () => {
  assert.deepEqual(extractCore('(משה),'), { lead: '(', core: 'משה', trail: '),' });
  assert.deepEqual(extractCore('@22קודים'), { lead: '@22', core: 'קודים', trail: '' });
  assert.deepEqual(extractCore("'בראשית'"), { lead: "'", core: 'בראשית', trail: "'" });
  assert.deepEqual(extractCore('ר"ת.'), { lead: '', core: 'ר"ת', trail: '.' });
  assert.deepEqual(extractCore("א'"), { lead: '', core: "א'", trail: '' });
  assert.equal(extractCore('123').core, '');
});

test('זיהוי ראשי תיבות', () => {
  assert.ok(isAbbreviation('ר"ת'));
  assert.ok(isAbbreviation("א'"));
  assert.ok(!isAbbreviation('משה'));
});

test('רצפי אותיות שימוש', () => {
  assert.ok(isValidPrefixSequence('ו'));
  assert.ok(isValidPrefixSequence('וכש'));
  assert.ok(isValidPrefixSequence('מה'));
  assert.ok(!isValidPrefixSequence('לו'));
  assert.ok(!isValidPrefixSequence('בה'));
  assert.ok(!isValidPrefixSequence('הל'));
});

test('ניקוד אותיות שימוש', () => {
  const n = normalizeMarks;
  assert.deepEqual(vocalizePrefix('ל', 'נְתַנְאֵל'), [n('לִנְתַנְאֵל'), n('לַנְּתַנְאֵל')]);
  assert.equal(vocalizePrefix('ל', 'מַדָּף')[0], n('לְמַדָּף'));
  assert.equal(vocalizePrefix('ל', 'מַדָּף')[1], n('לַמַּדָּף'));
  assert.equal(vocalizePrefix('ה', 'אָרֶץ')[0], n('הָאָרֶץ'));
  assert.equal(vocalizePrefix('ה', 'מֶּלֶךְ')[0], n('הַמֶּלֶךְ'));
  assert.equal(vocalizePrefix('ב', 'יְרוּשָׁלַיִם')[0], n('בִּירוּשָׁלַיִם'));
  assert.equal(vocalizePrefix('ו', 'בַּיִת')[0], n('וּבַיִת'));
  assert.equal(vocalizePrefix('ו', 'דָּוִד')[0], n('וְדָוִד'));
  assert.equal(vocalizePrefix('ו', 'אֲנִי')[0], n('וַאֲנִי'));
  assert.equal(vocalizePrefix('מ', 'בַּיִת')[0], n('מִבַּיִת'));
  assert.equal(vocalizePrefix('מ', 'עִיר')[0], n('מֵעִיר'));
  assert.equal(vocalizePrefix('ש', 'לּוֹ')[0], n('שֶׁלּוֹ'));
});

test('כתיב חסר', () => {
  assert.deepEqual(defectiveVariants('לימד'), ['למד']);
  assert.ok(defectiveVariants('מקווה').includes('מקוה'));
});

function sampleDict() {
  const d = new Dictionary();
  d.add('מֹשֶׁה');
  d.add('מֹשֶׁה');      // כפילות אינה נוספת
  d.add('נְתַנְאֵל');
  d.add('לִמֵּד');
  d.add('לָמַד');
  d.add('רַבּוֹתֵינוּ', 'רז"ל');
  return d;
}

test('המילון: הוספה, סדר ומחיקה', () => {
  const d = sampleDict();
  assert.equal(d.get('משה').length, 1);
  assert.deepEqual(d.get('למד'), [normalizeMarks('לִמֵּד'), normalizeMarks('לָמַד')]);
  assert.ok(d.move('למד', 'לָמַד', 'top'));
  assert.equal(d.get('למד')[0], normalizeMarks('לָמַד'));
  assert.ok(d.remove('למד', 'לָמַד'));
  assert.equal(d.get('למד').length, 1);
  assert.ok(!d.add('משה'), 'מילה לא מנוקדת לא נוספת בלי אישור מפורש');
  assert.ok(d.add('משה', null, { allowUnvocalized: true }));
});

test('המילון: הוספה מטקסט, גיבוי ושחזור', () => {
  const d = new Dictionary();
  const added = d.addFromText('וַיְדַבֵּר מֹשֶׁה אֶל־הָעָם, "שָׁלוֹם" לכם');
  assert.equal(added, 5);
  const copy = new Dictionary();
  copy.importData(JSON.parse(JSON.stringify(d.toJSON())));
  assert.deepEqual([...copy.map], [...d.map]);
  const fromTsv = new Dictionary();
  assert.equal(fromTsv.importData('עכשיו\tעַכְשָׁו'), 1);
  assert.equal(fromTsv.get('עכשיו')[0], normalizeMarks('עַכְשָׁו'));
});

test('הצעות: מקור, אותיות שימוש וכתיב חסר', () => {
  const d = sampleDict();
  assert.deepEqual(suggest('משה', d, S).map((x) => x.mark), ['']);
  const pre = suggest('לנתנאל', d, S);
  assert.ok(pre.length >= 1 && pre.every((x) => x.mark === '+'));
  const def = suggest('לימד', d, S);
  assert.ok(def.length >= 1 && def.every((x) => x.mark === '–'));
  assert.deepEqual(suggest('לנתנאל', d, { ...S, addPrefixes: false }), []);
  assert.equal(suggest('רז״ל', d, S)[0].text, normalizeMarks('רַבּוֹתֵינוּ'));
});

test('החלטה: ברירת מחדל מול הרצת ניקוד', () => {
  const d = sampleDict();
  const always = new Map();
  const base = { always, insideBrackets: false };
  const run = (core, settings) => decide({ ...base, core, suggestions: suggest(core, d, settings), settings });

  assert.equal(run('משה', S).action, 'apply');          // אפשרות יחידה
  assert.equal(run('משה', { ...S, askSingle: true }).action, 'ask');
  assert.equal(run('למד', S).action, 'ask');
  assert.equal(run('למד', RUN_PRESET).action, 'apply');
  assert.equal(run('שולחן', S).action, 'manual');
  assert.equal(run('שולחן', RUN_PRESET).action, 'skip');
  assert.equal(run('לימד', RUN_PRESET).action, 'skip'); // כתיב חסר בהרצה: אל תשנה
  assert.equal(run('לימד', { ...RUN_PRESET, spellingMode: 'apply' }).action, 'apply');
  assert.equal(run('רז"ל', S).action, 'ask');            // פתיחת ר"ת: שאל
  assert.equal(run('ב', S).action, 'skip');              // אות בודדת
  assert.equal(run('מֹשֶׁה', RUN_PRESET).action, 'skip'); // מילה מנוקדת
  assert.equal(run('מֹשֶׁה', S).action, 'apply');

  always.set('למד', 'לָמַד');
  assert.deepEqual(run('למד', S), { action: 'apply', text: 'לָמַד' });
  assert.equal(decide({ ...base, core: 'משה', suggestions: [], settings: S, insideBrackets: true }).action, 'skip');
});

test('סוגריים', () => {
  const st = newBracketState();
  updateBrackets(st, '([');
  assert.deepEqual(st, { round: 1, square: 1, curly: 0 });
  updateBrackets(st, '])');
  assert.deepEqual(st, { round: 0, square: 0, curly: 0 });
});

test('תיקון הגדרות', () => {
  const s = sanitizeSettings({ whenMultiple: 'xyz', autosaveEvery: 5, skipRound: 'yes' });
  assert.equal(s.whenMultiple, 'ask');
  assert.equal(s.autosaveEvery, 100);
  assert.equal(s.skipRound, false);
});
