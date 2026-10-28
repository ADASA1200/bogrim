import ipaddress

import numpy as np
import pytest

from bridge import config as cfgmod
from bridge.audio import G711, StreamResampler, _ALAW_DEC, _ULAW_DEC
from bridge.sdp import SdpError, build_answer, choose_codec, parse_offer
from bridge.sip import SipMessage, digest_authorization, parse_addr, uri_parts
from bridge.tools import ToolContext, _check_url, _is_public_ip, build_registry, fetch_url, get_datetime

from .fakes import tone


# ---- G.711 ---------------------------------------------------------------

def test_g711_known_levels():
    assert _ULAW_DEC[0xFF] == 0 and _ULAW_DEC[0x00] == -32124 and _ULAW_DEC[0x80] == 32124
    assert _ALAW_DEC[0xD5] == 8 and _ALAW_DEC[0x55] == -8
    assert G711("PCMA").encode(b"\x00\x00") == bytes([0xD5])
    assert G711("PCMU").encode(b"\x00\x00") == bytes([0xFF])
    assert G711("PCMA").payload_type == 8 and G711("PCMU").payload_type == 0


@pytest.mark.parametrize("name", ["PCMA", "PCMU"])
def test_g711_code_roundtrip(name):
    codec = G711(name)
    codes = bytes(range(256))
    again = codec.encode(codec.decode(codes))
    mismatched = [i for i in range(256) if again[i] != codes[i]]
    # mu-law has two codes for zero (0x7F/0xFF); everything else must be exact
    assert mismatched in ([], [0x7F]), mismatched


@pytest.mark.parametrize("name", ["PCMA", "PCMU"])
def test_g711_snr(name):
    codec = G711(name)
    pcm = np.frombuffer(tone(8000, 500, 440, 0.7), dtype="<i2").astype(float)
    out = np.frombuffer(codec.decode(codec.encode(pcm.astype("<i2").tobytes())), dtype="<i2").astype(float)
    snr = 10 * np.log10(np.sum(pcm ** 2) / np.sum((pcm - out) ** 2))
    assert snr > 33


# ---- resampling ------------------------------------------------------------

def test_resampler_rate_and_tone():
    up = StreamResampler(8000, 16000)
    src = tone(8000, 1000, 500)
    out = b"".join(up.process(src[i:i + 321]) for i in range(0, len(src), 321))  # odd chunking
    samples = len(out) // 2
    assert 16000 - 700 < samples <= 16000  # filter delay is held back (~26 ms)
    x = np.frombuffer(out, dtype="<i2").astype(float)
    peak = np.argmax(np.abs(np.fft.rfft(x[2000:10000]))) * 16000 / 8000
    assert abs(peak - 500) < 15

    down = StreamResampler(24000, 8000)
    out = down.process(tone(24000, 1000, 1000))
    assert 8000 - 400 < len(out) // 2 <= 8000


# ---- SDP -------------------------------------------------------------------

OFFER = ("v=0\r\no=- 1 1 IN IP4 10.0.0.5\r\ns=-\r\nc=IN IP4 10.0.0.5\r\nt=0 0\r\n"
         "m=audio 4000 RTP/AVP 0 8 101\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\n"
         "a=rtpmap:101 telephone-event/8000\r\na=fmtp:101 0-16\r\n")


def test_sdp_negotiation():
    offer = parse_offer(OFFER)
    assert (offer.remote_ip, offer.remote_port, offer.telephone_event_pt) == ("10.0.0.5", 4000, 101)
    assert choose_codec(offer, ("PCMA", "PCMU")) == (8, "PCMA")
    assert choose_codec(offer, ("PCMU", "PCMA")) == (0, "PCMU")
    ans = build_answer("1.2.3.4", 10000, 8, "PCMA", 101)
    assert "m=audio 10000 RTP/AVP 8 101" in ans and "c=IN IP4 1.2.3.4" in ans and "a=rtpmap:8 PCMA/8000" in ans


def test_sdp_rejects_srtp_and_unknown_codecs():
    with pytest.raises(SdpError):
        parse_offer(OFFER.replace("RTP/AVP", "RTP/SAVP"))
    with pytest.raises(SdpError):
        choose_codec(parse_offer(OFFER.replace("m=audio 4000 RTP/AVP 0 8 101", "m=audio 4000 RTP/AVP 101")), ("PCMA",))
    with pytest.raises(SdpError):
        parse_offer(OFFER.replace("4000", "0"))


# ---- SIP parsing -------------------------------------------------------------

def test_sip_parse_compact_folded_multivalue():
    raw = (b"INVITE sip:tok@1.2.3.4:5060 SIP/2.0\r\nv: SIP/2.0/UDP a:5060;branch=z9hG4bK1, SIP/2.0/UDP b:5060;branch=z9hG4bK2\r\n"
           b"f: \"Dan\" <sip:0501@x>;tag=abc\r\nt: <sip:tok@1.2.3.4>\r\ni: call-1\r\nCSeq: 7 INVITE\r\n"
           b"Record-Route: <sip:p1;lr>,<sip:p2;lr>\r\nSubject: hello\r\n world\r\nl: 4\r\n\r\nbodyEXTRA")
    m = SipMessage.parse(raw)
    assert m.method == "INVITE" and m.call_id == "call-1" and m.cseq == (7, "INVITE")
    assert len(m.get_list("via")) == 2 and m.get_list("record-route") == ["<sip:p1;lr>", "<sip:p2;lr>"]
    assert m.get("subject") == "hello world" and m.body == b"body"
    assert parse_addr(m.get("from")) == ("sip:0501@x", "abc", "Dan")
    assert uri_parts(m.uri) == ("tok", "1.2.3.4", 5060)
    assert SipMessage.parse(b"garbage") is None


def test_uri_parts_variants():
    assert uri_parts("sip:user@host") == ("user", "host", 5060)
    assert uri_parts("sip:host:5080;transport=udp") == ("", "host", 5080)
    assert uri_parts("sip:u:pw@h:6000;x=y") == ("u", "h", 6000)


def test_digest_rfc2617_vector():
    chal = ('Digest realm="testrealm@host.com", qop="auth,auth-int", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41"')
    out = digest_authorization(chal, "Mufasa", "Circle Of Life", "GET", "/dir/index.html", cnonce="0a4f113b")
    assert 'response="6629fae49393a05397450978507c4ef1"' in out and "qop=auth" in out


# ---- tools -------------------------------------------------------------------

@pytest.mark.parametrize("ip,ok", [("8.8.8.8", True), ("127.0.0.1", False), ("10.1.2.3", False),
                                   ("192.168.0.1", False), ("169.254.169.254", False), ("::1", False),
                                   ("::ffff:127.0.0.1", False), ("100.64.0.1", False)])
def test_public_ip_check(ip, ok):
    assert _is_public_ip(ip) is ok


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/", "http://127.0.0.1/",
                                 "http://169.254.169.254/latest/meta-data", "https://example.com:8443/",
                                 "http://user:pw@example.com/", "http://[::1]/"])
def test_fetch_url_rejects_unsafe(url):
    with pytest.raises(ValueError):
        _check_url(url)


async def test_fetch_url_blocks_localhost_name():
    res = await build_registry().call("fetch_url", {"url": "http://localhost/"}, ToolContext())
    assert "error" in res


async def test_get_datetime_has_hebrew_date():
    res = await get_datetime({}, ToolContext())
    assert res["timezone"] == "Asia/Jerusalem" and res["weekday_hebrew"].startswith("יום ")
    assert res["hebrew_date"] and "T" in res["iso"]
    assert "error" in await get_datetime({"timezone": "Nowhere/Land"}, ToolContext())


def test_registry_declarations_are_valid_schemas():
    names = {d.name for d in build_registry().declarations()}
    assert names == {"get_datetime", "fetch_url", "get_caller_info", "end_call"}
    assert "fetch_url" not in {d.name for d in build_registry(enable_fetch_url=False).declarations()}


# ---- config ------------------------------------------------------------------

def test_config_validation(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith(("GEMINI", "ACCESS", "PUBLIC", "YEMOT", "STATUS", "ALLOWED", "SIP_", "RTP_", "MAX_")):
            monkeypatch.delenv(k)
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.Config.from_env()  # no key
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.Config.from_env()  # no token / register host
    monkeypatch.setenv("ACCESS_TOKEN", "short")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.Config.from_env()
    monkeypatch.setenv("ACCESS_TOKEN", "a" * 8 + ":" + "b" * 10)
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.Config.from_env()  # ':' is not allowed by Yemot
    monkeypatch.setenv("ACCESS_TOKEN", "Abc123_-.xyzABC123456")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.Config.from_env()  # no PUBLIC_IP
    monkeypatch.setenv("PUBLIC_IP", "203.0.113.7")
    monkeypatch.setenv("ALLOWED_SOURCE_NETWORKS", "198.51.100.0/24, 203.0.113.9")
    c = cfgmod.Config.from_env()
    assert c.gemini_model == "gemini-3.8-live" and c.sip_port == 5060
    assert ipaddress.ip_network("198.51.100.0/24") in c.allowed_networks
