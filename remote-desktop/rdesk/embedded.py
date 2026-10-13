"""מצב "המחשב הזה הוא גם השרת": מריץ שרת איתות מוטבע בתוך המארח, בלי צד שלישי.

החיבור בין שני המחשבים (וידאו, קלט, קבצים) תמיד ישיר ומוצפן (WebRTC). המחשב
שמריץ את השרת המוטבע הוא רק נקודת ההכרות בין הצדדים - בדיוק כמו שרת איתות
נפרד, רק שהוא רץ בתוך אותה תוכנה במקום בתהליך/במחשב נפרד.

מגבלה שאין לה פתרון בלי צד שלישי: הצד השני חייב לדעת כתובת שמגיעה לכאן.
באותה רשת מקומית (LAN) זה עובד מיד עם כתובת ה-LAN. מהאינטרנט צריך הפניית
פורט (Port Forwarding) בנתב של המחשב הזה אל הפורט שבו רץ השרת.
"""
from __future__ import annotations

import asyncio
import socket
import urllib.error
import urllib.request

import websockets

from . import protocol as P
from .signaling_server import SignalingServer


def lan_ip() -> str | None:
    """מנחש את כתובת ה-IP ברשת המקומית שממנה המחשב פונה החוצה.

    לא שולח בפועל שום מידע (UDP connect() רק בוחר ממשק לפי טבלת הניתוב).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def public_ip(timeout: float = 3.0) -> str | None:
    """כתובת ה-IP הציבורית של המחשב (best effort; עלול להיכשל בלי אינטרנט)."""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            ip = r.read().decode().strip()
            return ip or None
    except (urllib.error.URLError, OSError, ValueError):
        return None


class EmbeddedServer:
    """שרת האיתות הרץ בתוך תהליך המארח, עם הכתובות שהצד השני צריך."""

    def __init__(self, server: SignalingServer, ws_server, port: int, lan: str | None) -> None:
        self._server = server
        self._ws_server = ws_server
        self.port = port
        self.lan_ip = lan
        self.public_ip: str | None = None   # ממולא בנפרד (דורש רשת); ראו fill_public_ip

    @property
    def active_connections(self) -> int:
        return len(self._server.clients)

    async def fill_public_ip(self) -> str | None:
        self.public_ip = await asyncio.get_running_loop().run_in_executor(None, public_ip)
        return self.public_ip

    async def close(self) -> None:
        self._ws_server.close()
        await self._ws_server.wait_closed()


async def start(port: int = 8765) -> EmbeddedServer:
    """מפעיל שרת איתות על כל הממשקים (0.0.0.0) בפורט הנתון."""
    server = SignalingServer()
    ws_server = await websockets.serve(
        server.handler, "0.0.0.0", port, max_size=P.MAX_SIGNAL_BYTES,
    )
    # lan_ip() חוסם סינכרונית (socket.connect עם timeout) - לא רוצים לתקוע את
    # לולאת ה-asyncio איתו, אז מריצים אותו ב-executor.
    ip = await asyncio.get_running_loop().run_in_executor(None, lan_ip)
    return EmbeddedServer(server, ws_server, port, ip)
