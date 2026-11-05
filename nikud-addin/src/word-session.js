/* global Word */
// החיבור למסמך Word: איתור המילים, החלפתן, ביטול ושמירה.
// כל שאר הלוגיקה נמצאת ב-core ואינה תלויה ב-Office.

import { tokenize, extractCore, updateBrackets, newBracketState } from './core/analyzer.js';
import { stripMarks, hasNikud, clusters, isLetter, makeKey } from './core/hebrew.js';

const WORD_DELIMITERS = [' ', '\t', ' ', '\u000B'];

function countOccurrencesBefore(haystack, needle, endIndex) {
  let n = 0;
  let i = haystack.indexOf(needle);
  while (i >= 0 && i < endIndex) {
    n++;
    i = haystack.indexOf(needle, i + needle.length);
  }
  return n;
}

/**
 * @typedef {object} WordItem
 * @property {string} text      הגרעין כפי שהוא כעת במסמך
 * @property {string} key       המפתח במילון, לפי הטקסט המקורי
 * @property {string} lead      מה שלפני הגרעין באותו טוקן
 * @property {string} trail     מה שאחריו
 * @property {{round:number,square:number,curly:number}} brackets
 * @property {Word.Range|null} range
 */

export class WordSession {
  constructor() {
    this.ctx = null;
    this.paragraphs = [];
    this.nextParagraph = 0;
    this.scope = null;
    /** @type {WordItem[]} */
    this.items = [];
    this.undoStack = [];
    this.brackets = newBracketState();
    this.singleWord = false;
  }

  /**
   * פותח הקשר ארוך-טווח מול המסמך.
   * בלי בחירה: מהסמן עד סוף המסמך. עם בחירה: רק הטקסט שנבחר.
   * במצב מילה בודדת: המילה שבה עומד הסמן.
   */
  async open({ singleWord = false } = {}) {
    this.singleWord = singleWord;
    const ctx = (this.ctx = new Word.RequestContext());
    const sel = ctx.document.getSelection();
    sel.load('isEmpty');
    await ctx.sync();

    if (singleWord) {
      await this.#openSingleWord(sel);
      return;
    }

    this.scope = sel.isEmpty ? sel.getRange('Start').expandTo(ctx.document.body.getRange('End')) : sel;
    ctx.trackedObjects.add(this.scope);
    const paras = this.scope.paragraphs;
    paras.load('items');
    await ctx.sync();
    this.paragraphs = paras.items;
    for (const p of this.paragraphs) ctx.trackedObjects.add(p);
  }

  async #openSingleWord(sel) {
    const ctx = this.ctx;
    const para = sel.paragraphs.getFirst();
    const trs = para.getRange('Whole').getTextRanges(WORD_DELIMITERS, true);
    trs.load('items/text');
    await ctx.sync();
    const rels = trs.items.map((tr) => tr.compareLocationWith(sel));
    await ctx.sync();
    let target = trs.items.find((_, i) => ['Contains', 'InsideStart', 'InsideEnd', 'Equal', 'Inside'].includes(rels[i].value));
    if (!target) target = trs.items.find((_, i) => rels[i].value === 'AdjacentBefore');
    if (!target) target = trs.items.find((_, i) => rels[i].value === 'AdjacentAfter');
    if (!target) return;
    await this.#collect([target]);
  }

  /** טוען את הפסקה הבאה. מחזיר false כשאין עוד. */
  async loadMore() {
    if (this.singleWord) return false;
    while (this.nextParagraph < this.paragraphs.length) {
      const i = this.nextParagraph++;
      const p = this.paragraphs[i];
      const isEdge = i === 0 || i === this.paragraphs.length - 1;
      const r = isEdge ? p.getRange('Whole').intersectWithNullObject(this.scope) : p.getRange('Whole');
      r.load('isNullObject');
      const trs = r.getTextRanges(WORD_DELIMITERS, true);
      trs.load('items/text');
      await this.ctx.sync();
      if (r.isNullObject) continue;
      const before = this.items.length;
      await this.#collect(trs.items);
      if (this.items.length > before) return true;
    }
    return false;
  }

  /** בונה פריטים מטווחי טקסט ומאתר לכל גרעין את הטווח המדויק שלו. */
  async #collect(textRanges) {
    const ctx = this.ctx;
    const pending = [];
    for (const tr of textRanges) {
      const t = tr.text;
      const local = [];
      for (const tok of tokenize(t)) {
        const { lead, core, trail } = extractCore(tok.text);
        updateBrackets(this.brackets, lead);
        if (core) {
          const start = tok.start + lead.length;
          local.push({
            text: core,
            key: makeKey(core),
            lead,
            trail,
            brackets: { ...this.brackets },
            range: null,
            occ: countOccurrencesBefore(t, core, start),
          });
        }
        updateBrackets(this.brackets, trail);
      }
      if (!local.length) continue;
      const byCore = new Map();
      for (const it of local) {
        if (!byCore.has(it.text)) {
          const res = tr.search(it.text, { matchCase: true });
          res.load('items');
          byCore.set(it.text, res);
        }
      }
      pending.push({ local, byCore });
    }
    await ctx.sync();
    for (const { local, byCore } of pending) {
      for (const it of local) {
        const res = byCore.get(it.text).items;
        it.range = res[it.occ] ?? res[res.length - 1] ?? null;
        if (it.range) {
          ctx.trackedObjects.add(it.range);
          delete it.occ;
          this.items.push(it);
        }
      }
    }
  }

  async select(item) {
    item.range.select('Select');
    await this.ctx.sync();
  }

  /**
   * מחליף את המילה בצורה המנוקדת.
   * כשהאותיות לא השתנו, הניקוד מוכנס אחרי כל אות בנפרד,
   * וכך נשמר העיצוב גם כשחלק מהמילה מעוצב אחרת.
   */
  async apply(item, newText, { dollars = false, preserveFormatting = true } = {}) {
    const ctx = this.ctx;
    const oldText = item.text;
    let newRange = null;

    const sameLetters = stripMarks(newText) === oldText && !hasNikud(oldText);
    if (preserveFormatting && sameLetters && newText !== oldText) {
      const chars = item.range.search('?', { matchWildcards: true });
      chars.load('items/text');
      await ctx.sync();
      const cls = clusters(newText);
      if (chars.items.length === cls.length && chars.items.every((c, i) => c.text === cls[i].base)) {
        let lastRange = chars.items[chars.items.length - 1];
        cls.forEach((c, i) => {
          if (c.marks.length && isLetter(c.base)) {
            const ins = chars.items[i].insertText(c.marks.join(''), 'After');
            if (i === cls.length - 1) lastRange = ins;
          }
        });
        newRange = chars.items[0].expandTo(lastRange);
      }
    }
    if (!newRange) newRange = item.range.insertText(newText, 'Replace');

    let dollarsRange = null;
    if (dollars) dollarsRange = newRange.insertText('$$', 'Before');

    ctx.trackedObjects.add(newRange);
    if (dollarsRange) ctx.trackedObjects.add(dollarsRange);
    await ctx.sync();

    this.undoStack.push({ item, oldText, dollarsRange });
    item.range = newRange;
    item.text = newText;
  }

  /** מבטל את ההחלפה האחרונה. מחזיר את הפריט שהוחזר, או null. */
  async undo() {
    const entry = this.undoStack.pop();
    if (!entry) return null;
    const { item, oldText, dollarsRange } = entry;
    const r = item.range.insertText(oldText, 'Replace');
    this.ctx.trackedObjects.add(r);
    if (dollarsRange) dollarsRange.insertText('', 'Replace');
    await this.ctx.sync();
    item.range = r;
    item.text = oldText;
    return item;
  }

  async save() {
    try {
      this.ctx.document.save();
      await this.ctx.sync();
      return true;
    } catch (e) {
      console.warn('השמירה האוטומטית נכשלה', e);
      return false;
    }
  }

  close() {
    this.ctx = null;
    this.items = [];
    this.undoStack = [];
  }
}

// ---------- פעולות קצרות על הבחירה ----------

/** מכניס סימן ניקוד או טעם במקום הסמן ומעביר את הסמן אחריו. */
export async function insertAtCursor(text) {
  await Word.run(async (ctx) => {
    const sel = ctx.document.getSelection();
    const r = sel.insertText(text, 'End');
    r.select('End');
    await ctx.sync();
  });
}

/** מסיר ניקוד (או טעמים בלבד) מהבחירה, מילה אחרי מילה. */
export async function stripSelection({ taamimOnly = false } = {}) {
  return Word.run(async (ctx) => {
    const sel = ctx.document.getSelection();
    const trs = sel.getTextRanges(WORD_DELIMITERS, true);
    trs.load('items/text');
    await ctx.sync();
    let changed = 0;
    for (const tr of trs.items) {
      const t = tr.text;
      const stripped = taamimOnly ? [...t].filter((c) => c < '֑' || c > '֯').join('') : stripMarks(t);
      if (stripped !== t) {
        tr.insertText(stripped, 'Replace');
        changed++;
      }
    }
    await ctx.sync();
    return changed;
  });
}

export async function getSelectionText() {
  return Word.run(async (ctx) => {
    const sel = ctx.document.getSelection();
    sel.load('text');
    await ctx.sync();
    return sel.text;
  });
}
