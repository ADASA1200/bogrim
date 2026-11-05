// תחליף מינימלי ל-Word JavaScript API, לבדיקות בדפדפן בלי Word.
// המסמך הוא מחרוזת אחת, ופסקאות מופרדות ב-\r. עיצוב אינו מדומה.
// נטען לפני החלונית דרך addInitScript.
(function () {
  const doc = { text: window.__FAKE_DOC_TEXT__ ?? '', selStart: 0, selEnd: 0, saves: 0 };
  const ranges = new Set();
  window.__fakeDoc = doc;

  function edit(s, e, text) {
    const delta = text.length - (e - s);
    doc.text = doc.text.slice(0, s) + text + doc.text.slice(e);
    for (const r of ranges) {
      if (s === e) {
        // הוספה בנקודה: טווח שמסתיים בדיוק בנקודה אינו מתרחב
        if (r.start === s && r.end === s) { r.start += delta; r.end += delta; continue; }
        if (r.start >= s) r.start += delta;
        if (r.end > s) r.end += delta;
      } else {
        r.start = r.start >= e ? r.start + delta : r.start > s ? s : r.start;
        r.end = r.end >= e ? r.end + delta : r.end > s ? s + text.length : r.end;
      }
    }
  }

  const coll = (items) => ({ items, load() { return this; } });

  class Range {
    constructor(start, end) {
      this.start = start;
      this.end = end;
      this.isNullObject = false;
      ranges.add(this);
    }
    load() { return this; }
    get text() { return doc.text.slice(this.start, this.end); }
    get isEmpty() { return this.start === this.end; }
    getRange(loc = 'Whole') {
      if (loc === 'Start') return new Range(this.start, this.start);
      if (loc === 'End') return new Range(this.end, this.end);
      return new Range(this.start, this.end);
    }
    expandTo(other) { return new Range(Math.min(this.start, other.start), Math.max(this.end, other.end)); }
    intersectWithNullObject(other) {
      const s = Math.max(this.start, other.start);
      const e = Math.min(this.end, other.end);
      const r = new Range(s, Math.max(s, e));
      r.isNullObject = e < s || (e === s && this.start !== this.end);
      return r;
    }
    get paragraphs() {
      const out = [];
      let p = 0;
      for (const part of doc.text.split('\r')) {
        const ps = p;
        const pe = p + part.length + 1;
        if (pe > this.start && ps <= this.end) out.push(new Paragraph(ps, Math.min(pe, doc.text.length)));
        p = pe;
      }
      const c = coll(out);
      c.getFirst = () => out[0];
      return c;
    }
    getTextRanges(delims) {
      const items = [];
      let i = this.start;
      const isDelim = (ch) => delims.includes(ch) || ch === '\r';
      while (i < this.end) {
        while (i < this.end && isDelim(doc.text[i])) i++;
        const s = i;
        while (i < this.end && !isDelim(doc.text[i])) i++;
        if (i > s) items.push(new Range(s, i));
      }
      return coll(items);
    }
    search(str, opts = {}) {
      const items = [];
      const t = this.text;
      if (opts.matchWildcards && str === '?') {
        for (let i = 0; i < t.length; i++) items.push(new Range(this.start + i, this.start + i + 1));
        return coll(items);
      }
      let i = t.indexOf(str);
      while (i >= 0) {
        items.push(new Range(this.start + i, this.start + i + str.length));
        i = t.indexOf(str, i + str.length);
      }
      return coll(items);
    }
    insertText(text, loc) {
      if (loc === 'Replace') {
        const s = this.start;
        const e = this.end;
        edit(s, e, text);
        this.start = s;
        this.end = s + text.length;
        return new Range(s, s + text.length);
      }
      const p = loc === 'Before' || loc === 'Start' ? this.start : this.end;
      edit(p, p, text);
      return new Range(p, p + text.length);
    }
    select() { doc.selStart = this.start; doc.selEnd = this.end; }
    compareLocationWith(o) {
      let value;
      if (this.start === o.start && this.end === o.end) value = 'Equal';
      else if (this.start <= o.start && this.end >= o.end) value = 'Contains';
      else if (this.end === o.start) value = 'AdjacentBefore';
      else if (this.start === o.end) value = 'AdjacentAfter';
      else value = this.end < o.start ? 'Before' : 'After';
      return { value };
    }
  }

  class Paragraph extends Range {
    getRange() { return new Range(this.start, this.end); }
  }

  function makeContext() {
    return {
      document: {
        getSelection: () => new Range(doc.selStart, doc.selEnd),
        body: { getRange: (loc) => (loc === 'End' ? new Range(doc.text.length, doc.text.length) : new Range(0, doc.text.length)) },
        save: () => { doc.saves++; },
      },
      trackedObjects: { add() {}, remove() {} },
      sync: async () => {},
    };
  }

  window.Word = {
    RequestContext: function () { return makeContext(); },
    run: async (fn) => fn(makeContext()),
  };
  window.Office = {
    HostType: { Word: 'Word' },
    onReady: (cb) => { setTimeout(() => cb({ host: 'Word' }), 0); return Promise.resolve({ host: 'Word' }); },
  };
})();
