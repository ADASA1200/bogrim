"""TCP Tunneling (כמו ב-AnyDesk): מעבר פורט דרך הערוץ המוצפן הקיים (WebRTC
data channel בשם "tunnel"), בלי לפתוח שום פורט חדש ברשת מבחוץ. הצופה פותח
פורט מקומי; חיבור אליו נפתח כחיבור TCP אמיתי בצד המארח ליעד המבוקש (למשל
RDP/SSH פנימי), והבתים עוברים משני הכיוונים דרך הסשן המוצפן.

פריימינג על אותו data channel: הודעות טקסט (JSON) הן בקרה
(open/opened/close/error); הודעות בינאריות הן נתונים - 4 בתים ראשונים הם
מזהה זרם (stream id, big-endian uint32), השאר הוא המטען הגולמי. כמה
"זרמים" (חיבורי TCP נפרדים) חולקים את אותו data channel אחד, כדי לא
לדרוש renegotiation של ה-SDP בכל open() חדש.
"""
from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Callable

log = logging.getLogger("rdesk.tunnel")

_HEADER = struct.Struct(">I")
CHUNK = 16 * 1024


def pack_data(stream_id: int, payload: bytes) -> bytes:
    return _HEADER.pack(stream_id) + payload


def unpack_data(frame: bytes) -> tuple[int, bytes]:
    (stream_id,) = _HEADER.unpack_from(frame)
    return stream_id, frame[_HEADER.size:]


class TunnelHost:
    """בצד המארח: open() שמגיע מהצופה פותח חיבור TCP אמיתי ליעד, ומעביר
    בתים בשני הכיוונים. ``allowed_targets=None`` לא מגביל יעדים (מעבר
    לכך שהחיבור כבר מחייב הרשאת control)."""

    def __init__(self, send_text: Callable[[str], None], send_binary: Callable[[bytes], None],
                allowed_targets: set[tuple[str, int]] | None = None) -> None:
        self._send_text = send_text
        self._send_binary = send_binary
        self._allowed = allowed_targets
        self._writers: dict[int, asyncio.StreamWriter] = {}

    def handle_message(self, data) -> None:
        if isinstance(data, str):
            self._handle_control(data)
        elif isinstance(data, (bytes, bytearray)):
            self._handle_data(bytes(data))

    def _handle_control(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        op, sid = msg.get("op"), msg.get("id")
        if op == "open" and isinstance(sid, int):
            host, port = str(msg.get("host", "")), msg.get("port")
            try:
                port = int(port)
            except (TypeError, ValueError):
                return
            asyncio.ensure_future(self._open(sid, host, port))
        elif op == "close" and isinstance(sid, int):
            self._close_stream(sid)

    def _handle_data(self, frame: bytes) -> None:
        if len(frame) < _HEADER.size:
            return
        stream_id, payload = unpack_data(frame)
        writer = self._writers.get(stream_id)
        if writer is not None:
            writer.write(payload)

    async def _open(self, stream_id: int, host: str, port: int) -> None:
        if self._allowed is not None and (host, port) not in self._allowed:
            self._send_text(json.dumps({"op": "error", "id": stream_id, "reason": "target not allowed"}))
            return
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 5)
        except Exception as e:
            self._send_text(json.dumps({"op": "error", "id": stream_id, "reason": str(e)[:200]}))
            return
        self._writers[stream_id] = writer
        self._send_text(json.dumps({"op": "opened", "id": stream_id}))
        asyncio.ensure_future(self._pump_to_channel(stream_id, reader))

    async def _pump_to_channel(self, stream_id: int, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                chunk = await reader.read(CHUNK)
                if not chunk:
                    break
                self._send_binary(pack_data(stream_id, chunk))
        except Exception:
            log.exception("tunnel stream %s read failed", stream_id)
        finally:
            self._close_stream(stream_id)
            self._send_text(json.dumps({"op": "close", "id": stream_id}))

    def _close_stream(self, stream_id: int) -> None:
        writer = self._writers.pop(stream_id, None)
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass

    def close_all(self) -> None:
        for sid in list(self._writers):
            self._close_stream(sid)


class TunnelViewer:
    """בצד הצופה: פותח שרת TCP מקומי לכל חוק העברה; כל חיבור אליו הופך
    ל"זרם" אחד מעל ה-data channel, עד שהמארח מאשר (opened) או דוחה (error)."""

    def __init__(self, send_text: Callable[[str], None], send_binary: Callable[[bytes], None]) -> None:
        self._send_text = send_text
        self._send_binary = send_binary
        self._next_id = 1
        self._writers: dict[int, asyncio.StreamWriter] = {}
        self._opened: dict[int, asyncio.Future] = {}
        self._servers: dict[int, asyncio.base_events.Server] = {}

    def handle_message(self, data) -> None:
        if isinstance(data, str):
            self._handle_control(data)
        elif isinstance(data, (bytes, bytearray)):
            self._handle_data(bytes(data))

    def _handle_control(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        op, sid = msg.get("op"), msg.get("id")
        if op == "opened" and sid in self._opened:
            fut = self._opened.pop(sid)
            if not fut.done():
                fut.set_result(True)
        elif op == "error" and sid in self._opened:
            fut = self._opened.pop(sid)
            if not fut.done():
                fut.set_exception(ConnectionError(str(msg.get("reason", "tunnel error"))))
        elif op == "close" and isinstance(sid, int):
            writer = self._writers.pop(sid, None)
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    pass

    def _handle_data(self, frame: bytes) -> None:
        if len(frame) < _HEADER.size:
            return
        stream_id, payload = unpack_data(frame)
        writer = self._writers.get(stream_id)
        if writer is not None:
            writer.write(payload)

    async def start_forward(self, local_port: int, remote_host: str, remote_port: int) -> None:
        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            stream_id = self._next_id
            self._next_id += 1
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._opened[stream_id] = fut
            self._writers[stream_id] = writer
            self._send_text(json.dumps({"op": "open", "id": stream_id, "host": remote_host, "port": remote_port}))
            try:
                await asyncio.wait_for(fut, 10)
            except Exception:
                self._writers.pop(stream_id, None)
                writer.close()
                return
            try:
                while True:
                    chunk = await reader.read(CHUNK)
                    if not chunk:
                        break
                    self._send_binary(pack_data(stream_id, chunk))
            except Exception:
                log.exception("tunnel stream %s read failed", stream_id)
            finally:
                self._send_text(json.dumps({"op": "close", "id": stream_id}))
                self._writers.pop(stream_id, None)
                try:
                    writer.close()
                except Exception:
                    pass

        server = await asyncio.start_server(handle_client, "127.0.0.1", local_port)
        self._servers[local_port] = server

    async def stop_forward(self, local_port: int) -> None:
        server = self._servers.pop(local_port, None)
        if server is not None:
            server.close()
            await server.wait_closed()

    async def close_all(self) -> None:
        for port in list(self._servers):
            await self.stop_forward(port)
        for sid in list(self._writers):
            writer = self._writers.pop(sid, None)
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    pass
