"""צד הצופה: המחשב ששולט. מתחבר לפי מזהה וסיסמה, מקבל וידאו ושולח קלט."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable

import websockets
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

from . import config, protocol as P
from .clipboard import Clipboard
from .files import FileTransfer
from .host import make_rtc_config
from .tunnel import TunnelViewer

log = logging.getLogger("rdesk.viewer")


class ConnectError(Exception):
    pass


class ViewerClient:
    def __init__(
        self,
        server_url: str,
        on_event: Callable[..., None] | None = None,
        clipboard=None,
        download_dir: Path | str = Path.home() / "RDesk" / "Received",
        rtc_config: RTCConfiguration | None = None,
    ) -> None:
        self.server_url = server_url
        self.on_event = on_event or (lambda kind, **kw: None)
        self.clipboard = clipboard or Clipboard()
        self.download_dir = Path(download_dir)
        self.rtc_config = rtc_config or make_rtc_config()
        self.pc: RTCPeerConnection | None = None
        self.control = None
        self.files: FileTransfer | None = None
        self.tunnel: TunnelViewer | None = None
        self._tunnel_ch = None
        self.latest_frame = None       # numpy RGB אחרון
        self.frame_seq = 0
        self.monitors: list[dict] = []
        self.monitor = 1
        self.perms = P.Permissions()
        self.connected = False
        self.mode = "interactive"
        self.code = ""
        self._tasks: list[asyncio.Task] = []
        self._hello = asyncio.Event()
        self._last_clip: str | None = None

    # ------------------------------------------------------------ חיבור
    async def connect(self, host_id: str, password: str = "", totp: str = "", invite: str = "",
                      timeout: float = 90) -> None:
        """password אופציונלי: סיסמת גישה ללא נוכחות. בלעדיה ממתינים לאישור המשתמש.
        totp: קוד דו-שלבי, רק אם המארח הגדיר שהוא נדרש בנוסף לסיסמה.
        invite: token חד-פעמי מקישור הזמנה לסשן - עוקף גם אישור וגם סיסמה."""
        host_id = P.clean_id(host_id)
        # מזהה קבוע (לא אקראי-חדש-בכל-חיבור) - כדי שמארח יוכל "לזכור" את הצופה
        # הזה בין התחברויות (אמון תמידי למזהה ספציפי).
        me = config.viewer_identity(config.load())
        async with websockets.connect(self.server_url, max_size=P.MAX_SIGNAL_BYTES) as ws:
            await ws.send(P.dumps({"type": "register", "id": me}))
            await self._expect(ws, "registered", 10)

            async def send(payload):
                await ws.send(P.dumps({"type": "relay", "to": host_id, "payload": payload}))

            await send({"kind": "hello"})
            ch = await self._next_payload(ws, 10)
            if ch.get("kind") == "reject":
                raise ConnectError(ch.get("reason", "rejected"))
            if ch.get("kind") != "challenge":
                raise ConnectError("protocol error")
            nonce = str(ch["nonce"])
            key = (await asyncio.get_running_loop().run_in_executor(None, P.derive_key, password)
                   if password else None)

            pc = RTCPeerConnection(self.rtc_config)
            self.pc = pc
            pc.addTransceiver("video", direction="recvonly")
            self.control = pc.createDataChannel("control")
            files_ch = pc.createDataChannel("files")
            self.files = FileTransfer(
                files_ch, self.download_dir, enabled=lambda: self.perms.files,
                on_event=lambda kind, **kw: self.on_event("file_" + kind, **kw))
            self.control.on("message", self._on_control)

            tunnel_ch = pc.createDataChannel("tunnel")
            self._tunnel_ch = tunnel_ch

            def send_if_open(data):
                if tunnel_ch.readyState == "open":
                    tunnel_ch.send(data)
            self.tunnel = TunnelViewer(send_text=send_if_open, send_binary=send_if_open)
            tunnel_ch.on("message", lambda m: self.tunnel.handle_message(m))

            @pc.on("track")
            def on_track(track):
                if track.kind == "video":
                    self._tasks.append(asyncio.ensure_future(self._video_loop(track)))

            @pc.on("connectionstatechange")
            async def on_state():
                if pc.connectionState in ("failed", "closed") and self.connected:
                    await self._closed("connection lost")

            await pc.setLocalDescription(await pc.createOffer())
            sdp = pc.localDescription.sdp
            await send({"kind": "offer", "sdp": sdp,
                        "auth": P.auth_tag(key, nonce, "viewer", sdp) if key else None,
                        "totp": totp or None, "invite": invite or None})
            ans = await self._next_payload(ws, timeout)   # ממתין גם לאישור המשתמש
        if ans.get("kind") == "reject":
            await pc.close()
            raise ConnectError(ans.get("reason", "rejected"))
        # אם נשלחה סיסמה והמארח הכיר אותה - התשובה חתומה ומאומתת.
        # אחרת (חיבור שאושר ע"י המשתמש) אין חתימה, ומסתמכים על קוד האבטחה.
        self.mode = "interactive"
        if ans.get("kind") != "answer":
            await pc.close()
            raise ConnectError("protocol error")
        if ans.get("auth"):
            if key is None or not P.verify_tag(
                    key, nonce, "host", str(ans.get("sdp", "")), str(ans["auth"])):
                await pc.close()
                raise ConnectError("host authentication failed")
            self.mode = "unattended"
        self.code = P.session_code(sdp, str(ans["sdp"]))
        await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type="answer"))
        try:
            await asyncio.wait_for(self._hello.wait(), 30)
        except asyncio.TimeoutError:
            await pc.close()
            raise ConnectError("timed out waiting for host")
        self.connected = True
        self._tasks.append(asyncio.ensure_future(self._clipboard_loop()))
        self.on_event("connected", monitors=self.monitors, perms=self.perms.to_json(),
                      mode=self.mode, code=self.code)

    async def _expect(self, ws, typ: str, timeout: float) -> dict:
        while True:
            m = P.loads(await asyncio.wait_for(ws.recv(), timeout))
            if m.get("type") == typ:
                return m
            if m.get("type") == "error":
                raise ConnectError(m.get("reason", "server error"))
            if m.get("type") == "unreachable":
                raise ConnectError("host not found / offline")

    async def _next_payload(self, ws, timeout: float) -> dict:
        while True:
            m = P.loads(await asyncio.wait_for(ws.recv(), timeout))
            if m.get("type") == "relay":
                return m.get("payload") or {}
            if m.get("type") == "unreachable":
                raise ConnectError("host not found / offline")

    # ------------------------------------------------------------ קליטה
    async def _video_loop(self, track) -> None:
        try:
            while True:
                frame = await track.recv()
                self.latest_frame = frame.to_ndarray(format="rgb24")
                self.frame_seq += 1
        except Exception:
            pass

    def _on_control(self, raw) -> None:
        if not isinstance(raw, str):
            return
        try:
            m = json.loads(raw)
        except ValueError:
            return
        t = m.get("t") if isinstance(m, dict) else None
        if t == "hello":
            self.monitors = m.get("monitors", [])
            self.monitor = m.get("monitor", 1)
            self.perms = P.Permissions(**{k: bool(v) for k, v in m.get("perms", {}).items()
                                          if k in P.Permissions.__dataclass_fields__})
            self._hello.set()
        elif t == "perms":
            self.perms = P.Permissions(**{k: bool(v) for k, v in m.get("perms", {}).items()
                                          if k in P.Permissions.__dataclass_fields__})
            self.on_event("perms", perms=self.perms.to_json())
        elif t == "chat":
            self.on_event("chat", text=str(m.get("text", ""))[:2000])
        elif t == "clip" and self.perms.clipboard:
            text = str(m.get("text", ""))
            if len(text.encode()) <= P.MAX_CLIPBOARD_BYTES:
                self._last_clip = text
                self.clipboard.set(text)
        elif t == "wb":
            self.on_event("whiteboard", data=m.get("data"))
        elif t == "bye":
            asyncio.ensure_future(self._closed("host ended the session"))

    async def _clipboard_loop(self) -> None:
        self._last_clip = self.clipboard.get()
        while self.connected:
            await asyncio.sleep(0.7)
            if not self.perms.clipboard:
                continue
            cur = self.clipboard.get()
            if cur and cur != self._last_clip and len(cur.encode()) <= P.MAX_CLIPBOARD_BYTES:
                self._last_clip = cur
                self._send({"t": "clip", "text": cur})

    # ------------------------------------------------------------ שליחה
    def _send(self, obj: dict) -> None:
        if self.control is not None and self.control.readyState == "open":
            self.control.send(P.dumps(obj))

    def send_input(self, ev: dict) -> None:
        if self.perms.control:
            self._send(ev)

    def set_quality(self, fps: int | None = None, scale: float | None = None) -> None:
        cfg = {"t": "cfg"}
        if fps is not None: cfg["fps"] = fps
        if scale is not None: cfg["scale"] = scale
        self._send(cfg)

    def set_monitor(self, index: int) -> None:
        self.monitor = index
        self._send({"t": "cfg", "monitor": index})

    def send_chat(self, text: str) -> None:
        self._send({"t": "chat", "text": text[:2000]})

    def send_whiteboard(self, data: dict) -> None:
        self._send({"t": "wb", "data": data})

    async def send_file(self, path: str) -> None:
        if self.files and self.perms.files:
            await self.files.send_file(path)

    async def start_tunnel(self, local_port: int, remote_host: str, remote_port: int) -> None:
        if self.perms.control and self.tunnel:
            await self.tunnel.start_forward(local_port, remote_host, remote_port)

    async def stop_tunnel(self, local_port: int) -> None:
        if self.tunnel:
            await self.tunnel.stop_forward(local_port)

    # ------------------------------------------------------------ סיום
    async def disconnect(self) -> None:
        if self.connected:
            self._send({"t": "bye"})
        await self._closed("disconnected")

    async def _closed(self, reason: str) -> None:
        if not self.connected and self.pc is None:
            return
        was = self.connected
        self.connected = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self.files:
            self.files.close()
        if self.tunnel:
            await self.tunnel.close_all()
        pc, self.pc = self.pc, None
        if pc:
            await pc.close()
        if was:
            self.on_event("closed", reason=reason)
