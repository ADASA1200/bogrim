"""בדיקות ל-tunnel.py (TCP Tunneling): מחברים TunnelViewer ו-TunnelHost
ישירות דרך callables (בלי WebRTC בכלל) ובודקים זרימת בתים אמיתית מקצה
לקצה דרך שרת echo TCP אמיתי."""
import asyncio

import pytest

from rdesk.tunnel import TunnelHost, TunnelViewer, pack_data, unpack_data
from test_end_to_end import free_port, wait_for


def test_pack_unpack_round_trip():
    frame = pack_data(42, b"hello world")
    sid, payload = unpack_data(frame)
    assert sid == 42
    assert payload == b"hello world"


async def _echo_server(port: int):
    async def handle(reader, writer):
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", port)


def _wire(host: TunnelHost, viewer: TunnelViewer) -> None:
    """מחברים את שני הצדדים ישירות - במקום שני קצוות של data channel אחד."""
    host._send_text = lambda s: viewer.handle_message(s)
    host._send_binary = lambda b: viewer.handle_message(b)
    viewer._send_text = lambda s: host.handle_message(s)
    viewer._send_binary = lambda b: host.handle_message(b)


async def test_tunnel_relays_bytes_through_echo_server():
    echo_port = free_port()
    echo_srv = await _echo_server(echo_port)
    local_port = free_port()

    host = TunnelHost(send_text=lambda s: None, send_binary=lambda b: None)
    viewer = TunnelViewer(send_text=lambda s: None, send_binary=lambda b: None)
    _wire(host, viewer)

    try:
        await viewer.start_forward(local_port, "127.0.0.1", echo_port)

        reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
        writer.write(b"hello tunnel")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(100), 5)
        assert data == b"hello tunnel"

        writer.write(b"second message")
        await writer.drain()
        data2 = await asyncio.wait_for(reader.read(100), 5)
        assert data2 == b"second message"

        writer.close()
    finally:
        await viewer.close_all()
        host.close_all()
        echo_srv.close()
        await echo_srv.wait_closed()


async def test_tunnel_rejects_disallowed_target():
    local_port = free_port()
    host = TunnelHost(send_text=lambda s: None, send_binary=lambda b: None,
                      allowed_targets={("127.0.0.1", 9999)})
    viewer = TunnelViewer(send_text=lambda s: None, send_binary=lambda b: None)
    _wire(host, viewer)

    try:
        await viewer.start_forward(local_port, "127.0.0.1", 12345)   # לא ברשימה המורשית
        reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
        data = await asyncio.wait_for(reader.read(100), 5)
        assert data == b""   # המארח דחה - הצופה סוגר את חיבור ה-TCP המקומי
        writer.close()
    finally:
        await viewer.close_all()
        host.close_all()


async def test_tunnel_closes_local_socket_when_target_unreachable():
    local_port = free_port()
    unreachable_port = free_port()   # לא מאזין שם אף שירות
    host = TunnelHost(send_text=lambda s: None, send_binary=lambda b: None)
    viewer = TunnelViewer(send_text=lambda s: None, send_binary=lambda b: None)
    _wire(host, viewer)

    try:
        await viewer.start_forward(local_port, "127.0.0.1", unreachable_port)
        reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
        data = await asyncio.wait_for(reader.read(100), 5)
        assert data == b""
        writer.close()
    finally:
        await viewer.close_all()
        host.close_all()


async def test_multiple_concurrent_streams_do_not_cross_talk():
    echo_port = free_port()
    echo_srv = await _echo_server(echo_port)
    local_port = free_port()

    host = TunnelHost(send_text=lambda s: None, send_binary=lambda b: None)
    viewer = TunnelViewer(send_text=lambda s: None, send_binary=lambda b: None)
    _wire(host, viewer)

    try:
        await viewer.start_forward(local_port, "127.0.0.1", echo_port)

        async def one_client(tag: bytes):
            reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
            writer.write(tag * 50)
            await writer.drain()
            got = b""
            while len(got) < len(tag) * 50:
                got += await reader.read(4096)
            writer.close()
            return got

        results = await asyncio.gather(one_client(b"A"), one_client(b"B"), one_client(b"C"))
        assert results[0] == b"A" * 50
        assert results[1] == b"B" * 50
        assert results[2] == b"C" * 50
    finally:
        await viewer.close_all()
        host.close_all()
        echo_srv.close()
        await echo_srv.wait_closed()
