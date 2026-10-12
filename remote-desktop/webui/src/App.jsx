import { useEffect, useState } from "react";
import HostApp from "./host/HostApp";
import ViewerApp from "./viewer/ViewerApp";
import { ToastHost } from "./components/ui";

function readMode() {
  return window.location.hash === "#viewer" ? "viewer" : "host";
}

export default function App() {
  const [mode, setMode] = useState(readMode());
  useEffect(() => {
    const onHash = () => setMode(readMode());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return (
    <>
      {mode === "viewer" ? <ViewerApp /> : <HostApp />}
      <ToastHost />
    </>
  );
}
