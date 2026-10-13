import { useEffect, useState } from "react";
import { callApi } from "../bridge";
import { Button, Card, pushToast } from "../components/ui";

const MODE_LABEL = { interactive: "אישור ידני", unattended: "ללא נוכחות", trusted: "מכשיר מהימן", invite: "קישור הזמנה" };

function formatId(id) {
  return (id || "").match(/.{1,3}/g)?.join(" ") || id;
}

function fmtTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString("he-IL") : "—";
}

function fmtDuration(start, end) {
  if (!end) return "פעיל כרגע";
  const sec = Math.max(0, Math.round(end - start));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m ? `${m} דק' ${s} שנ'` : `${s} שניות`;
}

export function HistoryTab() {
  const [log, setLog] = useState(null);
  const [trusted, setTrusted] = useState(null);

  async function reload() {
    const [l, t] = await Promise.all([callApi("getConnectionLog"), callApi("getTrustedDevices")]);
    setLog(l);
    setTrusted(t);
  }

  useEffect(() => {
    reload();
  }, []);

  async function clearLog() {
    if (!window.confirm("לנקות את כל יומן החיבורים?")) return;
    await callApi("clearConnectionLog");
    setLog([]);
    pushToast("היומן נוקה.");
  }

  async function removeTrust(peer) {
    await callApi("removeTrustedDevice", peer);
    setTrusted((t) => t.filter((d) => d.peer !== peer));
    pushToast("האמון בוטל - החיבור הבא ממזהה זה יבקש אישור.");
  }

  if (!log || !trusted) {
    return (
      <Card title="יומן חיבורים">
        <span className="spinner" />
      </Card>
    );
  }

  return (
    <>
      <Card title="מכשירים מהימנים" right={<span className="text-faint">{trusted.length}</span>}>
        {trusted.length === 0 ? (
          <div className="empty-state">
            אין עדיין מכשירים מהימנים. אפשר לסמן "זכור מכשיר זה" בחלון בקשת החיבור בפעם הבאה שמישהו מתחבר.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {trusted.map((d) => (
              <div key={d.peer} className="row-between">
                <span className="ltr">{formatId(d.peer)}</span>
                <Button variant="ghost" size="sm" onClick={() => removeTrust(d.peer)}>
                  הסר אמון
                </Button>
              </div>
            ))}
          </div>
        )}
        <p className="card-help">
          מכשיר מהימן מתחבר בלי בקשת אישור, עם ההרשאות שסומנו כשסומן "זכור". ניתן לבטל את האמון בכל רגע כאן.
        </p>
      </Card>

      <Card
        title="יומן חיבורים"
        right={
          <Button variant="ghost" size="sm" onClick={clearLog} disabled={log.length === 0}>
            נקה יומן
          </Button>
        }
      >
        {log.length === 0 ? (
          <div className="empty-state">עדיין אין חיבורים מתועדים.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {log.map((e, i) => (
              <div key={i} className="row-between">
                <div>
                  <div className="ltr">{formatId(e.peer)}</div>
                  <div className="text-faint">
                    {fmtTime(e.startedAt)} · {fmtDuration(e.startedAt, e.endedAt)}
                  </div>
                </div>
                <span className="text-faint">{MODE_LABEL[e.mode] || e.mode}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
