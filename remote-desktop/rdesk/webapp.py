"""ממשק ה-React: חלון דפדפן מקומי (pywebview) שמריץ את ה-frontend, מחובר
ללוגיקת הליבה הקיימת (host.py / viewer.py / embedded.py) דרך API חשוף ל-JS.

אין כאן שינוי בפרוטוקול או בלוגיקה - רק שכבת הצגה חדשה שמחליפה את gui_host.py
ו-gui_viewer.py (ה-tkinter נשארים בקוד כ-fallback דרך ‎--legacy-ui).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import threading
import uuid
from pathlib import Path

import webview

from . import config, embedded as E, protocol as P
from .aio import AsyncRunner
from .host import HostService
from .viewer import ViewerClient

APPROVAL_TIMEOUT = 30


def dist_dir() -> Path:
    """תיקיית ה-build של React, גם בהרצה רגילה וגם מתוך קובץ EXE ארוז."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "webui_dist"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "webui" / "dist"


def _index_html() -> str:
    idx = dist_dir() / "index.html"
    if not idx.exists():
        raise FileNotFoundError(
            f"webui build not found at {idx}. הריצו `npm run build` בתוך remote-desktop/webui."
        )
    return str(idx)


def _encode_frame_jpeg(arr) -> str:
    from PIL import Image

    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=78)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class _WindowPusher:
    """עטיפה דקה סביב webview.Window: שולח אירוע JSON ל-JS, שקטה אם החלון כבר נסגר."""

    def __init__(self) -> None:
        self.win: webview.Window | None = None

    def push(self, kind: str, data=None) -> None:
        win = self.win
        if win is None:
            return
        code = f"window.__rdeskEvent && window.__rdeskEvent({json.dumps(kind)}, {json.dumps(data)})"
        try:
            win.evaluate_js(code)
        except Exception:
            pass


# ------------------------------------------------------------------ מארח
class HostAPI(_WindowPusher):
    def __init__(self, server_arg: str | None, runner: AsyncRunner, injector=None, screen=None) -> None:
        super().__init__()
        self.runner = runner
        self.cfg = config.load()
        self.id = config.host_identity(self.cfg)
        self.server_arg = server_arg
        self.server = config.server_url(server_arg)
        key, uperms = config.get_unattended(self.cfg)
        self.unattended_perms = uperms
        emb_on, emb_port = config.get_embedded(self.cfg)
        self.embedded_on, self.embedded_port = emb_on, emb_port
        self.embedded: E.EmbeddedServer | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._online = False
        self._session_mode: str | None = None
        self._session_code: str | None = None
        self._started = False

        host_server = f"ws://127.0.0.1:{emb_port}" if emb_on else self.server
        self.service = HostService(
            host_server, self.id, approval=self._approval, on_event=self._on_event,
            unattended_key=key, unattended_perms=uperms, injector=injector, screen=screen,
        )

    def start(self) -> None:
        # win.events.loaded עלול לירות יותר מפעם אחת (ניווט/טעינה חוזרת) -
        # בלי השמירה הזו היינו מריצים שני לולאות service.run() מקבילות שנאבקות
        # על אותו חיבור ws ומייצרות ניתוקים אקראיים.
        if self._started:
            return
        self._started = True
        self.runner.submit(self._start_and_run())

    async def _start_and_run(self) -> None:
        if self.embedded_on:
            try:
                self.embedded = await E.start(self.embedded_port)
            except OSError as e:
                self.push("toast", {"text": f"לא ניתן להפעיל את השרת המוטבע: {e}", "tone": "danger"})
            else:
                self.push("embedded_update", {"port": self.embedded.port, "lanIp": self.embedded.lan_ip})
                asyncio.ensure_future(self._fill_public_ip())
        try:
            await self.service.run()
        except Exception:
            import logging
            logging.getLogger("rdesk.webapp").exception("host service loop crashed")

    async def _fill_public_ip(self) -> None:
        if self.embedded is not None:
            ip = await self.embedded.fill_public_ip()
            self.push("embedded_update", {"publicIp": ip})

    def _on_event(self, kind: str, **kw) -> None:
        if kind == "status":
            self._online = bool(kw.get("online"))
            self.push("status", {"online": self._online})
        elif kind == "session_start":
            self._session_mode, self._session_code = kw["mode"], kw["code"]
            self.push("session_start", {"peer": kw["peer"], "perms": kw["perms"], "mode": kw["mode"], "code": kw["code"]})
        elif kind == "session_end":
            self._session_mode = self._session_code = None
            self.push("session_end", {})
        elif kind == "chat":
            self.push("chat", {"text": kw["text"]})
        elif kind == "alert":
            self.push("alert", {"reason": kw.get("reason")})
        elif kind in ("file_received", "file_sent", "file_error"):
            self.push("file_event", {
                "kind": kind.replace("file_", ""),
                "path": kw.get("path", ""), "name": kw.get("name", ""),
                "reason": kw.get("reason", ""),
            })

    async def _approval(self, info: dict):
        req_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        self.push("ask_approval", {"requestId": req_id, "peer": info["peer"]})
        try:
            return await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending.pop(req_id, None)

    # ---------------------------------------------------------------- JS API
    def getState(self):
        key, uperms = config.get_unattended(self.cfg)
        sess = self.service.session
        return {
            "id": self.id,
            "online": self._online,
            "recent": self.cfg.get("recent", []),
            "server": self.server,
            "unattended": {"enabled": key is not None, "hasKey": key is not None,
                          "control": uperms.control, "clipboard": uperms.clipboard, "files": uperms.files},
            "embedded": {"enabled": self.embedded_on, "port": self.embedded.port if self.embedded else self.embedded_port,
                        "lanIp": self.embedded.lan_ip if self.embedded else None,
                        "publicIp": self.embedded.public_ip if self.embedded else None},
            "session": None if not sess else {
                "peer": sess.peer, "perms": sess.perms.to_json(),
                "mode": self._session_mode or "interactive",
                "code": self._session_code or "",
            },
        }

    def openViewer(self, host_id: str, password: str):
        host_id = P.clean_id(host_id)
        if host_id == self.id:
            return  # ה-UI כבר חוסם את זה; זו רק הגנה כפולה
        cfg = config.load()
        recent = [host_id] + [r for r in cfg.get("recent", []) if r != host_id]
        cfg["recent"] = recent[:10]
        config.save(cfg)
        self.cfg = cfg
        preset = {"server": self.server, "id": host_id, "password": password,
                  "recent": recent[:10], "autoConnect": True}
        open_viewer_window(self.server_arg, self.runner, preset)

    def setPermission(self, key: str, value: bool) -> None:
        self.runner.call(lambda: self.service.set_permissions(**{key: bool(value)}))

    def sendChat(self, text: str) -> None:
        self.runner.call(self.service.send_chat, text)

    def pickAndSendFile(self):
        win = self.win
        result = win.create_file_dialog(webview.OPEN_DIALOG) if win else None
        if result:
            self.runner.submit(self.service.send_file(result[0]))

    def disconnect(self) -> None:
        self.runner.submit(self.service.disconnect())

    def setServer(self, url: str) -> None:
        self.cfg = config.load()
        self.cfg["server"] = url.strip()
        config.save(self.cfg)

    def setEmbedded(self, opts: dict) -> None:
        self.cfg = config.load()
        config.set_embedded(self.cfg, bool(opts.get("enabled")), int(opts.get("port", 8765)))

    def setUnattended(self, opts: dict):
        self.cfg = config.load()
        if not opts.get("enabled"):
            config.clear_unattended(self.cfg)
            self.runner.call(self.service.set_unattended, None)
            return
        password = opts.get("password")
        _, cur = config.get_unattended(self.cfg)
        if password and len(password) < config.MIN_UNATTENDED_LEN:
            raise Exception("too_short")
        if not password and config.get_unattended(self.cfg)[0] is None:
            raise Exception("need_password")
        perms = P.Permissions(control=bool(opts.get("control", True)), clipboard=bool(opts.get("clipboard", True)),
                              files=bool(opts.get("files", True)), chat=True)
        key = config.set_unattended(self.cfg, password or None, perms)
        self.runner.call(self.service.set_unattended, key, perms)

    def respondApproval(self, req_id: str, perms: dict | None) -> None:
        fut = self._pending.get(req_id)
        if fut is None:
            return
        result = None if perms is None else P.Permissions(
            control=bool(perms.get("control")), clipboard=bool(perms.get("clipboard")),
            files=bool(perms.get("files")), chat=True)
        self.runner.call(lambda: (not fut.done()) and fut.set_result(result))


def open_host_window(server_arg: str | None, runner: AsyncRunner, **win_kw) -> HostAPI:
    api = HostAPI(server_arg, runner)
    opts = {"width": 580, "height": 820, "min_size": (420, 560), **win_kw}
    win = webview.create_window("RDesk", url=_index_html(), js_api=api, **opts)
    api.win = win
    win.events.loaded += lambda: api.start()
    return api


# ------------------------------------------------------------------ צופה
class ViewerAPI(_WindowPusher):
    def __init__(self, runner: AsyncRunner, preset: dict | None) -> None:
        super().__init__()
        self.runner = runner
        self.preset = preset
        self.client: ViewerClient | None = None
        self._pump_task = None

    def getViewerPreset(self):
        if self.preset:
            return self.preset
        cfg = config.load()
        return {"server": config.server_url(None), "recent": cfg.get("recent", [])}

    def viewerConnect(self, server: str, host_id: str, password: str):
        fut = self.runner.submit(self._connect(server, host_id, password))
        try:
            return fut.result(95)
        except Exception as e:
            raise Exception(str(e)) from None

    async def _connect(self, server: str, host_id: str, password: str):
        client = ViewerClient(server, on_event=self._on_event)
        self.client = client
        await client.connect(host_id, password)
        self._pump_task = asyncio.ensure_future(self._frame_pump())
        return {
            "monitors": [m for m in client.monitors],
            "monitor": client.monitor,
            "perms": client.perms.to_json(),
            "mode": client.mode,
            "code": client.code,
        }

    async def _frame_pump(self) -> None:
        last_seq = -1
        loop = asyncio.get_running_loop()
        while self.client and self.client.connected:
            frame = self.client.latest_frame
            seq = self.client.frame_seq
            if frame is not None and seq != last_seq:
                last_seq = seq
                b64 = await loop.run_in_executor(None, _encode_frame_jpeg, frame)
                self.push("frame", b64)
            await asyncio.sleep(1 / 30)

    def _on_event(self, kind: str, **kw) -> None:
        if kind == "chat":
            self.push("chat", {"text": kw["text"]})
        elif kind == "perms":
            self.push("perms_changed", {"perms": kw["perms"]})
        elif kind == "closed":
            self.push("closed", {"reason": kw.get("reason")})
        elif kind in ("file_received", "file_error"):
            self.push("file_event", {"kind": kind.replace("file_", ""), "path": kw.get("path", ""), "reason": kw.get("reason", "")})

    def sendInput(self, ev: dict) -> None:
        if self.client:
            self.runner.call(self.client.send_input, ev)

    def setQuality(self, fps: int, scale: float) -> None:
        if self.client:
            self.runner.call(self.client.set_quality, fps, scale)

    def setMonitor(self, index: int) -> None:
        if self.client:
            self.runner.call(self.client.set_monitor, index)

    def sendChat(self, text: str) -> None:
        if self.client:
            self.runner.call(self.client.send_chat, text)

    def pickAndSendFile(self):
        win = self.win
        result = win.create_file_dialog(webview.OPEN_DIALOG) if win else None
        if result and self.client:
            self.runner.submit(self.client.send_file(result[0]))

    def viewerDisconnect(self) -> None:
        if self.client:
            self.runner.submit(self.client.disconnect())


def open_viewer_window(server_arg: str | None, runner: AsyncRunner, preset: dict | None = None, **win_kw) -> ViewerAPI:
    api = ViewerAPI(runner, preset)
    opts = {"width": 1100, "height": 720, "min_size": (640, 420), **win_kw}
    win = webview.create_window("RDesk - צופה", url=_index_html() + "#viewer", js_api=api, **opts)
    api.win = win
    return api


# ------------------------------------------------------------------ כניסה
def run_app(server: str | None = None) -> None:
    runner = AsyncRunner()
    open_host_window(server, runner)
    webview.start()


def run_viewer(server: str | None = None) -> None:
    runner = AsyncRunner()
    cfg = config.load()
    preset = {"server": config.server_url(server), "recent": cfg.get("recent", [])}
    open_viewer_window(server, runner, preset)
    webview.start()
