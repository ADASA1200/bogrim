"""מריץ לולאת asyncio ב-thread רקע כדי לשלב עם tkinter."""
from __future__ import annotations

import asyncio
import threading


class AsyncRunner:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True, name="asyncio")
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, on_done=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        if on_done:
            fut.add_done_callback(on_done)
        return fut

    def call(self, fn, *a):
        self.loop.call_soon_threadsafe(fn, *a)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)   # בלי זה ה-thread יכול להמשיך לרוץ אחרי ש-stop() חזר
