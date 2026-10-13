"""בדיקות ל-rdesk.webapp (הגשר בין React ל-Python) בלי חלון pywebview אמיתי -
מריצות את אותה לוגיקה (HostAPI/ViewerAPI) שה-UI קורא לה, עם push() מוקלט
במקום evaluate_js אמיתי. הבדיקה הידנית המלאה (עם WebKitGTK אמיתי) נעשתה
בנפרד; זו הבדיקה שרצה כל הזמן ב-CI."""
import asyncio

import pytest

from rdesk import protocol as P, webapp
from rdesk import tray as rdesk_tray
from rdesk.aio import AsyncRunner
from rdesk.capture import SyntheticScreen
from rdesk.inject import NullInjector
from test_end_to_end import free_port, wait_for


class FakeTrayIcon:
    """תחליף קל ל-TrayIcon האמיתי (pystray) - בודק רק שה-API מקבל את
    הקריאות הנכונות, בלי תלות בבאקאנד מגש אמיתי של המערכת."""

    def __init__(self, on_open, on_disconnect, on_quit):
        self.on_open, self.on_disconnect, self.on_quit = on_open, on_disconnect, on_quit
        self.available = True
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def set_connected(self, connected, peer=""):
        self.calls.append(("connected", connected, peer))


def recorder(events: list):
    def push(kind, data=None):
        events.append((kind, data))
    return push


@pytest.fixture
def runner():
    r = AsyncRunner()
    yield r
    r.stop()


@pytest.fixture
def host_events():
    return []


@pytest.fixture
def host_api(tmp_path, runner, host_events, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    # connlog.LOG_FILE מחושב פעם אחת מ-CONFIG_DIR בזמן import - בלי זה הבדיקות
    # היו כותבות ליומן האמיתי ב-~/.rdesk במקום לתיקייה הזמנית של הבדיקה.
    monkeypatch.setattr(webapp.connlog, "LOG_FILE", tmp_path / "connections.json")
    webapp.config.save({"id": "135791357", "embedded_server": {"enabled": True, "port": free_port()}})
    api = webapp.HostAPI(None, runner, injector=NullInjector(), screen=SyntheticScreen())
    api.push = recorder(host_events)
    api.start()
    return api


async def wait_online(api, timeout=5):
    assert await wait_for(lambda: api._online, timeout)


async def test_get_state_shape(host_api):
    await wait_online(host_api)
    s = host_api.getState()
    assert s["id"] == "135791357"
    assert s["online"] is True
    assert s["embedded"]["enabled"] is True
    assert s["session"] is None
    assert s["unattended"]["enabled"] is False


async def test_full_connect_approve_video_chat_disconnect(host_api, host_events, runner, tmp_path):
    await wait_online(host_api)
    port = host_api.embedded_port

    viewer_events = []
    viewer_api = webapp.ViewerAPI(runner, None)
    viewer_api.push = recorder(viewer_events)

    async def do_connect():
        return await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")

    fut = runner.submit(do_connect())

    # ממתינים שבקשת האישור תגיע ל-API של המארח (כמו שה-React modal היה עושה)
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    host_api.respondApproval(req["requestId"], {"control": True, "clipboard": True, "files": True, "chat": True})

    info = await asyncio.wrap_future(fut)
    assert info["mode"] == "interactive"
    assert len(info["code"]) == 7

    # וידאו: ה-frame pump אמור לדחוף אירועי "frame" (base64 jpeg) לצד הצופה
    assert await wait_for(lambda: any(k == "frame" for k, _ in viewer_events), 5)
    assert isinstance(next(d for k, d in viewer_events if k == "frame"), str)

    # קוד האבטחה זהה משני הצדדים
    host_code = next(d["code"] for k, d in host_events if k == "session_start")
    assert host_code == info["code"]

    # צ'אט בשני הכיוונים
    viewer_api.sendChat("שלום מהצופה")
    assert await wait_for(lambda: any(k == "chat" and d["text"] == "שלום מהצופה" for k, d in host_events))
    host_api.sendChat("שלום מהמארח")
    assert await wait_for(lambda: any(k == "chat" and d["text"] == "שלום מהמארח" for k, d in viewer_events))

    # הרשאות
    host_api.setPermission("files", False)
    assert await wait_for(lambda: any(k == "perms_changed" and not d["perms"]["files"] for k, d in viewer_events))

    # ניתוק מצד הצופה -> המארח רואה session_end
    viewer_api.viewerDisconnect()
    assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))
    assert host_api.getState()["session"] is None


async def test_approval_decline_and_timeout_path(host_api, host_events, runner):
    await wait_online(host_api)
    port = host_api.embedded_port
    viewer_api = webapp.ViewerAPI(runner, None)
    viewer_api.push = recorder([])

    async def do_connect():
        try:
            await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")
            return "connected"
        except Exception as e:
            return str(e)

    fut = runner.submit(do_connect())
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    host_api.respondApproval(req["requestId"], None)   # דחייה

    result = await asyncio.wrap_future(fut)
    assert result == "declined"


def test_set_unattended_validation(host_api):
    with pytest.raises(Exception, match="need_password"):
        host_api.setUnattended({"enabled": True})
    with pytest.raises(Exception, match="too_short"):
        host_api.setUnattended({"enabled": True, "password": "short"})
    host_api.setUnattended({"enabled": True, "password": "a-long-enough-password",
                            "control": True, "clipboard": False, "files": True})
    s = host_api.getState()
    assert s["unattended"]["enabled"] is True
    assert s["unattended"]["clipboard"] is False


def test_get_clipboard_text(host_api, monkeypatch):
    monkeypatch.setattr(host_api._clipboard, "get", lambda: "hello from clipboard")
    assert host_api.getClipboardText() == "hello from clipboard"


def test_get_clipboard_text_empty_when_none(host_api, monkeypatch):
    monkeypatch.setattr(host_api._clipboard, "get", lambda: None)
    assert host_api.getClipboardText() == ""


def test_tray_tracks_session_lifecycle(host_api, monkeypatch):
    monkeypatch.setattr(rdesk_tray, "TrayIcon", FakeTrayIcon)
    host_api.init_tray()
    fake = host_api.tray
    assert fake.calls == ["start"]

    host_api._on_event("session_start", peer="111222333", perms={}, mode="interactive", code="1234567")
    assert ("connected", True, "111222333") in fake.calls

    host_api._on_event("session_end")
    assert fake.calls[-1] == ("connected", False, "")


async def test_approval_lights_tray_and_resets_on_decline(host_api, host_events, runner, monkeypatch):
    monkeypatch.setattr(rdesk_tray, "TrayIcon", FakeTrayIcon)
    host_api.init_tray()
    fake = host_api.tray
    await wait_online(host_api)
    port = host_api.embedded_port

    viewer_api = webapp.ViewerAPI(runner, None)
    viewer_api.push = recorder([])

    async def do_connect():
        try:
            await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")
            return "connected"
        except Exception as e:
            return str(e)

    fut = runner.submit(do_connect())
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    assert ("connected", True, req["peer"]) in fake.calls

    host_api.respondApproval(req["requestId"], None)  # דחייה

    result = await asyncio.wrap_future(fut)
    assert result == "declined"
    assert fake.calls[-1] == ("connected", False, "")


def test_connection_log_round_trip(host_api):
    host_api._on_event("session_start", peer="v1", mode="interactive", perms={"control": True}, code="1234567")
    host_api._on_event("session_end", peer="v1")

    log = host_api.getConnectionLog()
    assert len(log) == 1
    assert log[0]["peer"] == "v1"
    assert log[0]["mode"] == "interactive"
    assert log[0]["endedAt"] is not None

    host_api.clearConnectionLog()
    assert host_api.getConnectionLog() == []


def test_trusted_devices_list_and_remove(host_api):
    host_api.cfg = webapp.config.load()
    webapp.config.set_trusted(host_api.cfg, "v_test_device", P.Permissions())

    devices = host_api.getTrustedDevices()
    assert any(d["peer"] == "v_test_device" for d in devices)

    host_api.removeTrustedDevice("v_test_device")
    devices = host_api.getTrustedDevices()
    assert not any(d["peer"] == "v_test_device" for d in devices)


async def test_remembering_a_device_wires_up_host_service_trust_check(host_api, host_events, runner):
    """בדיקת ה-API/ה-webui: "זכור מכשיר זה" בחלון האישור שומר פרופיל הרשאות,
    וה-HostService (trust_check) רואה אותו דרך self.cfg המתעדכן. בדיקה נפרדת
    וקלה יותר ל"מתחבר שוב בלי אישור בפועל" (בלי handshake WebRTC שני, יקר ולא
    נחוץ כאן) נמצאת ב-test_embedded_server.py."""
    await wait_online(host_api)
    port = host_api.embedded_port

    viewer = webapp.ViewerAPI(runner, None)
    viewer.push = recorder([])

    async def connect():
        return await viewer._connect(f"ws://127.0.0.1:{port}", "135791357", "")

    fut = runner.submit(connect())
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    peer = req["peer"]
    host_api.respondApproval(req["requestId"],
                              {"control": True, "clipboard": False, "files": True, "chat": True, "remember": True})
    info = await asyncio.wrap_future(fut)
    assert info["mode"] == "interactive"   # מנקודת המבט של הצופה - לא השתמש בסיסמה

    assert webapp.config.get_trusted(webapp.config.load(), peer) is not None
    trusted_perms = host_api.service.trust_check(peer)
    assert trusted_perms is not None and trusted_perms.clipboard is False

    viewer.viewerDisconnect()
    assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))
