// כלי עזר בסיסיים לטקסט עברי: אותיות, סימני ניקוד וטעמים.
// הקובץ אינו תלוי ב-Office, ולכן אפשר לבדוק אותו ב-Node.

export const MARKS = Object.freeze({
  SHEVA: 'ְ',
  HATAF_SEGOL: 'ֱ',
  HATAF_PATAH: 'ֲ',
  HATAF_QAMATS: 'ֳ',
  HIRIQ: 'ִ',
  TSERE: 'ֵ',
  SEGOL: 'ֶ',
  PATAH: 'ַ',
  QAMATS: 'ָ',
  HOLAM: 'ֹ',
  HOLAM_HASER_VAV: 'ֺ',
  QUBUTS: 'ֻ',
  DAGESH: 'ּ',
  METEG: 'ֽ',
  RAFE: 'ֿ',
  SHIN_DOT: 'ׁ',
  SIN_DOT: 'ׂ',
  QAMATS_QATAN: 'ׇ',
});

export const MAQAF = '־';
export const GERESH = '׳';
export const GERSHAYIM = '״';
export const ZWJ = '‍';

export const isLetter = (ch) => ch >= 'א' && ch <= 'ת';
export const isTaam = (ch) => ch >= '֑' && ch <= '֯';
export const isPoint = (ch) =>
  (ch >= 'ְ' && ch <= 'ֽ') ||
  ch === 'ֿ' || ch === 'ׁ' || ch === 'ׂ' || ch === 'ׇ';
/** כל סימן מצטרף עברי: ניקוד, טעמים ונקודות עליונה/תחתונה. */
export const isMark = (ch) => isTaam(ch) || isPoint(ch) || ch === 'ׄ' || ch === 'ׅ';
export const isVowel = (ch) => (ch >= 'ְ' && ch <= 'ֻ') || ch === 'ׇ';
export const isHataf = (ch) => ch === MARKS.HATAF_SEGOL || ch === MARKS.HATAF_PATAH || ch === MARKS.HATAF_QAMATS;

export const GUTTURALS = 'אהחע';
export const BGDKPT = 'בגדכפת';

/** מסיר את כל סימני הניקוד והטעמים. אפשר להשאיר טעמים בלבד. */
export function stripMarks(s, { keepTaamim = false } = {}) {
  let out = '';
  for (const ch of s) {
    if (isMark(ch) && !(keepTaamim && isTaam(ch))) continue;
    out += ch;
  }
  return out;
}

/** מסיר טעמים בלבד ומשאיר את הניקוד. */
export function stripTaamim(s) {
  let out = '';
  for (const ch of s) if (!isTaam(ch)) out += ch;
  return out;
}

export const hasNikud = (s) => [...s].some(isPoint);
export const hasHebrewLetter = (s) => [...s].some(isLetter);
export const letterCount = (s) => [...s].filter(isLetter).length;

/** מפרק מחרוזת לצירופים: תו בסיס יחד עם הסימנים שאחריו. */
export function clusters(s) {
  const out = [];
  for (const ch of s) {
    if ((isMark(ch) || ch === ZWJ) && out.length) out[out.length - 1].marks.push(ch);
    else out.push({ base: ch, marks: [] });
  }
  return out;
}

export const joinClusters = (cl) => cl.map((c) => c.base + c.marks.join('')).join('');

function markRank(c) {
  if (c === MARKS.SHIN_DOT || c === MARKS.SIN_DOT) return 0;
  if (c === MARKS.DAGESH) return 1;
  if (c === MARKS.RAFE) return 2;
  if (isVowel(c)) return 3;
  if (c === MARKS.METEG) return 4;
  if (c === ZWJ) return 5;
  return 6; // טעמים וסימנים אחרים
}

/**
 * מסדר את הסימנים שעל כל אות בסדר קבוע: נקודת שין, דגש, רפה, תנועה, מתג, טעמים.
 * בלי הסדר הזה אותה מילה יכולה להופיע במילון בכמה צורות.
 */
export function normalizeMarks(s) {
  return joinClusters(
    clusters(s).map((c) => ({
      base: c.base,
      marks: c.marks
        .map((m, i) => ({ m, i }))
        .sort((a, b) => markRank(a.m) - markRank(b.m) || a.i - b.i)
        .map((x) => x.m),
    })),
  );
}

/** מאחד גרש וגרשיים עבריים עם המקבילים שלהם במקלדת. */
export const normalizeQuotes = (s) =>
  s.replace(/[״“”„]/g, '"').replace(/[׳‘’]/g, "'");

/** המפתח של מילה במילון: האותיות בלי ניקוד, עם מירכאות אחידות. */
export const makeKey = (s) => normalizeQuotes(stripMarks(s)).replace(new RegExp(ZWJ, 'g'), '');

/** האם שתי מחרוזות מנוקדות זהות, בלי קשר לסדר הסימנים. */
export const sameVocalization = (a, b) => normalizeMarks(a) === normalizeMarks(b);
