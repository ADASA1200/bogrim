import { useEffect, useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, Field, Input } from "../components/ui";

const REASONS = {
  "bad password": "הסיסמה שגויה",
  declined: "המשתמש במחשב המרוחק דחה את החיבור",
  busy: "המחשב המרוחק עסוק בסשן אחר",
  blocked: "נחסמת זמנית עקב ניסיונות רבים. נסו שוב בעוד דקה",
  "host not found / offline": "המזהה לא נמצא או שהמחשב המרוחק לא מחובר",
  "host authentication failed": "אימות המחשב המרוחק נכשל (ייתכן ניסיון התחזות)",
  "timed out waiting for host": "המחשב המרוחק לא הגיב בזמן",
};

export function ConnectScreen({ onConnected }) {
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("ws://127.0.0.1:8765");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    callApi("getViewerPreset").then((p) => {
      if (p) {
        setServer(p.server || server);
        if (p.id) setId(p.id);
        if (p.password) setPassword(p.password);
        setRecent(p.recent || []);
        if (p.autoConnect) connect(p.id, p.password, p.server);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect(presetId, presetPw, presetServer) {
    const useId = (presetId ?? id).replace(/\D/g, "");
    const usePw = presetPw ?? password;
    const useServer = presetServer ?? server;
    if (!useId) {
      setIsError(true);
      setMsg("יש להזין את המזהה של המחשב המרוחק");
      return;
    }
    setBusy(true);
    setIsError(false);
    setMsg(usePw ? "מתחבר..." : "ממתין לאישור המשתמש במחשב המרוחק...");
    try {
      const info = await callApi("viewerConnect", useServer, useId, usePw);
      onConnected(info);
    } catch (e) {
      setIsError(true);
      const code = String(e?.message || e);
      setMsg("החיבור נכשל: " + (REASONS[code] || code));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="scroll-area" style={{ alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "min(420px, 100%)" }}>
        <h2 style={{ textAlign: "center", marginBottom: 20 }}>חיבור למחשב מרוחק</h2>
        <Card>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Field label="מזהה">
              <Input dir="ltr" placeholder="123 456 789" value={id} onChange={(e) => setId(e.target.value)} onKeyDown={(e) => e.key === "Enter" && connect()} />
            </Field>
            <Field label="סיסמה (אופציונלי)">
              <Input type="password" dir="ltr" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && connect()} />
            </Field>
            <p className="card-help">
              בלי סיסמה - המשתמש במחשב המרוחק יתבקש לאשר את החיבור.
              עם סיסמת גישה ללא נוכחות (אם הוגדרה שם) - החיבור יתבצע בלי אישור.
            </p>
            <Field label="שרת">
              <Input dir="ltr" value={server} onChange={(e) => setServer(e.target.value)} />
            </Field>
            <Button variant="primary" className="btn-block" loading={busy} onClick={() => connect()}>
              התחבר
            </Button>
            {msg && <p className="text-sm" style={{ color: isError ? "var(--danger)" : "var(--fg-muted)", textAlign: "center" }}>{msg}</p>}
            {recent.length > 0 && (
              <div className="recent-list">
                {recent.map((r) => (
                  <div key={r} className="recent-item" onClick={() => setId(r)}>{r}</div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
