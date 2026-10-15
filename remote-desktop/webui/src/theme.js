// ערכת נושא (בהיר/כהה): נשמר ב-localStorage של חלון ה-webview (פר-מכשיר, פר-
// פרופיל WebView2 - שורד הפעלות חוזרות כמו כל localStorage רגיל). ברירת
// המחדל היא בהיר. data-theme נקבע על document.documentElement לפני ה-render
// הראשון (ראו main.jsx) כדי שלא יהיה הבהוב של הערכה הכהה ברגע הטעינה.
const KEY = "rdesk-theme";

export function getTheme() {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function setTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(KEY, t);
  } catch {
    // אחסון חסום (למשל חלון פרטי) - עדיין עובד לסשן הנוכחי, פשוט לא נשמר
  }
}

export function applyStoredTheme() {
  setTheme(getTheme());
}
