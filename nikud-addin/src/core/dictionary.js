// מודל המילון: מפתח לא מנוקד, ולכל מפתח רשימה מסודרת של צורות מנוקדות.
// הסדר חשוב: האפשרות הראשונה היא זו שנבחרת ב"הרצת ניקוד".

import { makeKey, normalizeMarks, hasNikud, stripTaamim } from './hebrew.js';
import { tokenize, extractCore } from './analyzer.js';

export class Dictionary {
  constructor() {
    /** @type {Map<string, string[]>} */
    this.map = new Map();
    /** מפתחות ששונו מאז השמירה האחרונה */
    this.dirty = new Set();
  }

  get size() {
    return this.map.size;
  }

  /** מחזיר עותק של רשימת האפשרויות למפתח. */
  get(key) {
    return [...(this.map.get(makeKey(key)) ?? [])];
  }

  has(key) {
    return this.map.has(makeKey(key));
  }

  /**
   * מוסיף צורה למילון. אם לא נותנים מפתח, הוא נגזר מהצורה עצמה.
   * עם מפתח מפורש אפשר לשמור צורה שונה מהמילה המקורית, למשל עכשיו → עַכְשָׁו,
   * או פתיחה של ראשי תיבות.
   * @returns {boolean} האם נוספה צורה חדשה
   */
  add(vocalized, key = null, { allowUnvocalized = false } = {}) {
    const value = normalizeMarks(stripTaamim(vocalized.trim()));
    if (!value) return false;
    if (!allowUnvocalized && !hasNikud(value) && key === null) return false;
    const k = makeKey(key ?? value);
    if (!k) return false;
    const list = this.map.get(k) ?? [];
    if (list.includes(value)) return false;
    list.push(value);
    this.map.set(k, list);
    this.dirty.add(k);
    return true;
  }

  remove(key, vocalized) {
    const k = makeKey(key);
    const list = this.map.get(k);
    if (!list) return false;
    const i = list.indexOf(normalizeMarks(vocalized));
    if (i < 0) return false;
    list.splice(i, 1);
    if (list.length === 0) this.map.delete(k);
    this.dirty.add(k);
    return true;
  }

  /** מזיז צורה ברשימה: מספר חיובי מוריד, שלילי מעלה, 'top' לראש הרשימה. */
  move(key, vocalized, delta) {
    const k = makeKey(key);
    const list = this.map.get(k);
    if (!list) return false;
    const i = list.indexOf(normalizeMarks(vocalized));
    if (i < 0) return false;
    const j = delta === 'top' ? 0 : Math.max(0, Math.min(list.length - 1, i + delta));
    if (i === j) return false;
    const [item] = list.splice(i, 1);
    list.splice(j, 0, item);
    this.dirty.add(k);
    return true;
  }

  /** מוסיף את כל המילים המנוקדות שבטקסט. מחזיר כמה צורות חדשות נוספו. */
  addFromText(text) {
    let added = 0;
    for (const tok of tokenize(text)) {
      const { core } = extractCore(tok.text);
      if (core && hasNikud(core) && this.add(core)) added++;
    }
    return added;
  }

  /** מפתחות שמתחילים במחרוזת החיפוש, ממוינים. */
  searchKeys(prefix, limit = 300) {
    const p = makeKey(prefix);
    const out = [];
    for (const k of this.map.keys()) if (k.startsWith(p)) out.push(k);
    out.sort((a, b) => a.localeCompare(b, 'he'));
    return out.slice(0, limit);
  }

  toJSON() {
    return { format: 'nikud-kal-dictionary', version: 1, entries: Object.fromEntries(this.map) };
  }

  /** טוען גיבוי JSON או קובץ טקסט מנוקד. מחזיר כמה צורות נוספו. */
  importData(data) {
    if (typeof data === 'string') {
      const trimmed = data.trim();
      if (trimmed.startsWith('{')) return this.importData(JSON.parse(trimmed));
      // שורות בצורה "מפתח<TAB>צורה<TAB>צורה", או סתם טקסט מנוקד
      let added = 0;
      for (const line of trimmed.split(/\r?\n/)) {
        const cols = line.split('\t').map((c) => c.trim()).filter(Boolean);
        if (cols.length >= 2) {
          for (const v of cols.slice(1)) if (this.add(v, cols[0], { allowUnvocalized: true })) added++;
        } else if (cols.length === 1) {
          added += this.addFromText(cols[0]);
        }
      }
      return added;
    }
    if (!data || data.format !== 'nikud-kal-dictionary' || typeof data.entries !== 'object') {
      throw new Error('קובץ המילון אינו בפורמט המוכר');
    }
    let added = 0;
    for (const [k, list] of Object.entries(data.entries)) {
      if (!Array.isArray(list)) continue;
      for (const v of list) if (typeof v === 'string' && this.add(v, k, { allowUnvocalized: true })) added++;
    }
    return added;
  }

  /** טעינה מהאחסון: מחליף את התוכן בלי לסמן מפתחות כשונו. */
  loadEntries(entries) {
    this.map = new Map(entries);
    this.dirty.clear();
  }

  takeDirty() {
    const keys = [...this.dirty];
    this.dirty.clear();
    return keys.map((k) => [k, this.map.get(k) ?? null]);
  }
}
