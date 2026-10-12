"""בדיקות ל-rdesk.webapp (הגשר בין React ל-Python) בלי חלון pywebview אמיתי -
מריצות את אותה לוגיקה (HostAPI/ViewerAPI) שה-UI קורא לה, עם push() מוקלט
במקום evaluate_js אמיתי. הבדיקה הידנית המלאה (עם WebKitGTK אמיתי) נעשתה
בנפרד; זו הבדיקה שרצה כל הזמן ב-CI."""
import asyncio

import pytest

from rdesk import protocol as P, webapp
from rdesk.aio import AsyncRunner
from rdesk.capture import SyntheticScreen
from rdesk.inject import NullInjector
from test_end_to_end import free_port, wait_for


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
