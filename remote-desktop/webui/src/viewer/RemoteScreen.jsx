import { useEffect, useRef, useState } from "react";
import { callApi, on } from "../bridge";
import { Whiteboard } from "../components/Whiteboard";
import { keyName, shouldPreventDefault } from "./keymap";

const BUTTONS = { 0: "left", 1: "middle", 2: "right" };

export function RemoteScreen({ viewOnly, sessionId }) {
  const imgRef = useRef(null);
  const boxRef = useRef(null);
  const lastMoveRef = useRef(0);
  const [size, setSize] = useState({ w: 1, h: 1 });
  const [fps, setFps] = useState(0);
  const frameCountRef = useRef(0);
  const fpsClockRef = useRef(performance.now());
  const [drawing, setDrawing] = useState(false);
  const [strokes, setStrokes] = useState([]);

  useEffect(() => {
    const off = on("frame", (b64) => {
      const img = imgRef.current;
      if (!img) return;
      img.src = "data:image/jpeg;base64," + b64;
      frameCountRef.current += 1;
      const now = performance.now();
      if (now - fpsClockRef.current >= 1000) {
        setFps(frameCountRef.current);
        frameCountRef.current = 0;
        fpsClockRef.current = now;
      }
    });
    return off;
  }, []);

  useEffect(() => {
    const off = on("whiteboard", (d) => {
      const data = d?.data;
      if (!data) return;
      if (data.type === "clear") setStrokes([]);
      else setStrokes((s) => [...s, data]);
    });
    return off;
  }, []);

  function onStroke(stroke) {
    setStrokes((s) => [...s, stroke]);
    callApi("sendWhiteboard", stroke);
  }

  function clearWhiteboard() {
    setStrokes([]);
    callApi("sendWhiteboard", { type: "clear" });
  }

  function onImgLoad() {
    const img = imgRef.current;
    if (img && img.naturalWidth) setSize({ w: img.naturalWidth, h: img.naturalHeight });
  }

  // מחשבים את מלבן התמונה בפועל (object-fit: contain ממרכז עם "פסי קולנוע")
  function contentRect() {
    const box = boxRef.current;
    if (!box) return { x: 0, y: 0, w: 1, h: 1 };
    const bw = box.clientWidth;
    const bh = box.clientHeight;
    const s = Math.min(bw / size.w, bh / size.h);
    const w = size.w * s;
    const h = size.h * s;
    return { x: (bw - w) / 2, y: (bh - h) / 2, w, h };
  }

  function normPos(e) {
    const box = boxRef.current.getBoundingClientRect();
    const r = contentRect();
    const x = (e.clientX - box.left - r.x) / r.w;
    const y = (e.clientY - box.top - r.y) / r.h;
    return { x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
  }

  function send(ev) {
    if (!viewOnly) callApi("sendInput", ev);
  }

  function onMove(e) {
    const now = performance.now();
    if (now - lastMoveRef.current < 16) return; // ~60/שנייה
    lastMoveRef.current = now;
    const { x, y } = normPos(e);
    send({ t: "mm", x, y });
  }

  function onDown(e) {
    e.preventDefault();
    boxRef.current.focus();
    const { x, y } = normPos(e);
    send({ t: "md", b: BUTTONS[e.button] || "left", x, y });
  }

  function onUp(e) {
    const { x, y } = normPos(e);
    send({ t: "mu", b: BUTTONS[e.button] || "left", x, y });
  }

  function onWheel(e) {
    e.preventDefault();
    send({ t: "ms", dx: 0, dy: e.deltaY > 0 ? -1 : 1 });
  }

  function onKeyDown(e) {
    if (shouldPreventDefault(e)) e.preventDefault();
    const k = keyName(e);
    if (k) send({ t: "kd", k });
  }
  function onKeyUp(e) {
    const k = keyName(e);
    if (k) send({ t: "ku", k });
  }

  return (
    <div
      ref={boxRef}
      tabIndex={0}
      onMouseMove={onMove}
      onMouseDown={onDown}
      onMouseUp={onUp}
      onWheel={onWheel}
      onKeyDown={onKeyDown}
      onKeyUp={onKeyUp}
      onContextMenu={(e) => e.preventDefault()}
      style={{
        flex: 1,
        background: "#000",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        outline: "none",
        cursor: viewOnly ? "default" : "crosshair",
        overflow: "hidden",
      }}
    >
      <img
        ref={imgRef}
        onLoad={onImgLoad}
        alt=""
        draggable={false}
        style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", userSelect: "none", pointerEvents: "none" }}
      />
      {(() => {
        const r = contentRect();
        return (
          <div style={{ position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h }}>
            <Whiteboard active={drawing} strokes={strokes} onStroke={onStroke} />
          </div>
        );
      })()}
      <div
        className="ltr"
        style={{
          position: "absolute",
          bottom: 8,
          insetInlineStart: 8,
          background: "rgba(0,0,0,0.55)",
          color: "#fff",
          fontSize: 11,
          padding: "3px 8px",
          borderRadius: 6,
          display: "flex",
          gap: 8,
          alignItems: "center",
        }}
      >
        <span>{size.w}x{size.h} · {fps} FPS</span>
        {!viewOnly && (
          <>
            <button
              className={`btn btn-sm ${drawing ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setDrawing((d) => !d)}
              style={{ padding: "2px 8px" }}
            >
              {drawing ? "מצב שליטה" : "שיתוף סקיצות"}
            </button>
            {drawing && (
              <button className="btn btn-ghost btn-sm" onClick={clearWhiteboard} style={{ padding: "2px 8px" }}>
                נקה
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
