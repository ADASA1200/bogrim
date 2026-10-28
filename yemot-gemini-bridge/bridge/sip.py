"""A small SIP-over-UDP user agent: answers INVITEs, sends BYE, optionally REGISTERs.

Only what Yemot's `routing_ip` / `type=sip` flows need is implemented; this is not a general stack.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import socket
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

log = logging.getLogger("bridge.sip")

CRLF = "\r\n"
USER_AGENT = "yemot-gemini-bridge/1.0"
ALLOW = "INVITE, ACK, CANCEL, BYE, OPTIONS, INFO, UPDATE"
COMPACT = {"v": "via", "f": "from", "t": "to", "i": "call-id", "m": "contact",
           "l": "content-length", "c": "content-type", "k": "supported", "s": "subject"}
CANONICAL = {"call-id": "Call-ID", "cseq": "CSeq", "www-authenticate": "WWW-Authenticate",
             "user-agent": "User-Agent", "content-type": "Content-Type", "content-length": "Content-Length",
             "max-forwards": "Max-Forwards", "record-route": "Record-Route"}


def _split_commas(value: str) -> list[str]:
    parts, depth, quote, cur = [], 0, False, []
    for ch in value:
        if ch == '"':
            quote = not quote
        elif ch == "<" and not quote:
            depth += 1
        elif ch == ">" and not quote:
            depth = max(0, depth - 1)
        if ch == "," and depth == 0 and not quote:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


class SipMessage:
    def __init__(self) -> None:
        self.method: str | None = None
        self.uri: str | None = None
        self.status: int | None = None
        self.reason: str = ""
        self.headers: list[tuple[str, str]] = []
        self.body: bytes = b""

    @property
    def is_request(self) -> bool:
        return self.method is not None

    @classmethod
    def parse(cls, data: bytes) -> "SipMessage | None":
        try:
            head, _, body = data.partition(b"\r\n\r\n")
            if not _:
                head, _, body = data.partition(b"\n\n")
            lines = head.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
            first = lines[0].strip()
            if not first:
                return None
            msg = cls()
            if first.startswith("SIP/2.0"):
                _, code, *reason = first.split(" ", 2)
                msg.status = int(code)
                msg.reason = reason[0] if reason else ""
            else:
                method, uri, version = first.split(" ")
                if not version.startswith("SIP/2.0"):
                    return None
                msg.method, msg.uri = method.upper(), uri
            for line in lines[1:]:
                if not line:
                    continue
                if line[0] in " \t" and msg.headers:
                    name, value = msg.headers[-1]
                    msg.headers[-1] = (name, value + " " + line.strip())
                    continue
                name, _, value = line.partition(":")
                name = name.strip().lower()
                msg.headers.append((COMPACT.get(name, name), value.strip()))
            length = msg.get("content-length")
            msg.body = body[: int(length)] if length and length.isdigit() else body
            return msg
        except (ValueError, IndexError):
            return None

    def get(self, name: str, default: str | None = None) -> str | None:
        name = name.lower()
        for n, v in self.headers:
            if n == name:
                return v
        return default

    def get_list(self, name: str) -> list[str]:
        out: list[str] = []
        name = name.lower()
        for n, v in self.headers:
            if n == name:
                out.extend(_split_commas(v))
        return out

    def add(self, name: str, value: str) -> None:
        self.headers.append((name.lower(), value))

    def serialize(self) -> bytes:
        first = f"{self.method} {self.uri} SIP/2.0" if self.is_request else f"SIP/2.0 {self.status} {self.reason}"
        lines = [first]
        for n, v in self.headers:
            if n == "content-length":
                continue
            lines.append(f"{CANONICAL.get(n, n.title())}: {v}")
        lines.append(f"Content-Length: {len(self.body)}")
        return (CRLF.join(lines) + CRLF + CRLF).encode() + self.body

    # convenience accessors
    @property
    def call_id(self) -> str:
        return self.get("call-id", "")

    @property
    def cseq(self) -> tuple[int, str]:
        num, _, method = (self.get("cseq") or "0 ").partition(" ")
        return (int(num) if num.isdigit() else 0), method.strip().upper()


def parse_addr(value: str) -> tuple[str, str | None, str]:
    """'"Name" <sip:u@h>;tag=x' -> (uri, tag, display)."""
    value = value.strip()
    display = ""
    if "<" in value:
        display = value.split("<", 1)[0].strip().strip('"')
        uri = value.split("<", 1)[1].split(">", 1)[0]
        params = value.split(">", 1)[1]
    else:
        uri, _, params = value.partition(";")
        params = ";" + params
    m = re.search(r";\s*tag=([^;>\s]+)", params)
    return uri.strip(), (m.group(1) if m else None), display


def uri_parts(uri: str) -> tuple[str, str, int]:
    """'sip:user@host:port;x=y' -> (user, host, port)."""
    rest = uri.split(":", 1)[1] if ":" in uri else uri
    rest = rest.split(";", 1)[0].split("?", 1)[0]
    user, host = ("", rest)
    if "@" in rest:
        user, host = rest.rsplit("@", 1)
    user = user.split(":", 1)[0]
    port = 5060
    if host.startswith("["):
        host, _, p = host[1:].partition("]")
        port = int(p[1:]) if p.startswith(":") else 5060
    elif ":" in host:
        host, _, p = host.partition(":")
        port = int(p) if p.isdigit() else 5060
    return user, host, port


def new_branch() -> str:
    return "z9hG4bK" + secrets.token_hex(8)


# ---------------------------------------------------------------------------
# Public data types used by the call layer
# ---------------------------------------------------------------------------

@dataclass
class Invite:
    request: SipMessage
    source: tuple[str, int]
    request_user: str
    from_uri: str
    from_display: str
    sdp: str
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)

    def header(self, name: str) -> str | None:
        return self.request.get(name)


@dataclass
class Accept:
    sdp: str
    call: Any  # object with on_remote_bye(), on_dtmf(str), on_reinvite(str)->str|None


@dataclass
class Reject:
    code: int
    reason: str


class InviteHandler(Protocol):
    async def on_invite(self, inv: Invite) -> Accept | Reject: ...


@dataclass
class Dialog:
    call_id: str
    local_tag: str
    remote_tag: str
    local_uri: str
    remote_uri: str
    remote_target: str
    route_set: list[str]
    peer: tuple[str, int]
    call: Any
    local_cseq: int = field(default_factory=lambda: secrets.randbelow(9000) + 1000)
    ack: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

class SipEndpoint(asyncio.DatagramProtocol):
    def __init__(self, public_ip: str, port: int, handler: InviteHandler):
        self.public_ip = public_ip
        self.port = port
        self.handler = handler
        self.transport: asyncio.DatagramTransport | None = None
        self.dialogs: dict[str, Dialog] = {}
        self._invite_tx: dict[tuple[str, int], dict] = {}
        self._pending: dict[str, Invite] = {}
        self._waiters: dict[tuple[str, int], asyncio.Future] = {}
        self.response_sources: set[str] = set()
        self._tasks: set[asyncio.Task] = set()

    # ---- lifecycle -----------------------------------------------------
    async def start(self, bind_ip: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(bind_ip, self.port))

    def connection_made(self, transport) -> None:
        self.transport = transport

    def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        if self.transport:
            self.transport.close()

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_task_error)
        return task

    @staticmethod
    def _log_task_error(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            log.error("SIP task failed", exc_info=task.exception())

    def send(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport:
            self.transport.sendto(data, addr)

    @property
    def contact_uri(self) -> str:
        return f"sip:bridge@{self.public_ip}:{self.port}"

    # ---- inbound -------------------------------------------------------
    def datagram_received(self, data: bytes, addr) -> None:
        if data.strip() in (b"", b"\r\n\r\n"):  # keep-alive pings
            return
        msg = SipMessage.parse(data)
        if msg is None:
            return
        addr = (addr[0], addr[1])
        if msg.is_request:
            self._spawn(self._on_request(msg, addr))
        else:
            self._on_response(msg, addr)

    def _on_response(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        num, _ = msg.cseq
        fut = self._waiters.get((msg.call_id, num))
        if fut and not fut.done() and (msg.status or 0) >= 200:
            self.response_sources.add(addr[0])  # addresses that really answered our requests
            fut.set_result(msg)

    async def _on_request(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        method = msg.method
        if method == "INVITE":
            await self._on_invite(msg, addr)
        elif method == "ACK":
            self._on_ack(msg)
        elif method == "CANCEL":
            self._on_cancel(msg, addr)
        elif method == "BYE":
            await self._on_bye(msg, addr)
        elif method in ("OPTIONS",):
            self.send(self.response(msg, 200, "OK", extra=[("Allow", ALLOW)]).serialize(), addr)
        elif method in ("INFO", "UPDATE"):
            await self._on_info_update(msg, addr)
        else:
            self.send(self.response(msg, 405, "Method Not Allowed", extra=[("Allow", ALLOW)]).serialize(), addr)

    # ---- responses -----------------------------------------------------
    def response(self, req: SipMessage, code: int, reason: str, *, to_tag: str | None = None,
                 body: str | None = None, extra: list[tuple[str, str]] | None = None,
                 source: tuple[str, int] | None = None, contact: bool = False) -> SipMessage:
        resp = SipMessage()
        resp.status, resp.reason = code, reason
        vias = req.get_list("via")
        for i, via in enumerate(vias):
            if i == 0 and source:
                if re.search(r";\s*rport(?![=\w])", via):
                    via = re.sub(r";\s*rport(?![=\w])", f";rport={source[1]}", via)
                if "received=" not in via:
                    via += f";received={source[0]}"
            resp.add("via", via)
        resp.add("from", req.get("from", ""))
        to = req.get("to", "")
        if to_tag and parse_addr(to)[1] is None:
            to += f";tag={to_tag}"
        resp.add("to", to)
        resp.add("call-id", req.call_id)
        resp.add("cseq", req.get("cseq", ""))
        resp.add("server", USER_AGENT)
        if contact:
            resp.add("contact", f"<{self.contact_uri}>")
        for rr in req.get_list("record-route"):
            resp.add("record-route", rr)
        for n, v in extra or []:
            resp.add(n, v)
        if body is not None:
            resp.add("content-type", "application/sdp")
            resp.body = body.encode()
        return resp

    # ---- INVITE --------------------------------------------------------
    async def _on_invite(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        num, _ = msg.cseq
        key = (msg.call_id, num)
        prior = self._invite_tx.get(key)
        if prior:  # retransmitted INVITE: replay our latest response
            if prior.get("last"):
                self.send(prior["last"], addr)
            return
        _, to_tag, _ = parse_addr(msg.get("to", ""))
        if to_tag:
            await self._on_reinvite(msg, addr, key)
            return

        now = asyncio.get_running_loop().time()
        for k in [k for k, v in self._invite_tx.items() if now - v["t"] > 120]:
            del self._invite_tx[k]
        tx = {"last": None, "ack": asyncio.Event(), "t": now}
        self._invite_tx[key] = tx
        user, _, _ = uri_parts(msg.uri or "")
        from_uri, _, from_display = parse_addr(msg.get("from", ""))
        inv = Invite(msg, addr, user, from_uri, from_display, msg.body.decode("utf-8", "replace"))
        self._pending[msg.call_id] = inv
        local_tag = secrets.token_hex(6)

        def emit(resp: SipMessage) -> None:
            data = resp.serialize()
            tx["last"] = data
            self.send(data, addr)

        try:
            self.send(self.response(msg, 100, "Trying", source=addr).serialize(), addr)
            emit(self.response(msg, 180, "Ringing", to_tag=local_tag, source=addr, contact=True))
            result = await self.handler.on_invite(inv)
            if inv.cancelled.is_set():
                if isinstance(result, Accept):
                    self._spawn(self._safe_call(result.call.on_remote_bye()))
                emit(self.response(msg, 487, "Request Terminated", to_tag=local_tag, source=addr))
                self._spawn(self._retransmit(tx, addr, 3))
                return
            if isinstance(result, Reject):
                emit(self.response(msg, result.code, result.reason, to_tag=local_tag, source=addr))
                self._spawn(self._retransmit(tx, addr, 3))
                return
            remote_uri, remote_tag, _ = parse_addr(msg.get("from", ""))
            local_uri, _, _ = parse_addr(msg.get("to", ""))
            contact = msg.get("contact")
            target = parse_addr(contact)[0] if contact else remote_uri
            dialog = Dialog(call_id=msg.call_id, local_tag=local_tag, remote_tag=remote_tag or "",
                            local_uri=local_uri, remote_uri=remote_uri, remote_target=target,
                            route_set=msg.get_list("record-route"), peer=addr, call=result.call,
                            ack=tx["ack"])
            self.dialogs[msg.call_id] = dialog
            emit(self.response(msg, 200, "OK", to_tag=local_tag, body=result.sdp, source=addr, contact=True,
                               extra=[("Allow", ALLOW)]))
            self._spawn(self._await_ack(dialog, tx, addr))
        except Exception:
            log.exception("INVITE handling failed")
            emit(self.response(msg, 500, "Server Error", to_tag=local_tag, source=addr))
        finally:
            self._pending.pop(msg.call_id, None)

    async def _on_reinvite(self, msg: SipMessage, addr: tuple[str, int], key) -> None:
        dialog = self.dialogs.get(msg.call_id)
        if not dialog or dialog.closed:
            self.send(self.response(msg, 481, "Call/Transaction Does Not Exist", source=addr).serialize(), addr)
            return
        tx = {"last": None, "ack": asyncio.Event(), "t": asyncio.get_running_loop().time()}
        self._invite_tx[key] = tx
        sdp = await self._safe_call(dialog.call.on_reinvite(msg.body.decode("utf-8", "replace")))
        if sdp is None:
            resp = self.response(msg, 488, "Not Acceptable Here", source=addr)
        else:
            resp = self.response(msg, 200, "OK", body=sdp, source=addr, contact=True, extra=[("Allow", ALLOW)])
        tx["last"] = resp.serialize()
        self.send(tx["last"], addr)
        self._spawn(self._retransmit(tx, addr, 5))

    async def _retransmit(self, tx: dict, addr: tuple[str, int], attempts: int) -> None:
        delay = 0.5
        for _ in range(attempts):
            try:
                await asyncio.wait_for(tx["ack"].wait(), delay)
                return
            except asyncio.TimeoutError:
                self.send(tx["last"], addr)
                delay = min(delay * 2, 4.0)

    async def _await_ack(self, dialog: Dialog, tx: dict, addr: tuple[str, int]) -> None:
        delay, waited = 0.5, 0.0
        while waited < 32.0:
            try:
                await asyncio.wait_for(dialog.ack.wait(), delay)
            except asyncio.TimeoutError:
                waited += delay
                self.send(tx["last"], addr)
                delay = min(delay * 2, 4.0)
                continue
            await self._safe_call(dialog.call.on_answered())
            return
        log.warning("no ACK for %s; dropping call", dialog.call_id)
        await self.hangup(dialog)
        await self._safe_call(dialog.call.on_remote_bye())

    def _on_ack(self, msg: SipMessage) -> None:
        num, _ = msg.cseq
        tx = self._invite_tx.get((msg.call_id, num))
        if tx:
            tx["ack"].set()
        dialog = self.dialogs.get(msg.call_id)
        if dialog:
            dialog.ack.set()

    def _on_cancel(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        inv = self._pending.get(msg.call_id)
        if inv is None:
            self.send(self.response(msg, 481, "Call/Transaction Does Not Exist", source=addr).serialize(), addr)
            return
        self.send(self.response(msg, 200, "OK", source=addr).serialize(), addr)
        inv.cancelled.set()

    # ---- in-dialog requests -------------------------------------------
    async def _on_bye(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        dialog = self.dialogs.get(msg.call_id)
        if not dialog:
            self.send(self.response(msg, 481, "Call/Transaction Does Not Exist", source=addr).serialize(), addr)
            return
        self.send(self.response(msg, 200, "OK", source=addr).serialize(), addr)
        if not dialog.closed:
            dialog.closed = True
            await self._safe_call(dialog.call.on_remote_bye())
        self.dialogs.pop(msg.call_id, None)

    async def _on_info_update(self, msg: SipMessage, addr: tuple[str, int]) -> None:
        dialog = self.dialogs.get(msg.call_id)
        if not dialog:
            self.send(self.response(msg, 481, "Call/Transaction Does Not Exist", source=addr).serialize(), addr)
            return
        if msg.method == "INFO":
            ctype = (msg.get("content-type") or "").lower()
            body = msg.body.decode("utf-8", "replace")
            digit = None
            if "dtmf-relay" in ctype:
                m = re.search(r"Signal\s*=\s*([0-9*#A-Da-d])", body)
                digit = m.group(1).upper() if m else None
            elif "dtmf" in ctype:
                digit = body.strip()[:1] or None
            if digit:
                await self._safe_call(dialog.call.on_dtmf(digit))
            self.send(self.response(msg, 200, "OK", source=addr).serialize(), addr)
        else:  # UPDATE: acknowledge, nothing to renegotiate
            self.send(self.response(msg, 200, "OK", source=addr, contact=True).serialize(), addr)

    @staticmethod
    async def _safe_call(coro):
        try:
            return await coro
        except Exception:
            log.exception("call handler raised")
            return None

    # ---- outbound BYE --------------------------------------------------
    async def hangup(self, dialog: Dialog) -> None:
        if dialog.closed:
            return
        dialog.closed = True
        dialog.local_cseq += 1
        req = SipMessage()
        req.method = "BYE"
        route = dialog.route_set
        loose = bool(route) and ";lr" in route[0]
        req.uri = dialog.remote_target
        dest = dialog.peer
        if loose:
            _, host, port = uri_parts(parse_addr(route[0])[0])
            dest = (host, port)
        req.add("via", f"SIP/2.0/UDP {self.public_ip}:{self.port};rport;branch={new_branch()}")
        req.add("max-forwards", "70")
        for r in route:
            req.add("route", r)
        req.add("from", f"<{dialog.local_uri}>;tag={dialog.local_tag}")
        req.add("to", f"<{dialog.remote_uri}>;tag={dialog.remote_tag}")
        req.add("call-id", dialog.call_id)
        req.add("cseq", f"{dialog.local_cseq} BYE")
        req.add("user-agent", USER_AGENT)
        await self._request(req, dest, dialog.call_id, dialog.local_cseq, attempts=3)
        self.dialogs.pop(dialog.call_id, None)

    async def _request(self, req: SipMessage, dest: tuple[str, int], call_id: str, cseq: int,
                       attempts: int = 4, first_timeout: float = 0.5) -> SipMessage | None:
        """Send a non-INVITE request with T1-style retransmission; return the final response."""
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiters[(call_id, cseq)] = fut
        data = req.serialize()
        try:
            delay = first_timeout
            for _ in range(attempts):
                self.send(data, dest)
                try:
                    return await asyncio.wait_for(asyncio.shield(fut), delay)
                except asyncio.TimeoutError:
                    delay = min(delay * 2, 4.0)
            return None
        finally:
            self._waiters.pop((call_id, cseq), None)


# ---------------------------------------------------------------------------
# Registration client (for `type=sip` extension mode)
# ---------------------------------------------------------------------------

def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def digest_authorization(challenge: str, user: str, password: str, method: str, uri: str, nc: int = 1,
                         cnonce: str | None = None) -> str:
    fields = {k.lower(): (quoted or bare)
              for k, quoted, bare in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', challenge)}
    realm, nonce = fields.get("realm", ""), fields.get("nonce", "")
    algo = fields.get("algorithm", "MD5").upper()
    if algo != "MD5":
        raise ValueError(f"unsupported digest algorithm {algo}")
    ha1 = _md5(f"{user}:{realm}:{password}")
    ha2 = _md5(f"{method}:{uri}")
    qops = [q.strip() for q in fields.get("qop", "").split(",") if q.strip()]
    parts = [f'username="{user}"', f'realm="{realm}"', f'nonce="{nonce}"', f'uri="{uri}"', "algorithm=MD5"]
    if "auth" in qops:
        cnonce = cnonce or secrets.token_hex(8)
        resp = _md5(f"{ha1}:{nonce}:{nc:08x}:{cnonce}:auth:{ha2}")
        parts += [f'response="{resp}"', "qop=auth", f"nc={nc:08x}", f'cnonce="{cnonce}"']
    else:
        parts.append(f'response="{_md5(f"{ha1}:{nonce}:{ha2}")}"')
    if fields.get("opaque"):
        parts.append(f'opaque="{fields["opaque"]}"')
    return "Digest " + ", ".join(parts)


class Registration:
    """Keeps a Yemot SIP account registered so `type=sip` extensions can ring this bridge.

    Yemot blocks an IP that sends 5 bad requests in a row, so a rejected registration (wrong password, unknown
    account) is retried only `max_auth_failures` times, far apart, and then registration stops until restart.
    Plain network timeouts are not "bad requests" and are retried with a growing delay.
    """

    def __init__(self, endpoint: SipEndpoint, host: str, port: int, user: str, password: str, expires: int,
                 auth_retry_delay: float = 600.0, max_auth_failures: int = 2):
        self.ep, self.host, self.port = endpoint, host, port
        self.user, self.password, self.expires = user, password, expires
        self.auth_retry_delay, self.max_auth_failures = auth_retry_delay, max_auth_failures
        self.call_id = secrets.token_hex(8) + "@" + endpoint.public_ip
        self.tag = secrets.token_hex(5)
        self.cseq = 0
        self.registered = False
        self.halted = False
        self.rejections = 0
        self.last_status: int | None = None
        self.server_ips: set[str] = set()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="sip-register")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self.registered:
            await self._register(0)
            self.registered = False

    @property
    def trusted_ips(self) -> set[str]:
        return self.server_ips | self.ep.response_sources

    async def _run(self) -> None:
        backoff = 5.0
        while True:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(self.host, self.port, family=socket.AF_INET,
                                                                       type=socket.SOCK_DGRAM)
                self.server_ips = {i[4][0] for i in infos}
                result = await self._register(self.expires)
            except Exception:
                log.exception("registration attempt crashed")
                result = "timeout"
            was_registered, self.registered = self.registered, result == "ok"
            if result == "ok":
                if not was_registered:
                    log.info("registered with %s as %s; calls to the type=sip extension will ring this bridge",
                             self.host, self.user)
                backoff, self.rejections = 5.0, 0
                await asyncio.sleep(max(15, self.expires * 0.5))
            elif result == "rejected":
                self.rejections += 1
                if self.rejections >= self.max_auth_failures:
                    self.halted = True
                    log.error("Yemot rejected the SIP registration (SIP %s) %d times; STOPPED to avoid an IP block. "
                              "Check YEMOT_SIP_USER/YEMOT_SIP_PASSWORD/YEMOT_REGISTER_HOST and restart.",
                              self.last_status, self.rejections)
                    return
                log.error("Yemot rejected the SIP registration (SIP %s); one more try in %.0fs",
                          self.last_status, self.auth_retry_delay)
                await asyncio.sleep(self.auth_retry_delay)
            else:
                log.warning("no answer from the Yemot SIP server; retry in %.0fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120.0)

    async def _register(self, expires: int) -> str:
        """Returns 'ok', 'rejected' (the server answered but refused) or 'timeout' (no answer)."""
        dest = (next(iter(self.server_ips)) if self.server_ips else self.host, self.port)
        uri = f"sip:{self.host}"
        auth: str | None = None
        auth_header = "authorization"
        for _ in range(2):
            self.cseq += 1
            req = SipMessage()
            req.method, req.uri = "REGISTER", uri
            req.add("via", f"SIP/2.0/UDP {self.ep.public_ip}:{self.ep.port};rport;branch={new_branch()}")
            req.add("max-forwards", "70")
            req.add("from", f"<sip:{self.user}@{self.host}>;tag={self.tag}")
            req.add("to", f"<sip:{self.user}@{self.host}>")
            req.add("call-id", self.call_id)
            req.add("cseq", f"{self.cseq} REGISTER")
            req.add("contact", f"<sip:{self.user}@{self.ep.public_ip}:{self.ep.port}>;expires={expires}")
            req.add("expires", str(expires))
            req.add("allow", ALLOW)
            req.add("user-agent", USER_AGENT)
            if auth:
                req.add(auth_header, auth)
            resp = await self.ep._request(req, dest, self.call_id, self.cseq)
            if resp is None:
                return "timeout"
            self.last_status = resp.status
            if resp.status in (401, 407) and not auth:  # the normal digest challenge, not a failure
                chal = resp.get("www-authenticate") or resp.get("proxy-authenticate") or ""
                try:
                    auth = digest_authorization(chal, self.user, self.password, "REGISTER", uri)
                except ValueError as exc:
                    log.error("cannot answer the digest challenge: %s", exc)
                    return "rejected"
                auth_header = "authorization" if resp.status == 401 else "proxy-authorization"
                continue
            return "ok" if resp.status and 200 <= resp.status < 300 else "rejected"
        return "rejected"
