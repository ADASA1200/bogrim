"""בדיקות ל-rdesk.webapp (הגשר בין React ל-Python) בלי חלון pywebview אמיתי -
מריצות את אותה לוגיקה (HostAPI/ViewerAPI) שה-UI קורא לה, עם push() מוקלט
במקום evaluate_js אמיתי. הבדיקה הידנית המלאה (עם WebKitGTK אמיתי) נעשתה
בנפרד; זו הבדיקה שרצה כל הזמן ב-CI."""
import asyncio
import time

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
    yield api

    # בלי סגירה מפורשת כאן, שרת האיתות המוטבע וה-HostService.run() של הבדיקה
    # הזו נשארים פעילים ברקע עד ש-runner.stop() עוצר את הלולאה - וזה התחרות
    # (race) שגרמה ל-Fatal Python error: Aborted בין Thread-ים שונים כשהבדיקות
    # רבות מספיק כדי להצטבר. עדיף לסגור הכול באופן דטרמיניסטי כאן.
    async def cleanup():
        await api.service.stop()
        if api.embedded is not None:
            await api.embedded.close()

    try:
        runner.submit(cleanup()).result(timeout=5)
    except Exception:
        pass


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
    # "מחובר בתור X · מחשב Y" בכרטיס "המחשב הזה" - כמו "Logged in as" ב-AnyDesk
    assert s["username"]
    assert s["computer"]


def test_viewer_preset_includes_local_identity(runner):
    """ConnectScreen מציג למשתמש בשקיפות מה ישותף עם המארח ("שם המשתמש
    והמחשב שלכם (X@Y) יוצגו למארח") - גם כש-preset לא הוגדר כלל (חיבור
    ידני רגיל, לא דרך openViewer/invite-link)."""
    viewer = webapp.ViewerAPI(runner, None)
    p = viewer.getViewerPreset()
    assert p["username"]
    assert p["computer"]


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

    # Whiteboard (שיתוף סקיצות) - גם זה דו-כיווני, על אותו control channel
    stroke = {"type": "stroke", "points": [[0.1, 0.1], [0.2, 0.2]], "color": "#fff", "width": 3}
    viewer_api.sendWhiteboard(stroke)
    assert await wait_for(lambda: any(k == "whiteboard" and d["data"] == stroke for k, d in host_events))
    host_api.sendWhiteboard({"type": "clear"})
    assert await wait_for(lambda: any(k == "whiteboard" and d["data"] == {"type": "clear"} for k, d in viewer_events))

    # הרמת הרשאות (UAC): בקשה מהצופה -> אירוע אצל המארח -> תגובה חוזרת.
    # מדמים שה-OS "הציג" את ה-UAC בהצלחה (uac.request_elevation) - זה לינוקס,
    # אין שום משמעות אמיתית ל-UAC כאן; זו בדיקת הפרוטוקול/הגישור בלבד.
    import rdesk.uac as uac_module
    uac_calls = []
    orig_request_elevation = uac_module.request_elevation
    uac_module.request_elevation = lambda *a, **kw: (uac_calls.append(1) or True)
    try:
        viewer_api.requestElevation()
        assert await wait_for(lambda: any(k == "elevation_requested" for k, _ in host_events))
        host_api.respondElevation(True)
        assert await wait_for(lambda: any(k == "elevate_result" and d["ok"] is True for k, d in viewer_events))
        assert uac_calls == [1]
    finally:
        uac_module.request_elevation = orig_request_elevation

    # הרשאות
    host_api.setPermission("files", False)
    assert await wait_for(lambda: any(k == "perms_changed" and not d["perms"]["files"] for k, d in viewer_events))

    # ניתוק מצד הצופה -> המארח רואה session_end
    viewer_api.viewerDisconnect()
    assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))
    assert host_api.getState()["session"] is None


class FakePrivacyGuard:
    """תחליף ל-PrivacyGuard האמיתי - בודק רק את חיווט ה-API, בלי לתפוס קלט
    פיזי או לפתוח חלון overlay אמיתי בתוך בדיקה אוטומטית."""

    def __init__(self):
        self.active = False

    def enable(self):
        self.active = True

    def disable(self):
        self.active = False


async def test_privacy_mode_toggle_and_auto_disable_on_session_end(host_api, host_events, runner):
    fake_privacy = FakePrivacyGuard()
    host_api.service.privacy = fake_privacy
    await wait_online(host_api)
    port = host_api.embedded_port

    viewer_api = webapp.ViewerAPI(runner, None)
    viewer_events = []
    viewer_api.push = recorder(viewer_events)

    async def do_connect():
        return await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")

    fut = runner.submit(do_connect())
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    host_api.respondApproval(req["requestId"], {"control": True, "clipboard": True, "files": True, "chat": True})
    await asyncio.wrap_future(fut)

    assert not fake_privacy.active
    host_api.setPrivacyMode(True)
    assert await wait_for(lambda: fake_privacy.active, 5)
    assert any(k == "privacy_changed" and d["enabled"] for k, d in host_events)

    viewer_api.viewerDisconnect()
    assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))
    assert await wait_for(lambda: not fake_privacy.active, 5)   # לא משאירים נעול אחרי שהסשן נגמר


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


def test_wol_mac_round_trip_and_rejects_bad_mac(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    viewer = webapp.ViewerAPI(runner, None)

    assert viewer.getWolMac("135791357") == ""
    viewer.setWolMac("135791357", "AA:BB:CC:DD:EE:FF")
    assert viewer.getWolMac("135791357") == "AA:BB:CC:DD:EE:FF"

    with pytest.raises(Exception):
        viewer.setWolMac("135791357", "not a mac")


def test_wake_on_lan_sends_packet_for_saved_mac(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    sent = []
    monkeypatch.setattr(webapp.wol, "send", lambda mac, **kw: sent.append(mac))

    viewer = webapp.ViewerAPI(runner, None)
    with pytest.raises(Exception, match="no_mac_saved"):
        viewer.wakeOnLan("135791357")

    viewer.setWolMac("135791357", "AA:BB:CC:DD:EE:FF")
    viewer.wakeOnLan("135791357")
    assert sent == ["AA:BB:CC:DD:EE:FF"]


def test_create_invite_link_is_one_time_use(host_api):
    info = host_api.createInviteLink(minutes=5)
    assert info["url"].startswith(f"rdesk://connect/{host_api.id}/")
    parsed = P.parse_invite_url(info["url"])
    assert parsed["id"] == host_api.id

    perms = host_api._check_invite(parsed["token"])
    assert perms is not None and perms.control is True
    assert host_api._check_invite(parsed["token"]) is None   # חד-פעמי - בשנייה אין כלום


def test_create_invite_link_expires(host_api, monkeypatch):
    info = host_api.createInviteLink(minutes=5)
    parsed = P.parse_invite_url(info["url"])

    real_time = time.time
    monkeypatch.setattr(webapp.time, "time", lambda: real_time() + 10 * 60)
    assert host_api._check_invite(parsed["token"]) is None


async def test_regenerate_id_updates_config_and_host_service(host_api, runner):
    """למשתמש שה-ID האקראי שהוגרל "נראה" לו קליט/לא מספיק אקראי - אפשרות
    להחליף אותו. בודקים שזה לא רק שינוי קוסמטי: ה-HostService עצמו (שקובע
    עם איזה מזהה הוא נרשם מול שרת האיתות) מתעדכן בהתאם."""
    await wait_online(host_api)
    old_id = host_api.id

    new_id = host_api.regenerateId()
    assert new_id != old_id
    assert len(new_id) == 9 and new_id.isdigit()
    assert host_api.id == new_id
    assert webapp.config.load()["id"] == new_id
    assert await wait_for(lambda: host_api.service.id == new_id, 5)


def test_open_viewer_allows_connecting_to_this_computer_itself(host_api, monkeypatch):
    """בעבר openViewer חזר בלי לעשות כלום אם המזהה המבוקש היה המזהה של
    המחשב הזה עצמו - חסימה שקטה בלי שום משוב, שגרמה למי שרצה לבדוק את
    ה-flow המלא (מארח+צופה על אותו מחשב) לחשוב ש"בקשת החיבור לא קופצת".
    הוסר בכוונה: צריך אופציה להתחבר לעצמך, לבדיקה."""
    opened = []
    monkeypatch.setattr(webapp, "open_viewer_window",
                        lambda server_arg, runner, preset=None, **kw: opened.append((server_arg, preset)))

    host_api.openViewer(host_api.id, "")

    assert len(opened) == 1
    _, preset = opened[0]
    assert preset["id"] == host_api.id
    assert host_api.id in webapp.config.load()["recent"]


def test_viewer_preset_autoconnect_is_consumed_once(runner):
    """רגרסיה: viewer window שנפתח עם autoConnect=True (openViewer, invite
    link) וחוזר למסך ההתחברות אחרי ניתוק (ConnectScreen נטען מחדש) לא אמור
    להתחבר-מחדש אוטומטית בלי שהמשתמש ביקש - זה היה שולח למארח בקשת אישור
    חדשה בכל פעם שסשן הסתיים, אפילו ניתוק יזום."""
    preset = {"server": "ws://127.0.0.1:8765", "id": "111222333", "password": "", "autoConnect": True}
    viewer = webapp.ViewerAPI(runner, preset)

    first = viewer.getViewerPreset()
    assert first["autoConnect"] is True

    second = viewer.getViewerPreset()
    assert second["autoConnect"] is False
    assert second["id"] == "111222333"   # שאר השדות נשארים זמינים למילוי השדות מחדש

    third = viewer.getViewerPreset()
    assert third["autoConnect"] is False


def test_parse_invite_link_via_viewer_api(runner):
    viewer = webapp.ViewerAPI(runner, None)
    url = P.make_invite_url("135791357", "tok", "ws://127.0.0.1:8765")
    assert viewer.parseInviteLink(url) == {"id": "135791357", "token": "tok", "server": "ws://127.0.0.1:8765"}
    assert viewer.parseInviteLink("not a link") is None


def test_start_tunnel_without_connection_raises(runner):
    viewer = webapp.ViewerAPI(runner, None)
    with pytest.raises(Exception, match="not_connected"):
        viewer.startTunnel(12345, "127.0.0.1", 80)


async def test_start_tunnel_via_viewer_api_relays_real_bytes(host_api, host_events, runner):
    import asyncio as _asyncio

    await wait_online(host_api)
    port = host_api.embedded_port

    echo_port = free_port()

    async def handle_echo(reader, writer):
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    echo_srv = await _asyncio.start_server(handle_echo, "127.0.0.1", echo_port)
    local_port = free_port()
    try:
        viewer_api = webapp.ViewerAPI(runner, None)
        viewer_api.push = recorder([])

        async def do_connect():
            return await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")

        fut = runner.submit(do_connect())
        assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
        req = next(d for k, d in host_events if k == "ask_approval")
        host_api.respondApproval(req["requestId"], {"control": True, "clipboard": True, "files": True, "chat": True})
        await _asyncio.wrap_future(fut)

        viewer_api.startTunnel(local_port, "127.0.0.1", echo_port)
        reader, writer = await _asyncio.open_connection("127.0.0.1", local_port)
        writer.write(b"via webapp bridge")
        await writer.drain()
        data = await _asyncio.wait_for(reader.read(100), 5)
        assert data == b"via webapp bridge"
        writer.close()

        viewer_api.stopTunnel(local_port)
        viewer_api.viewerDisconnect()
        assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))
    finally:
        echo_srv.close()
        await echo_srv.wait_closed()


async def _start_signaling_on_runner(runner, port, accounts_path):
    """מריצים גם את שרת האיתות על הלולאה של runner (לא על לולאת הבדיקה) -
    חיבור בין שתי לולאות asyncio שונות בתוך אותו תהליך נתקע בסנדבוקס הזה
    (זה לא מתאים לייצור, שם הלקוח מתחבר לתהליך/מחשב אחר לגמרי ממילא)."""
    from rdesk.signaling_server import serve as serve_signaling
    return await asyncio.wrap_future(runner.submit(serve_signaling("127.0.0.1", port, accounts_path=accounts_path)))


async def _stop_signaling_on_runner(runner, ws_server):
    async def _close():
        ws_server.close()
        await ws_server.wait_closed()
    await asyncio.wrap_future(runner.submit(_close()))


async def test_account_register_login_and_address_book(tmp_path, runner, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    port = free_port()
    ws_server = await _start_signaling_on_runner(runner, port, tmp_path / "accounts.json")
    try:
        api = webapp.HostAPI(None, runner, injector=NullInjector(), screen=SyntheticScreen())
        api.server = f"ws://127.0.0.1:{port}"

        assert api.getAccountState() == {"loggedIn": False, "username": None}

        r = api.registerAccount("alice", "a-long-enough-password")
        assert r["loggedIn"] is True
        assert r["contacts"] == []
        assert api.getAccountState() == {"loggedIn": True, "username": "alice"}

        api.setAddressBook([{"id": "111222333", "label": "חבר"}])
        assert api.getAddressBook() == [{"id": "111222333", "label": "חבר"}]

        # דף חדש (למשל הפעלה מחדש של האפליקציה) - הפרטים נטענים מהדיסק ומתחברים מחדש
        api2 = webapp.HostAPI(None, runner, injector=NullInjector(), screen=SyntheticScreen())
        api2.server = f"ws://127.0.0.1:{port}"
        assert api2.getAccountState() == {"loggedIn": True, "username": "alice"}
        assert api2.getAddressBook() == [{"id": "111222333", "label": "חבר"}]

        api2.logoutAccount()
        assert api2.getAccountState() == {"loggedIn": False, "username": None}
    finally:
        await _stop_signaling_on_runner(runner, ws_server)


async def test_login_account_wrong_password_raises(tmp_path, runner, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    port = free_port()
    ws_server = await _start_signaling_on_runner(runner, port, tmp_path / "accounts.json")
    try:
        api = webapp.HostAPI(None, runner, injector=NullInjector(), screen=SyntheticScreen())
        api.server = f"ws://127.0.0.1:{port}"
        api.registerAccount("alice", "a-long-enough-password")

        with pytest.raises(Exception, match="bad_credentials"):
            api.loginAccount("alice", "wrong-password")
    finally:
        await _stop_signaling_on_runner(runner, ws_server)


def test_viewer_auto_prints_file_named_as_print_job(runner, monkeypatch):
    printed = []
    monkeypatch.setattr(webapp.printing, "print_received_file", lambda path: printed.append(path) or True)

    viewer = webapp.ViewerAPI(runner, None)
    events = []
    viewer.push = recorder(events)

    viewer._on_event("file_received", name="rdesk-print-report.pdf", path="/tmp/rdesk-print-report.pdf")
    assert printed == ["/tmp/rdesk-print-report.pdf"]
    assert events == [("file_event", {"kind": "printed", "path": "/tmp/rdesk-print-report.pdf"})]


def test_viewer_does_not_auto_print_ordinary_files(runner, monkeypatch):
    printed = []
    monkeypatch.setattr(webapp.printing, "print_received_file", lambda path: printed.append(path) or True)

    viewer = webapp.ViewerAPI(runner, None)
    events = []
    viewer.push = recorder(events)

    viewer._on_event("file_received", name="vacation.jpg", path="/tmp/vacation.jpg")
    assert printed == []
    assert events == [("file_event", {"kind": "received", "path": "/tmp/vacation.jpg"})]


async def test_host_forwards_new_print_file_to_connected_viewer(host_api, host_events, runner, tmp_path, monkeypatch):
    printed = []
    monkeypatch.setattr(webapp.printing, "print_received_file", lambda path: printed.append(path) or True)

    await wait_online(host_api)
    port = host_api.embedded_port

    viewer_api = webapp.ViewerAPI(runner, None)
    viewer_events = []
    viewer_api.push = recorder(viewer_events)

    async def do_connect():
        return await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")

    fut = runner.submit(do_connect())
    assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
    req = next(d for k, d in host_events if k == "ask_approval")
    host_api.respondApproval(req["requestId"], {"control": True, "clipboard": True, "files": True, "chat": True})
    await asyncio.wrap_future(fut)

    fake_pdf = tmp_path / "out.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake printable content")
    await asyncio.wrap_future(runner.submit(host_api._on_print_file(fake_pdf)))

    assert await wait_for(lambda: any(k == "file_event" and d["kind"] == "printed" for k, d in viewer_events), 10)
    assert len(printed) == 1
    assert "rdesk-print-out" in printed[0] and printed[0].endswith(".pdf")
    assert not fake_pdf.exists()   # נמחק/נדחף - בכל מקרה לא נשאר במקום המקורי

    viewer_api.viewerDisconnect()
    assert await wait_for(lambda: any(k == "session_end" for k, _ in host_events))


async def test_declined_elevation_never_calls_uac_and_reports_not_ok(host_api, host_events, runner):
    import rdesk.uac as uac_module

    uac_calls = []
    orig = uac_module.request_elevation
    uac_module.request_elevation = lambda *a, **kw: (uac_calls.append(1) or True)
    try:
        await wait_online(host_api)
        port = host_api.embedded_port

        viewer_api = webapp.ViewerAPI(runner, None)
        viewer_events = []
        viewer_api.push = recorder(viewer_events)

        async def do_connect():
            return await viewer_api._connect(f"ws://127.0.0.1:{port}", "135791357", "")

        fut = runner.submit(do_connect())
        assert await wait_for(lambda: any(k == "ask_approval" for k, _ in host_events), 10)
        req = next(d for k, d in host_events if k == "ask_approval")
        host_api.respondApproval(req["requestId"], {"control": True, "clipboard": True, "files": True, "chat": True})
        await asyncio.wrap_future(fut)

        viewer_api.requestElevation()
        assert await wait_for(lambda: any(k == "elevation_requested" for k, _ in host_events))
        host_api.respondElevation(False)   # המשתמש במארח דוחה את הבקשה

        assert await wait_for(lambda: any(k == "elevate_result" and d["ok"] is False for k, d in viewer_events))
        assert uac_calls == []   # לא ניגשים כלל ל-OS אם המשתמש דחה

        viewer_api.viewerDisconnect()
    finally:
        uac_module.request_elevation = orig
