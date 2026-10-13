"""בדיקות ל-PrivacyGuard: חוסם קלט מקומי בזמן מצב פרטיות. משתמשות ב-listener
מזויף (לא pynput אמיתי) כדי לא לתפוס קלט פיזי בפועל בתוך הרצת בדיקה."""
import time

from rdesk.privacy import PrivacyGuard


class FakeListener:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def fake_listeners():
    return FakeListener(), FakeListener()


def test_enable_starts_listeners_and_sets_active():
    guard = PrivacyGuard(listener_factory=fake_listeners)
    assert not guard.active
    guard.enable()
    assert guard.active
    assert guard._kb.started
    assert guard._mouse.started
    guard.disable()


def test_disable_stops_listeners_and_clears_active():
    guard = PrivacyGuard(listener_factory=fake_listeners)
    guard.enable()
    kb, mouse = guard._kb, guard._mouse
    guard.disable()
    assert not guard.active
    assert kb.stopped
    assert mouse.stopped
    assert guard._kb is None and guard._mouse is None


def test_enable_twice_is_a_no_op():
    calls = []

    def factory():
        calls.append(1)
        return FakeListener(), FakeListener()

    guard = PrivacyGuard(listener_factory=factory)
    guard.enable()
    guard.enable()
    assert len(calls) == 1
    guard.disable()


def test_disable_without_enable_is_a_no_op():
    guard = PrivacyGuard(listener_factory=fake_listeners)
    guard.disable()   # לא אמור לזרוק
    assert not guard.active


def test_enable_does_not_raise_even_without_a_display():
    """ה-overlay רץ ב-thread נפרד ומטפל בחריגות שלו (למשל בלי DISPLAY) -
    enable() עצמו לא אמור להיכשל."""
    guard = PrivacyGuard(listener_factory=fake_listeners)
    guard.enable()
    time.sleep(0.2)   # נותן ל-thread של ה-overlay רגע לנסות ולהיכשל בשקט
    assert guard.active
    guard.disable()
