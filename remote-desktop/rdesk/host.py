"""צד המארח: המחשב שנשלט. מציג מסך, מקבל קלט, ומבקש אישור מהמשתמש."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

import websockets
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from . import acl, protocol as P
from .privacy import PrivacyGuard
from .tunnel import TunnelHost
from .capture import MssScreen, ScreenTrack
from .clipboard import Clipboard
from .files import FileTransfer
from .inject import apply_event

log = logging.getLogger("rdesk.host")

DEFAULT_ICE = ["stun:stun.l.google.com:19302"]

ApprovalFn = Callable[[dict], Awaitable[Optional[P.Permissions]]]


def make_rtc_config(stun: list[str] | None = None, turn: dict | None = None) -> RTCConfiguration:
    """RDESK_STUN=url1,url2 מחליף את שרתי ה-STUN (ריק = בלי STUN, לרשת מקומית)."""
    if stun is None and "RDESK_STUN" in os.environ:
        stun = [u for u in os.environ["RDESK_STUN"].split(",") if u.strip()]
    servers = [RTCIceServer(urls=u) for u in (DEFAULT_ICE if stun is None else stun)]
    if turn:
        servers.append(RTCIceServer(urls=turn["url"], username=turn.get("username"),
                                    credential=turn.get("credential")))
    return RTCConfiguration(iceServers=servers)


class Session:
    def __init__(self, peer: str, pc: RTCPeerConnection, perms: P.Permissions) -> None:
        self.peer = peer
        self.pc = pc
        self.perms = perms
        self.control = None
        self.files: FileTransfer | None = None
        self.tunnel: "TunnelHost | None" = None
        self.tasks: list[asyncio.Task] = []
        self.started = time.time()
        self.closed = False
        self.track = None
        self._last_clip: str | None = None


class HostService:
    def __init__(
        self,
        server_url: str,
        host_id: str,
        screen=None,
        injector=None,
        clipboard=None,
        approval: ApprovalFn | None = None,
        on_event: Callable[..., None] | None = None,
        download_dir: Path | str = Path.home() / "RDesk" / "Received",
        rtc_config: RTCConfiguration | None = None,
        unattended_key: bytes | None = None,
        unattended_perms: P.Permissions | None = None,
        trust_check: Callable[[str], Optional[P.Permissions]] | None = None,
        invite_check: Callable[[str], Optional[P.Permissions]] | None = None,
        ip_whitelist: list[str] | None = None,
        totp_secret: str | None = None,
        interactive_mode: str = "always",
        window_open_check: Callable[[], bool] | None = None,
    ) -> None:
        self.server_url = server_url
        self.id = host_id
        # חיבור עם מזהה בלבד מחכה לאישור המשתמש. אם הוגדרה סיסמה קבועה
        # (גישה ללא נוכחות) - מי שמקליד אותה נכנס בלי אישור.
        self.unattended_key = unattended_key
        self.unattended_perms = unattended_perms or P.Permissions()
        self.screen = screen or MssScreen()
        if injector is None:
            from .inject import PynputInjector
            injector = PynputInjector()
        self.injector = injector
        self.clipboard = clipboard or Clipboard()
        self.approval = approval
        # הרשאות שמורות למזהה ספציפי ("זכור את המכשיר הזה" בחלון האישור) -
        # מדלגות על בקשת האישור, בלי להיות תלויות בסיסמת גישה ללא נוכחות גלובלית.
        self.trust_check = trust_check
        # קישור הזמנה לסשן (כמו Session Invitation של AnyDesk): token חד-פעמי
        # שה-API הכין מראש - בודק/צורך אותו, בלי תלות בסיסמה גלובלית או באישור.
        self.invite_check = invite_check
        # בקרת גישה (כמו ה-ACL/2FA/Interactive-Access של AnyDesk): רשימת IP
        # מורשים (רשימה ריקה = בלי הגבלה), קוד TOTP נוסף על סיסמת הגישה
        # ללא-נוכחות, ומצב לחיבור אינטראקטיבי (תמיד לשאול / רק כשהחלון פתוח / לעולם לא).
        self.ip_whitelist = ip_whitelist or []
        self.totp_secret = totp_secret
        self.interactive_mode = interactive_mode
        self.window_open_check = window_open_check or (lambda: True)
        self.on_event = on_event or (lambda kind, **kw: None)
        # מצב פרטיות (כמו AnyDesk): חוסם קלט מקומי פיזי + מכסה את הצג הפיזי
        # בזמן סשן, בלי להשפיע על מה שהצופה המרוחק רואה/שולט בו.
        self.privacy = PrivacyGuard()
        self.download_dir = Path(download_dir)
        self.rtc_config = rtc_config or make_rtc_config()
        self.ws = None
        self.session: Session | None = None
        self._pending: dict[str, tuple[str, float]] = {}   # peer -> (nonce, זמן)
        self._busy_negotiating = False
        self._fails = 0
        self._declines = 0
        self._blocked_until = 0.0
        self._stop = asyncio.Event()
        self.registered = asyncio.Event()

    # ------------------------------------------------------------ איתות
    async def run(self) -> None:
        """רץ לנצח: מתחבר לשרת האיתות ומתחבר מחדש בנפילה, עם backoff מתרחב."""
        backoff = 1.0
        while not self._stop.is_set():
            # לא מדווחים "אין חיבור" על הפסקה של כמה שניות שמתאוששת לבד -
            # רק אם ההתנתקות נמשכת באמת (ראו _delayed_offline).
            offline_task = asyncio.ensure_future(self._delayed_offline())
            try:
                async with websockets.connect(self.server_url, max_size=P.MAX_SIGNAL_BYTES) as ws:
                    self.ws = ws
                    await ws.send(P.dumps({"type": "register", "id": self.id}))
                    offline_task.cancel()
                    backoff = 1.0   # התחברנו בהצלחה - איפוס זמן ההמתנה לניסיון הבא
                    async for raw in ws:
                        # כל הודעה בטסק נפרד: חלון האישור לא חוסם הודעות אחרות
                        asyncio.ensure_future(self._on_signal(P.loads(raw)))
            except (OSError, websockets.WebSocketException) as e:
                log.warning("signaling connection lost: %s", e)
            finally:
                offline_task.cancel()
            self.ws = None
            self.registered.clear()
            try:
                await asyncio.wait_for(self._stop.wait(), backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 15.0)

    async def _delayed_offline(self) -> None:
        try:
            await asyncio.sleep(3)
            self.on_event("status", online=False)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self._stop.set()
        await self.disconnect()
        if self.ws:
            await self.ws.close()

    async def set_id(self, new_id: str) -> None:
        """מחליף את מזהה המארח בזמן ריצה (למשל: מישהו רוצה מספר שנראה
        פחות 'נחמד'/קליט). מכריח רישום מחדש אצל שרת האיתות עם המזהה החדש -
        run() שולח register עם self.id בכל פעם שהוא מתחבר מחדש, אז סגירת
        החיבור הנוכחי מספיקה כדי שה-ID החדש ייכנס לתוקף."""
        self.id = new_id
        self.registered.clear()
        if self.ws is not None:
            await self.ws.close()

    async def _send(self, peer: str, payload: dict) -> None:
        if self.ws:
            await self.ws.send(P.dumps({"type": "relay", "to": peer, "payload": payload}))

    async def _on_signal(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "registered":
            self.registered.set()
            self.on_event("status", online=True, id=self.id)
        elif kind == "error":
            self.on_event("error", reason=msg.get("reason"))
        elif kind == "relay":
            peer, payload = str(msg.get("from")), msg.get("payload") or {}
            from_ip = msg.get("from_ip")
            try:
                await self._on_peer(peer, payload, from_ip)
            except Exception:
                log.exception("error handling peer message")
                await self._send(peer, {"kind": "reject", "reason": "internal error"})

    async def _on_peer(self, peer: str, p: dict, from_ip: str | None = None) -> None:
        k = p.get("kind")
        now = time.time()
        if k == "hello":
            if not acl.ip_allowed(from_ip, self.ip_whitelist):
                await self._send(peer, {"kind": "reject", "reason": "ip_blocked"})
                return
            if self.session or self._busy_negotiating:
                await self._send(peer, {"kind": "reject", "reason": "busy"})
                return
            if now < self._blocked_until:
                await self._send(peer, {"kind": "reject", "reason": "blocked"})
                return
            nonce = P.new_nonce()
            self._pending = {a: v for a, v in self._pending.items() if now - v[1] < 60}
            self._pending[peer] = (nonce, now)
            await self._send(peer, {"kind": "challenge", "nonce": nonce})
        elif k == "offer":
            nonce_t = self._pending.pop(peer, None)
            if nonce_t is None or self.session or self._busy_negotiating:
                await self._send(peer, {"kind": "reject", "reason": "no session"})
                return
            nonce = nonce_t[0]
            sdp = str(p.get("sdp", ""))
            tag = p.get("auth")
            invite_token = p.get("invite")
            # נבדק/נצרך פעם אחת כאן (חד-פעמי) - התוצאה מועברת ל-_accept_offer
            invite_perms = self.invite_check(invite_token) if invite_token and self.invite_check else None
            key, mode = None, "interactive"
            if tag and self.unattended_key is not None:
                # הוקלדה סיסמה והמארח מוגדר לגישה ללא נוכחות - חייבת להיות נכונה
                if now < self._blocked_until or not P.verify_tag(
                        self.unattended_key, nonce, "viewer", sdp, str(tag)):
                    self._fails += 1
                    if self._fails >= P.MAX_AUTH_ATTEMPTS:
                        self._blocked_until = now + P.BLOCK_SECONDS
                        self._fails = 0
                        self.on_event("alert", reason="blocked")
                    await self._send(peer, {"kind": "reject", "reason": "bad password"})
                    return
                if self.totp_secret and not acl.totp_verify(self.totp_secret, str(p.get("totp") or "")):
                    # סיסמה נכונה אבל בלי קוד דו-שלבי תקף - גם זה נחשב ניסיון כושל
                    self._fails += 1
                    if self._fails >= P.MAX_AUTH_ATTEMPTS:
                        self._blocked_until = now + P.BLOCK_SECONDS
                        self._fails = 0
                        self.on_event("alert", reason="blocked")
                    await self._send(peer, {"kind": "reject", "reason": "bad totp"})
                    return
                key, mode = self.unattended_key, "unattended"
            elif invite_perms is not None:
                mode = "invite"   # קישור הזמנה תקף - עוקף גם את interactive_mode
            elif self.interactive_mode == "never":
                # גישה אינטראקטיבית כבויה כליל - רק גישה ללא-נוכחות עם סיסמה
                await self._send(peer, {"kind": "reject", "reason": "interactive disabled"})
                return
            elif self.interactive_mode == "window_open" and not self.window_open_check():
                # החלון מוסתר למגש - לא נוכל להציג בקשת אישור, אז לא ממתינים לסרק
                await self._send(peer, {"kind": "reject", "reason": "window closed"})
                return
            # בלי סיסמה (או כשאין סיסמה קבועה במארח): ממתינים לאישור המשתמש
            self._fails = 0
            self._busy_negotiating = True
            try:
                await self._accept_offer(peer, nonce, sdp, key, mode, invite_perms)
            finally:
                self._busy_negotiating = False

    # ------------------------------------------------------------ סשן
    async def _accept_offer(self, peer: str, nonce: str, sdp: str, key: bytes | None, mode: str,
                             invite_perms: P.Permissions | None = None) -> None:
        trusted_perms = None if mode in ("unattended", "invite") or self.trust_check is None else self.trust_check(peer)
        if mode == "unattended":
            perms = P.Permissions(**self.unattended_perms.to_json())   # בלי אישור
        elif mode == "invite":
            perms = invite_perms   # קישור הזמנה חד-פעמי - בלי אישור
        elif trusted_perms is not None:
            perms, mode = trusted_perms, "trusted"   # מזהה שסומן "זכור" בעבר - בלי אישור
        elif self.approval is not None:
            perms = await self.approval({"peer": peer})
        else:
            perms = P.Permissions()
        if perms is None:
            # הגנה מפני הצפת חלונות אישור: 3 דחיות רצופות חוסמות לדקה
            self._declines += 1
            if self._declines >= 3:
                self._declines = 0
                self._blocked_until = time.time() + P.BLOCK_SECONDS
                self.on_event("alert", reason="spam")
            await self._send(peer, {"kind": "reject", "reason": "declined"})
            return
        self._declines = 0

        pc = RTCPeerConnection(self.rtc_config)
        sess = Session(peer, pc, perms)
        track = ScreenTrack(self.screen)
        await track.refresh_monitors()
        pc.addTrack(track)
        sess.track = track

        @pc.on("datachannel")
        def on_channel(ch):
            if ch.label == "control":
                sess.control = ch
                ch.on("message", lambda m: self._on_control(sess, m))
                # ערוץ שנוצר ע"י הצד השני כבר פתוח כשהאירוע מגיע
                if ch.readyState == "open":
                    asyncio.ensure_future(self._on_control_open(sess))
                else:
                    ch.on("open", lambda: asyncio.ensure_future(self._on_control_open(sess)))
            elif ch.label == "files":
                sess.files = FileTransfer(
                    ch, self.download_dir, enabled=lambda: sess.perms.files,
                    on_event=lambda kind, **kw: self.on_event("file_" + kind, **kw))
            elif ch.label == "tunnel":
                # TCP Tunneling (כמו AnyDesk): דורש הרשאת שליטה מלאה, כי זה
                # שווה-ערך ליצירת חיבורים יוצאים חדשים ברשת של המארח.
                def send_if_open(data):
                    if ch.readyState == "open":
                        ch.send(data)
                tun = TunnelHost(send_text=send_if_open, send_binary=send_if_open)
                sess.tunnel = tun
                ch.on("message", lambda m: tun.handle_message(m) if sess.perms.control else None)

        @pc.on("connectionstatechange")
        async def on_state():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self._end_session(sess)

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        answer = pc.localDescription.sdp
        self.session = sess
        await self._send(peer, {
            "kind": "answer", "sdp": answer,
            "auth": P.auth_tag(key, nonce, "host", answer) if key else None,
        })
        self.on_event("session_start", peer=peer, perms=perms.to_json(), mode=mode,
                      code=P.session_code(sdp, answer))

    async def _on_control_open(self, sess: Session) -> None:
        mons = await sess.track.refresh_monitors()
        self._ctl_send(sess, {
            "t": "hello", "monitors": mons, "monitor": sess.track.monitor,
            "perms": sess.perms.to_json(),
        })
        sess.tasks.append(asyncio.ensure_future(self._clipboard_loop(sess)))

    def _ctl_send(self, sess: Session, obj: dict) -> None:
        if sess.control is not None and sess.control.readyState == "open":
            sess.control.send(P.dumps(obj))

    def _on_control(self, sess: Session, raw) -> None:
        if not isinstance(raw, str):
            return
        try:
            m = json.loads(raw)
        except ValueError:
            return
        if not isinstance(m, dict):
            return
        t = m.get("t")
        if t in ("mm", "md", "mu", "ms", "kd", "ku"):
            geom = sess.track.current_geometry()
            if sess.perms.control and geom:
                try:
                    apply_event(self.injector, m, geom)
                except Exception:
                    log.exception("input injection failed")
        elif t == "cfg":
            try:
                if "fps" in m:
                    sess.track.fps = max(1, min(60, int(m["fps"])))
                if "scale" in m:
                    sess.track.scale = max(0.2, min(1.0, float(m["scale"])))
                if "monitor" in m and int(m["monitor"]) in {x["index"] for x in sess.track.monitors()}:
                    sess.track.monitor = int(m["monitor"])
            except (TypeError, ValueError):
                pass
        elif t == "chat" and sess.perms.chat:
            self.on_event("chat", peer=sess.peer, text=str(m.get("text", ""))[:2000])
        elif t == "clip" and sess.perms.clipboard:
            text = str(m.get("text", ""))
            if len(text.encode()) <= P.MAX_CLIPBOARD_BYTES:
                sess._last_clip = text
                self.clipboard.set(text)
        elif t == "wb":
            self.on_event("whiteboard", peer=sess.peer, data=m.get("data"))
        elif t == "elevate_request":
            self.on_event("elevation_requested", peer=sess.peer)
        elif t == "bye":
            asyncio.ensure_future(self._end_session(sess))

    async def _clipboard_loop(self, sess: Session) -> None:
        sess._last_clip = self.clipboard.get()
        while not sess.closed:
            await asyncio.sleep(0.7)
            if not sess.perms.clipboard:
                continue
            cur = self.clipboard.get()
            if cur and cur != sess._last_clip and len(cur.encode()) <= P.MAX_CLIPBOARD_BYTES:
                sess._last_clip = cur
                self._ctl_send(sess, {"t": "clip", "text": cur})

    # ------------------------------------------------------------ פעולות מה-GUI
    def set_unattended(self, key: bytes | None, perms: P.Permissions | None = None) -> None:
        """מפעיל/מכבה גישה ללא נוכחות. key=None מכבה."""
        self.unattended_key = key
        if perms is not None:
            self.unattended_perms = perms

    def set_ip_whitelist(self, entries: list[str]) -> None:
        self.ip_whitelist = list(entries or [])

    def set_totp_secret(self, secret: str | None) -> None:
        self.totp_secret = secret

    def set_interactive_mode(self, mode: str) -> None:
        self.interactive_mode = mode

    def set_privacy_mode(self, enabled: bool) -> None:
        if not self.session:
            return
        self.privacy.enable() if enabled else self.privacy.disable()

    def send_chat(self, text: str) -> None:
        if self.session:
            self._ctl_send(self.session, {"t": "chat", "text": text[:2000]})

    def send_whiteboard(self, data: dict) -> None:
        if self.session:
            self._ctl_send(self.session, {"t": "wb", "data": data})

    async def respond_elevation(self, approved: bool) -> None:
        """המשתמש במחשב המארח אישר/דחה בקשת הרמת-הרשאות (UAC) מהצופה.
        אישור מנסה להציג את חלון ה-UAC האמיתי של Windows - אין דרך
        לדעת כאן אם המשתמש אכן לחץ "כן" עליו, רק אם הוא *הוצג* (ראו uac.py)."""
        if not self.session:
            return
        ok = False
        if approved:
            from . import uac
            ok = uac.request_elevation()
        self._ctl_send(self.session, {"t": "elevate_result", "ok": ok})

    def set_permissions(self, **kw) -> None:
        """שינוי הרשאות תוך כדי סשן (למשל ביטול שליטה)."""
        if not self.session:
            return
        for k, v in kw.items():
            if hasattr(self.session.perms, k):
                setattr(self.session.perms, k, bool(v))
        if not self.session.perms.control:
            self.injector.release_all()
            if self.session.tunnel is not None:
                self.session.tunnel.close_all()
        self._ctl_send(self.session, {"t": "perms", "perms": self.session.perms.to_json()})

    async def send_file(self, path: str) -> None:
        if self.session and self.session.files and self.session.perms.files:
            await self.session.files.send_file(path)

    async def disconnect(self) -> None:
        if self.session:
            self._ctl_send(self.session, {"t": "bye"})
            await self._end_session(self.session)

    async def _end_session(self, sess: Session) -> None:
        if sess.closed:
            return
        sess.closed = True
        self.privacy.disable()   # לא משאירים את המחשב נעול/חוסם קלט אחרי שהסשן נגמר
        for t in sess.tasks:
            t.cancel()
        if sess.files:
            sess.files.close()
        if sess.tunnel:
            sess.tunnel.close_all()
        try:
            self.injector.release_all()
        except Exception:
            pass
        if self.session is sess:
            self.session = None
        await sess.pc.close()
        sess.track.stop()
        self.on_event("session_end", peer=sess.peer)
