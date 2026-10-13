"""בדיקות ל-wol.py (Wake-on-LAN)."""
import socket

import pytest

from rdesk import wol


def test_normalize_mac_accepts_colon_and_dash():
    assert wol.normalize_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"
    assert wol.normalize_mac("aa-bb-cc-dd-ee-ff") == "aa-bb-cc-dd-ee-ff"


def test_normalize_mac_rejects_garbage():
    for bad in ("", "not a mac", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AABBCCDDEEFF"):
        with pytest.raises(ValueError):
            wol.normalize_mac(bad)


def test_build_magic_packet_shape():
    packet = wol.build_magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    mac = bytes.fromhex("AABBCCDDEEFF")
    assert packet[6:12] == mac
    assert packet[-6:] == mac
    assert packet.count(mac) == 16


def test_send_broadcasts_a_udp_packet(monkeypatch):
    sent = {}

    class FakeSocket:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def setsockopt(self, *a):
            sent["broadcast_enabled"] = True

        def sendto(self, data, addr):
            sent["data"] = data
            sent["addr"] = addr

    monkeypatch.setattr(socket, "socket", FakeSocket)
    wol.send("AA:BB:CC:DD:EE:FF", broadcast="192.168.1.255", port=9)

    assert sent["broadcast_enabled"]
    assert sent["addr"] == ("192.168.1.255", 9)
    assert len(sent["data"]) == 102
