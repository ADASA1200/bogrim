"""Minimal SDP offer/answer for a single G.711 audio stream (plain RTP/AVP)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

STATIC_CODECS = {0: "PCMU", 8: "PCMA"}


class SdpError(Exception):
    pass


@dataclass
class Offer:
    remote_ip: str
    remote_port: int
    codecs: list[tuple[int, str]]  # (payload type, name) in the offerer's preference order
    telephone_event_pt: int | None
    ptime: int


def parse_offer(body: str) -> Offer:
    session_ip = None
    media_ip = None
    port = 0
    in_audio = False
    pts: list[int] = []
    rtpmap: dict[int, str] = {}
    ptime = 20
    for raw in body.replace("\r", "").split("\n"):
        line = raw.strip()
        if line.startswith("c=IN IP4 "):
            ip = line[len("c=IN IP4 "):].split("/")[0].strip()
            if in_audio:
                media_ip = ip
            else:
                session_ip = ip
        elif line.startswith("m="):
            in_audio = False
            parts = line[2:].split()
            if parts and parts[0] == "audio" and not pts:
                if parts[2] != "RTP/AVP":
                    raise SdpError(f"unsupported transport {parts[2]} (SRTP/DTLS not supported)")
                port = int(parts[1])
                pts = [int(p) for p in parts[3:] if p.isdigit()]
                in_audio = True
        elif in_audio and line.startswith("a=rtpmap:"):
            num, _, enc = line[len("a=rtpmap:"):].partition(" ")
            rtpmap[int(num)] = enc.split("/")[0].upper()
        elif in_audio and line.startswith("a=ptime:"):
            try:
                ptime = int(line[len("a=ptime:"):])
            except ValueError:
                pass
    ip = media_ip or session_ip
    if not pts or port == 0 or not ip:
        raise SdpError("no usable audio stream in offer")
    codecs: list[tuple[int, str]] = []
    te_pt = None
    for pt in pts:
        name = rtpmap.get(pt) or STATIC_CODECS.get(pt)
        if name == "TELEPHONE-EVENT":
            te_pt = te_pt or pt
        elif name in ("PCMA", "PCMU"):
            codecs.append((pt, name))
    return Offer(ip, port, codecs, te_pt, ptime)


def choose_codec(offer: Offer, preference: tuple[str, ...]) -> tuple[int, str]:
    """Pick the first codec from our preference list that the caller offered."""
    for want in preference:
        for pt, name in offer.codecs:
            if name == want:
                return pt, name
    raise SdpError("no common codec (need PCMA or PCMU)")


def build_answer(public_ip: str, rtp_port: int, codec_pt: int, codec_name: str,
                 te_pt: int | None, session_id: int | None = None) -> str:
    sid = session_id or int(time.time()) * 1000 + random.randint(0, 999)
    lines = [
        "v=0",
        f"o=- {sid} {sid} IN IP4 {public_ip}",
        "s=yemot-gemini-bridge",
        f"c=IN IP4 {public_ip}",
        "t=0 0",
        f"m=audio {rtp_port} RTP/AVP {codec_pt}" + (f" {te_pt}" if te_pt is not None else ""),
        f"a=rtpmap:{codec_pt} {codec_name}/8000",
    ]
    if te_pt is not None:
        lines += [f"a=rtpmap:{te_pt} telephone-event/8000", f"a=fmtp:{te_pt} 0-16"]
    lines += ["a=ptime:20", "a=sendrecv"]
    return "\r\n".join(lines) + "\r\n"
