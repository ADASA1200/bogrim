"""Wake-on-LAN: שליחת מגיק-פאקט לרשת המקומית להעיר מחשב כבוי/בשינה לפני
ניסיון להתחבר אליו (כמו הפיצ'ר המקביל ב-AnyDesk). עובד רק באותה רשת
מקומית (broadcast) - בלי VPN/תיעול מיוחד אין דרך לשלוח WoL מהאינטרנט."""
from __future__ import annotations

import re
import socket

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def normalize_mac(mac: str) -> str:
    mac = (mac or "").strip()
    if not _MAC_RE.match(mac):
        raise ValueError("bad_mac")
    return mac


def _mac_bytes(mac: str) -> bytes:
    return bytes(int(b, 16) for b in re.split("[:-]", mac))


def build_magic_packet(mac: str) -> bytes:
    """6 בתים של 0xFF ואז כתובת ה-MAC חזורה 16 פעם - הפורמט הסטנדרטי."""
    return b"\xff" * 6 + _mac_bytes(normalize_mac(mac)) * 16


def send(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, port))
