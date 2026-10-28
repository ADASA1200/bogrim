"""Connectivity probe: `python -m bridge.probe HOST [--port 5060] [--token T] [--seconds 6]`

Without --token it sends SIP OPTIONS (is the port open and the bridge alive?).
With --token it places a short test call exactly like Yemot's routing_ip leg would: INVITE -> ACK -> RTP
for N seconds -> BYE, and reports whether audio came back from the model.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import secrets
import socket
import struct
import time

import numpy as np

from .audio import G711
from .sip import SipMessage


def _sip(sock: socket.socket, host: str, port: int, text: str) -> None:
    sock.sendto(text.encode(), (host, port))


def _recv(sock: socket.socket, timeout: float) -> SipMessage | None:
    sock.settimeout(timeout)
    try:
        data, _ = sock.recvfrom(65535)
    except socket.timeout:
        return None
    return SipMessage.parse(data)


def run(host: str, port: int, token: str | None, seconds: float, rtp_port: int) -> int:
    sip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sip.bind(("0.0.0.0", 0))
    local_ip = _local_ip(host)
    lport = sip.getsockname()[1]
    call_id = secrets.token_hex(6) + "@probe"
    via = f"SIP/2.0/UDP {local_ip}:{lport};rport;branch=z9hG4bK{secrets.token_hex(4)}"
    if not token:
        _sip(sip, host, port, f"OPTIONS sip:ping@{host}:{port} SIP/2.0\r\nVia: {via}\r\nMax-Forwards: 70\r\n"
             f"From: <sip:probe@{local_ip}>;tag=p1\r\nTo: <sip:ping@{host}>\r\nCall-ID: {call_id}\r\nCSeq: 1 OPTIONS\r\n"
             f"Content-Length: 0\r\n\r\n")
        resp = _recv(sip, 3)
        print("no answer: port closed/filtered or bridge down" if resp is None else f"bridge alive: {resp.status} {resp.reason}")
        return 0 if resp else 1

    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtp.bind(("0.0.0.0", rtp_port))
    rtp.setblocking(False)
    sdp = (f"v=0\r\no=- 1 1 IN IP4 {local_ip}\r\ns=probe\r\nc=IN IP4 {local_ip}\r\nt=0 0\r\n"
           f"m=audio {rtp_port} RTP/AVP 8 0 101\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:0 PCMU/8000\r\n"
           f"a=rtpmap:101 telephone-event/8000\r\na=fmtp:101 0-16\r\na=ptime:20\r\na=sendrecv\r\n")
    frm = f"<sip:probe@{local_ip}>;tag=p1"
    to = f"<sip:{token}@{host}>"
    _sip(sip, host, port, f"INVITE sip:{token}@{host}:{port} SIP/2.0\r\nVia: {via}\r\nMax-Forwards: 70\r\nFrom: {frm}\r\n"
         f"To: {to}\r\nCall-ID: {call_id}\r\nCSeq: 1 INVITE\r\nContact: <sip:probe@{local_ip}:{lport}>\r\n"
         f"Content-Type: application/sdp\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}")
    final = None
    deadline = time.time() + 15
    while time.time() < deadline:
        m = _recv(sip, 1)
        if m and not m.is_request:
            print(f"<- {m.status} {m.reason}")
            if m.status >= 200:
                final = m
                break
    if final is None or final.status != 200:
        print("call not established")
        return 1
    remote_port = int(final.body.decode().split("m=audio ")[1].split()[0])
    codec = G711("PCMA" if "PCMA" in final.body.decode() else "PCMU")
    _sip(sip, host, port, f"ACK sip:{host}:{port} SIP/2.0\r\nVia: {via.replace('branch=', 'branch=ack')}\r\nMax-Forwards: 70\r\n"
         f"From: {frm}\r\nTo: {final.get('to')}\r\nCall-ID: {call_id}\r\nCSeq: 1 ACK\r\nContent-Length: 0\r\n\r\n")
    print(f"call established ({codec.name}); listening for {seconds:.0f}s ...")
    t = np.arange(160) / 8000
    silence = bytes([codec.silence_byte]) * 160
    seq, ts, ssrc = 0, 0, secrets.randbits(32)
    got = loud = 0
    end = time.time() + seconds
    while time.time() < end:
        hdr = struct.pack("!BBHII", 0x80, codec.payload_type, seq & 0xFFFF, ts, ssrc)
        rtp.sendto(hdr + silence, (host, remote_port))
        seq += 1
        ts += 160
        try:
            while True:
                data, _ = rtp.recvfrom(2048)
                got += 1
                pcm = np.frombuffer(codec.decode(data[12:]), dtype="<i2")
                loud += int(len(pcm) and np.abs(pcm).max() > 1500)
        except BlockingIOError:
            pass
        time.sleep(0.02)
    print(f"RTP packets received: {got}; packets with audible speech: {loud}")
    _sip(sip, host, port, f"BYE sip:{host}:{port} SIP/2.0\r\nVia: {via.replace('branch=', 'branch=bye')}\r\nMax-Forwards: 70\r\n"
         f"From: {frm}\r\nTo: {final.get('to')}\r\nCall-ID: {call_id}\r\nCSeq: 2 BYE\r\nContent-Length: 0\r\n\r\n")
    _recv(sip, 2)
    print("model audio heard: YES" if loud else "model audio heard: NO (check GEMINI_API_KEY / logs)")
    return 0 if loud else 2


def _local_ip(target: str) -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 9))
        return s.getsockname()[0]
    finally:
        s.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=5060)
    ap.add_argument("--token")
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--rtp-port", type=int, default=40000)
    a = ap.parse_args()
    raise SystemExit(run(a.host, a.port, a.token, a.seconds, a.rtp_port))


if __name__ == "__main__":
    main()
