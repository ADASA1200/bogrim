"""Test doubles: a fake Gemini Live client and a fake Yemot (SIP caller)."""

from __future__ import annotations

import asyncio
import math
import re
import secrets
import struct

import numpy as np
from google.genai import types

from bridge.audio import G711
from bridge.sip import SipMessage


def tone(rate: int, ms: int, freq: float = 440.0, amp: float = 0.5) -> bytes:
    n = rate * ms // 1000
    t = np.arange(n) / rate
    return (np.sin(2 * math.pi * freq * t) * amp * 32767).astype("<i2").tobytes()


# ---------------------------------------------------------------- Gemini

class FakeSession:
    """Mimics google.genai AsyncSession: receive() ends at each turn_complete."""

    def __init__(self, script):
        self.script = script
        self.audio_bytes = 0
        self.texts: list[str] = []
        self.client_contents: list = []
        self.tool_responses: list = []
        self._q: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def push(self, msg) -> None:
        self._q.put_nowait(msg)

    async def send_realtime_input(self, *, audio=None, text=None, **kw):
        if audio is not None:
            self.audio_bytes += len(audio.data)
        if text is not None:
            self.texts.append(text)
            await self.script.on_text(self, text)

    async def send_client_content(self, *, turns=None, turn_complete=None):
        self.client_contents.append(turns)
        await self.script.on_greeting(self)

    async def send_tool_response(self, *, function_responses):
        self.tool_responses.extend(function_responses)
        await self.script.on_tool_response(self, function_responses)

    async def receive(self):
        while True:
            msg = await self._q.get()
            if msg == "DROP":
                raise ConnectionError("fake connection drop")
            yield msg
            if msg.server_content and msg.server_content.turn_complete:
                return


def audio_msg(pcm24k: bytes):
    return types.LiveServerMessage(server_content=types.LiveServerContent(
        model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(
            data=pcm24k, mime_type="audio/pcm;rate=24000"))])))


def turn_complete_msg():
    return types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True))


def tool_call_msg(name: str, args: dict | None = None, call_id: str = "c1"):
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(
        function_calls=[types.FunctionCall(id=call_id, name=name, args=args or {})]))


class Script:
    """Default behaviour: greet with a tone; DTMF 5 -> get_datetime -> goodbye tone -> end_call."""

    async def on_greeting(self, s: FakeSession):
        s.push(audio_msg(tone(24000, 400)))
        s.push(turn_complete_msg())

    async def on_text(self, s: FakeSession, text: str):
        if "DTMF: 5" in text:
            s.push(tool_call_msg("get_datetime", {}, "t1"))

    async def on_tool_response(self, s: FakeSession, responses):
        if responses[0].name == "get_datetime":
            s.push(audio_msg(tone(24000, 300, 600)))
            s.push(tool_call_msg("end_call", {"reason": "done"}, "t2"))
            s.push(turn_complete_msg())


class FakeLive:
    def __init__(self, script=None):
        self.script = script or Script()
        self.sessions: list[FakeSession] = []
        self.configs: list = []
        outer = self

        class _CM:
            def __init__(self, model, config):
                self.model, self.config = model, config
                self.session = FakeSession(outer.script)

            async def __aenter__(self):
                outer.sessions.append(self.session)
                outer.configs.append((self.model, self.config))
                return self.session

            async def __aexit__(self, *exc):
                self.session.closed = True

        class _Live:
            def connect(_, *, model, config):
                return _CM(model, config)

        class _Aio:
            live = _Live()

        self.aio = _Aio()


# ---------------------------------------------------------------- Yemot

class FakeYemot(asyncio.DatagramProtocol):
    """A minimal SIP caller + RTP endpoint that behaves like Yemot's routing_ip leg."""

    def __init__(self, bridge_addr, token, rtp_port, codec="PCMA"):
        self.bridge = bridge_addr
        self.token = token
        self.rtp_port = rtp_port
        self.codec = G711(codec)
        self.call_id = secrets.token_hex(6) + "@yemot.test"
        self.sip_msgs: list[SipMessage] = []
        self.sip_event = asyncio.Event()
        self.rtp_rx: list[bytes] = []
        self.rtp_seqs: list[int] = []
        self.bye_received = asyncio.Event()
        self.final_status: int | None = None
        self._sip_tr = None
        self._rtp_tr = None
        self._ssrc = secrets.randbits(32)
        self._seq = 0
        self._ts = 0
        self.to_tag = ""
        self.sip_port = 0

    async def open(self):
        loop = asyncio.get_running_loop()
        self._sip_tr, _ = await loop.create_datagram_endpoint(lambda: self, local_addr=("127.0.0.1", 0))
        self.sip_port = self._sip_tr.get_extra_info("sockname")[1]
        self._rtp_tr, _ = await loop.create_datagram_endpoint(lambda: _RtpSink(self), local_addr=("127.0.0.1", self.rtp_port))

    def close(self):
        for t in (self._sip_tr, self._rtp_tr):
            if t:
                t.close()

    # SIP
    def datagram_received(self, data, addr):
        m = SipMessage.parse(data)
        if not m:
            return
        if m.is_request and m.method == "BYE":
            ok = f"SIP/2.0 200 OK\r\nVia: {m.get('via')}\r\nFrom: {m.get('from')}\r\nTo: {m.get('to')}\r\nCall-ID: {m.call_id}\r\nCSeq: {m.get('cseq')}\r\nContent-Length: 0\r\n\r\n"
            self._sip_tr.sendto(ok.encode(), addr)
            self.bye_received.set()
            return
        self.sip_msgs.append(m)
        self.sip_event.set()

    def send_invite(self, user=None, sdp_extra="", transport="RTP/AVP", codecs="8 0 101"):
        user = self.token if user is None else user
        sdp = (f"v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n"
               f"m=audio {self.rtp_port} {transport} {codecs}\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:0 PCMU/8000\r\n"
               f"a=rtpmap:101 telephone-event/8000\r\na=fmtp:101 0-16\r\na=ptime:20\r\na=sendrecv\r\n{sdp_extra}")
        branch = "z9hG4bK" + secrets.token_hex(4)
        self.invite_text = (
            f"INVITE sip:{user}@127.0.0.1:{self.bridge[1]} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:{self.sip_port};branch={branch};rport\r\n"
            f"Max-Forwards: 70\r\nFrom: \"0501234567\" <sip:0501234567@yemot.test>;tag=ytag\r\n"
            f"To: <sip:{user}@127.0.0.1>\r\nCall-ID: {self.call_id}\r\nCSeq: 1 INVITE\r\n"
            f"Contact: <sip:yemot@127.0.0.1:{self.sip_port}>\r\nX-Yemot-CallID: abc123\r\nX-Yemot-Path: /1/2\r\n"
            f"Content-Type: application/sdp\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}")
        self._sip_tr.sendto(self.invite_text.encode(), self.bridge)

    def send_cancel(self):
        head = self.invite_text.split("\r\n\r\n")[0].split("\r\n")
        lines = [head[0].replace("INVITE", "CANCEL", 1)]
        for h in head[1:]:
            if h.lower().startswith(("content-", "contact", "x-yemot")):
                continue
            lines.append(h.replace("1 INVITE", "1 CANCEL"))
        lines.append("Content-Length: 0")
        self._sip_tr.sendto(("\r\n".join(lines) + "\r\n\r\n").encode(), self.bridge)

    async def wait_final(self, timeout=8):
        end = asyncio.get_running_loop().time() + timeout
        while True:
            for m in self.sip_msgs:
                if not m.is_request and m.status >= 200 and m.cseq[1] == "INVITE":
                    self.final = m
                    self.final_status = m.status
                    return m
            left = end - asyncio.get_running_loop().time()
            if left <= 0:
                raise TimeoutError("no final response")
            self.sip_event.clear()
            try:
                await asyncio.wait_for(self.sip_event.wait(), left)
            except asyncio.TimeoutError:
                pass

    def send_ack(self):
        to = self.final.get("to")
        ack = (f"ACK sip:bridge@127.0.0.1:{self.bridge[1]} SIP/2.0\r\n"
               f"Via: SIP/2.0/UDP 127.0.0.1:{self.sip_port};branch=z9hG4bK{secrets.token_hex(4)}\r\n"
               f"Max-Forwards: 70\r\nFrom: \"0501234567\" <sip:0501234567@yemot.test>;tag=ytag\r\n"
               f"To: {to}\r\nCall-ID: {self.call_id}\r\nCSeq: 1 ACK\r\nContent-Length: 0\r\n\r\n")
        self._sip_tr.sendto(ack.encode(), self.bridge)

    def send_request(self, method, extra="", body="", ctype=None, cseq=2):
        to = self.final.get("to")
        head = (f"{method} sip:bridge@127.0.0.1:{self.bridge[1]} SIP/2.0\r\n"
                f"Via: SIP/2.0/UDP 127.0.0.1:{self.sip_port};branch=z9hG4bK{secrets.token_hex(4)};rport\r\n"
                f"Max-Forwards: 70\r\nFrom: \"0501234567\" <sip:0501234567@yemot.test>;tag=ytag\r\n"
                f"To: {to}\r\nCall-ID: {self.call_id}\r\nCSeq: {cseq} {method}\r\n{extra}")
        if ctype:
            head += f"Content-Type: {ctype}\r\n"
        self._sip_tr.sendto((head + f"Content-Length: {len(body)}\r\n\r\n{body}").encode(), self.bridge)

    # RTP
    def send_rtp_frame(self, pcm8k: bytes, pt=None, payload=None):
        pt = self.codec.payload_type if pt is None else pt
        payload = self.codec.encode(pcm8k) if payload is None else payload
        hdr = struct.pack("!BBHII", 0x80, pt, self._seq & 0xFFFF, self._ts, self._ssrc)
        self._seq += 1
        self._ts += 160
        self._rtp_tr.sendto(hdr + payload, ("127.0.0.1", self.rtp_dest))

    def send_dtmf(self, event: int):
        ts = self._ts
        for i, end in enumerate((False, False, True, True, True)):
            payload = bytes([event, 0x80 if end else 0, 0, 160 * (i + 1) & 0xFF])
            hdr = struct.pack("!BBHII", 0x80, 101, self._seq & 0xFFFF, ts, self._ssrc)
            self._seq += 1
            self._rtp_tr.sendto(hdr + payload, ("127.0.0.1", self.rtp_dest))
        self._ts += 800

    rtp_dest = 0


class _RtpSink(asyncio.DatagramProtocol):
    def __init__(self, owner: FakeYemot):
        self.owner = owner

    def datagram_received(self, data, addr):
        if len(data) > 12:
            self.owner.rtp_rx.append(data[12:])
            self.owner.rtp_seqs.append(struct.unpack("!H", data[2:4])[0])
