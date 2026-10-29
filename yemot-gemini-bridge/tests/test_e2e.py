"""End-to-end: fake Yemot (SIP+RTP) <-> real bridge code <-> fake Gemini Live."""

import asyncio

import numpy as np
import pytest

from bridge.audio import G711
from bridge.call import CallManager
from bridge.config import Config
from bridge.sip import SipEndpoint
from bridge.tools import build_registry

from .fakes import FakeLive, FakeYemot, Script, audio_msg, tone, turn_complete_msg

TOKEN = "Tok3n_for-tests-0123456789"
SIP_PORT = 15060
RTP_MIN = 16000


@pytest.fixture
async def stack():
    made = []

    async def build(max_calls=3, live=None, **cfg_over):
        cfg = Config(gemini_api_key="x", public_ip="127.0.0.1", sip_bind="127.0.0.1", sip_port=SIP_PORT,
                     rtp_min=RTP_MIN, rtp_max=RTP_MIN + 60, access_token=TOKEN, max_calls=max_calls, **cfg_over)
        live = live or FakeLive()
        mgr = CallManager(cfg, build_registry(), gemini_client=live)
        ep = SipEndpoint(cfg.public_ip, cfg.sip_port, mgr)
        mgr.endpoint = ep
        await ep.start(cfg.sip_bind)
        made.append((mgr, ep))
        return mgr, ep, live

    yield build
    for mgr, ep in made:
        await mgr.shutdown()
        ep.close()
    await asyncio.sleep(0.05)


async def open_yemot(rtp_port=17000, **kw) -> FakeYemot:
    y = FakeYemot(("127.0.0.1", SIP_PORT), TOKEN, rtp_port, **kw)
    await y.open()
    return y


async def until(cond, timeout=6.0):
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def has_audio(frames: list[bytes], codec: G711, min_peak=2000) -> bool:
    return any(np.abs(np.frombuffer(codec.decode(f), dtype="<i2")).max() > min_peak for f in frames if len(f) == 160)


async def answer_call(y: FakeYemot, **invite_kw):
    y.send_invite(**invite_kw)
    final = await y.wait_final()
    assert final.status == 200, final.status
    return final


async def test_full_call_with_tools_and_agent_hangup(stack):
    mgr, ep, live = await stack()
    y = await open_yemot()
    try:
        final = await answer_call(y)
        # response hygiene: To tag, Contact, SDP answer with our RTP port, codec = first of PCMA/PCMU we share
        assert "tag=" in final.get("to") and final.get("contact")
        sdp = final.body.decode()
        assert "RTP/AVP 8 101" in sdp and "a=rtpmap:8 PCMA/8000" in sdp
        port = int(sdp.split("m=audio ")[1].split()[0])
        assert RTP_MIN <= port <= RTP_MIN + 60 and port % 2 == 0
        y.rtp_dest = port
        assert [m.status for m in y.sip_msgs[:2]] == [100, 180]
        y.send_ack()

        # greeting is requested after ACK and its audio comes back as paced 20 ms RTP
        await until(lambda: live.sessions and live.sessions[0].client_contents)
        await until(lambda: has_audio(y.rtp_rx, y.codec))
        # constant 20 ms cadence with consecutive sequence numbers
        seqs = y.rtp_seqs
        assert all((b - a) & 0xFFFF == 1 for a, b in zip(seqs, seqs[1:]))

        # caller audio reaches Gemini as 16 kHz PCM (2x the sample count of the G.711 input)
        speech = tone(8000, 20, 700)
        for _ in range(30):
            y.send_rtp_frame(speech)
            await asyncio.sleep(0.02)
        sess = live.sessions[0]
        await until(lambda: sess.audio_bytes > 30 * 640 * 0.7)

        # model config: thinking untouched, search + function tools, resumption on
        model, config = live.configs[0]
        assert model == "gemini-3.8-live"
        assert config.response_modalities == ["AUDIO"] and config.thinking_config is None
        tool_kinds = [("search" if t.google_search else "fn") for t in config.tools]
        assert tool_kinds == ["search", "fn"]
        assert {d.name for d in config.tools[1].function_declarations} >= {"end_call", "get_datetime", "fetch_url"}
        assert config.session_resumption is not None and config.context_window_compression is not None

        # DTMF (RFC 2833) is forwarded as text -> model calls get_datetime -> says goodbye -> end_call -> BYE
        y.send_dtmf(5)
        await until(lambda: any("DTMF: 5" in t for t in sess.texts))
        await until(lambda: [r.name for r in sess.tool_responses] == ["get_datetime", "end_call"])
        assert sess.tool_responses[0].response["hebrew_date"]
        await asyncio.wait_for(y.bye_received.wait(), 15)
        await until(lambda: not mgr.calls)
        assert sess.closed
        assert len(mgr.ports._free) == len(range(RTP_MIN, RTP_MIN + 60, 2))  # port returned to the pool
    finally:
        y.close()


async def test_wrong_token_is_404_and_never_reaches_gemini(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17010)
    try:
        y.send_invite(user="wrong-token-wrong-token")
        assert (await y.wait_final()).status == 404
        assert not live.sessions and not mgr.calls
    finally:
        y.close()


async def test_srtp_offer_rejected_488(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17020)
    try:
        y.send_invite(transport="RTP/SAVP")
        assert (await y.wait_final()).status == 488
        assert not live.sessions
    finally:
        y.close()


async def test_busy_when_at_capacity(stack):
    mgr, ep, live = await stack(max_calls=1)
    y1, y2 = await open_yemot(17030), await open_yemot(17040)
    try:
        await answer_call(y1)
        y1.send_ack()
        y2.send_invite()
        assert (await y2.wait_final()).status == 486
    finally:
        y1.close(); y2.close()


async def test_caller_hangup_cleans_up(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17050)
    try:
        await answer_call(y)
        y.send_ack()
        await until(lambda: live.sessions and live.sessions[0].client_contents)
        y.send_request("BYE")
        await until(lambda: any(m.status == 200 and m.cseq[1] == "BYE" for m in y.sip_msgs if not m.is_request))
        await until(lambda: not mgr.calls)
        assert live.sessions[0].closed
    finally:
        y.close()


async def test_invite_retransmission_creates_one_call(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17060)
    try:
        y.send_invite()
        y._sip_tr.sendto(y.invite_text.encode(), y.bridge)  # same INVITE again
        await y.wait_final()
        y.send_ack()
        await asyncio.sleep(0.3)
        assert len(live.sessions) == 1 and len(mgr.calls) == 1
    finally:
        y.close()


async def test_gemini_drop_reconnects_with_resumption_handle(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17070)
    try:
        await answer_call(y)
        y.send_ack()
        await until(lambda: live.sessions and live.sessions[0].client_contents)
        first = live.sessions[0]
        from google.genai import types
        first.push(types.LiveServerMessage(session_resumption_update=types.LiveServerSessionResumptionUpdate(
            new_handle="handle-1", resumable=True)))
        await asyncio.sleep(0.1)
        first.push("DROP")
        await until(lambda: len(live.sessions) == 2, 8)
        assert live.configs[1][1].session_resumption.handle == "handle-1"
        assert mgr.calls  # call survived
        assert not live.sessions[1].client_contents  # no re-greeting/apology when context is resumed
    finally:
        y.close()


async def test_barge_in_flushes_playback(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17080)
    try:
        await answer_call(y)
        y.send_ack()
        await until(lambda: live.sessions and live.sessions[0].client_contents)
        call = next(iter(mgr.calls.values()))
        call.rtp.play(b"\x01\x02" * 8000)  # 1 s queued
        assert call.rtp.buffered_ms() > 500
        from google.genai import types
        live.sessions[0].push(types.LiveServerMessage(server_content=types.LiveServerContent(interrupted=True)))
        await until(lambda: call.rtp.buffered_ms() < 40)
    finally:
        y.close()


async def test_pcmu_fallback_when_alaw_not_offered(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17090, codec="PCMU")
    try:
        final = await answer_call(y, codecs="0 101")
        assert "RTP/AVP 0 101" in final.body.decode() and "PCMU/8000" in final.body.decode()
        y.rtp_dest = int(final.body.decode().split("m=audio ")[1].split()[0])
        y.send_ack()
        await until(lambda: has_audio(y.rtp_rx, y.codec))
    finally:
        y.close()


async def test_firewall_pinhole_packets_are_sent_before_the_call_is_acked(stack):
    mgr, ep, live = await stack()
    y = await open_yemot(17140)
    try:
        await answer_call(y)  # final 200 received, ACK deliberately not sent yet
        await until(lambda: len(y.rtp_rx) >= 5)
        assert not has_audio(y.rtp_rx, y.codec)  # only silence before the call is answered
        n = len(y.rtp_rx)
        y.send_ack()
        await until(lambda: len(y.rtp_rx) > n + 10)
        seqs = y.rtp_seqs
        assert all((b - a) & 0xFFFF == 1 for a, b in zip(seqs, seqs[1:]))  # sequence continues without a gap
    finally:
        y.close()
