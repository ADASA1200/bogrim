"""בדיקות ל-uac.py: בלינוקס (סביבת הבדיקות) שתי הפונקציות אמורות להחזיר
False/לא לנסות כלום - אין להן שום משמעות בלי Windows. מדמים גם win32
כדי לבדוק את ה-fallback כשה-API לא קיים בפועל.

קריטי: "אין ctypes.windll אמיתי" חייב להיות מדומה במפורש (sys.modules["ctypes"]
מוחלף), ולא רק מונח כהנחה שקטה על סביבת הבדיקות! בגרסה קודמת של הבדיקות האלה
הייתה רק monkeypatch.setattr(uac.sys, "platform", "win32") בלי לגעת ב-ctypes
בכלל - זה "עבד" בלינוקס רק כי ctypes.windll באמת לא קיים שם, אבל בהרצה על
Windows אמיתי ctypes.windll.shell32 כן קיים ועובד, אז test_request_elevation
קרא בפועל ל-ShellExecuteW(None, "runas", sys.executable, "", None, 1) - והציג
(או אפילו ביצע בהצלחה) בקשת UAC אמיתית להרמת python.exe ריק על המחשב שהריץ
את הבדיקות. לעולם לא לסמוך על "אין ctypes.windll בסביבה הזו" מבלי לאכוף את
זה בעצמנו - ראו FakeCtypesWithoutWindll למטה."""
from rdesk import uac


class FakeCtypesWithoutWindll:
    """מדמה מודול ctypes בלי windll בכלל (המצב האמיתי בלינוקס) - בניגוד
    לסמוך על זה שסביבת הריצה הנוכחית פשוט לא תומכת ב-windll."""


def test_is_elevated_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "linux")
    assert uac.is_elevated() is False


def test_request_elevation_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "linux")
    assert uac.request_elevation() is False


def test_is_elevated_handles_missing_ctypes_api_gracefully(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "win32")
    monkeypatch.setitem(__import__("sys").modules, "ctypes", FakeCtypesWithoutWindll())
    assert uac.is_elevated() is False


def test_request_elevation_handles_missing_ctypes_api_gracefully(monkeypatch):
    monkeypatch.setattr(uac.sys, "platform", "win32")
    monkeypatch.setitem(__import__("sys").modules, "ctypes", FakeCtypesWithoutWindll())
    assert uac.request_elevation() is False   # לא קורא בשום אופן ל-ShellExecuteW אמיתי


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
