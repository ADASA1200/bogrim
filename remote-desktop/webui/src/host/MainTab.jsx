import { useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, Checkbox, CopyButton, Field, Input, Pill, pushToast } from "../components/ui";
import { Chat } from "./Chat";
import { reasonText } from "./HostApp";

function formatId(id) {
  return (id || "").match(/.{1,3}/g)?.join(" ") || id;
}

export function MainTab({ state, setState }) {
  const [connectId, setConnectId] = useState("");
  const [connectPw, setConnectPw] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [creatingInvite, setCreatingInvite] = useState(false);

  async function makeInvite() {
    setCreatingInvite(true);
    try {
      const r = await callApi("createInviteLink", 10);
      setInviteUrl(r.url);
      pushToast(`נוצר קישור הזמנה חד-פעמי, בתוקף ל-${r.expiresInMinutes} דקות.`);
    } finally {
      setCreatingInvite(false);
    }
  }

  async function openViewer() {
    const id = connectId.replace(/\D/g, "");
    if (!id) {
      setConnectError("יש להזין את המזהה של המחשב המרוחק");
      return;
    }
    if (id === state.id) {
      setConnectError("לא ניתן להתחבר למחשב הזה עצמו");
      return;
    }
    setConnecting(true);
    setConnectError("");
    try {
      await callApi("openViewer", id, connectPw);
      setConnectPw("");
      const fresh = await callApi("getState");
      setState(fresh);
    } catch (e) {
      setConnectError(reasonText(String(e)));
    } finally {
      setConnecting(false);
    }
  }

  return (
    <>
      <Card title="המחשב הזה">
        <div className="row-between">
          <span className="id-display">{formatId(state.id)}</span>
          <CopyButton text={state.id} title="העתק מזהה" />
        </div>
        <div className="mt-2">
          <Pill tone={state.online ? "success" : "danger"}>
            {state.online ? "מחובר לשרת - מוכן לקבל חיבורים" : "אין חיבור לשרת, מנסה שוב..."}
          </Pill>
        </div>
        <p className="card-help">חיבור עם הסיסמה הזמנית דורש את אישורך בכל פעם.</p>
        <div className="mt-2">
          <Button variant="ghost" size="sm" loading={creatingInvite} onClick={makeInvite}>
            צור קישור הזמנה לסשן
          </Button>
          {inviteUrl && (
            <div className="row-between mt-1">
              <span className="text-sm ltr" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{inviteUrl}</span>
              <CopyButton text={inviteUrl} />
            </div>
          )}
          {inviteUrl && (
            <p className="card-help">
              קישור חד-פעמי, בתוקף ל-10 דקות - פתיחתו מתחברת אוטומטית בלי אישור ובלי סיסמה. שתפו רק עם מי שבוטחים בו.
            </p>
          )}
        </div>
      </Card>

      {state.embedded?.enabled && (
        <Card title="המחשב הזה כשרת (בלי שרת נפרד)">
          <Pill tone={state.embedded.port ? "success" : "warn"}>
            {state.embedded.port ? `שרת מוטבע רץ בפורט ${state.embedded.port}` : "מפעיל..."}
          </Pill>
          <div className="mt-2" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row-between">
              <span className="text-sm ltr">{state.embedded.lanIp ? `ws://${state.embedded.lanIp}:${state.embedded.port}` : "—"}</span>
              <CopyButton text={state.embedded.lanIp ? `ws://${state.embedded.lanIp}:${state.embedded.port}` : ""} title="העתק (רשת מקומית)" />
            </div>
            <div className="row-between">
              <span className="text-sm ltr">{state.embedded.publicIp ? `ws://${state.embedded.publicIp}:${state.embedded.port}` : "לא זוהה IP ציבורי"}</span>
              <CopyButton text={state.embedded.publicIp ? `ws://${state.embedded.publicIp}:${state.embedded.port}` : ""} title="העתק (אינטרנט)" disabled={!state.embedded.publicIp} />
            </div>
          </div>
        </Card>
      )}

      <Card title="התחברות למחשב אחר">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Field label="מזהה">
            <Input placeholder="123 456 789" dir="ltr" value={connectId} onChange={(e) => setConnectId(e.target.value)} />
          </Field>
          <Field label="סיסמה (אופציונלי)">
            <Input type="password" dir="ltr" value={connectPw} onChange={(e) => setConnectPw(e.target.value)} />
          </Field>
          <p className="card-help">
            בלי סיסמה - המשתמש במחשב המרוחק יתבקש לאשר את החיבור. עם סיסמת גישה ללא נוכחות (אם הוגדרה שם) - החיבור יתבצע בלי אישור.
          </p>
          {connectError && <p className="text-sm" style={{ color: "var(--danger)" }}>{connectError}</p>}
          <Button variant="primary" className="btn-block" loading={connecting} onClick={openViewer}>
            התחבר
          </Button>
          {state.recent?.length > 0 && (
            <div className="recent-list mt-1">
              {state.recent.map((id) => (
                <div key={id} className="recent-item" onClick={() => setConnectId(id)}>
                  {formatId(id)}
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card title="סשן פעיל" right={state.session && <Pill tone="danger">מחובר כעת</Pill>}>
        {!state.session ? (
          <div className="empty-state">אין חיבור פעיל</div>
        ) : (
          <SessionPanel state={state} setState={setState} />
        )}
      </Card>
    </>
  );
}

function SessionPanel({ state, setState }) {
  const { session } = state;

  async function togglePerm(key, value) {
    await callApi("setPermission", key, value);
    setState((s) => ({ ...s, session: { ...s.session, perms: { ...s.session.perms, [key]: value } } }));
  }

  async function disconnect() {
    await callApi("disconnect");
  }

  async function sendFile() {
    await callApi("pickAndSendFile");
  }

  async function togglePrivacy() {
    const next = !session.privacy;
    await callApi("setPrivacyMode", next);
    setState((s) => ({ ...s, session: { ...s.session, privacy: next } }));
  }

  return (
    <>
      {session.mode === "unattended" && <Pill tone="warn">גישה ללא נוכחות (ללא אישור)</Pill>}
      {session.mode === "trusted" && <Pill tone="success">מכשיר מהימן (אושר אוטומטית)</Pill>}
      {session.mode === "invite" && <Pill tone="success">התחבר עם קישור הזמנה</Pill>}
      <p className="text-faint mt-1">קוד אבטחה: {session.code}</p>
      <div className="row mt-2" style={{ gap: 16, flexWrap: "wrap" }}>
        <Checkbox label="קבצים" checked={session.perms.files} onChange={(e) => togglePerm("files", e.target.checked)} />
        <Checkbox label="לוח" checked={session.perms.clipboard} onChange={(e) => togglePerm("clipboard", e.target.checked)} />
        <Checkbox label="שליטה" checked={session.perms.control} onChange={(e) => togglePerm("control", e.target.checked)} />
      </div>
      <div className="row mt-2">
        <Button variant="ghost" onClick={sendFile}>שלח קובץ</Button>
        <Button variant={session.privacy ? "primary" : "ghost"} onClick={togglePrivacy}>
          {session.privacy ? "כבה מצב פרטיות" : "מצב פרטיות"}
        </Button>
        <Button variant="danger" onClick={disconnect}>נתק</Button>
      </div>
      {session.privacy && (
        <p className="text-faint mt-1">
          המסך הפיזי כאן חסום והקלדה/עכבר מקומיים כבויים - הצופה המרוחק ממשיך לראות ולשלוט כרגיל.
        </p>
      )}
      <Chat
        messages={session.chat}
        onSend={async (text) => {
          await callApi("sendChat", text);
          setState((s) => ({ ...s, session: { ...s.session, chat: [...s.session.chat, { from: "me", text }] } }));
        }}
      />
    </>
  );
}
