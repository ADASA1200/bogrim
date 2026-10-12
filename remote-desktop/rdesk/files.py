"""העברת קבצים דו-כיוונית על ערוץ נתונים ייעודי (מוצפן ב-DTLS)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from pathlib import Path

from . import protocol as P


def safe_name(name: str) -> str:
    """מונע path traversal: משאיר שם קובץ בלבד."""
    name = os.path.basename(str(name).replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", name).strip(". ")
    return name or "file"


class FileTransfer:
    """שולח וקולט קבצים. הפרוטוקול: JSON {"op":"start",...} -> בינארי... -> {"op":"end"}."""

    def __init__(self, channel, download_dir: Path, enabled=lambda: True, on_event=None):
        self.ch = channel
        self.dir = Path(download_dir)
        self.enabled = enabled
        self.on_event = on_event or (lambda kind, **kw: None)
        self._fh = None
        self._expected = 0
        self._got = 0
        self._path: Path | None = None
        self._open_name = ""
        channel.on("message", self._on_message)

    # ---- קליטה ----
    def _on_message(self, msg) -> None:
        if isinstance(msg, (bytes, bytearray)):
            if self._fh is None:
                return
            self._got += len(msg)
            if self._got > self._expected:
                self._abort("file larger than announced")
                return
            self._fh.write(msg)
            self.on_event("progress", name=self._open_name, done=self._got, total=self._expected)
            return
        try:
            m = json.loads(msg)
        except ValueError:
            return
        op = m.get("op")
        if op == "start":
            self._abort_silent()
            if not self.enabled():
                self._send({"op": "denied", "reason": "file transfer not allowed"})
                return
            size = int(m.get("size", -1))
            if not 0 <= size <= P.MAX_FILE_BYTES:
                self._send({"op": "denied", "reason": "bad size"})
                return
            self.dir.mkdir(parents=True, exist_ok=True)
            name = safe_name(m.get("name"))
            path = self.dir / name
            while path.exists():
                path = self.dir / f"{path.stem}-{secrets.token_hex(2)}{path.suffix}"
            self._fh = open(path, "wb")
            self._path, self._open_name = path, name
            self._expected, self._got = size, 0
            self.on_event("incoming", name=name, total=size)
        elif op == "end":
            if self._fh is None:
                return
            ok = self._got == self._expected
            self._fh.close(); self._fh = None
            if ok:
                self.on_event("received", name=self._open_name, path=str(self._path))
            else:
                self._path.unlink(missing_ok=True)
                self.on_event("error", name=self._open_name, reason="incomplete")
        elif op == "denied":
            self.on_event("error", name="", reason=m.get("reason", "denied"))

    def _abort(self, reason: str) -> None:
        name = self._open_name
        self._abort_silent()
        self.on_event("error", name=name, reason=reason)

    def _abort_silent(self) -> None:
        if self._fh is not None:
            self._fh.close(); self._fh = None
            if self._path:
                self._path.unlink(missing_ok=True)

    def close(self) -> None:
        self._abort_silent()

    # ---- שליחה ----
    def _send(self, obj: dict) -> None:
        if self.ch.readyState == "open":
            self.ch.send(json.dumps(obj))

    async def send_file(self, path: str) -> None:
        p = Path(path)
        size = p.stat().st_size
        if size > P.MAX_FILE_BYTES:
            raise ValueError("file too large")
        self._send({"op": "start", "name": p.name, "size": size})
        sent = 0
        loop = asyncio.get_running_loop()
        with open(p, "rb") as f:
            while True:
                chunk = await loop.run_in_executor(None, f.read, P.FILE_CHUNK)
                if not chunk:
                    break
                while self.ch.bufferedAmount > 1_000_000:  # backpressure
                    await asyncio.sleep(0.01)
                if self.ch.readyState != "open":
                    raise ConnectionError("channel closed")
                self.ch.send(chunk)
                sent += len(chunk)
                self.on_event("sending", name=p.name, done=sent, total=size)
        self._send({"op": "end"})
        self.on_event("sent", name=p.name)
