// שכבת תקשורת מול פייתון (pywebview) + אוטובוס אירועים לדחיפות מהצד השני.
//
// פייתון -> JS: קורא ל-`window.evaluate_js("window.__rdeskEvent(kind, data)")`.
// JS -> פייתון: `callApi("methodName", ...args)` עוטף את `window.pywebview.api`.
//
// במצב פיתוח (npm run dev, בלי pywebview אמיתי) נופלים ל-mock כדי שאפשר
// יהיה לראות ולערוך את העיצוב בלי להריץ את כל התוכנה.

const listeners = new Map(); // kind -> Set<fn>

function emit(kind, data) {
  for (const fn of listeners.get(kind) || []) fn(data);
  for (const fn of listeners.get("*") || []) fn(kind, data);
}

export function on(kind, fn) {
  if (!listeners.has(kind)) listeners.set(kind, new Set());
  listeners.get(kind).add(fn);
  return () => listeners.get(kind)?.delete(fn);
}

// נקודת הכניסה שפייתון קורא לה
window.__rdeskEvent = (kind, data) => emit(kind, data);

let readyPromise = null;

export function whenReady() {
  if (readyPromise) return readyPromise;
  readyPromise = new Promise((resolve) => {
    if (window.pywebview?.api) return resolve();
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
    // רשת ביטחון: אם pywebview לא יורה את האירוע (למשל מצב dev), לא נתקע
    setTimeout(resolve, 300);
  });
  return readyPromise;
}

const DEV_MOCK = !window.pywebview;

async function mockCall(method, args) {
  console.debug("[mock api]", method, args);
  const mocks = {
    getState: () => ({
      id: "123456789",
      online: true,
      recent: ["111222333", "444555666"],
      unattended: { enabled: false, control: true, clipboard: true, files: true },
      server: "ws://127.0.0.1:8765",
      embedded: { enabled: true, port: 8765, lanIp: "192.168.1.50", publicIp: "203.0.113.7", connections: 1 },
      session: null,
    }),
    getClipboardText: () => "דוגמה שהודבקה מהלוח",
    getConnectionLog: () => [
      { peer: "v1a2b3c4d5e6", mode: "interactive", startedAt: Date.now() / 1000 - 600, endedAt: Date.now() / 1000 - 540 },
    ],
    getTrustedDevices: () => [{ peer: "444555666", perms: { control: true, clipboard: true, files: true } }],
  };
  await new Promise((r) => setTimeout(r, 150));
  return mocks[method] ? mocks[method]() : null;
}

export async function callApi(method, ...args) {
  if (DEV_MOCK) return mockCall(method, args);
  await whenReady();
  const fn = window.pywebview.api[method];
  if (!fn) throw new Error(`API method not found: ${method}`);
  return fn(...args);
}

export function copyToClipboard(text) {
  navigator.clipboard?.writeText(text).catch(() => {});
}
