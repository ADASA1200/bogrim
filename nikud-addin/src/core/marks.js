// טבלאות הסימנים לכפתורים ולמקלדת. code הוא KeyboardEvent.code של מקש הקיצור.

export const NIKUD = [
  { mark: 'ְ', name: 'שווא', code: 'Digit1' },
  { mark: 'ִ', name: 'חיריק', code: 'Digit2' },
  { mark: 'ֵ', name: 'צירה', code: 'Digit3' },
  { mark: 'ֶ', name: 'סגול', code: 'Digit4' },
  { mark: 'ַ', name: 'פתח', code: 'Digit5' },
  { mark: 'ָ', name: 'קמץ', code: 'Digit6' },
  { mark: 'ֹ', name: 'חולם', code: 'Digit7' },
  { mark: 'ֻ', name: 'קובוץ', code: 'Digit8' },
  { mark: 'ּ', name: 'דגש / שורוק', code: 'Digit9' },
  { mark: 'ׁ', name: 'נקודת שין ימנית', code: 'Digit0' },
  { mark: 'ׂ', name: 'נקודת שין שמאלית', code: 'Minus' },
  { mark: 'ֱ', name: 'חטף סגול', code: 'Digit4', shift: true },
  { mark: 'ֲ', name: 'חטף פתח', code: 'Digit5', shift: true },
  { mark: 'ֳ', name: 'חטף קמץ', code: 'Digit6', shift: true },
  { mark: 'ׇ', name: 'קמץ קטן', code: 'Digit6', alt: true },
  { mark: 'ֺ', name: 'חולם חסר לוו', code: 'Digit7', shift: true },
  { mark: 'ֽ', name: 'מתג', code: 'Equal' },
  { mark: 'ֿ', name: 'רפה', code: 'Equal', shift: true },
];

export const TAAMIM = [
  { mark: '֑', name: 'אתנחתא' },
  { mark: '֒', name: 'סגולתא' },
  { mark: '֓', name: 'שלשלת' },
  { mark: '֔', name: 'זקף קטן' },
  { mark: '֕', name: 'זקף גדול' },
  { mark: '֖', name: 'טפחא' },
  { mark: '֗', name: 'רביע' },
  { mark: '֘', name: 'זרקא' },
  { mark: '֙', name: 'פשטא' },
  { mark: '֚', name: 'יתיב' },
  { mark: '֛', name: 'תביר' },
  { mark: '֜', name: 'גרש' },
  { mark: '֝', name: 'גרש מוקדם' },
  { mark: '֞', name: 'גרשיים' },
  { mark: '֟', name: 'קרני פרה' },
  { mark: '֠', name: 'תלישא גדולה' },
  { mark: '֡', name: 'פזר' },
  { mark: '֢', name: 'אתנח הפוך' },
  { mark: '֣', name: 'מונח' },
  { mark: '֤', name: 'מהפך' },
  { mark: '֥', name: 'מרכא' },
  { mark: '֦', name: 'מרכא כפולה' },
  { mark: '֧', name: 'דרגא' },
  { mark: '֨', name: 'קדמא' },
  { mark: '֩', name: 'תלישא קטנה' },
  { mark: '֪', name: 'ירח בן יומו' },
  { mark: '֫', name: 'עולה' },
  { mark: '֬', name: 'עילוי' },
  { mark: '֭', name: 'דחי' },
  { mark: '֮', name: 'צינורית' },
  { mark: 'ֽ', name: 'מתג / געיה' },
  { mark: '־', name: 'מקף', standalone: true },
  { mark: '׀', name: 'פסק', standalone: true },
  { mark: '׃', name: 'סוף פסוק', standalone: true },
];

/** חולם חסר אחרי ו', כמו במילה מצְו‍ֹת: ZWJ ואחריו חולם. */
export const HOLAM_AFTER_VAV = { mark: '‍ֹ', name: 'חולם אחרי ו\'' };

/** מזהה הפקודה של סימן ברצועת הכלים, למשל mark_5B0. */
export const markId = (mark) => 'mark_' + [...mark].map((c) => c.codePointAt(0).toString(16).toUpperCase()).join('_');

/** הסימן לפי מקש, או null. */
export function markForKey(e) {
  const hit = NIKUD.find((n) => n.code === e.code && !!n.shift === e.shiftKey && !!n.alt === e.altKey);
  if (hit) return hit.mark;
  // גם המספרים שבצד המקלדת
  const m = /^Numpad(\d)$/.exec(e.code);
  if (m && !e.shiftKey && !e.altKey) return NIKUD.find((n) => n.code === `Digit${m[1]}` && !n.shift && !n.alt)?.mark ?? null;
  return null;
}

export function keyLabel(n) {
  if (!n.code) return '';
  const base = n.code.replace('Digit', '').replace('Minus', '-').replace('Equal', '=');
  return (n.shift ? '⇧' : '') + (n.alt ? 'Alt+' : '') + base;
}
