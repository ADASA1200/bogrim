import { useEffect, useRef, useState } from "react";
import { callApi, on } from "../bridge";
import { Button, Checkbox, Field, Input, pushToast } from "../components/ui";
import { Chat } from "../host/Chat";
import { RemoteScreen } from "./RemoteScreen";

export function SessionScreen({ info, onClosed }) {
  const [viewOnly, setViewOnly] = useState(!info.perms.control);
  const [perms, setPerms] = useState(info.perms);
  const [monitor, setMonitor] = useState(info.monitor);
  const [quality, setQuality] = useState("high");
  const [chatOpen, setChatOpen] = useState(false);
  const [chat, setChat] = useState([]);
  const [tunnelOpen, setTunnelOpen] = useState(false);
  const [tunnels, setTunnels] = useState([]);
  const [newLocalPort, setNewLocalPort] = useState("");
  const [newRemoteHost, setNewRemoteHost] = useState("127.0.0.1");
  const [newRemotePort, setNewRemotePort] = useState("");
  const rootRef = useRef(null);

  async function addTunnel() {
    const localPort = parseInt(newLocalPort, 10);
    const remotePort = parseInt(newRemotePort, 10);
    if (!Number.isInteger(localPort) || !Number.isInteger(remotePort)) {
      pushToast("פורט לא תקין.", "danger");
      return;
    }
    try {
      await callApi("startTunnel", localPort, newRemoteHost, remotePort);
      setTunnels((t) => [...t, { localPort, remoteHost: newRemoteHost, remotePort }]);
      setNewLocalPort("");
      setNewRemotePort("");
    } catch (e) {
      pushToast("פתיחת המעבר נכשלה: " + String(e?.message || e), "danger");
    }
  }

  async function removeTunnel(localPort) {
    await callApi("stopTunnel", localPort);
    setTunnels((t) => t.filter((x) => x.localPort !== localPort));
  }

  useEffect(() => {
    const offs = [
      on("chat", (d) => setChat((c) => [...c, { from: "them", text: d.text }])),
      on("perms_changed", (d) => {
        setPerms(d.perms);
        if (!d.perms.control) setViewOnly(true);
      }),
      on("closed", (d) => {
        pushToast("הסשן נסגר: " + (d.reason || ""), "danger");
        onClosed();
      }),
      on("file_event", (d) => {
        const map = {
          received: `התקבל קובץ: ${d.path}`,
          error: `שגיאת קובץ: ${d.reason}`,
          printed: "נשלחה הדפסה מהמחשב המרוחק למדפסת כאן.",
          print_failed: "התקבלה הדפסה מהמחשב המרוחק אך השליחה למדפסת נכשלה.",
        };
        if (map[d.kind]) pushToast(map[d.kind], d.kind === "error" || d.kind === "print_failed" ? "danger" : "default");
      }),
      on("elevate_result", (d) =>
        pushToast(
          d.ok ? "בקשת הרמת ההרשאות נשלחה - יש לאשר את חלון ה-UAC במחשב המרוחק." : "בקשת הרמת ההרשאות נדחתה או נכשלה.",
          d.ok ? "default" : "danger"
        )
      ),
    ];
    return () => offs.forEach((f) => f());
  }, [onClosed]);

  function setQualityAndSend(q) {
    setQuality(q);
    const presets = { high: [24, 1.0], mid: [15, 0.7], low: [8, 0.5] };
    const [fps, scale] = presets[q];
    callApi("setQuality", fps, scale);
  }

  async function disconnect() {
    await callApi("viewerDisconnect");
    onClosed();
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) rootRef.current.requestFullscreen?.();
    else document.exitFullscreen?.();
  }

  return (
    <div ref={rootRef} style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="titlebar" style={{ gap: 14 }}>
        <div className="titlebar-title grow">
          <span className="ltr">קוד אבטחה: {info.code}</span>
          <span className="text-faint">· {info.mode === "unattended" ? "גישה ללא נוכחות" : "באישור המשתמש"}</span>
        </div>
        <Checkbox label="צפייה בלבד" checked={viewOnly} disabled={!perms.control} onChange={(e) => setViewOnly(e.target.checked)} />
        {info.monitors?.length > 1 && (
          <select className="input" style={{ width: "auto" }} value={monitor} onChange={(e) => {
            const v = Number(e.target.value); setMonitor(v); callApi("setMonitor", v);
          }}>
            {info.monitors.map((m) => (
              <option key={m.index} value={m.index}>צג {m.index} ({m.width}x{m.height})</option>
            ))}
          </select>
        )}
        <select className="input" style={{ width: "auto" }} value={quality} onChange={(e) => setQualityAndSend(e.target.value)}>
          <option value="high">איכות: גבוהה</option>
          <option value="mid">איכות: בינונית</option>
          <option value="low">איכות: נמוכה</option>
        </select>
        <Button variant="ghost" size="sm" onClick={() => callApi("pickAndSendFile")} disabled={!perms.files}>שלח קובץ</Button>
        <Button variant="ghost" size="sm" onClick={() => setChatOpen((v) => !v)}>צ'אט</Button>
        <Button variant="ghost" size="sm" disabled={!perms.control} onClick={() => setTunnelOpen((v) => !v)}>
          מעבר פורט (TCP)
        </Button>
        <Button variant="ghost" size="sm" disabled={!perms.control} onClick={() => callApi("requestElevation")}>
          בקש הרמת הרשאות (UAC)
        </Button>
        <Button variant="ghost" size="sm" onClick={toggleFullscreen}>מסך מלא</Button>
        <Button variant="danger" size="sm" onClick={disconnect}>נתק</Button>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <RemoteScreen viewOnly={viewOnly} />
        {chatOpen && (
          <div style={{ width: 280, borderInlineStart: "1px solid var(--border-soft)", background: "var(--bg-elev-1)", padding: 14, display: "flex", flexDirection: "column" }}>
            <Chat
              messages={chat}
              onSend={async (text) => {
                await callApi("sendChat", text);
                setChat((c) => [...c, { from: "me", text }]);
              }}
            />
          </div>
        )}
        {tunnelOpen && (
          <div style={{ width: 280, borderInlineStart: "1px solid var(--border-soft)", background: "var(--bg-elev-1)", padding: 14, display: "flex", flexDirection: "column", gap: 10, overflowY: "auto" }}>
            <strong>מעבר פורט (TCP Tunneling)</strong>
            <p className="card-help">
              פותח פורט מקומי שמחבר, דרך הסשן המוצפן, לשירות TCP בצד המחשב המרוחק (RDP/SSH פנימי וכו').
            </p>
            <Field label="פורט מקומי">
              <Input dir="ltr" value={newLocalPort} onChange={(e) => setNewLocalPort(e.target.value)} />
            </Field>
            <Field label="כתובת היעד במחשב המרוחק">
              <Input dir="ltr" value={newRemoteHost} onChange={(e) => setNewRemoteHost(e.target.value)} />
            </Field>
            <Field label="פורט יעד">
              <Input dir="ltr" value={newRemotePort} onChange={(e) => setNewRemotePort(e.target.value)} />
            </Field>
            <Button variant="primary" size="sm" onClick={addTunnel}>פתח מעבר</Button>
            {tunnels.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {tunnels.map((t) => (
                  <div key={t.localPort} className="row-between">
                    <span className="text-sm ltr">127.0.0.1:{t.localPort} → {t.remoteHost}:{t.remotePort}</span>
                    <Button variant="ghost" size="sm" onClick={() => removeTunnel(t.localPort)}>סגור</Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
