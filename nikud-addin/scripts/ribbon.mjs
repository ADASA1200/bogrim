// הגדרת הכפתורים ברצועת הכלים. משמשת לבניית הסמלים, המניפסט וקיצורי המקשים.
import { NIKUD, TAAMIM, HOLAM_AFTER_VAV, markId } from '../src/core/marks.js';

export { markId };

export const COMMANDS = [
  { id: 'autoNikud', label: 'ניקוד אוטומטי', tip: 'ניקוד מהסמן והלאה, או של הקטע שנבחר.', icon: { bg: '#2b579a', glyph: 'אָ', badge: '▶' }, key: 'F5' },
  { id: 'singleWord', label: 'מילה בודדת', tip: 'ניקוד או תיקון של המילה שבמקום הסמן.', icon: { bg: '#2b579a', glyph: 'אָ', badge: '1' }, key: 'F6' },
  { id: 'manualNikud', label: 'ניקוד ידני', tip: 'ניקוד ידני מילה אחרי מילה.', icon: { bg: '#2b579a', glyph: 'אָ', badge: '✎' }, key: 'F7' },
  { id: 'verseNikud', label: 'ניקוד פסוקים', tip: 'ניקוד הפסוק שנבחר לפי התנ"ך, עם מקור ומירכאות.', icon: { bg: '#2e7d32', glyph: 'תנ״ך', small: true }, key: 'F8' },
];

export const TOOLS = [
  { id: 'removeNikud', label: 'מחק ניקוד', tip: 'הסרת הניקוד מהטקסט שנבחר.', icon: { bg: '#b42318', glyph: 'אָ', badge: '✕' }, key: 'Ctrl+Shift+Delete' },
  { id: 'addToDictionary', label: 'הוסף מילים למילון', tip: 'כל המילים המנוקדות שבבחירה נכנסות למילון.', icon: { bg: '#6a3d9a', glyph: 'מ', badge: '+' }, key: 'Ctrl+Shift+Insert' },
  { id: 'openDictionary', label: 'מילון', tip: 'צפייה ועריכה של המילון.', icon: { bg: '#6a3d9a', glyph: 'מ' }, key: 'Ctrl+Shift+D' },
  { id: 'openSettings', label: 'הגדרות', tip: 'הגדרות הניקוד.', icon: { bg: '#555b63', glyph: '⚙' }, key: 'Ctrl+Shift+S' },
];

const vowelMarks = ['ְ', 'ֱ', 'ֲ', 'ֳ', 'ִ', 'ֵ', 'ֶ', 'ַ', 'ָ', 'ׇ', 'ֹ', 'ֻ'];
const markEntry = (m) => ({ id: markId(m.mark), label: m.name, tip: `הוספת ${m.name} אחרי האות שלפני הסמן.`, mark: m.mark, standalone: !!m.standalone });

export const VOWELS = vowelMarks.map((v) => markEntry(NIKUD.find((n) => n.mark === v)));
export const SIGNS = [
  ...NIKUD.filter((n) => !vowelMarks.includes(n.mark)).map(markEntry),
  markEntry(HOLAM_AFTER_VAV),
];
export const TAAMIM_ITEMS = TAAMIM.map(markEntry);

export const ALL_MARKS = [...VOWELS, ...SIGNS, ...TAAMIM_ITEMS].filter(
  (m, i, a) => a.findIndex((x) => x.id === m.id) === i,
);
