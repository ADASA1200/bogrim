// ב-DOM, KeyboardEvent.key כבר נותן את התו הנכון (כולל עברית, לפי פריסת
// המקלדת של המערכת) או שם מקש קריא למקשים מיוחדים - בניגוד ל-Tk, אין צורך
// בטבלת keysym ידנית. ממפים רק את השמות המיוחדים לפרוטוקול של rdesk (זהה
// לרשימת NAMED_KEYS ב-rdesk/inject.py).
const SPECIAL = {
  Enter: "enter",
  Tab: "tab",
  " ": "space",
  Backspace: "backspace",
  Delete: "delete",
  Escape: "esc",
  Home: "home",
  End: "end",
  PageUp: "page_up",
  PageDown: "page_down",
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  Insert: "insert",
  Shift: "shift",
  Control: "ctrl",
  Alt: "alt",
  Meta: "cmd",
  CapsLock: "caps_lock",
  ContextMenu: "menu",
  PrintScreen: "print_screen",
  Pause: "pause",
  NumLock: "num_lock",
  ScrollLock: "scroll_lock",
};

export function keyName(e) {
  if (e.key in SPECIAL) return SPECIAL[e.key];
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(e.key)) return e.key.toLowerCase();
  if (e.key.length === 1) return e.key; // תו רגיל, בכל שפה
  return null; // מקש לא מזוהה (מדיה, עוצמת קול וכו') - פשוט מתעלמים
}

// מקשים שחייבים preventDefault כדי שהדפדפן לא "יבלע" אותם (ניווט/גלילה/טאב)
const PREVENT = new Set(["Tab", "Backspace", " ", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown"]);
export function shouldPreventDefault(e) {
  return PREVENT.has(e.key) || e.ctrlKey || e.altKey || e.metaKey;
}
