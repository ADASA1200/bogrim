"""בדיקות מקצה לקצה ללא תצוגה גרפית: מסך מלאכותי, הזרקה מדומה, STUN כבוי."""
import asyncio
import socket

import pytest

from rdesk import protocol as P
from rdesk.capture import SyntheticScreen
from rdesk.clipboard import MemoryClipboard
from rdesk.host import HostService, make_rtc_config
from rdesk.inject import NullInjector
from rdesk.signaling_server import serve
from rdesk.viewer import ConnectError, ViewerClient


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_for(cond, timeout=15):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.fixture
async def env(tmp_path):
    port = free_port()
    server = await serve("127.0.0.1", port)
    url = f"ws://127.0.0.1:{port}"
    events = []
    inj = NullInjector()
    host_clip = MemoryClipboard("host-initial")
    approval_log = []

    async def approve(info):
        approval_log.append(info)
        return env.perms

    host = HostService(
        url, "123456789", "secret-pass", screen=SyntheticScreen(),
        injector=inj, clipboard=host_clip, approval=approve,
        on_event=lambda k, **kw: events.append((k, kw)),
        download_dir=tmp_path / "host_recv", rtc_config=make_rtc_config([]),
    )
    task = asyncio.ensure_future(host.run())
    await asyncio.wait_for(host.registered.wait(), 5)

    class Env: pass
    env = Env()
    env.url, env.host, env.inj, env.events, env.host_clip = url, host, inj, events, host_clip
    env.perms = P.Permissions()
    env.tmp = tmp_path
    env.approvals = approval_log

    def make_viewer(name="viewer"):
        vevents = []
        clip = MemoryClipboard("viewer-initial")
        v = ViewerClient(url, on_event=lambda k, **kw: vevents.append((k, kw)),
                         clipboard=clip, download_dir=tmp_path / (name + "_recv"),
                         rtc_config=make_rtc_config([]))
        v.events, v.clip = vevents, clip
        return v
    env.make_viewer = make_viewer
    yield env
    await host.stop()
    task.cancel()
    server.close()
    await server.wait_closed()


async def test_video_and_input(env):
    v = env.make_viewer()
    await v.connect("123 456 789", "secret-pass")
    assert v.connected and v.monitors[0]["width"] == 640
    assert await wait_for(lambda: v.frame_seq >= 3), "no video frames received"
    assert v.latest_frame.shape == (360, 640, 3)

    v.send_input({"t": "md", "b": "left", "x": 0.5, "y": 0.5})
    v.send_input({"t": "kd", "k": "a"})
    v.send_input({"t": "ku", "k": "a"})
    assert await wait_for(lambda: ("key", "a", False) in env.inj.events)
    assert ("move", 319, 179) in env.inj.events
    assert ("button", "left", True) in env.inj.events
    await v.disconnect()
    assert await wait_for(lambda: env.host.session is None)
    assert ("release_all",) in env.inj.events


async def test_wrong_password_rejected_and_blocked(env):
    v = env.make_viewer()
    with pytest.raises(ConnectError, match="bad password"):
        await v.connect("123456789", "nope")
    assert env.approvals == []          # אפילו לא הגיע לחלון אישור
    for _ in range(P.MAX_AUTH_ATTEMPTS):
        try:
            await env.make_viewer().connect("123456789", "nope")
        except ConnectError:
            pass
    with pytest.raises(ConnectError, match="blocked"):
        await env.make_viewer().connect("123456789", "secret-pass")


async def test_user_declines(env):
    async def decline(info): return None
    env.host.approval = decline
    with pytest.raises(ConnectError, match="declined"):
        await env.make_viewer().connect("123456789", "secret-pass")


async def test_unknown_host(env):
    with pytest.raises(ConnectError, match="not found"):
        await env.make_viewer().connect("999999999", "x")


async def test_view_only_blocks_input(env):
    env.perms = P.Permissions(control=False)
    v = env.make_viewer()
    await v.connect("123456789", "secret-pass")
    assert not v.perms.control
    v._send({"t": "kd", "k": "x"})          # גם אם צופה זדוני עוקף את הלקוח
    await asyncio.sleep(0.5)
    assert not any(e[0] == "key" for e in env.inj.events)
    await v.disconnect()


async def test_busy_second_viewer(env):
    v1 = env.make_viewer()
    await v1.connect("123456789", "secret-pass")
    with pytest.raises(ConnectError, match="busy"):
        await env.make_viewer().connect("123456789", "secret-pass")
    await v1.disconnect()


async def test_chat_clipboard_and_quality(env):
    v = env.make_viewer()
    await v.connect("123456789", "secret-pass")
    v.send_chat("שלום")
    assert await wait_for(lambda: ("chat", {"peer": env.host.session.peer, "text": "שלום"}) in env.events)
    env.host.send_chat("hi viewer")
    assert await wait_for(lambda: ("chat", {"text": "hi viewer"}) in v.events)

    v.clip.set("copied on viewer")
    assert await wait_for(lambda: env.host_clip.text == "copied on viewer")
    env.host_clip.set("copied on host")
    assert await wait_for(lambda: v.clip.text == "copied on host")

    v.set_quality(fps=10, scale=0.5)
    assert await wait_for(lambda: env.host.session.track.scale == 0.5)
    seq = v.frame_seq
    assert await wait_for(lambda: v.frame_seq > seq + 1 and v.latest_frame.shape[1] == 320)
    await v.disconnect()


async def test_file_transfer_both_ways_and_path_traversal(env):
    v = env.make_viewer()
    await v.connect("123456789", "secret-pass")
    src = env.tmp / "../evil.bin"
    real = env.tmp / "data.bin"
    payload = bytes(range(256)) * 2000
    real.write_bytes(payload)
    await v.send_file(str(real))
    assert await wait_for(lambda: (env.tmp / "host_recv" / "data.bin").exists()
                          and any(k == "file_received" for k, _ in env.events))
    assert (env.tmp / "host_recv" / "data.bin").read_bytes() == payload

    await env.host.send_file(str(real))
    assert await wait_for(lambda: any(k == "file_received" for k, _ in v.events))
    assert (env.tmp / "viewer_recv" / "data.bin").read_bytes() == payload
    await v.disconnect()


async def test_file_permission_denied(env):
    env.perms = P.Permissions(files=False)
    v = env.make_viewer()
    await v.connect("123456789", "secret-pass")
    f = env.tmp / "x.txt"; f.write_text("hi")
    await v.send_file(str(f))                # הלקוח חוסם לפי ההרשאות
    assert not (env.tmp / "host_recv" / "x.txt").exists()
    v.perms.files = True                     # צופה זדוני עוקף את הלקוח
    await v.send_file(str(f))
    await asyncio.sleep(0.5)
    assert not (env.tmp / "host_recv" / "x.txt").exists()
    await v.disconnect()


def test_safe_name():
    from rdesk.files import safe_name
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("..\\..\\win\\x.exe") == "x.exe"
    assert safe_name("") == "file"
    assert safe_name("a:b?.txt") == "a_b_.txt"
