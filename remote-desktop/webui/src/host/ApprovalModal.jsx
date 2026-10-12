import { useEffect, useState } from "react";
import { callApi } from "../bridge";
import { Button, Checkbox, Modal } from "../components/ui";

export function ApprovalModal({ info, onDone }) {
  const [control, setControl] = useState(true);
  const [clipboard, setClipboard] = useState(true);
  const [files, setFiles] = useState(true);
  const [left, setLeft] = useState(30);

  useEffect(() => {
    const t = setInterval(() => setLeft((l) => Math.max(0, l - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (left === 0) respond(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left]);

  async function respond(perms) {
    await callApi("respondApproval", info.requestId, perms);
    onDone();
  }

  return (
    <Modal title="בקשת חיבור" onClose={() => respond(null)}>
      <p>מישהו מבקש להתחבר למחשב שלך. לאפשר?</p>
      <div className="mt-2" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Checkbox label="אפשר שליטה (עכבר ומקלדת)" checked={control} onChange={(e) => setControl(e.target.checked)} />
        <Checkbox label="אפשר סנכרון לוח" checked={clipboard} onChange={(e) => setClipboard(e.target.checked)} />
        <Checkbox label="אפשר העברת קבצים" checked={files} onChange={(e) => setFiles(e.target.checked)} />
      </div>
      <p className="text-faint mt-2">בקשה תפוג אוטומטית בעוד {left} שניות</p>
      <div className="modal-actions">
        <Button
          variant="primary"
          onClick={() => respond({ control, clipboard, files, chat: true })}
        >
          אשר
        </Button>
        <Button variant="ghost" onClick={() => respond(null)}>
          דחה
        </Button>
      </div>
    </Modal>
  );
}
