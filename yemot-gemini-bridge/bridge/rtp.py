"""RTP endpoint: G.711 in/out with a 20 ms pacer, RFC 2833 DTMF receive."""

from __future__ import annotations

import asyncio
import logging
import random
import struct
from typing import Callable

from .audio import FRAME_SAMPLES, G711

log = logging.getLogger("bridge.rtp")

DTMF_DIGITS = "0123456789*#ABCD"
FRAME_BYTES_PCM = FRAME_SAMPLES * 2
MAX_BUFFER_SECONDS = 120


class PortPool:
    """Hands out even UDP ports from [low, high]; RTCP port+1 is left unused."""

    def __init__(self, low: int, high: int):
        start = low if low % 2 == 0 else low + 1
        self._free = list(range(start, high, 2))
        random.shuffle(self._free)

    def acquire(self) -> int:
        if not self._free:
            raise RuntimeError("no free RTP ports")
        return self._free.pop()

    def release(self, port: int) -> None:
        self._free.append(port)


class RtpSession(asyncio.DatagramProtocol):
    def __init__(self, codec: G711, remote: tuple[str, int], te_pt: int | None,
                 on_pcm: Callable[[bytes], None], on_dtmf: Callable[[str], None]):
        self.codec = codec
        self.remote = remote
        self.te_pt = te_pt
        self._on_pcm = on_pcm
        self._on_dtmf = on_dtmf
        self._transport: asyncio.DatagramTransport | None = None
        self._latched = False
        self._ssrc = random.getrandbits(32)
        self._seq = random.getrandbits(16)
        self._ts = random.getrandbits(32)
        self._marker = True
        self._out = bytearray()
        self._pacer: asyncio.Task | None = None
        self._last_dtmf_ts: int | None = None
        self.packets_in = 0
        self.packets_out = 0
        self.last_rx = 0.0

    async def start(self, bind_ip: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(bind_ip, port))

    def start_sending(self) -> None:
        """Begin the 20 ms send clock; call once the call is answered."""
        if self._pacer is None and self._transport is not None:
            self._pacer = asyncio.create_task(self._pace(), name="rtp-pacer")

    def connection_made(self, transport) -> None:  # noqa: D401
        self._transport = transport

    def close(self) -> None:
        if self._pacer:
            self._pacer.cancel()
        if self._transport:
            self._transport.close()
            self._transport = None

    def set_remote(self, remote: tuple[str, int]) -> None:
        """Called on re-INVITE; allow the media address to move."""
        self.remote = remote
        self._latched = False

    # ---- receive -------------------------------------------------------
    def datagram_received(self, data: bytes, addr) -> None:
        if len(data) < 12 or data[0] >> 6 != 2:
            return
        if not self._latched:
            self.remote = (addr[0], addr[1])  # symmetric RTP: trust the first packet's source
            self._latched = True
        elif addr[0] != self.remote[0]:
            return
        cc = data[0] & 0x0F
        offset = 12 + 4 * cc
        if data[0] & 0x10:  # header extension
            if len(data) < offset + 4:
                return
            offset += 4 + 4 * struct.unpack("!H", data[offset + 2:offset + 4])[0]
        end = len(data)
        if data[0] & 0x20 and end > offset:  # padding
            end -= data[end - 1]
        payload = data[offset:end]
        pt = data[1] & 0x7F
        self.packets_in += 1
        self.last_rx = asyncio.get_running_loop().time()
        if pt == self.codec.payload_type:
            if payload:
                self._on_pcm(self.codec.decode(payload))
        elif self.te_pt is not None and pt == self.te_pt and len(payload) >= 4:
            self._handle_dtmf(payload, struct.unpack("!I", data[4:8])[0])

    def _handle_dtmf(self, payload: bytes, rtp_ts: int) -> None:
        event, flags = payload[0], payload[1]
        if flags & 0x80 and rtp_ts != self._last_dtmf_ts and event < len(DTMF_DIGITS):
            self._last_dtmf_ts = rtp_ts
            self._on_dtmf(DTMF_DIGITS[event])

    # ---- send ----------------------------------------------------------
    def play(self, pcm8k: bytes) -> None:
        self._out += pcm8k
        limit = MAX_BUFFER_SECONDS * 16000
        if len(self._out) > limit:
            del self._out[: len(self._out) - limit]

    def clear(self) -> None:
        self._out.clear()

    def buffered_ms(self) -> int:
        return len(self._out) // 16  # 8 kHz * 2 bytes = 16 bytes/ms

    def _send_frame(self, pcm: bytes | None) -> None:
        if not self._transport:
            return
        payload = self.codec.encode(pcm) if pcm else bytes([self.codec.silence_byte]) * FRAME_SAMPLES
        header = struct.pack("!BBHII", 0x80, (0x80 if self._marker else 0) | self.codec.payload_type,
                             self._seq, self._ts, self._ssrc)
        self._marker = False
        self._seq = (self._seq + 1) & 0xFFFF
        self._ts = (self._ts + FRAME_SAMPLES) & 0xFFFFFFFF
        self._transport.sendto(header + payload, self.remote)
        self.packets_out += 1

    async def _pace(self) -> None:
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        while True:
            if len(self._out) >= FRAME_BYTES_PCM:
                frame = bytes(self._out[:FRAME_BYTES_PCM])
                del self._out[:FRAME_BYTES_PCM]
            elif self._out:  # pad the tail of an utterance
                frame = bytes(self._out) + b"\x00" * (FRAME_BYTES_PCM - len(self._out))
                self._out.clear()
            else:
                frame = None
            self._send_frame(frame)
            next_t += 0.020
            delay = next_t - loop.time()
            if delay < -0.2:  # fell far behind (suspended loop): resync instead of bursting
                next_t = loop.time()
                delay = 0
            await asyncio.sleep(max(0.0, delay))
