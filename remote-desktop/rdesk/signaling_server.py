"""שרת איתות (Signaling) - מעביר הודעות בין מארח לצופה לפי מזהה.

השרת לא רואה וידאו, קלט או קבצים - רק הודעות SDP קצרות. אחרי שהחיבור
מוקם הנתונים עוברים ישירות (P2P) או דרך TURN, מוצפנים ב-DTLS-SRTP.

הרצה:  python -m rdesk server --host 0.0.0.0 --port 8765
להצפנת האיתות (wss) מומלץ להציב אחרי reverse proxy עם TLS, או להעביר
--certfile / --keyfile.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
import time
from collections import defaultdict

import websockets

from . import protocol as P

log = logging.getLogger("rdesk.server")

MAX_CONN_PER_IP = 50
MSGS_PER_SECOND = 20


class SignalingServer:
    def __init__(self) -> None:
        self.clients: dict[str, object] = {}
        self.per_ip: dict[str, int] = defaultdict(int)

    async def handler(self, ws) -> None:
        ip = (ws.remote_address or ("?",))[0]
        if self.per_ip[ip] >= MAX_CONN_PER_IP:
            await ws.close(1013, "too many connections")
            return
        self.per_ip[ip] += 1
        my_id = None
        window_start, count = time.monotonic(), 0
        try:
            async for raw in ws:
                now = time.monotonic()
                if now - window_start >= 1:
                    window_start, count = now, 0
                count += 1
                if count > MSGS_PER_SECOND:
                    await ws.close(1008, "rate limit")
                    return
                if not isinstance(raw, str) or len(raw) > P.MAX_SIGNAL_BYTES:
                    await ws.close(1009, "bad message")
                    return
                try:
                    msg = P.loads(raw)
                except ValueError:
                    continue
                kind = msg.get("type")
                if kind == "register":
                    want = str(msg.get("id", ""))
                    if not want.isalnum() or len(want) > 32:
                        await ws.send(P.dumps({"type": "error", "reason": "bad id"}))
                        continue
                    if my_id is not None:
                        continue
                    if want in self.clients:
                        await ws.send(P.dumps({"type": "error", "reason": "id in use"}))
                        continue
                    my_id = want
                    self.clients[my_id] = ws
                    await ws.send(P.dumps({"type": "registered", "id": my_id}))
                elif kind == "relay" and my_id is not None:
                    target = self.clients.get(str(msg.get("to", "")))
                    if target is None:
                        await ws.send(P.dumps({"type": "unreachable", "to": msg.get("to")}))
                        continue
                    # from_ip: הכתובת האמיתית של השולח (לא ניתנת לזיוף - זו כתובת
                    # הסוקט בפועל) - כדי שהצד המקבל יוכל לאכוף רשימת IP מורשים.
                    await target.send(P.dumps({
                        "type": "relay", "from": my_id, "from_ip": ip, "payload": msg.get("payload"),
                    }))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.per_ip[ip] -= 1
            if my_id is not None and self.clients.get(my_id) is ws:
                del self.clients[my_id]


async def serve(host: str = "127.0.0.1", port: int = 8765,
                certfile: str | None = None, keyfile: str | None = None):
    ctx = None
    if certfile:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
    server = SignalingServer()
    ws_server = await websockets.serve(
        server.handler, host, port, ssl=ctx, max_size=P.MAX_SIGNAL_BYTES,
    )
    log.info("signaling server listening on %s:%s (%s)", host, port,
             "wss" if ctx else "ws")
    return ws_server


async def run_forever(host: str, port: int, certfile=None, keyfile=None) -> None:
    ws_server = await serve(host, port, certfile, keyfile)
    await ws_server.wait_closed()
