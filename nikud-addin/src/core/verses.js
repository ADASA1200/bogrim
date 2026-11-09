// חיפוש פסוקים: מתאים מילים שהמשתמש כתב לפסוק בתנ"ך, גם בכתיב מלא או חסר
// וגם כשהשמות הקדושים כתובים בכינוי (ה', יי, אלקים).

import { stripMarks, stripTaamim, normalizeMarks, normalizeQuotes } from './hebrew.js';

const FINALS = { 'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ' };
const SUBSTITUTE_NAME = /^([ובלכמהש]{0,3})(?:ה'|ד'|יי|ייי|יקוק|יקו"ק|הוי"ה)$/;
const SUBSTITUTE_ELOKIM = /אלו?ק/;

/**
 * שלד המילה להשוואה: אותיות בלי ניקוד, בלי אותיות סופיות, ובלי ו' וי' (חוץ מהאות הראשונה).
 * שם הוי"ה וכינוייו הופכים ל-#, ו"אלקים" הופך ל"אלהים".
 * substitute: המשתמש כתב כינוי במקום השם. במקרה כזה משאירים את מה שכתב.
 * @returns {{skel: string, substitute: boolean}}
 */
export function skeleton(word) {
  const w = normalizeQuotes(stripMarks(word)).replace(/[^א-ת'"]/g, '');
  const name = SUBSTITUTE_NAME.exec(w);
  if (name) return { skel: name[1] + '#', substitute: true };
  let letters = w.replace(/['"]/g, '');
  let substitute = false;
  if (SUBSTITUTE_ELOKIM.test(letters)) {
    letters = letters.replace(/אלו?ק/g, 'אלה');
    substitute = true;
  }
  letters = letters.replace(/יהוה/g, '#');
  letters = letters.replace(/[ךםןףץ]/g, (c) => FINALS[c]);
  if (!letters) return { skel: '', substitute: false };
  return { skel: letters[0] + letters.slice(1).replace(/[וי]/g, ''), substitute };
}

/** מספר בגימטריה, בלי גרשיים: 15 → טו, 119 → קיט. */
export function gematria(n) {
  const parts = [];
  let x = n;
  for (const [v, l] of [[400, 'ת'], [300, 'ש'], [200, 'ר'], [100, 'ק']]) {
    while (x >= v) {
      parts.push(l);
      x -= v;
    }
  }
  if (x === 15) parts.push('טו');
  else if (x === 16) parts.push('טז');
  else {
    const tens = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ'];
    const ones = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט'];
    parts.push(tens[Math.floor(x / 10)] + ones[x % 10]);
  }
  return parts.join('');
}

/** פירוק פסוק למילים, עם המפריד שאחרי כל מילה (רווח או מקף). */
export function splitVerse(text) {
  const out = [];
  const re = /([^\s־]+)([\s־]*)/g;
  let m;
  while ((m = re.exec(text))) {
    out.push({ text: m[1], sep: m[2].includes('־') ? '־' : m[2] ? ' ' : '' });
  }
  return out;
}

/** מוריד טעמים, מתג (געיה), פסק וסוף פסוק. */
const stripCantillation = (s) => stripTaamim(s).replace(/[\u05BD\u05C0\u05C3]/g, '');

export class VerseIndex {
  /** @param {{books: Array<{he: string, chapters: string[][]}>}} data */
  constructor(data) {
    this.refs = [];   // [bookIdx, chapter, verse]
    this.words = [];  // לכל פסוק: [{text, sep}]
    this.skels = [];  // לכל פסוק: שלדי המילים
    this.books = data.books.map((b) => b.he);
    /** @type {Map<string, number[]>} שלד → מספרי פסוקים */
    this.index = new Map();
    data.books.forEach((b, bi) => {
      b.chapters.forEach((ch, ci) => {
        ch.forEach((v, vi) => {
          const id = this.refs.length;
          const words = splitVerse(v);
          const skels = words.map((w) => skeleton(w.text).skel);
          this.refs.push([bi, ci + 1, vi + 1]);
          this.words.push(words);
          this.skels.push(skels);
          for (const s of new Set(skels)) {
            if (!s) continue;
            let list = this.index.get(s);
            if (!list) this.index.set(s, (list = []));
            list.push(id);
          }
        });
      });
    });
  }

  get size() {
    return this.refs.length;
  }

  /** "בראשית א, א" */
  refText(id) {
    const [b, c, v] = this.refs[id];
    return `${this.books[b]} ${gematria(c)}, ${gematria(v)}`;
  }

  /**
   * מחפש את רצף המילים בפסוקים.
   * @param {string[]} userWords
   * @returns {Array<{id: number, start: number, len: number}>}
   */
  search(userWords, limit = 50) {
    const query = userWords.map(skeleton).map((x) => x.skel);
    if (!query.length || query.some((s) => !s)) return [];
    // מתחילים מהמילה הנדירה ביותר
    let rarest = null;
    for (const s of query) {
      const list = this.index.get(s);
      if (!list) return [];
      if (!rarest || list.length < rarest.length) rarest = list;
    }
    const out = [];
    for (const id of rarest) {
      const sk = this.skels[id];
      for (let i = 0; i + query.length <= sk.length; i++) {
        let ok = true;
        for (let j = 0; j < query.length; j++) {
          if (sk[i + j] !== query[j]) {
            ok = false;
            break;
          }
        }
        if (ok) {
          out.push({ id, start: i, len: query.length });
          if (out.length >= limit) return out;
          break;
        }
      }
    }
    return out;
  }

  /**
   * בונה את הטקסט להכנסה.
   * @param {{id:number,start:number,len:number}} match
   * @param {{full?: boolean, taamim?: boolean, nikud?: boolean, userWords?: string[]}} opts
   */
  render(match, { full = false, taamim = false, nikud = true, userWords = [] } = {}) {
    const words = this.words[match.id];
    const from = full ? 0 : match.start;
    const to = full ? words.length : match.start + match.len;
    let out = '';
    for (let i = from; i < to; i++) {
      const u = i - match.start;
      const user = u >= 0 && u < match.len ? userWords[u] : undefined;
      let t;
      if (user !== undefined && skeleton(user).substitute) {
        t = user; // משאירים את הכינוי שהמשתמש כתב
      } else if (user !== undefined && !nikud) {
        t = user; // בלי ניקוד: המילים של המשתמש כמו שהן
      } else {
        t = words[i].text;
        if (!nikud) t = stripMarks(t).replace(/[׀׃]/g, '');
        else if (!taamim) t = stripCantillation(t);
        t = normalizeMarks(t);
      }
      out += t;
      if (i < to - 1) out += words[i].sep || ' ';
    }
    return out.trim();
  }

  /** הפסוק המלא בלי טעמים, להצגה ברשימת התוצאות. */
  preview(id) {
    return this.words[id].map((w, i, a) => stripCantillation(w.text) + (i < a.length - 1 ? w.sep || ' ' : '')).join('');
  }
}
