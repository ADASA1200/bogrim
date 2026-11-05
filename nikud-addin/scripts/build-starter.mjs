// בונה את data/starter-dictionary.json מרשימה קצרה שנכתבה ידנית.
import { writeFileSync } from 'node:fs';
import { Dictionary } from '../src/core/dictionary.js';

const words = `
מֹשֶׁה אַהֲרֹן דָּוִד שְׁלֹמֹה אַבְרָהָם יִצְחָק יַעֲקֹב יִשְׂרָאֵל יְרוּשָׁלַיִם נְתַנְאֵל
תּוֹרָה שָׁלוֹם בַּיִת מֶלֶךְ אֶרֶץ עוֹלָם אָדָם יוֹם לַיְלָה שָׁנָה עִיר אִישׁ לֵב
דָּבָר אֱמֶת חֶסֶד מִצְוָה תְּפִלָּה בְּרָכָה שַׁבָּת כִּי אֲשֶׁר עַל אֶל לֹא הוּא הִיא הֵם
אֲנִי אַתָּה זֶה זֹאת מָה מִי גַּם אוֹ אִם שֶׁל
אֶת אֵת אַתְּ עִם עַם כָּל כֹּל
סֵפֶר סָפַר סִפֵּר סַפָּר לָמַד לִמֵּד
`.trim().split(/\s+/);

const special = [
  ['עכשיו', 'עַכְשָׁו'],
  ['ז"ל', 'זִכְרוֹנוֹ לִבְרָכָה'],
  ['רז"ל', 'רַבּוֹתֵינוּ זִכְרוֹנָם לִבְרָכָה'],
  ['הקב"ה', 'הַקָּדוֹשׁ בָּרוּךְ הוּא'],
  ['ע"ה', 'עָלָיו הַשָּׁלוֹם'],
  ['בע"ה', 'בְּעֶזְרַת הַשֵּׁם'],
];

const d = new Dictionary();
for (const w of words) d.add(w);
for (const [k, v] of special) d.add(v, k);
writeFileSync(new URL('../data/starter-dictionary.json', import.meta.url), JSON.stringify(d.toJSON(), null, 1) + '\n');
console.log(`starter dictionary: ${d.size} keys`);
