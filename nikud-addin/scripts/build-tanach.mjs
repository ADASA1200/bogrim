// בונה את data/tanach.json מהקבצים שהוריד scripts/fetch-tanach.sh.
// מנקה את הסימון של המהדורה: פתוחות וסתומות, הערות שוליים, כתיב וקרי (נשאר הקרי).
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2];
if (!dir) {
  console.error('usage: node scripts/build-tanach.mjs <dir-with-sefaria-json>');
  process.exit(1);
}

const books = readFileSync(new URL('./tanach-books.tsv', import.meta.url), 'utf8')
  .trim().split('\n').map((l) => l.split('\t'));

export function cleanVerse(v) {
  return v
    .replace(/<\/?(?:small|big|b)>/g, '')                               // אותיות גדולות וקטנות, פסק מודגש
    .replace(/<sup class="footnote-marker">[^<]*<\/sup><i class="footnote">[\s\S]*?<\/i>/g, '')
    .replace(/<span class="mam-spi-[a-z]+">[^<]*<\/span>/g, '')        // {פ} {ס} נ הפוכה
    .replace(/<span class="mam-kq-k">[^<]*<\/span>/g, '')              // הכתיב
    .replace(/<span class="mam-kq-q">\[([^\]]*)\]<\/span>/g, '$1')     // הקרי
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&thinsp;/g, '')
    .replace(/͏/g, '')
    .replace(/\s*\u05C0\s*/g, '\u05C0 ')                                // פסק צמוד למילה שלפניו
    .replace(/\s+/g, ' ')
    .trim();
}

const out = {
  title: 'מקרא על פי המסורה',
  source: 'https://he.wikisource.org/wiki/מקרא_על_פי_המסורה (דרך Sefaria)',
  license: 'CC BY-SA 4.0',
  books: [],
};
let verses = 0;
for (const [en, he] of books) {
  const raw = JSON.parse(readFileSync(join(dir, `${en.replace(/ /g, '_')}.json`), 'utf8'));
  const chapters = raw.versions[0].text.map((ch) => ch.map(cleanVerse));
  for (const ch of chapters) {
    for (const v of ch) {
      if (/[<>{}()[\]&]/.test(v)) throw new Error(`${he}: סימון שלא נוקה: ${v}`);
      verses++;
    }
  }
  out.books.push({ he, en, chapters });
}
writeFileSync(new URL('../data/tanach.json', import.meta.url), JSON.stringify(out));
console.log(`tanach.json: ${out.books.length} books, ${verses} verses`);
