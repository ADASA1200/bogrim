"""לכידת מסך ושידורו כטראק וידאו של WebRTC."""
from __future__ import annotations

import asyncio
import fractions
import time
from concurrent.futures import ThreadPoolExecutor

import av
import numpy as np
from aiortc import VideoStreamTrack

VIDEO_CLOCK = 90000


class MssScreen:
    """לכידה אמיתית בעזרת mss (Windows / macOS / Linux-X11)."""

    def __init__(self) -> None:
        self._sct = None

    def _get(self):
        if self._sct is None:
            import mss  # נטען בעצלתיים - צריך להיווצר באותו thread שמשתמש בו
            self._sct = mss.mss()
        return self._sct

    def monitors(self) -> list[dict]:
        mons = self._get().monitors
        return [
            {"index": i, "left": m["left"], "top": m["top"],
             "width": m["width"], "height": m["height"]}
            for i, m in enumerate(mons) if i >= 1
        ] or [{"index": 0, "left": mons[0]["left"], "top": mons[0]["top"],
               "width": mons[0]["width"], "height": mons[0]["height"]}]

    def grab(self, index: int) -> np.ndarray:
        sct = self._get()
        mons = sct.monitors
        if index >= len(mons):
            index = 1 if len(mons) > 1 else 0
        shot = sct.grab(mons[index])
        return np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)


class SyntheticScreen:
    """מסך מלאכותי לבדיקות (ללא תצוגה גרפית)."""

    def __init__(self, width: int = 640, height: int = 360) -> None:
        self.w, self.h, self.n = width, height, 0

    def monitors(self) -> list[dict]:
        return [{"index": 1, "left": 0, "top": 0, "width": self.w, "height": self.h}]

    def grab(self, index: int) -> np.ndarray:
        self.n += 1
        img = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        img[..., 3] = 255
        x = (self.n * 8) % self.w
        img[:, :, 2] = np.linspace(0, 255, self.w, dtype=np.uint8)[None, :]
        img[:, max(0, x - 8):x, :3] = 255
        return img


class ScreenTrack(VideoStreamTrack):
    """שולח את המסך כווידאו. ניתן לשנות fps, קנה מידה וצג תוך כדי סשן."""

    kind = "video"

    def __init__(self, screen, fps: int = 20, scale: float = 1.0, monitor: int = 1):
        super().__init__()
        self.screen = screen
        self.fps = fps
        self.scale = scale
        self.monitor = monitor
        self.paused = False
        self._mons: list[dict] = []
        self._t0: float | None = None
        self._next = 0.0
        # thread יחיד: mss דורש שכל הקריאות יהיו מאותו thread
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")

    async def refresh_monitors(self) -> list[dict]:
        """קורא את רשימת הצגים מה-thread של הלכידה (דרישת mss ב-Windows)."""
        self._mons = await asyncio.get_running_loop().run_in_executor(
            self._pool, self.screen.monitors)
        if self.monitor not in {m["index"] for m in self._mons}:
            self.monitor = self._mons[0]["index"]
        return self._mons

    def monitors(self) -> list[dict]:
        return self._mons

    def current_geometry(self) -> dict | None:
        for m in self._mons:
            if m["index"] == self.monitor:
                return m
        return None

    def _grab_scaled(self) -> av.VideoFrame:
        arr = self.screen.grab(self.monitor)
        frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="bgra")
        h, w = arr.shape[:2]
        nw = max(2, int(w * self.scale) // 2 * 2)
        nh = max(2, int(h * self.scale) // 2 * 2)
        return frame.reformat(width=nw, height=nh, format="yuv420p")

    async def recv(self) -> av.VideoFrame:
        loop = asyncio.get_running_loop()
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        delay = self._next - now
        if delay > 0:
            await asyncio.sleep(delay)
        self._next = max(now, self._next) + 1.0 / max(1, self.fps)
        frame = await loop.run_in_executor(self._pool, self._grab_scaled)
        frame.pts = int((time.monotonic() - self._t0) * VIDEO_CLOCK)
        frame.time_base = fractions.Fraction(1, VIDEO_CLOCK)
        return frame

    def stop(self) -> None:
        super().stop()
        self._pool.shutdown(wait=False)
