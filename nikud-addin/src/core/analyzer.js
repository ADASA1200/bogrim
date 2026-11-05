// פירוק טקסט למילים, הפקת הצעות ניקוד מהמילון, וקבלת החלטה לכל מילה.

import {
  MARKS, MAQAF, GERESH, GERSHAYIM,
  isLetter, isMark, isVowel, isHataf, clusters, joinClusters,
  normalizeMarks, makeKey, hasNikud, letterCount, GUTTURALS, BGDKPT,
} from './hebrew.js';

// ---------- פירוק לטוקנים ----------

const SEPARATORS = /[\s ־\-‐‑–]+/u;

/** מפצל לטוקנים לפי רווחים ומקפים, עליון או אמצעי. */
export function tokenize(text) {
  const out = [];
  const re = new RegExp(SEPARATORS.source, 'gu');
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), start: last });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), start: last });
  return out;
}

const QUOTE_CHARS = `"'${GERESH}${GERSHAYIM}“”‘’`;
const isQuote = (ch) => QUOTE_CHARS.includes(ch);

/**
 * מפריד טוקן לגרעין עברי ולמה שמסביבו: סוגריים, פיסוק, ספרות.
 * גרשיים באמצע המילה נשארים בגרעין (ר"ת), וגרש בסוף נשאר רק כשאין לפני המילה גרש פותח.
 * @returns {{lead: string, core: string, trail: string}}
 */
export function extractCore(token) {
  const chars = [...token];
  let first = -1;
  let last = -1;
  chars.forEach((ch, i) => {
    if (isLetter(ch)) {
      if (first < 0) first = i;
      last = i;
    }
  });
  if (first < 0) return { lead: token, core: '', trail: '' };
  let end = last + 1;
  while (end < chars.length && (isMark(chars[end]) || chars[end] === '‍')) end++;
  const lead = chars.slice(0, first).join('');
  const leadHasQuote = [...lead].some(isQuote);
  if (end < chars.length && isQuote(chars[end]) && !leadHasQuote) end++;
  return { lead, core: chars.slice(first, end).join(''), trail: chars.slice(end).join('') };
}

/** האם הגרעין הוא ראשי תיבות או קיצור: גרשיים בפנים, או גרש בסוף. */
export function isAbbreviation(core) {
  const chars = [...core];
  return chars.some((ch, i) => isQuote(ch) && i < chars.length - 1) || isQuote(chars[chars.length - 1] ?? '');
}

/** מעדכן את עומק הסוגריים לפי הטקסט. */
export function updateBrackets(state, text) {
  for (const ch of text) {
    if (ch === '(') state.round++;
    else if (ch === ')') state.round = Math.max(0, state.round - 1);
    else if (ch === '[') state.square++;
    else if (ch === ']') state.square = Math.max(0, state.square - 1);
    else if (ch === '{') state.curly++;
    else if (ch === '}') state.curly = Math.max(0, state.curly - 1);
  }
  return state;
}

export const newBracketState = () => ({ round: 0, square: 0, curly: 0 });

export function insideSkippedBrackets(state, settings) {
  return (settings.skipRound && state.round > 0) ||
    (settings.skipSquare && state.square > 0) ||
    (settings.skipCurly && state.curly > 0);
}

// ---------- אותיות השימוש (מ"ש וכל"ב, ה, ו) ----------

const PREFIX_LETTERS = 'ומשהכלב';

function firstVowelOf(cl) {
  return cl.marks.find(isVowel) ?? null;
}

function setVowel(cl, vowel) {
  const marks = cl.marks.filter((m) => !isVowel(m));
  if (vowel) marks.push(vowel);
  return { base: cl.base, marks };
}

function withDagesh(cl) {
  if (GUTTURALS.includes(cl.base) || cl.base === 'ר' || cl.marks.includes(MARKS.DAGESH)) return cl;
  return { base: cl.base, marks: [MARKS.DAGESH, ...cl.marks] };
}

function withoutDageshKal(cl) {
  if (!BGDKPT.includes(cl.base)) return cl;
  return { base: cl.base, marks: cl.marks.filter((m) => m !== MARKS.DAGESH) };
}

const HATAF_TO_SHORT = {
  [MARKS.HATAF_PATAH]: MARKS.PATAH,
  [MARKS.HATAF_SEGOL]: MARKS.SEGOL,
  [MARKS.HATAF_QAMATS]: MARKS.QAMATS,
};

const join = (prefix, cls) => normalizeMarks(prefix + joinClusters(cls));

/** ה הידיעה, ובאותיות בכ"ל גם כשה' נבלעת: הַמֶּלֶךְ, לַמֶּלֶךְ. */
function definite(prefixLetter, cls) {
  const [head, ...rest] = cls;
  const base = prefixLetter + ('בכ'.includes(prefixLetter) ? MARKS.DAGESH : '');
  if ('אער'.includes(head.base)) return join(base + MARKS.QAMATS, cls);
  if ('הח'.includes(head.base)) return join(base + MARKS.PATAH, cls);
  return join(base + MARKS.PATAH, [withDagesh(head), ...rest]);
}

/** אות שימוש עם שווא: לְ, בְּ, כְּ. לפני שווא היא מקבלת חיריק, ולפני חטף את התנועה הקצרה המתאימה. */
function shevaForm(prefixLetter, cls) {
  const [head, ...rest] = cls;
  const base = prefixLetter + ('בכ'.includes(prefixLetter) ? MARKS.DAGESH : '');
  const v = firstVowelOf(head);
  if (v === MARKS.SHEVA) {
    if (head.base === 'י') return join(base + MARKS.HIRIQ, [setVowel(head, null), ...rest]);
    return join(base + MARKS.HIRIQ, [withoutDageshKal(head), ...rest]);
  }
  if (v && isHataf(v)) return join(base + HATAF_TO_SHORT[v], cls);
  return join(base + MARKS.SHEVA, [withoutDageshKal(head), ...rest]);
}

/** מחזיר את הצורות האפשריות של אות שימוש אחת לפני גזע מנוקד. */
export function vocalizePrefix(p, stemVoc) {
  const cls = clusters(stemVoc);
  if (!cls.length) return [];
  const [head, ...rest] = cls;
  const v = firstVowelOf(head);
  switch (p) {
    case 'ה':
      return [definite('ה', cls)];
    case 'ב':
    case 'כ':
    case 'ל':
      return [shevaForm(p, cls), definite(p, cls)];
    case 'מ':
      if (GUTTURALS.includes(head.base) || head.base === 'ר') return [join('מ' + MARKS.TSERE, cls)];
      return [join('מ' + MARKS.HIRIQ, [withDagesh(head), ...rest])];
    case 'ש':
      if (GUTTURALS.includes(head.base) || head.base === 'ר') return [join('ש' + MARKS.SHIN_DOT + MARKS.SEGOL, cls)];
      return [join('ש' + MARKS.SHIN_DOT + MARKS.SEGOL, [withDagesh(head), ...rest])];
    case 'ו':
      if (v === MARKS.SHEVA && head.base === 'י') return [join('ו' + MARKS.HIRIQ, [setVowel(head, null), ...rest])];
      if (v === MARKS.SHEVA || 'בומפ'.includes(head.base)) {
        return [join('ו' + MARKS.DAGESH, [withoutDageshKal(head), ...rest])];
      }
      if (v && isHataf(v)) return [join('ו' + HATAF_TO_SHORT[v], cls)];
      return [join('ו' + MARKS.SHEVA, [withoutDageshKal(head), ...rest])];
    default:
      return [];
  }
}

/** האם רצף האותיות יכול להיות צירוף של אותיות שימוש. */
export function isValidPrefixSequence(seq) {
  const chars = [...seq];
  if (!chars.length || chars.length > 3) return false;
  for (let i = 0; i < chars.length; i++) {
    const c = chars[i];
    if (!PREFIX_LETTERS.includes(c)) return false;
    if (c === 'ו' && i !== 0) return false;
    if (c === 'ה' && i !== chars.length - 1) return false;
    if (c === 'ה' && i > 0 && 'בכל'.includes(chars[i - 1])) return false;
  }
  return true;
}

/** הצעות שנבנות מגזע שנמצא במילון ומאותיות שימוש לפניו. */
export function prefixedCandidates(key, dict, limit = 12) {
  const out = [];
  const letters = [...key];
  for (let n = 1; n <= 3 && letters.length - n >= 2; n++) {
    const pre = letters.slice(0, n).join('');
    if (!isValidPrefixSequence(pre)) continue;
    const stem = letters.slice(n).join('');
    for (const stemVoc of dict.get(stem)) {
      if (!hasNikud(stemVoc)) continue;
      let forms = [stemVoc];
      for (const p of [...pre].reverse()) forms = forms.flatMap((f) => vocalizePrefix(p, f));
      for (const f of forms) {
        if (!out.includes(f)) out.push(f);
        if (out.length >= limit) return out;
      }
    }
  }
  return out;
}

// ---------- כתיב מלא לכתיב חסר ----------

/** גרסאות בכתיב חסר: הסרת י' או ו' אחת מאמצע המילה, וצמצום יי/וו. */
export function defectiveVariants(key) {
  const letters = [...key];
  const out = new Set();
  for (let i = 1; i < letters.length - 1; i++) {
    if (letters[i] === 'י' || letters[i] === 'ו') {
      out.add([...letters.slice(0, i), ...letters.slice(i + 1)].join(''));
    }
  }
  out.delete(key);
  return [...out].filter((v) => letterCount(v) >= 2);
}

// ---------- הצעות ----------

/**
 * @typedef {{text: string, mark: ''|'+'|'–', original: boolean}} Suggestion
 * original: הצורה קיימת במילון תחת המפתח של המילה, ולכן אפשר להזיז או למחוק אותה.
 */

/** @returns {Suggestion[]} */
export function suggest(core, dict, settings) {
  const key = makeKey(core);
  const seen = new Set();
  const out = [];
  const push = (text, mark, original) => {
    const t = normalizeMarks(text);
    if (seen.has(t)) return;
    seen.add(t);
    out.push({ text: t, mark, original });
  };

  for (const v of dict.get(key)) push(v, '', true);

  if (settings.addPrefixes && (out.length === 0 || settings.prefixAlways)) {
    for (const v of prefixedCandidates(key, dict)) push(v, '+', false);
  }

  if (out.length === 0) {
    for (const variant of defectiveVariants(key)) {
      for (const v of dict.get(variant)) push(v, '–', false);
    }
  }
  return out;
}

// ---------- החלטה לכל מילה ----------

/**
 * מחליט מה לעשות במילה לפני שמציגים אותה למשתמש.
 * @returns {{action: 'skip'} | {action: 'apply', text: string} | {action: 'ask'} | {action: 'manual'}}
 */
export function decide({ core, suggestions, settings, always, insideBrackets, force = false }) {
  const key = makeKey(core);
  const abbr = isAbbreviation(core);

  if (!force) {
    if (insideBrackets) return { action: 'skip' };
    if (settings.skipVocalized && hasNikud(core)) return { action: 'skip' };
    if (settings.skipSingleLetters && letterCount(core) === 1 && !abbr) return { action: 'skip' };
    if (settings.skipAbbreviations && abbr) return { action: 'skip' };
  }

  if (always.has(key)) return { action: 'apply', text: always.get(key) };

  if (suggestions.length === 0) {
    return settings.whenNone === 'next' ? { action: 'skip' } : { action: 'manual' };
  }

  const auto = suggestions.length === 1 ? !settings.askSingle : settings.whenMultiple === 'first';
  if (!auto) return { action: 'ask' };

  const first = suggestions[0];
  // בהרצה אוטומטית: פתיחת ר"ת ושינוי כתיב תלויים בהגדרה נפרדת
  const gate = (mode) =>
    mode === 'apply' ? { action: 'apply', text: first.text } :
    mode === 'skip' ? { action: 'skip' } : { action: 'ask' };
  if (abbr && makeKey(first.text) !== key) return gate(settings.abbreviationMode);
  if (first.mark === '–') return gate(settings.spellingMode);
  return { action: 'apply', text: first.text };
}
