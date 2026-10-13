"""בדיקות ל-rdesk.__main__: זיהוי קישור הזמנה (rdesk://) בשורת הפקודה, בלי
לפתוח חלון pywebview אמיתי (מוקים ל-_run_viewer_ui/net.use_system_trust_store)."""
from rdesk import __main__ as m


def test_invite_url_argv_routes_to_viewer_ui(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_run_viewer_ui", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(m.net, "use_system_trust_store", lambda: None)

    m.main(["rdesk://connect/123456789/sometoken?server=ws%3A%2F%2Fx"])

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] is None   # server
    assert args[1] is False  # legacy
    assert kwargs["invite_url"] == "rdesk://connect/123456789/sometoken?server=ws%3A%2F%2Fx"


def test_normal_argv_does_not_trigger_invite_path(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_run_viewer_ui", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(m, "_run_host_ui", lambda *a, **kw: calls.append(("host", a, kw)))
    monkeypatch.setattr(m.net, "use_system_trust_store", lambda: None)

    m.main(["app", "--server", "ws://127.0.0.1:8765"])

    # לא היה אמור להיכנס לנתיב ה-invite בכלל - _run_host_ui נקרא במקום
    assert any(c[0] == "host" for c in calls if isinstance(c, tuple) and len(c) == 3)
