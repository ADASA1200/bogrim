import { useEffect, useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, Checkbox, CopyButton, Field, Input, Pill, pushToast } from "../components/ui";

export function SettingsTab({ state, setState }) {
  return (
    <>
      <AccountCard />
      <RemotePrintingCard />
      <UnattendedCard state={state} setState={setState} />
      <TotpCard state={state} setState={setState} />
      <InteractiveAccessCard state={state} setState={setState} />
      <AccessControlCard state={state} setState={setState} />
      <ServerCard state={state} setState={setState} />
      <EmbeddedCard state={state} setState={setState} />
    </>
  );
}

function RemotePrintingCard() {
  const [state, setStateP] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    callApi("getPrintingState").then(setStateP);
  }, []);

  async function toggle() {
    setBusy(true);
    try {
      if (state.enabled) {
        await callApi("disableRemotePrinting");
        setStateP((s) => ({ ...s, enabled: false }));
        pushToast("הדפסה מרחוק כבויה.");
      } else {
        await callApi("enableRemotePrinting");
        setStateP((s) => ({ ...s, enabled: true }));
        pushToast("הדפסה מרחוק פעילה.");
      }
    } catch (e) {
      const code = String(e?.message || e);
      const msg = code === "install_failed_needs_admin"
        ? "ההפעלה נכשלה - ייתכן שצריך להריץ את RDesk כמנהל פעם אחת."
        : code === "not_supported" ? "התכונה נתמכת כרגע רק ב-Windows." : "ההפעלה נכשלה.";
      pushToast(msg, "danger");
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;

  return (
    <Card title="הדפסה מרחוק" right={<Pill tone={state.enabled ? "success" : "muted"}>{state.enabled ? "פעיל" : "כבוי"}</Pill>}>
      <p className="card-help">
        מאפשר להדפיס מהמחשב המרוחק (כשמתחברים אליו) ישירות למדפסת כאן. עובד ע"י מדפסת וירטואלית מקומית
        (משתמשת ב"Microsoft Print to PDF" הקיים של Windows) - נתמך רק ב-Windows, ועלול לדרוש הפעלת
        RDesk כמנהל פעם אחת כדי להתקין אותה.
      </p>
      {!state.supported ? (
        <Pill tone="muted">לא נתמך במערכת ההפעלה הזו</Pill>
      ) : (
        <Button variant={state.enabled ? "ghost" : "primary"} loading={busy} onClick={toggle}>
          {state.enabled ? "כבה" : "הפעל"}
        </Button>
      )}
    </Card>
  );
}

function AccountCard() {
  const [account, setAccount] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [newContactId, setNewContactId] = useState("");
  const [newContactLabel, setNewContactLabel] = useState("");

  async function reload() {
    const s = await callApi("getAccountState");
    setAccount(s);
    if (s.loggedIn) setContacts(await callApi("getAddressBook"));
  }

  useEffect(() => {
    reload();
  }, []);

  async function doRegister() {
    setBusy(true);
    try {
      const r = await callApi("registerAccount", username, password);
      setAccount({ loggedIn: true, username: r.username });
      setContacts(r.contacts || []);
      setPassword("");
      pushToast("החשבון נוצר ואתם מחוברים.");
    } catch (e) {
      pushToast("יצירת חשבון נכשלה: " + String(e?.message || e), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function doLogin() {
    setBusy(true);
    try {
      const r = await callApi("loginAccount", username, password);
      setAccount({ loggedIn: true, username: r.username });
      setContacts(r.contacts || []);
      setPassword("");
    } catch (e) {
      pushToast("התחברות נכשלה: " + String(e?.message || e), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function doLogout() {
    await callApi("logoutAccount");
    setAccount({ loggedIn: false, username: null });
    setContacts([]);
  }

  async function addContact() {
    const id = newContactId.replace(/\D/g, "");
    if (!id) return;
    const next = [...contacts, { id, label: newContactLabel || id }];
    try {
      await callApi("setAddressBook", next);
      setContacts(next);
      setNewContactId("");
      setNewContactLabel("");
    } catch (e) {
      pushToast("השמירה נכשלה: " + String(e?.message || e), "danger");
    }
  }

  async function removeContact(id) {
    const next = contacts.filter((c) => c.id !== id);
    await callApi("setAddressBook", next);
    setContacts(next);
  }

  if (!account) return null;

  return (
    <Card title="חשבון + פנקס כתובות משותף" right={<Pill tone={account.loggedIn ? "success" : "muted"}>{account.loggedIn ? `מחובר כ-${account.username}` : "לא מחובר"}</Pill>}>
      <p className="card-help">
        מסנכרן פנקס אנשי-קשר בין כל המכשירים שמתחברים לאותו שרת עם אותו חשבון. גרסה מצומצמת שרצה על שרת האיתות שלכם -
        לא שירות ענן בתשלום, בלי חיוב ובלי ניהול ארגון. דורש שרת איתות עצמאי (לא "המחשב הזה כשרת").
      </p>
      {!account.loggedIn ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Field label="שם משתמש">
            <Input dir="ltr" value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label="סיסמה">
            <Input type="password" dir="ltr" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <div className="row">
            <Button variant="primary" loading={busy} onClick={doLogin}>התחבר</Button>
            <Button variant="ghost" loading={busy} onClick={doRegister}>צור חשבון חדש</Button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {contacts.map((c) => (
              <div key={c.id} className="row-between">
                <span className="ltr">{c.label} - {c.id}</span>
                <Button variant="ghost" size="sm" onClick={() => removeContact(c.id)}>הסר</Button>
              </div>
            ))}
            {contacts.length === 0 && <div className="empty-state">הפנקס ריק</div>}
          </div>
          <div className="row">
            <Input dir="ltr" placeholder="מזהה" style={{ maxWidth: 140 }} value={newContactId} onChange={(e) => setNewContactId(e.target.value)} />
            <Input placeholder="תווית" value={newContactLabel} onChange={(e) => setNewContactLabel(e.target.value)} />
            <Button variant="primary" size="sm" onClick={addContact}>הוסף</Button>
          </div>
          <Button variant="ghost" size="sm" onClick={doLogout}>התנתק מהחשבון</Button>
        </div>
      )}
    </Card>
  );
}

function UnattendedCard({ state, setState }) {
  const u = state.unattended;
  const [enabled, setEnabled] = useState(u.enabled);
  const [password, setPassword] = useState("");
  const [control, setControl] = useState(u.control);
  const [clipboard, setClipboard] = useState(u.clipboard);
  const [files, setFiles] = useState(u.files);
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!enabled) {
      await callApi("setUnattended", { enabled: false });
      setState((s) => ({ ...s, unattended: { ...s.unattended, enabled: false } }));
      pushToast("ההגדרות נשמרו.");
      return;
    }
    if (password && password.length < 8) {
      pushToast("הסיסמה הקבועה חייבת להכיל לפחות 8 תווים.", "danger");
      return;
    }
    if (!password && !u.hasKey) {
      pushToast("כדי להפעיל גישה ללא נוכחות יש להגדיר סיסמה קבועה.", "danger");
      return;
    }
    if (password) {
      const ok = window.confirm(
        "מי שיודע את המזהה ואת הסיסמה הקבועה יוכל להתחבר למחשב הזה בלי אישור.\n" +
          "השתמשו בסיסמה ארוכה וייחודית, ושתפו אותה רק עם מי שבוטחים בו.\n\nלהפעיל?"
      );
      if (!ok) return;
    }
    setSaving(true);
    try {
      await callApi("setUnattended", { enabled: true, password: password || null, control, clipboard, files });
      setState((s) => ({ ...s, unattended: { enabled: true, hasKey: true, control, clipboard, files } }));
      setPassword("");
      pushToast("ההגדרות נשמרו.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="גישה ללא נוכחות (חיבור בלי אישור)">
      <Checkbox label="אפשר חיבור ללא אישור באמצעות סיסמה קבועה" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
      <div className="mt-2">
        <Field label="סיסמה קבועה">
          <Input type="password" dir="ltr" placeholder={u.hasKey ? "•••••••• (קיימת - השאירו ריק כדי לא לשנות)" : ""} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
      </div>
      <div className="row mt-2" style={{ gap: 16, flexWrap: "wrap" }}>
        <Checkbox label="קבצים" checked={files} onChange={(e) => setFiles(e.target.checked)} />
        <Checkbox label="לוח" checked={clipboard} onChange={(e) => setClipboard(e.target.checked)} />
        <Checkbox label="שליטה" checked={control} onChange={(e) => setControl(e.target.checked)} />
      </div>
      <Button variant="primary" className="mt-2" loading={saving} onClick={save}>שמור</Button>
      <p className="card-help">
        מי שיודע את המזהה ואת הסיסמה הקבועה יוכל להתחבר למחשב הזה בלי אישור. השתמשו בסיסמה ארוכה וייחודית, ושתפו אותה רק עם מי שבוטחים בו.
      </p>
    </Card>
  );
}

function TotpCard({ state, setState }) {
  const totpEnabled = state.unattended.totpEnabled;
  const [secret, setSecret] = useState(null);
  const [busy, setBusy] = useState(false);

  async function enable() {
    if (!state.unattended.hasKey) {
      pushToast("אימות דו-שלבי דורש שתהיה מוגדרת סיסמת גישה ללא-נוכחות.", "danger");
      return;
    }
    setBusy(true);
    try {
      const r = await callApi("setTotp", true);
      setSecret(r.secret);
      setState((s) => ({ ...s, unattended: { ...s.unattended, totpEnabled: true } }));
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    try {
      await callApi("setTotp", false);
      setSecret(null);
      setState((s) => ({ ...s, unattended: { ...s.unattended, totpEnabled: false } }));
      pushToast("אימות דו-שלבי כבוי.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="אימות דו-שלבי (TOTP) לגישה ללא-נוכחות" right={<Pill tone={totpEnabled ? "success" : "muted"}>{totpEnabled ? "מופעל" : "כבוי"}</Pill>}>
      <p className="card-help">
        מוסיף קוד בן 6 ספרות שמתחלף כל 30 שניות (כמו Google Authenticator) שחייבים להקליד בנוסף לסיסמה הקבועה.
        מחייב שתהיה מוגדרת סיסמת גישה ללא-נוכחות.
      </p>
      {secret && (
        <div className="mt-2" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <p className="text-faint">הזינו את המפתח הזה באפליקציית האימות שלכם (מוצג פעם אחת בלבד):</p>
          <div className="row-between">
            <span className="ltr id-display" style={{ fontSize: 16 }}>{secret}</span>
            <CopyButton text={secret} />
          </div>
        </div>
      )}
      <Button variant={totpEnabled ? "ghost" : "primary"} className="mt-2" loading={busy} onClick={totpEnabled ? disable : enable}>
        {totpEnabled ? "כבה אימות דו-שלבי" : "הפעל אימות דו-שלבי"}
      </Button>
    </Card>
  );
}

function InteractiveAccessCard({ state, setState }) {
  const [mode, setMode] = useState(state.interactiveMode || "always");
  const [saving, setSaving] = useState(false);

  async function save(next) {
    setMode(next);
    setSaving(true);
    try {
      await callApi("setInteractiveMode", next);
      setState((s) => ({ ...s, interactiveMode: next }));
      pushToast("ההגדרה נשמרה.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="מצב בקשת-אישור לחיבור אינטראקטיבי">
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label className="checkrow">
          <input type="radio" name="interactive-mode" checked={mode === "always"} disabled={saving} onChange={() => save("always")} />
          תמיד להציג בקשת אישור
        </label>
        <label className="checkrow">
          <input type="radio" name="interactive-mode" checked={mode === "window_open"} disabled={saving} onChange={() => save("window_open")} />
          להציג רק כשהחלון פתוח (לא מוסתר למגש)
        </label>
        <label className="checkrow">
          <input type="radio" name="interactive-mode" checked={mode === "never"} disabled={saving} onChange={() => save("never")} />
          לעולם לא - רק גישה ללא-נוכחות עם סיסמה
        </label>
      </div>
      <p className="card-help">כמו ה-Interactive Access של AnyDesk. לא משפיע על גישה ללא-נוכחות ועל מכשירים מהימנים.</p>
    </Card>
  );
}

function AccessControlCard({ state, setState }) {
  const [text, setText] = useState((state.ipWhitelist || []).join("\n"));
  const [saving, setSaving] = useState(false);

  async function save() {
    const entries = text.split("\n").map((s) => s.trim()).filter(Boolean);
    setSaving(true);
    try {
      await callApi("setIpWhitelist", entries);
      setState((s) => ({ ...s, ipWhitelist: entries }));
      pushToast(entries.length ? "רשימת ה-IP המורשים נשמרה." : "הסרת ההגבלה - כל כתובת IP מורשית.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="בקרת גישה: רשימת IP מורשים">
      <Field label="כתובת IP אחת (או רשת CIDR) בכל שורה - שורה ריקה = בלי הגבלה">
        <textarea
          className="input"
          dir="ltr"
          rows={4}
          placeholder={"192.168.1.42\n10.0.0.0/24"}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <Button variant="primary" className="mt-2" loading={saving} onClick={save}>שמור</Button>
      <p className="card-help">
        כשמוגדרת רשימה, חיבורים מכתובות שלא ברשימה נדחים לפני כל בקשת אישור - גם אם המזהה והסיסמה נכונים.
      </p>
    </Card>
  );
}

function ServerCard({ state, setState }) {
  const [server, setServer] = useState(state.server);
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await callApi("setServer", server);
      setState((s) => ({ ...s, server }));
      pushToast("הכתובת נשמרה. היא תיכנס לתוקף אחרי הפעלה מחדש של התוכנה.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Card title="שרת">
      <Field label="כתובת שרת האיתות">
        <Input dir="ltr" value={server} onChange={(e) => setServer(e.target.value)} />
      </Field>
      <Button variant="primary" className="mt-2" loading={saving} onClick={save}>שמור</Button>
    </Card>
  );
}

function EmbeddedCard({ state, setState }) {
  const e0 = state.embedded;
  const [enabled, setEnabled] = useState(e0.enabled);
  const [port, setPort] = useState(String(e0.port || 8765));
  const [saving, setSaving] = useState(false);

  async function save() {
    const p = parseInt(port, 10);
    if (!Number.isInteger(p) || p < 1 || p > 65535) {
      pushToast("הפורט צריך להיות מספר בין 1 ל-65535.", "danger");
      return;
    }
    setSaving(true);
    try {
      await callApi("setEmbedded", { enabled, port: p });
      pushToast("ההגדרה נשמרה. היא תיכנס לתוקף אחרי הפעלה מחדש של התוכנה.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="המחשב הזה כשרת (בלי שרת נפרד)">
      <Checkbox label="הפוך את המחשב הזה גם לשרת האיתות" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
      <div className="mt-2">
        <Field label="פורט">
          <Input dir="ltr" style={{ maxWidth: 120 }} value={port} onChange={(e) => setPort(e.target.value)} />
        </Field>
      </div>
      <p className="card-help">
        כשזה מופעל, אין צורך בשרת נפרד: המחשב הזה משמש גם כנקודת ההכרות בין שני הצדדים.
        החיבור עצמו (וידאו, קלט, קבצים) תמיד ישיר ומוצפן בין שני המחשבים.
        לחיבור באותה רשת (בית/משרד) זה עובד מיד. לחיבור מהאינטרנט צריך להגדיר הפניית פורט
        (Port Forwarding) בנתב של המחשב הזה אל הפורט שלמעלה, ולתת לצד השני את ה-IP הציבורי.
      </p>
      <Button variant="primary" className="mt-1" loading={saving} onClick={save}>שמור</Button>
    </Card>
  );
}
