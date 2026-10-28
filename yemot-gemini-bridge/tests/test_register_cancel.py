"""REGISTER with digest auth (type=sip mode), calls via the registered account, and CANCEL handling."""

import asyncio
import hashlib
import re

from bridge.call import CallManager
from bridge.config import Config
from bridge.sip import Registration, SipEndpoint, SipMessage
from bridge.tools import build_registry

from .fakes import FakeLive, FakeYemot
from .test_e2e import TOKEN, until

REG_PORT = 15070
BRIDGE_PORT = 15061


class FakeRegistrar(asyncio.DatagramProtocol):
    def __init__(self):
        self.requests: list[SipMessage] = []
        self.authed = 0
        self.tr = None

    def connection_made(self, tr):
        self.tr = tr

    def datagram_received(self, data, addr):
        m = SipMessage.parse(data)
        if not m or m.method != "REGISTER":
            return
        self.requests.append(m)
        auth = m.get("authorization")
        status, extra = 401, 'WWW-Authenticate: Digest realm="yemot.test", nonce="abc123", algorithm=MD5, qop="auth"\r\n'
        if auth:
            f = {k: (q or b) for k, q, b in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', auth)}
            md5 = lambda s: hashlib.md5(s.encode()).hexdigest()
            ha1 = md5(f"0772222770=2:yemot.test:s3cret")
            ha2 = md5(f"REGISTER:{f['uri']}")
            expect = md5(f"{ha1}:abc123:{f['nc']}:{f['cnonce']}:auth:{ha2}")
            if f["response"] == expect:
                status, extra = 200, f"Contact: {m.get('contact')}\r\n"
                self.authed += 1
        resp = (f"SIP/2.0 {status} {'OK' if status == 200 else 'Unauthorized'}\r\nVia: {m.get('via')}\r\n"
                f"From: {m.get('from')}\r\nTo: {m.get('to')};tag=r1\r\nCall-ID: {m.call_id}\r\nCSeq: {m.get('cseq')}\r\n"
                f"{extra}Content-Length: 0\r\n\r\n")
        self.tr.sendto(resp.encode(), addr)


async def test_register_with_digest_then_call_via_account():
    loop = asyncio.get_running_loop()
    registrar = FakeRegistrar()
    await loop.create_datagram_endpoint(lambda: registrar, local_addr=("127.0.0.1", REG_PORT))
    cfg = Config(gemini_api_key="x", public_ip="127.0.0.1", sip_bind="127.0.0.1", sip_port=BRIDGE_PORT,
                 rtp_min=16200, rtp_max=16260, register_host="127.0.0.1", register_port=REG_PORT,
                 register_user="0772222770=2", register_password="s3cret", register_expires=60)
    live = FakeLive()
    mgr = CallManager(cfg, build_registry(), gemini_client=live)
    ep = SipEndpoint(cfg.public_ip, cfg.sip_port, mgr)
    mgr.endpoint = ep
    await ep.start(cfg.sip_bind)
    reg = Registration(ep, cfg.register_host, cfg.register_port, cfg.register_user, cfg.register_password,
                       cfg.register_expires)
    mgr.registration = reg
    reg.start()
    try:
        await until(lambda: reg.registered)
        first, second = registrar.requests[:2]
        assert first.get("authorization") is None and second.get("authorization")
        assert second.cseq[0] == first.cseq[0] + 1
        assert "expires=60" in second.get("contact") and f"127.0.0.1:{BRIDGE_PORT}" in second.get("contact")

        # a call whose Request-URI user is our registered account, from the registrar's IP, is accepted
        y = FakeYemot(("127.0.0.1", BRIDGE_PORT), "0772222770=2", 17100)
        await y.open()
        y.send_invite()
        assert (await y.wait_final()).status == 200
        y.send_ack()
        await until(lambda: mgr.calls)
        # ...but the same user from a non-registrar IP would not match: simulate via a wrong user
        y2 = FakeYemot(("127.0.0.1", BRIDGE_PORT), "someone-else", 17110)
        await y2.open()
        y2.send_invite()
        assert (await y2.wait_final()).status == 404
        y.close(); y2.close()

        await reg.stop()  # unregisters with expires=0
        assert registrar.requests[-1].get("expires") == "0"
    finally:
        await mgr.shutdown()
        ep.close()


async def test_cancel_during_setup_sends_487_and_cleans_up():
    cfg = Config(gemini_api_key="x", public_ip="127.0.0.1", sip_bind="127.0.0.1", sip_port=BRIDGE_PORT + 2,
                 rtp_min=16300, rtp_max=16360, access_token=TOKEN)
    live = FakeLive()
    orig = live.aio.live.connect

    def slow_connect(**kw):
        cm = orig(**kw)
        enter = cm.__aenter__

        async def slow():
            await asyncio.sleep(0.8)
            return await enter()
        cm.__aenter__ = slow
        return cm

    live.aio.live.connect = slow_connect
    mgr = CallManager(cfg, build_registry(), gemini_client=live)
    ep = SipEndpoint(cfg.public_ip, cfg.sip_port, mgr)
    mgr.endpoint = ep
    await ep.start(cfg.sip_bind)
    y = FakeYemot(("127.0.0.1", BRIDGE_PORT + 2), TOKEN, 17120)
    await y.open()
    try:
        y.send_invite()
        await asyncio.sleep(0.2)
        y.send_cancel()
        await y.wait_final(timeout=5)
        assert y.final_status == 487
        assert any(m.status == 200 and m.cseq[1] == "CANCEL" for m in y.sip_msgs if not m.is_request)
        await until(lambda: live.sessions and live.sessions[0].closed)
        assert not mgr.calls
        assert len(mgr.ports._free) == len(range(16300, 16360, 2))
    finally:
        y.close()
        await mgr.shutdown()
        ep.close()
