import { useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, Checkbox, Field, Input, pushToast } from "../components/ui";

export function SettingsTab({ state, setState }) {
  return (
    <>
      <UnattendedCard state={state} setState={setState} />
      <ServerCard state={state} setState={setState} />
      <EmbeddedCard state={state} setState={setState} />
    </>
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
