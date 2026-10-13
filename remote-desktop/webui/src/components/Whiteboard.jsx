import { useEffect, useRef } from "react";

// שכבת שיתוף סקיצות (כמו Whiteboard של AnyDesk): קנבס שקוף שמצטרף מעל
// הסשן. נקודות הקו מנורמלות (0..1) כדי שיתאימו לכל גודל קנבס בכל צד -
// בדיוק כמו קואורדינטות העכבר המרוחקות ב-RemoteScreen.
export function Whiteboard({ active, strokes, onStroke, color = "#ff3b30", width = 3 }) {
  const canvasRef = useRef(null);
  const drawingRef = useRef(null);

  function redraw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const s of strokes) drawStroke(ctx, s, canvas.width, canvas.height);
    if (drawingRef.current) drawStroke(ctx, drawingRef.current, canvas.width, canvas.height);
  }

  function drawStroke(ctx, s, w, h) {
    if (!s?.points || s.points.length < 2) return;
    ctx.strokeStyle = s.color || color;
    ctx.lineWidth = s.width || width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(s.points[0][0] * w, s.points[0][1] * h);
    for (const [x, y] of s.points.slice(1)) ctx.lineTo(x * w, y * h);
    ctx.stroke();
  }

  function resize() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    redraw();
  }

  useEffect(() => {
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(redraw, [strokes]); // eslint-disable-line react-hooks/exhaustive-deps

  function posFromEvent(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    return [
      Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
      Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
    ];
  }

  function onDown(e) {
    if (!active) return;
    e.preventDefault();
    drawingRef.current = { points: [posFromEvent(e)], color, width };
  }
  function onMove(e) {
    if (!active || !drawingRef.current) return;
    drawingRef.current.points.push(posFromEvent(e));
    redraw();
  }
  function onUp() {
    if (!active || !drawingRef.current) return;
    const stroke = { type: "stroke", ...drawingRef.current };
    drawingRef.current = null;
    onStroke(stroke);
  }

  return (
    <canvas
      ref={canvasRef}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={onUp}
      onMouseLeave={onUp}
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: active ? "auto" : "none",
        cursor: active ? "crosshair" : "default",
      }}
    />
  );
}
