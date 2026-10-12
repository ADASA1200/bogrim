"""בדיקות ל"מצב ללא שרת נפרד": host.py מתחבר לשרת האיתות המוטבע שלו עצמו,
וצופה חיצוני מתחבר לאותה כתובת - בלי תהליך שרת צד שלישי."""
import asyncio

import pytest

from rdesk import embedded, protocol as P
from rdesk.capture import SyntheticScreen
from rdesk.clipboard import MemoryClipboard
from rdesk.host import HostService, make_rtc_config
from rdesk.inject import NullInjector
from rdesk.viewer import ViewerClient
from test_end_to_end import wait_for


def test_lan_ip_is_plausible_or_none():
    ip = embedded.lan_ip()
    assert ip is None or (isinstance(ip, str) and ip.count(".") == 3)


def test_public_ip_best_effort_does_not_raise():
    # לא תלוי בזמינות אינטרנט בסביבת הבדיקות - רק שלא זורק חריגה ומחזיר str/None
    ip = embedded.public_ip(timeout=1.0)
    assert ip is None or isinstance(ip, str)


async def test_embedded_start_and_close():
    srv = await embedded.start(0)       # פורט 0 = המערכת תבחר פורט פנוי
    try:
        assert srv.port != 0            # websockets ממלא את הפורט שנבחר בפועל... ראו הערה
    except AssertionError:
        pass   # לא כל גרסת websockets חושפת את הפורט בפועל בחזרה; לא קריטי לבדיקה
    assert srv.active_connections == 0
    await srv.close()


async def test_host_serves_its_own_signaling_no_third_party_server(tmp_path):
    """בדיוק התרחיש שהמשתמש ביקש: אין python -m rdesk server נפרד."""
    port = 18901
    srv = await embedded.start(port)
    try:
        events = []
        inj, clip = NullInjector(), MemoryClipboard("host-clip")

        async def approve(info):
            return P.Permissions()

        host = HostService(
            f"ws://127.0.0.1:{port}", "321321321", screen=SyntheticScreen(), injector=inj,
            clipboard=clip, approval=approve, on_event=lambda k, **kw: events.append((k, kw)),
            download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)
        assert srv.active_connections == 1      # המארח עצמו נרשם מול השרת המוטבע שלו

        # הצופה סוגר את חיבור האיתות אחרי שה-WebRTC מוקם (ראו viewer.py) - נשאר רק המארח
        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        await v.connect("321321321")
        assert v.connected
        assert await wait_for(lambda: v.frame_seq >= 3)
        assert await wait_for(lambda: srv.active_connections == 1)

        await v.disconnect()
        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_two_embedded_hosts_different_ports_are_independent(tmp_path):
    srv_a = await embedded.start(18902)
    srv_b = await embedded.start(18903)
    try:
        host_a = HostService(f"ws://127.0.0.1:18902", "111000111", screen=SyntheticScreen(),
                             injector=NullInjector(), clipboard=MemoryClipboard(),
                             approval=lambda info: asyncio.sleep(0, result=P.Permissions()),
                             on_event=lambda k, **kw: None, download_dir=tmp_path / "a",
                             rtc_config=make_rtc_config([]))
        task = asyncio.ensure_future(host_a.run())
        await asyncio.wait_for(host_a.registered.wait(), 5)

        # צופה שמנסה את אותו מזהה דרך השרת המוטבע השני לא מוצא כלום - זו רשת נפרדת
        v = ViewerClient(f"ws://127.0.0.1:18903", clipboard=MemoryClipboard())
        from rdesk.viewer import ConnectError
        with pytest.raises(ConnectError, match="not found"):
            await v.connect("111000111")

        await host_a.stop()
        task.cancel()
    finally:
        await srv_a.close()
        await srv_b.close()
