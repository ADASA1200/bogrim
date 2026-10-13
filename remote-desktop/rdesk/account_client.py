"""לקוח לחשבון+פנקס כתובות משותף (ראו accounts.py/signaling_server.py):
חיבור websocket קצר-מועד לשרת האיתות, לא קשור לחיבור ה-WebRTC של host/viewer.
"""
from __future__ import annotations

import asyncio

import websockets

from . import protocol as P


class AccountError(Exception):
    pass


async def _request(ws, payload: dict) -> dict:
    await ws.send(P.dumps(payload))
    reply = P.loads(await asyncio.wait_for(ws.recv(), 10))
    if reply.get("type") == "account_error":
        raise AccountError(str(reply.get("reason", "error")))
    return reply


async def register(server_url: str, username: str, password: str) -> None:
    async with websockets.connect(server_url, max_size=P.MAX_SIGNAL_BYTES) as ws:
        await _request(ws, {"type": "account_register", "username": username, "password": password})


async def login_and_get_contacts(server_url: str, username: str, password: str) -> list[dict]:
    async with websockets.connect(server_url, max_size=P.MAX_SIGNAL_BYTES) as ws:
        await _request(ws, {"type": "account_login", "username": username, "password": password})
        reply = await _request(ws, {"type": "address_book_get"})
        return list(reply.get("contacts", []))


async def set_contacts(server_url: str, username: str, password: str, contacts: list[dict]) -> None:
    async with websockets.connect(server_url, max_size=P.MAX_SIGNAL_BYTES) as ws:
        await _request(ws, {"type": "account_login", "username": username, "password": password})
        await _request(ws, {"type": "address_book_set", "contacts": contacts})
