import { useEffect, useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, Field, Input, pushToast } from "../components/ui";

const REASONS = {
  "bad password": "הסיסמה שגויה",
  "bad totp": "קוד האימות הדו-שלבי שגוי או לא עדכני",
  ip_blocked: "המחשב המרוחק חוסם חיבורים מכתובת ה-IP שלך",
  "interactive disabled": "המחשב המרוחק לא מאפשר חיבור עם בקשת אישור - רק גישה ללא-נוכחות",
  "window closed": "אפליקציית המארח מוסתרת למגש כרגע ולא יכולה להציג בקשת אישור",
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
  const [totp, setTotp] = useState("");
  const [invite, setInvite] = useState("");
  const [inviteText, setInviteText] = useState("");
  const [server, setServer] = useState("ws://127.0.0.1:8765");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [recent, setRecent] = useState([]);
  const [wolMac, setWolMac] = useState("");
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    callApi("getViewerPreset").then((p) => {
      if (p) {
        setServer(p.server || server);
        if (p.id) setId(p.id);
        if (p.password) setPassword(p.password);
        if (p.invite) setInvite(p.invite);
        setRecent(p.recent || []);
        if (p.autoConnect) connect(p.id, p.password, p.server, p.invite);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function pasteInviteLink(text) {
    setInviteText(text);
    if (!text.startsWith("rdesk://")) return;
    const parsed = await callApi("parseInviteLink", text);
    if (!parsed) {
      pushToast("קישור הזמנה לא תקין.", "danger");
      return;
    }
    setId(parsed.id);
    setInvite(parsed.token);
    if (parsed.server) setServer(parsed.server);
    connect(parsed.id, "", parsed.server || server, parsed.token);
  }

  useEffect(() => {
    const cleanId = id.replace(/\D/g, "");
    if (cleanId.length === 9) callApi("getWolMac", cleanId).then(setWolMac);
    else setWolMac("");
  }, [id]);

  async function saveWolMac(mac) {
    const cleanId = id.replace(/\D/g, "");
    if (cleanId.length !== 9) return;
    try {
      await callApi("setWolMac", cleanId, mac);
    } catch {
      pushToast("כתובת MAC לא תקינה (לדוגמה: AA:BB:CC:DD:EE:FF)", "danger");
    }
  }

  async function wake() {
    setWaking(true);
    try {
      await callApi("wakeOnLan", id.replace(/\D/g, ""));
      pushToast("נשלח מגיק-פאקט להעיר את המחשב ברשת המקומית.");
    } catch (e) {
      pushToast(String(e?.message || e) === "no_mac_saved" ? "אין כתובת MAC שמורה למזהה הזה" : "שליחה נכשלה", "danger");
    } finally {
      setWaking(false);
    }
  }

  async function connect(presetId, presetPw, presetServer, presetInvite) {
    const useId = (presetId ?? id).replace(/\D/g, "");
    const usePw = presetPw ?? password;
    const useServer = presetServer ?? server;
    const useInvite = presetInvite ?? invite;
    if (!useId) {
      setIsError(true);
      setMsg("יש להזין את המזהה של המחשב המרוחק");
      return;
    }
    setBusy(true);
    setIsError(false);
    setMsg(useInvite ? "מתחבר עם קישור הזמנה..." : usePw ? "מתחבר..." : "ממתין לאישור המשתמש במחשב המרוחק...");
    try {
      const info = await callApi("viewerConnect", useServer, useId, usePw, totp, useInvite);
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
            <Field label="קישור הזמנה (אופציונלי - דילוג על כל השדות למטה)">
              <Input dir="ltr" placeholder="rdesk://connect/..." value={inviteText} onChange={(e) => pasteInviteLink(e.target.value)} />
            </Field>
            <Field label="מזהה">
              <Input dir="ltr" placeholder="123 456 789" value={id} onChange={(e) => setId(e.target.value)} onKeyDown={(e) => e.key === "Enter" && connect()} />
            </Field>
            <Field label="סיסמה (אופציונלי)">
              <Input type="password" dir="ltr" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && connect()} />
            </Field>
            <Field label="קוד אימות דו-שלבי (רק אם המארח דורש)">
              <Input dir="ltr" maxLength={6} placeholder="000000" value={totp} onChange={(e) => setTotp(e.target.value)} onKeyDown={(e) => e.key === "Enter" && connect()} />
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
            <details>
              <summary className="text-faint" style={{ cursor: "pointer" }}>Wake-on-LAN (להעיר מחשב כבוי באותה רשת)</summary>
              <div className="mt-2" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <Field label="כתובת MAC של המחשב המרוחק">
                  <Input dir="ltr" placeholder="AA:BB:CC:DD:EE:FF" value={wolMac}
                    onChange={(e) => setWolMac(e.target.value)}
                    onBlur={(e) => saveWolMac(e.target.value)} />
                </Field>
                <Button variant="ghost" loading={waking} disabled={!wolMac} onClick={wake}>העיר מחשב</Button>
              </div>
            </details>
          </div>
        </Card>
      </div>
    </div>
  );
}
