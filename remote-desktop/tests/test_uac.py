"""בדיקות ל-uac.py: בלינוקס (סביבת הבדיקות) שתי הפונקציות אמורות להחזיר
False/לא לנסות כלום - אין להן שום משמעות בלי Windows. מדמים גם win32
כדי לבדוק את ה-fallback כשה-API לא קיים בפועל."""
from rdesk import uac


def test_is_elevated_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "linux")
    assert uac.is_elevated() is False


def test_request_elevation_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "linux")
    assert uac.request_elevation() is False


def test_is_elevated_handles_missing_ctypes_api_gracefully(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "win32")
    assert uac.is_elevated() is False   # אין ctypes.windll אמיתי בלינוקס - נכשל בשקט


def test_request_elevation_handles_missing_ctypes_api_gracefully(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "win32")
    assert uac.request_elevation() is False


def test_request_elevation_passes_args_and_interprets_result(monkeypatch):
    calls = []

    class FakeShell32:
        def ShellExecuteW(self, hwnd, verb, exe, params, directory, show):
            calls.append((verb, exe, params))
            return 33   # > 32 = הצליח להציג את הבקשה

    class FakeWindll:
        shell32 = FakeShell32()

    class FakeCtypes:
        windll = FakeWindll()

    monkeypatch.setattr(uac.sys, "platform", "win32")
    monkeypatch.setitem(__import__("sys").modules, "ctypes", FakeCtypes())

    assert uac.request_elevation(["--elevated-helper"]) is True
    assert calls[0][0] == "runas"
    assert "--elevated-helper" in calls[0][2]


def test_request_elevation_false_when_shell_execute_fails(monkeypatch):
    class FakeShell32:
        def ShellExecuteW(self, *a):
            return 0   # כישלון (למשל המשתמש ביטל את ה-UAC)

    class FakeWindll:
        shell32 = FakeShell32()

    class FakeCtypes:
        windll = FakeWindll()

    monkeypatch.setattr(uac.sys, "platform", "win32")
    monkeypatch.setitem(__import__("sys").modules, "ctypes", FakeCtypes())

    assert uac.request_elevation() is False
