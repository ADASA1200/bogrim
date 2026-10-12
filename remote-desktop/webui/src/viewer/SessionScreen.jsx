import { useEffect, useRef, useState } from "react";
import { callApi, on } from "../bridge";
import { Button, Checkbox, pushToast } from "../components/ui";
import { Chat } from "../host/Chat";
import { RemoteScreen } from "./RemoteScreen";

export function SessionScreen({ info, onClosed }) {
  const [viewOnly, setViewOnly] = useState(!info.perms.control);
  const [perms, setPerms] = useState(info.perms);
  const [monitor, setMonitor] = useState(info.monitor);
  const [quality, setQuality] = useState("high");
  const [chatOpen, setChatOpen] = useState(false);
  const [chat, setChat] = useState([]);
  const rootRef = useRef(null);

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
        const map = { received: `התקבל קובץ: ${d.path}`, error: `שגיאת קובץ: ${d.reason}` };
        if (map[d.kind]) pushToast(map[d.kind], d.kind === "error" ? "danger" : "default");
      }),
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
      </div>
    </div>
  );
}
