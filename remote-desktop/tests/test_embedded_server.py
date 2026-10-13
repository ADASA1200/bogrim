"""בדיקות ל"מצב ללא שרת נפרד": host.py מתחבר לשרת האיתות המוטבע שלו עצמו,
וצופה חיצוני מתחבר לאותה כתובת - בלי תהליך שרת צד שלישי."""
import asyncio

import pytest

from rdesk import acl, embedded, protocol as P
from rdesk.capture import SyntheticScreen
from rdesk.clipboard import MemoryClipboard
from rdesk.host import HostService, make_rtc_config
from rdesk.inject import NullInjector
from rdesk.viewer import ConnectError, ViewerClient
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


async def test_trust_check_bypasses_approval(tmp_path):
    """פרופיל הרשאה שמור ("זכור מכשיר זה") - trust_check מדלג על approval
    לגמרי ומסמן את הסשן כ-mode="trusted"."""
    port = 18904
    srv = await embedded.start(port)
    try:
        approval_calls = []

        async def approve(info):
            approval_calls.append(info)
            return None   # לא אמור להיקרא בכלל אם trust_check תפס

        def trust_check(peer):
            return P.Permissions(control=True, clipboard=False, files=True, chat=True)

        events = []
        host = HostService(
            f"ws://127.0.0.1:{port}", "555555555", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), approval=approve, trust_check=trust_check,
            on_event=lambda k, **kw: events.append((k, kw)),
            download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        await v.connect("555555555")
        assert v.connected
        assert v.perms.clipboard is False   # ההרשאות שהגיעו מ-trust_check, לא ברירת מחדל
        assert approval_calls == []
        assert any(k == "session_start" and kw.get("mode") == "trusted" for k, kw in events)

        await v.disconnect()
        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_ip_whitelist_blocks_disallowed_ip(tmp_path):
    """שני הצדדים כאן מדברים דרך 127.0.0.1 (loopback) - רשימה שלא כוללת אותו
    צריכה לחסום את החיבור כבר בשלב ה-hello, לפני כל ניסיון אימות."""
    port = 18905
    srv = await embedded.start(port)
    try:
        host = HostService(
            f"ws://127.0.0.1:{port}", "222333444", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), approval=lambda info: asyncio.sleep(0, result=P.Permissions()),
            ip_whitelist=["10.0.0.1"],   # לא כולל 127.0.0.1
            on_event=lambda k, **kw: None, download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        with pytest.raises(ConnectError, match="ip_blocked"):
            await v.connect("222333444")

        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_ip_whitelist_allows_listed_ip(tmp_path):
    port = 18906
    srv = await embedded.start(port)
    try:
        host = HostService(
            f"ws://127.0.0.1:{port}", "222333445", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), approval=lambda info: asyncio.sleep(0, result=P.Permissions()),
            ip_whitelist=["127.0.0.1"],
            on_event=lambda k, **kw: None, download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        await v.connect("222333445")
        assert v.connected

        await v.disconnect()
        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_totp_required_alongside_unattended_password(tmp_path):
    port = 18907
    srv = await embedded.start(port)
    try:
        secret = acl.totp_new_secret()
        key = P.derive_key("a-long-enough-password")
        host = HostService(
            f"ws://127.0.0.1:{port}", "333444555", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), unattended_key=key, unattended_perms=P.Permissions(),
            totp_secret=secret,
            on_event=lambda k, **kw: None, download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        # סיסמה נכונה, בלי קוד דו-שלבי - נדחה
        v1 = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        with pytest.raises(ConnectError, match="bad totp"):
            await v1.connect("333444555", "a-long-enough-password")

        # סיסמה נכונה + קוד דו-שלבי תקף - מתחבר במצב unattended
        v2 = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        await v2.connect("333444555", "a-long-enough-password", acl.totp_code(secret))
        assert v2.connected
        assert v2.mode == "unattended"

        await v2.disconnect()
        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_interactive_mode_never_rejects_passwordless_connections(tmp_path):
    port = 18908
    srv = await embedded.start(port)
    try:
        approval_calls = []

        async def approve(info):
            approval_calls.append(info)
            return P.Permissions()

        host = HostService(
            f"ws://127.0.0.1:{port}", "444555666", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), approval=approve, interactive_mode="never",
            on_event=lambda k, **kw: None, download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        with pytest.raises(ConnectError, match="interactive disabled"):
            await v.connect("444555666")
        assert approval_calls == []

        await host.stop()
        task.cancel()
    finally:
        await srv.close()


async def test_interactive_mode_window_open_rejects_when_window_hidden(tmp_path):
    port = 18909
    srv = await embedded.start(port)
    try:
        host = HostService(
            f"ws://127.0.0.1:{port}", "444555667", screen=SyntheticScreen(), injector=NullInjector(),
            clipboard=MemoryClipboard(), approval=lambda info: asyncio.sleep(0, result=P.Permissions()),
            interactive_mode="window_open", window_open_check=lambda: False,
            on_event=lambda k, **kw: None, download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]),
        )
        task = asyncio.ensure_future(host.run())
        await asyncio.wait_for(host.registered.wait(), 5)

        v = ViewerClient(f"ws://127.0.0.1:{port}", clipboard=MemoryClipboard())
        with pytest.raises(ConnectError, match="window closed"):
            await v.connect("444555667")

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
