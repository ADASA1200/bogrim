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
import time
import uuid
from pathlib import Path

import webview

from . import account_client, acl, config, connlog, embedded as E, printing, protocol as P, wol
from .aio import AsyncRunner
from .clipboard import Clipboard
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
        self._clipboard = Clipboard()

    def getClipboardText(self) -> str:
        """לחיצה ימנית על שדה טקסט מדביקה ישירות (ראו Input ב-webui) - קוראים
        את לוח הגזירים של המערכת כאן כי זה אמין יותר מה-Clipboard API של
        הדפדפן, שחסום/חלקי בחלק מגרסאות WebKitGTK."""
        return self._clipboard.get() or ""

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
        self._pending_peer: dict[str, str] = {}
        self._online = False
        self._session_mode: str | None = None
        self._session_code: str | None = None
        self._started = False
        self.tray = None
        self._window_visible = True
        self._invites: dict[str, tuple[P.Permissions, float]] = {}
        self._printer_port = printing.PrinterPort(config.CONFIG_DIR / "print_out")
        self._printer_task = None

        host_server = f"ws://127.0.0.1:{emb_port}" if emb_on else self.server
        self.service = HostService(
            host_server, self.id, approval=self._approval, on_event=self._on_event,
            unattended_key=key, unattended_perms=uperms, injector=injector, screen=screen,
            trust_check=self._check_trust, invite_check=self._check_invite,
            ip_whitelist=config.get_ip_whitelist(self.cfg), totp_secret=config.get_totp_secret(self.cfg),
            interactive_mode=config.get_interactive_mode(self.cfg), window_open_check=lambda: self._window_visible,
        )

    def _check_trust(self, peer: str) -> P.Permissions | None:
        return config.get_trusted(self.cfg, peer)

    def _check_invite(self, token: str) -> P.Permissions | None:
        entry = self._invites.pop(token, None)   # חד-פעמי - תמיד מוסר, גם אם פג תוקף
        if entry is None:
            return None
        perms, expires_at = entry
        return perms if time.time() <= expires_at else None

    # ------------------------------------------------------------- הדפסה מרחוק
    def getPrintingState(self) -> dict:
        return {"supported": self._printer_port.supported, "enabled": self._printer_task is not None}

    def enableRemotePrinting(self) -> dict:
        if not self._printer_port.supported:
            raise Exception("not_supported")
        if self._printer_task is None:
            if not self._printer_port.install():
                raise Exception("install_failed_needs_admin")
            self._printer_task = self.runner.submit(self._printer_port.watch(self._on_print_file))
        return {"enabled": True}

    def disableRemotePrinting(self) -> None:
        if self._printer_task is not None:
            self._printer_task.cancel()
            self._printer_task = None
        self._printer_port.uninstall()

    async def _on_print_file(self, path) -> None:
        """קובץ PDF חדש הופיע בתיקיית הפלט של המדפסת הווירטואלית - שולחים
        אותו לצופה המחובר (אם יש) דרך ערוץ הקבצים הקיים, עם שם שמסמן
        לצד השני להדפיס אותו מיד במקום רק לשמור (ראו printing.py)."""
        sess = self.service.session
        if sess is None or sess.files is None or not sess.perms.files:
            path.unlink(missing_ok=True)
            return
        target = path.with_name(printing.PRINT_NAME_PREFIX + path.name)
        path.rename(target)
        try:
            await sess.files.send_file(str(target))
        finally:
            target.unlink(missing_ok=True)

    def createInviteLink(self, minutes: int = 10) -> dict:
        now = time.time()
        self._invites = {t: v for t, v in self._invites.items() if v[1] > now}   # ניקוי ישנים
        token = uuid.uuid4().hex
        perms = P.Permissions(control=True, clipboard=True, files=True, chat=True)
        minutes = max(1, int(minutes))
        self._invites[token] = (perms, now + minutes * 60)
        return {"url": P.make_invite_url(self.id, token, self.server), "expiresInMinutes": minutes}

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

    def init_tray(self) -> None:
        """אייקון מגש-מערכת שקט וקבוע ליד השעון: פתיחה בלחיצה, והופך לאדום
        מהבהב כל עוד מישהו מחובר (או מחכה לאישור). סוגרים את החלון -> מוסתר
        למגש בלבד, לא יציאה מהאפליקציה (ראו _on_window_closing)."""
        from . import tray

        self.tray = tray.TrayIcon(self._tray_open, self._tray_disconnect, self._tray_quit)
        self.tray.start()
        if self.win is not None:
            self.win.events.closing += self._on_window_closing

    def _on_window_closing(self):
        if self.tray is not None and self.tray.available:
            self.win.hide()
            self._window_visible = False
            return False  # מבטל את הסגירה בפועל - נשארים ברקע עם האייקון
        return None

    def _tray_open(self) -> None:
        if self.win is not None:
            self.win.show()
            self.win.restore()
            self._window_visible = True

    def _tray_disconnect(self) -> None:
        self.disconnect()

    def _tray_quit(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass

    def _on_event(self, kind: str, **kw) -> None:
        if kind == "status":
            self._online = bool(kw.get("online"))
            self.push("status", {"online": self._online})
        elif kind == "session_start":
            self._session_mode, self._session_code = kw["mode"], kw["code"]
            self.push("session_start", {"peer": kw["peer"], "perms": kw["perms"], "mode": kw["mode"], "code": kw["code"]})
            if self.tray is not None:
                self.tray.set_connected(True, kw.get("peer", ""))
            connlog.start_entry(kw["peer"], kw["mode"], kw["perms"])
        elif kind == "session_end":
            self._session_mode = self._session_code = None
            self.push("session_end", {})
            self.push("privacy_changed", {"enabled": False})
            if self.tray is not None:
                self.tray.set_connected(False)
            connlog.end_last(kw.get("peer", ""))
        elif kind == "chat":
            self.push("chat", {"text": kw["text"]})
        elif kind == "whiteboard":
            self.push("whiteboard", {"data": kw.get("data")})
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
        self._pending_peer[req_id] = info["peer"]
        # בקשת חיבור שדורשת אישור אנושי - מציגים את החלון (אולי מוסתר למגש)
        # כדי שהמשתמש בכלל יראה את חלון האישור, ומדליקים את האייקון כ"מחכה".
        if self.win is not None:
            self.win.show()
            self.win.restore()
            self._window_visible = True
        if self.tray is not None:
            self.tray.set_connected(True, info.get("peer", ""))
        self.push("ask_approval", {"requestId": req_id, "peer": info["peer"]})
        try:
            result = await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            result = None
        finally:
            self._pending.pop(req_id, None)
            self._pending_peer.pop(req_id, None)
        if result is None and self._session_mode is None and self.tray is not None:
            self.tray.set_connected(False)  # נדחה/נפל בזמן - בלי session_start שיטפל בזה
        return result

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
                          "control": uperms.control, "clipboard": uperms.clipboard, "files": uperms.files,
                          "totpEnabled": config.get_totp_secret(self.cfg) is not None},
            "ipWhitelist": config.get_ip_whitelist(self.cfg),
            "interactiveMode": config.get_interactive_mode(self.cfg),
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

    def setPrivacyMode(self, enabled: bool) -> None:
        self.runner.call(self.service.set_privacy_mode, bool(enabled))
        self.push("privacy_changed", {"enabled": bool(enabled)})

    def sendChat(self, text: str) -> None:
        self.runner.call(self.service.send_chat, text)

    def sendWhiteboard(self, data: dict) -> None:
        self.runner.call(self.service.send_whiteboard, data)

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

    def setIpWhitelist(self, entries: list[str]) -> None:
        self.cfg = config.load()
        config.set_ip_whitelist(self.cfg, entries or [])
        self.runner.call(self.service.set_ip_whitelist, config.get_ip_whitelist(self.cfg))

    def setInteractiveMode(self, mode: str) -> None:
        self.cfg = config.load()
        config.set_interactive_mode(self.cfg, mode)
        self.runner.call(self.service.set_interactive_mode, mode)

    def setTotp(self, enabled: bool) -> dict:
        """enabled=True: מפעיל ומחזיר secret חדש (מוצג פעם אחת להזנה באפליקציית
        אימות). enabled=False: מכבה. דורש שסיסמת גישה-ללא-נוכחות תהיה מוגדרת."""
        self.cfg = config.load()
        if not enabled:
            config.set_totp_secret(self.cfg, None)
            self.runner.call(self.service.set_totp_secret, None)
            return {"enabled": False, "secret": None}
        if config.get_unattended(self.cfg)[0] is None:
            raise Exception("need_password")
        secret = acl.totp_new_secret()
        config.set_totp_secret(self.cfg, secret)
        self.runner.call(self.service.set_totp_secret, secret)
        return {"enabled": True, "secret": secret}

    def respondApproval(self, req_id: str, perms: dict | None) -> None:
        fut = self._pending.get(req_id)
        if fut is None:
            return
        result = None if perms is None else P.Permissions(
            control=bool(perms.get("control")), clipboard=bool(perms.get("clipboard")),
            files=bool(perms.get("files")), chat=True)
        if result is not None and perms.get("remember"):
            peer = self._pending_peer.get(req_id)
            if peer:
                self.cfg = config.load()
                config.set_trusted(self.cfg, peer, result)
        self.runner.call(lambda: (not fut.done()) and fut.set_result(result))

    def getConnectionLog(self, limit: int = 50):
        return connlog.recent(limit)

    def clearConnectionLog(self) -> None:
        connlog.clear()

    def getTrustedDevices(self):
        self.cfg = config.load()
        return [{"peer": peer, "perms": perms} for peer, perms in config.list_trusted(self.cfg).items()]

    def removeTrustedDevice(self, peer: str) -> None:
        self.cfg = config.load()
        config.remove_trusted(self.cfg, peer)

    # ---------------------------------------------- חשבון + פנקס כתובות
    def getAccountState(self) -> dict:
        self.cfg = config.load()
        acct = config.get_account(self.cfg)
        return {"loggedIn": acct is not None, "username": acct["username"] if acct else None}

    def registerAccount(self, username: str, password: str) -> dict:
        fut = self.runner.submit(account_client.register(self.server, username, password))
        try:
            fut.result(10)
        except Exception as e:
            raise Exception(str(e)) from None
        return self.loginAccount(username, password)

    def loginAccount(self, username: str, password: str) -> dict:
        fut = self.runner.submit(account_client.login_and_get_contacts(self.server, username, password))
        try:
            contacts = fut.result(10)
        except Exception as e:
            raise Exception(str(e)) from None
        self.cfg = config.load()
        config.set_account(self.cfg, username, password, contacts)
        return {"loggedIn": True, "username": username, "contacts": contacts}

    def logoutAccount(self) -> None:
        self.cfg = config.load()
        config.set_account(self.cfg, None, None)

    def getAddressBook(self) -> list:
        self.cfg = config.load()
        acct = config.get_account(self.cfg)
        return acct["contacts"] if acct else []

    def setAddressBook(self, contacts: list) -> None:
        self.cfg = config.load()
        acct = config.get_account(self.cfg)
        if not acct:
            raise Exception("not_logged_in")
        fut = self.runner.submit(
            account_client.set_contacts(self.server, acct["username"], acct["password"], contacts))
        try:
            fut.result(10)
        except Exception as e:
            raise Exception(str(e)) from None
        self.cfg = config.load()
        config.set_account_contacts(self.cfg, contacts)


def open_host_window(server_arg: str | None, runner: AsyncRunner, **win_kw) -> HostAPI:
    api = HostAPI(server_arg, runner)
    opts = {"width": 580, "height": 820, "min_size": (420, 560), **win_kw}
    win = webview.create_window("RDesk", url=_index_html(), js_api=api, **opts)
    api.win = win
    win.events.loaded += lambda: api.start()
    win.events.closed += lambda: api.tray and api.tray.stop()
    api.init_tray()
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

    def parseInviteLink(self, url: str) -> dict | None:
        return P.parse_invite_url(url)

    def getWolMac(self, host_id: str) -> str:
        return config.get_wol_mac(config.load(), P.clean_id(host_id)) or ""

    def setWolMac(self, host_id: str, mac: str) -> None:
        cfg = config.load()
        if mac:
            wol.normalize_mac(mac)   # זורק אם לא תקין - עדיף כישלון ברור מ-UI מאשר שמירה שקטה של MAC שגוי
        config.set_wol_mac(cfg, P.clean_id(host_id), mac or None)

    def wakeOnLan(self, host_id: str) -> None:
        mac = config.get_wol_mac(config.load(), P.clean_id(host_id))
        if not mac:
            raise Exception("no_mac_saved")
        wol.send(mac)

    def viewerConnect(self, server: str, host_id: str, password: str, totp: str = "", invite: str = ""):
        fut = self.runner.submit(self._connect(server, host_id, password, totp, invite))
        try:
            return fut.result(95)
        except Exception as e:
            raise Exception(str(e)) from None

    async def _connect(self, server: str, host_id: str, password: str, totp: str = "", invite: str = ""):
        client = ViewerClient(server, on_event=self._on_event)
        self.client = client
        await client.connect(host_id, password, totp, invite)
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
        elif kind == "whiteboard":
            self.push("whiteboard", {"data": kw.get("data")})
        elif kind == "perms":
            self.push("perms_changed", {"perms": kw["perms"]})
        elif kind == "closed":
            self.push("closed", {"reason": kw.get("reason")})
        elif kind == "file_received":
            name, path = kw.get("name", ""), kw.get("path", "")
            if printing.is_print_job(name):
                printed = printing.print_received_file(path)
                self.push("file_event", {"kind": "printed" if printed else "print_failed", "path": path})
            else:
                self.push("file_event", {"kind": "received", "path": path})
        elif kind == "file_error":
            self.push("file_event", {"kind": "error", "path": kw.get("path", ""), "reason": kw.get("reason", "")})

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

    def sendWhiteboard(self, data: dict) -> None:
        if self.client:
            self.runner.call(self.client.send_whiteboard, data)

    def pickAndSendFile(self):
        win = self.win
        result = win.create_file_dialog(webview.OPEN_DIALOG) if win else None
        if result and self.client:
            self.runner.submit(self.client.send_file(result[0]))

    def startTunnel(self, local_port: int, remote_host: str, remote_port: int):
        if not self.client:
            raise Exception("not_connected")
        fut = self.runner.submit(self.client.start_tunnel(int(local_port), remote_host, int(remote_port)))
        try:
            fut.result(10)
        except Exception as e:
            raise Exception(str(e)) from None

    def stopTunnel(self, local_port: int) -> None:
        if self.client:
            self.runner.submit(self.client.stop_tunnel(int(local_port)))

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


def run_viewer(server: str | None = None, invite_url: str | None = None) -> None:
    runner = AsyncRunner()
    cfg = config.load()
    preset = {"server": config.server_url(server), "recent": cfg.get("recent", [])}
    if invite_url:
        parsed = P.parse_invite_url(invite_url)
        if parsed:
            preset.update({
                "id": parsed["id"], "invite": parsed["token"], "password": "",
                "server": parsed["server"] or preset["server"], "autoConnect": True,
            })
    open_viewer_window(server, runner, preset)
    webview.start()
