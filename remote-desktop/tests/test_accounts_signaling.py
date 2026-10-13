"""בדיקות לפרוטוקול החשבון+פנקס הכתובות על שרת האיתות (signaling_server.py),
מעל websocket אמיתי - לא רק AccountStore בבדידותו (ראו test_accounts.py)."""
import asyncio

import pytest
import websockets

from rdesk import protocol as P
from rdesk.signaling_server import serve
from test_end_to_end import free_port


@pytest.fixture
async def server(tmp_path):
    port = free_port()
    accounts_path = tmp_path / "accounts.json"
    ws_server = await serve("127.0.0.1", port, accounts_path=accounts_path)
    yield f"ws://127.0.0.1:{port}"
    ws_server.close()
    await ws_server.wait_closed()


async def _recv_json(ws):
    return P.loads(await ws.recv())


async def test_accounts_disabled_by_default():
    port = free_port()
    ws_server = await serve("127.0.0.1", port)   # בלי accounts_path - כבוי
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(P.dumps({"type": "account_login", "username": "a", "password": "b"}))
            reply = await asyncio.wait_for(_recv_json(ws), 5)
            assert reply["type"] == "account_error"
            assert reply["reason"] == "accounts_disabled"
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def test_register_login_and_address_book_round_trip(server):
    async with websockets.connect(server) as ws:
        await ws.send(P.dumps({"type": "account_register", "username": "alice", "password": "a-long-password"}))
        reply = await asyncio.wait_for(_recv_json(ws), 5)
        assert reply["type"] == "account_ok"

        await ws.send(P.dumps({"type": "address_book_set", "contacts": [{"id": "123456789", "label": "אמא"}]}))
        reply = await asyncio.wait_for(_recv_json(ws), 5)
        assert reply["type"] == "account_ok"

        await ws.send(P.dumps({"type": "address_book_get"}))
        reply = await asyncio.wait_for(_recv_json(ws), 5)
        assert reply["type"] == "address_book"
        assert reply["contacts"] == [{"id": "123456789", "label": "אמא"}]

    # התחברות מ"מכשיר" אחר (ws נפרד) עם אותו חשבון - רואה את אותו פנקס
    async with websockets.connect(server) as ws2:
        await ws2.send(P.dumps({"type": "account_login", "username": "alice", "password": "a-long-password"}))
        reply = await asyncio.wait_for(_recv_json(ws2), 5)
        assert reply["type"] == "account_ok"

        await ws2.send(P.dumps({"type": "address_book_get"}))
        reply = await asyncio.wait_for(_recv_json(ws2), 5)
        assert reply["contacts"] == [{"id": "123456789", "label": "אמא"}]


async def test_login_with_wrong_password_rejected(server):
    async with websockets.connect(server) as ws:
        await ws.send(P.dumps({"type": "account_register", "username": "bob", "password": "a-long-password"}))
        await asyncio.wait_for(_recv_json(ws), 5)

    async with websockets.connect(server) as ws2:
        await ws2.send(P.dumps({"type": "account_login", "username": "bob", "password": "wrong-one"}))
        reply = await asyncio.wait_for(_recv_json(ws2), 5)
        assert reply["type"] == "account_error"
        assert reply["reason"] == "bad_credentials"


async def test_address_book_requires_login(server):
    async with websockets.connect(server) as ws:
        await ws.send(P.dumps({"type": "address_book_get"}))
        reply = await asyncio.wait_for(_recv_json(ws), 5)
        assert reply["type"] == "account_error"
        assert reply["reason"] == "not_logged_in"
