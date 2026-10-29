"""Call lifecycle: auth -> SDP -> RTP + Gemini session -> teardown."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
import time
from collections import defaultdict, deque
from typing import Any

from .audio import (GEMINI_IN_RATE, GEMINI_OUT_RATE, TELEPHONE_RATE, G711, StreamResampler, apply_volume,
                    noise_gate)
from .config import Config
from .gemini_live import GeminiLive
from .rtp import PortPool, RtpSession
from .sdp import SdpError, build_answer, choose_codec, parse_offer
from .sip import Accept, Invite, Reject, SipEndpoint, Registration
from .tools import ToolContext, ToolRegistry

log = logging.getLogger("bridge.call")

AUTH_FAIL_LIMIT = 10  # per source IP per minute
FAREWELL_DRAIN_TIMEOUT = 12


def _mask(number: str) -> str:
    return ("*" * max(0, len(number) - 4)) + number[-4:] if number else "unknown"


class Call:
    def __init__(self, manager: "CallManager", inv: Invite, ctx: ToolContext, rtp: RtpSession,
                 rtp_port: int):
        self.manager = manager
        self.call_id = inv.request.call_id
        self.ctx = ctx
        self.rtp = rtp
        self.rtp_port = rtp_port
        self.started = time.monotonic()
        self.up = StreamResampler(TELEPHONE_RATE, GEMINI_IN_RATE, quality="QQ")  # QQ: no buffering delay
        self.down = StreamResampler(GEMINI_OUT_RATE, TELEPHONE_RATE, quality="HQ")  # best anti-aliasing for 24k->8k
        self.gemini: GeminiLive | None = None
        self._ending = False
        self._turn_done = asyncio.Event()
        self._finished = asyncio.Event()
        self.answered_at: float | None = None
        self._watchdog: asyncio.Task | None = None
        self._farewell: asyncio.Task | None = None
        ctx.request_hangup = self.request_hangup
        self.label = f"{self.call_id[:8]}/{_mask(ctx.caller_number)}"

    # ---- media plumbing -----------------------------------------------
    def on_caller_pcm(self, pcm8k: bytes) -> None:
        if self.gemini and not self._ending:
            data = noise_gate(self.up.process(pcm8k), self.manager.cfg.input_noise_gate_rms)
            if data:
                self.gemini.send_audio(data)

    def on_model_audio(self, pcm24k: bytes) -> None:
        data = self.down.process(apply_volume(pcm24k, self.manager.cfg.output_volume))
        if data:
            self.rtp.play(data)

    def on_interrupt(self) -> None:
        self.rtp.clear()
        self.down.reset()

    def on_turn_complete(self) -> None:
        tail = self.down.flush()  # the filter still holds the last ~30 ms of the turn
        if tail:
            self.rtp.play(tail)
        self._turn_done.set()

    def on_gemini_closed(self, reason: str) -> None:
        asyncio.create_task(self.finish(reason, send_bye=True))

    # ---- SIP-facing callbacks ------------------------------------------
    async def on_answered(self) -> None:
        self.answered_at = asyncio.get_running_loop().time()
        self.rtp.start_sending()
        self._watchdog = asyncio.create_task(self._watch())
        if self.gemini:
            await self.gemini.say_greeting()

    async def on_remote_bye(self) -> None:
        await self.finish("remote hangup", send_bye=False)

    async def on_dtmf(self, digit: str) -> None:
        log.info("[%s] DTMF %s", self.label, digit)
        if digit == "#" and self.manager.cfg.hangup_on_hash:  # same as the proven bridge: '#' ends the call
            await self.finish("caller pressed #", send_bye=True)
            return
        if self.gemini:
            await self.gemini.send_text(f"[DTMF: {digit}]")

    async def on_reinvite(self, sdp: str) -> str | None:
        try:
            offer = parse_offer(sdp)
        except SdpError:
            return None
        self.rtp.set_remote((offer.remote_ip, offer.remote_port))
        cfg = self.manager.cfg
        return build_answer(cfg.public_ip, self.rtp_port, self.rtp.codec.payload_type, self.rtp.codec.name,
                            self.rtp.te_pt)

    # ---- ending --------------------------------------------------------
    def request_hangup(self, reason: str) -> None:
        """Called by the end_call tool: let the farewell finish, then hang up."""
        if self._ending:
            return
        self._ending = True
        log.info("[%s] hangup requested: %s", self.label, reason)
        self._turn_done.clear()
        self._farewell = asyncio.create_task(self._graceful_end())

    async def _graceful_end(self) -> None:
        try:
            await asyncio.wait_for(self._turn_done.wait(), FAREWELL_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            pass
        deadline = time.monotonic() + FAREWELL_DRAIN_TIMEOUT
        while self.rtp.buffered_ms() > 40 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.4)  # let the last frames leave and the network play them out
        await self.finish("ended by assistant", send_bye=True)

    async def _watch(self) -> None:
        cfg = self.manager.cfg
        interval = max(0.2, min(2.0, cfg.rtp_silence_timeout / 4))
        try:
            while not self._finished.is_set():
                await asyncio.sleep(interval)
                now = asyncio.get_running_loop().time()
                if time.monotonic() - self.started > cfg.max_call_seconds:
                    await self.finish("max duration", send_bye=True)
                    return
                # no RTP from the caller for rtp_silence_timeout seconds (also when none ever arrived)
                last = max(self.rtp.last_rx, self.answered_at or 0.0)
                if last and now - last > cfg.rtp_silence_timeout:
                    await self.finish("no RTP from caller", send_bye=True)
                    return
        except asyncio.CancelledError:
            pass

    async def finish(self, reason: str, *, send_bye: bool) -> None:
        if self._finished.is_set():
            return
        self._finished.set()
        duration = time.monotonic() - self.started
        log.info("[%s] call ended (%s) after %.0fs, tools=%d, rtp in/out=%d/%d", self.label, reason, duration,
                 self.gemini.tool_calls if self.gemini else 0, self.rtp.packets_in, self.rtp.packets_out)
        for task in (self._watchdog, self._farewell):
            if task and task is not asyncio.current_task():
                task.cancel()
        if send_bye:
            dialog = self.manager.endpoint.dialogs.get(self.call_id)
            if dialog:
                await self.manager.endpoint.hangup(dialog)
        if self.gemini:
            await self.gemini.close()
        self.rtp.close()
        self.manager.release(self)


class CallManager:
    def __init__(self, cfg: Config, registry: ToolRegistry, gemini_client: Any = None):
        self.cfg = cfg
        self.registry = registry
        self.gemini_client = gemini_client
        self.ports = PortPool(cfg.rtp_min, cfg.rtp_max)
        self.endpoint: SipEndpoint = None  # type: ignore[assignment]  # set by main
        self.registration: Registration | None = None
        self.calls: dict[str, Call] = {}
        self.total_calls = 0
        self._failures: dict[str, deque] = defaultdict(deque)

    # ---- admission -----------------------------------------------------
    def _rate_limited(self, ip: str) -> bool:
        q = self._failures[ip]
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        return len(q) >= AUTH_FAIL_LIMIT

    def _authorized(self, inv: Invite) -> bool:
        ip = inv.source[0]
        if self.cfg.allowed_networks:
            addr = ipaddress.ip_address(ip)
            if not any(addr in net for net in self.cfg.allowed_networks):
                return False
        user = inv.request_user.encode()
        if self.cfg.access_token and hmac.compare_digest(user, self.cfg.access_token.encode()):
            return True
        reg = self.registration
        if reg and reg.registered and ip in reg.trusted_ips and user == self.cfg.register_user.encode():
            return True
        return False

    async def on_invite(self, inv: Invite) -> Accept | Reject:
        ip = inv.source[0]
        if self._rate_limited(ip) or not self._authorized(inv):
            self._failures[ip].append(time.monotonic())
            u = inv.request_user
            log.warning("rejected INVITE from %s (auth; request-URI user %s, %d chars)", ip,
                        (u[:2] + "…") if len(u) > 4 else "?", len(u))
            return Reject(404, "Not Found")
        if len(self.calls) >= self.cfg.max_calls:
            return Reject(486, "Busy Here")
        try:
            offer = parse_offer(inv.sdp)
            pt, name = choose_codec(offer, self.cfg.codec_preference)
        except SdpError as exc:
            log.warning("SDP rejected: %s", exc)
            return Reject(488, "Not Acceptable Here")

        caller_number = self._caller_number(inv)
        ctx = ToolContext(
            caller_number=caller_number, called_user="", tz=self.cfg.tz,
            yemot_call_id=inv.header("x-yemot-callid") or "", yemot_path=inv.header("x-yemot-path") or "")
        port = self.ports.acquire()
        call: Call | None = None
        try:
            codec = G711(name)
            holder: dict[str, Call] = {}
            rtp = RtpSession(codec, (offer.remote_ip, offer.remote_port), offer.telephone_event_pt,
                             on_pcm=lambda b: holder["c"].on_caller_pcm(b),
                             on_dtmf=lambda d: asyncio.create_task(holder["c"].on_dtmf(d)))
            call = Call(self, inv, ctx, rtp, port)
            holder["c"] = call
            await rtp.start(self.cfg.sip_bind, port)
            call.gemini = GeminiLive(
                self.cfg, self.registry, ctx, on_audio=call.on_model_audio, on_interrupt=call.on_interrupt,
                on_turn_complete=call.on_turn_complete, on_closed=call.on_gemini_closed,
                client=self.gemini_client)
            await call.gemini.start()
            if inv.cancelled.is_set():  # caller gave up while we were connecting to Gemini
                await call.gemini.close()
                call.rtp.close()
                self.ports.release(port)
                return Reject(487, "Request Terminated")
            self.calls[call.call_id] = call
            self.total_calls += 1
            log.info("[%s] call accepted (%s, rtp port %d)", call.label, name, port)
            sdp = build_answer(self.cfg.public_ip, port, pt, name, offer.telephone_event_pt)
            rtp.punch()
            return Accept(sdp=sdp, call=call)
        except Exception as exc:
            log.error("could not set up call: %r", exc)
            if call is not None:
                if call.gemini:
                    await call.gemini.close()
                call.rtp.close()
            self.ports.release(port)
            return Reject(503, "Service Unavailable")

    @staticmethod
    def _caller_number(inv: Invite) -> str:
        for hdr in ("p-asserted-identity", "remote-party-id"):
            value = inv.header(hdr)
            if value and "sip:" in value:
                return value.split("sip:", 1)[1].split("@", 1)[0]
        uri = inv.from_uri
        return uri.split(":", 1)[1].split("@", 1)[0] if "@" in uri else ""

    def release(self, call: Call) -> None:
        if self.calls.pop(call.call_id, None) is not None:
            self.ports.release(call.rtp_port)

    async def shutdown(self) -> None:
        await asyncio.gather(*(c.finish("shutdown", send_bye=True) for c in list(self.calls.values())),
                             return_exceptions=True)
