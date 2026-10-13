import { useEffect, useState } from "react";
import { callApi, on } from "../bridge";
import { Tabs } from "../components/ui";
import { pushToast } from "../components/ui";
import { Modal, Button } from "../components/ui";
import { MainTab } from "./MainTab";
import { SettingsTab } from "./SettingsTab";
import { HistoryTab } from "./HistoryTab";
import { ApprovalModal } from "./ApprovalModal";

const REASONS = {
  "bad password": "הסיסמה שגויה",
  declined: "המשתמש במחשב המרוחק דחה את החיבור",
  busy: "המחשב המרוחק עסוק בסשן אחר",
  blocked: "נחסמת זמנית עקב ניסיונות רבים. נסו שוב בעוד דקה",
  "host not found / offline": "המזהה לא נמצא או שהמחשב המרוחק לא מחובר",
};
export function reasonText(code) {
  return REASONS[code] || code;
}

export default function HostApp() {
  const [tab, setTab] = useState("main");
  const [state, setState] = useState(null);
  const [pendingAsk, setPendingAsk] = useState(null);
  const [pendingElevation, setPendingElevation] = useState(null);

  useEffect(() => {
    callApi("getState").then(setState);
    const offs = [
      on("status", (d) => setState((s) => ({ ...s, online: d.online }))),
      on("session_start", (d) =>
        setState((s) => ({
          ...s,
          session: { peer: d.peer, perms: d.perms, mode: d.mode, code: d.code, chat: [], privacy: false, whiteboard: [] },
        }))
      ),
      on("session_end", () => setState((s) => ({ ...s, session: null }))),
      on("whiteboard", (d) =>
        setState((s) => {
          if (!s.session) return s;
          const data = d?.data;
          if (!data) return s;
          const whiteboard = data.type === "clear" ? [] : [...s.session.whiteboard, data];
          return { ...s, session: { ...s.session, whiteboard } };
        })
      ),
      on("privacy_changed", (d) =>
        setState((s) => (s.session ? { ...s, session: { ...s.session, privacy: d.enabled } } : s))
      ),
      on("perms_changed", (d) =>
        setState((s) => (s.session ? { ...s, session: { ...s.session, perms: d.perms } } : s))
      ),
      on("chat", (d) =>
        setState((s) =>
          s.session
            ? { ...s, session: { ...s.session, chat: [...s.session.chat, { from: "them", text: d.text }] } }
            : s
        )
      ),
      on("file_event", (d) => {
        const map = {
          received: `📥 התקבל קובץ: ${d.path}`,
          sent: `📤 נשלח: ${d.name}`,
          error: `⚠ שגיאת קובץ: ${d.reason}`,
        };
        if (map[d.kind]) pushToast(map[d.kind], d.kind === "error" ? "danger" : "default");
      }),
      on("alert", (d) =>
        pushToast(
          d.reason === "spam"
            ? "נדחו מספר בקשות חיבור ברצף. בקשות חדשות נחסמו לדקה."
            : "זוהו יותר מדי ניסיונות סיסמה שגויים. החיבורים נחסמו זמנית.",
          "danger"
        )
      ),
      on("ask_approval", (d) => setPendingAsk(d)),
      on("elevation_requested", (d) => setPendingElevation(d)),
      on("recent_updated", (d) => setState((s) => ({ ...s, recent: d.recent }))),
      on("embedded_update", (d) => setState((s) => ({ ...s, embedded: { ...s.embedded, ...d } }))),
    ];
    return () => offs.forEach((f) => f());
  }, []);

  if (!state) {
    return (
      <div className="app-shell">
        <div className="scroll-area" style={{ alignItems: "center", justifyContent: "center" }}>
          <span className="spinner" />
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { key: "main", label: "ראשי" },
          { key: "history", label: "יומן" },
          { key: "settings", label: "הגדרות" },
        ]}
      />
      <div className="scroll-area">
        {tab === "main" && <MainTab state={state} setState={setState} />}
        {tab === "history" && <HistoryTab />}
        {tab === "settings" && <SettingsTab state={state} setState={setState} />}
      </div>
      {pendingAsk && (
        <ApprovalModal
          info={pendingAsk}
          onDone={() => setPendingAsk(null)}
        />
      )}
      {pendingElevation && (
        <Modal title="בקשת הרשאות מנהל (UAC)" onClose={() => { callApi("respondElevation", false); setPendingElevation(null); }}>
          <p>
            הצד המרוחק (<span className="ltr">{pendingElevation.peer}</span>) מבקש להריץ פעולה בהרשאות מנהל במחשב הזה.
            אישור יציג את חלון ה-UAC הרגיל של Windows - עליכם לאשר אותו גם כן שם.
          </p>
          <div className="modal-actions">
            <Button variant="primary" onClick={() => { callApi("respondElevation", true); setPendingElevation(null); }}>
              אשר
            </Button>
            <Button variant="ghost" onClick={() => { callApi("respondElevation", false); setPendingElevation(null); }}>
              דחה
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
