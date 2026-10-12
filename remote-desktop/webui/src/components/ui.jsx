import { useEffect, useState } from "react";
import { copyToClipboard } from "../bridge";

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

export function Input({ dir, ...rest }) {
  return <input {...rest} dir={dir} className={`input ${rest.className || ""}`} />;
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

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabbar">
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
