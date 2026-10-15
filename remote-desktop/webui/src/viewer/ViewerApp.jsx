import { useEffect, useState } from "react";
import { on } from "../bridge";
import { ThemeToggle } from "../components/ui";
import { ConnectScreen } from "./ConnectScreen";
import { SessionScreen } from "./SessionScreen";

export default function ViewerApp() {
  const [connected, setConnected] = useState(null); // null = מסך חיבור; אובייקט = סשן פעיל

  useEffect(() => {
    const offs = [
      on("closed", (d) => setConnected(null)),
    ];
    return () => offs.forEach((f) => f());
  }, []);

  return (
    <div className="app-shell">
      {!connected && (
        <div style={{ position: "fixed", top: 10, insetInlineStart: 10, zIndex: 40 }}>
          <ThemeToggle />
        </div>
      )}
      {!connected ? (
        <ConnectScreen onConnected={setConnected} />
      ) : (
        <SessionScreen info={connected} onClosed={() => setConnected(null)} />
      )}
    </div>
  );
}
