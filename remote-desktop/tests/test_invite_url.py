"""בדיקות ל-protocol.make_invite_url/parse_invite_url (קישור הזמנה לסשן)."""
from rdesk import protocol as P


def test_round_trip():
    url = P.make_invite_url("123 456 789", "tok-abc_123", "ws://127.0.0.1:8765")
    parsed = P.parse_invite_url(url)
    assert parsed == {"id": "123456789", "token": "tok-abc_123", "server": "ws://127.0.0.1:8765"}


def test_round_trip_with_special_chars_in_server():
    url = P.make_invite_url("123456789", "tok", "wss://example.com:9999/path?a=b")
    parsed = P.parse_invite_url(url)
    assert parsed["server"] == "wss://example.com:9999/path?a=b"


def test_rejects_wrong_scheme():
    assert P.parse_invite_url("https://connect/123456789/tok") is None


def test_rejects_garbage():
    for bad in ("", "not a url at all", "rdesk://", "rdesk://connect/123456789", "rdesk://other/123456789/tok"):
        assert P.parse_invite_url(bad) is None
