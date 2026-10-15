import { useEffect, useState } from "react";
import { callApi, copyToClipboard } from "../bridge";
import { getTheme, setTheme } from "../theme.js";

// לחיצה ימנית על כל שדה טקסט מדביקה ישירות, בלי תפריט - נוח יותר כשמעתיקים
// מזהה/סיסמה/כתובת שרת. קוראים את הלוח דרך פייתון (פיברוך cross-platform;
// ה-Clipboard API של הדפדפן לא תמיד זמין/מורשה בתוך webview).
async function pasteOnContextMenu(e) {
  e.preventDefault();
  const el = e.currentTarget;
  let text = "";
  try {
    text = await callApi("getClipboardText");
  } catch {
    return;
  }
  if (!text) return;
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? el.value.length;
  setter.call(el, el.value.slice(0, start) + text + el.value.slice(end));
  el.dispatchEvent(new Event("input", { bubbles: true }));
  const pos = start + text.length;
  requestAnimationFrame(() => {
    try {
      el.setSelectionRange(pos, pos);
    } catch {
      /* שדות מסוג password/number לא תומכים ב-setSelectionRange בכל הדפדפנים */
    }
  });
}

export function Card({ title, right, children }) {
  return (
    <div className="card">
      {title && (
        <div className="card-title">
          <span>{title}</span>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function Button({ variant = "ghost", size, loading, children, ...rest }) {
  const cls = ["btn", `btn-${variant}`, size === "sm" ? "btn-sm" : "", rest.className || ""]
    .filter(Boolean)
    .join(" ");
  return (
    <button {...rest} className={cls} disabled={rest.disabled || loading}>
      {loading && <span className="spinner" />}
      {children}
    </button>
  );
}

export function IconButton({ children, title, ...rest }) {
  return (
    <button {...rest} className="btn btn-ghost btn-icon" title={title} aria-label={title}>
      {children}
    </button>
  );
}

export function ThemeToggle() {
  const [theme, setThemeState] = useState(getTheme());
  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    setThemeState(next);
  }
  return (
    <IconButton title={theme === "light" ? "מעבר לערכה כהה" : "מעבר לערכה בהירה"} onClick={toggle}>
      {theme === "light" ? "☾" : "☀"}
    </IconButton>
  );
}

export function CopyButton({ text, title = "העתק", disabled }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={disabled || !text}
      onClick={() => {
        copyToClipboard(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
    >
      {copied ? "הועתק ✓" : title}
    </Button>
  );
}

export function Field({ label, children }) {
  return (
    <label className="field">
      {label && <span className="field-label">{label}</span>}
      {children}
    </label>
  );
}

export function Input({ dir, onContextMenu, ...rest }) {
  const handleContextMenu = (e) => {
    pasteOnContextMenu(e);
    onContextMenu?.(e);
  };
  return (
    <input {...rest} dir={dir} onContextMenu={handleContextMenu} className={`input ${rest.className || ""}`} />
  );
}

export function Checkbox({ label, disabled, ...rest }) {
  return (
    <label className={`checkrow ${disabled ? "disabled" : ""}`}>
      <input type="checkbox" disabled={disabled} {...rest} />
      {label}
    </label>
  );
}

export function Pill({ tone = "muted", children }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="pill-dot" style={{ background: "currentColor" }} />
      {children}
    </span>
  );
}

export function Tabs({ tabs, value, onChange, right }) {
  return (
    <div className="tabbar" style={right ? { justifyContent: "space-between" } : undefined}>
      <div style={{ display: "flex", gap: 4 }}>
        {tabs.map((t) => (
          <div
            key={t.key}
            className={`tab ${value === t.key ? "active" : ""}`}
            onClick={() => onChange(t.key)}
          >
            {t.label}
          </div>
        ))}
      </div>
      {right && <div style={{ paddingBottom: 6 }}>{right}</div>}
    </div>
  );
}

export function Modal({ title, children, actions, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className="modal">
        <div className="modal-title">{title}</div>
        <div className="modal-body">{children}</div>
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  );
}

let toastId = 0;
const toastListeners = new Set();
export function pushToast(message, tone = "default") {
  const t = { id: ++toastId, message, tone };
  toastListeners.forEach((fn) => fn(t));
}

export function ToastHost() {
  const [toasts, setToasts] = useState([]);
  useEffect(() => {
    const fn = (t) => {
      setToasts((ts) => [...ts, t]);
      setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== t.id)), 4500);
    };
    toastListeners.add(fn);
    return () => toastListeners.delete(fn);
  }, []);
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.tone !== "default" ? `toast-${t.tone}` : ""}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
