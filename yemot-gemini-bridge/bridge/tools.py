"""Function tools exposed to Gemini (Google Search grounding is configured separately)."""

from __future__ import annotations

import asyncio
import datetime as dt
import html.parser
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import aiohttp
from google.genai import types
from pyluach import dates as heb_dates

log = logging.getLogger("bridge.tools")

FETCH_MAX_BYTES = 300_000
FETCH_MAX_CHARS = 6000
FETCH_TIMEOUT = 8
WEEKDAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


@dataclass
class ToolContext:
    caller_number: str = ""
    called_user: str = ""
    yemot_call_id: str = ""
    yemot_path: str = ""
    tz: str = "Asia/Jerusalem"
    request_hangup: Callable[[str], None] = lambda reason: None


Handler = Callable[[dict, ToolContext], Awaitable[dict]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON-schema-like: {"type": "object", "properties": {...}, "required": [...]}
    handler: Handler


def _schema(node: dict) -> types.Schema:
    kwargs: dict[str, Any] = {"type": node["type"].upper()}
    if "description" in node:
        kwargs["description"] = node["description"]
    if "enum" in node:
        kwargs["enum"] = node["enum"]
    if "properties" in node:
        kwargs["properties"] = {k: _schema(v) for k, v in node["properties"].items()}
    if "required" in node:
        kwargs["required"] = node["required"]
    return types.Schema(**kwargs)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def declarations(self) -> list[types.FunctionDeclaration]:
        return [types.FunctionDeclaration(name=t.name, description=t.description,
                                          parameters=_schema(t.parameters))
                for t in self._tools.values()]

    async def call(self, name: str, args: dict, ctx: ToolContext) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name}"}
        try:
            return await tool.handler(args or {}, ctx)
        except Exception as exc:  # tool failures go back to the model, never crash the call
            log.warning("tool %s failed: %s", name, exc)
            return {"error": str(exc)[:300]}


# ---------------------------------------------------------------------------
# get_datetime
# ---------------------------------------------------------------------------

async def get_datetime(args: dict, ctx: ToolContext) -> dict:
    tz_name = args.get("timezone") or ctx.tz
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return {"error": f"unknown timezone {tz_name}"}
    now = dt.datetime.now(tz)
    # Hebrew day rolls at sunset; we report the civil-date mapping and say so.
    h = heb_dates.HebrewDate.from_pydate(now.date())
    return {
        "timezone": tz_name,
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M"),
        "weekday_hebrew": "יום " + WEEKDAYS_HE[now.weekday()],
        "hebrew_date": h.hebrew_date_string(),
        "hebrew_date_note": "לפי התאריך האזרחי; התאריך העברי מתחלף בשקיעה",
    }


# ---------------------------------------------------------------------------
# fetch_url (SSRF-hardened)
# ---------------------------------------------------------------------------

def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


class _PublicOnlyResolver(aiohttp.abc.AbstractResolver):
    """Re-checks every address at connect time, which defeats DNS rebinding."""

    def __init__(self) -> None:
        self._inner = aiohttp.ThreadedResolver()

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        infos = await self._inner.resolve(host, port, family)
        safe = [i for i in infos if _is_public_ip(i["host"])]
        if not safe:
            raise OSError(f"address for {host} is not public")
        return safe

    async def close(self) -> None:
        await self._inner.close()


def _check_url(url: str) -> str:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("only http/https URLs are allowed")
    host = parts.hostname or ""
    if not host or parts.username or parts.password:
        raise ValueError("invalid URL")
    if parts.port not in (None, 80, 443):
        raise ValueError("only ports 80/443 are allowed")
    try:
        ipaddress.ip_address(host)
        if not _is_public_ip(host):
            raise ValueError("address is not public")
    except ValueError as exc:
        if "public" in str(exc):
            raise
    return url


class _TextExtractor(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


async def fetch_url(args: dict, ctx: ToolContext) -> dict:
    url = _check_url(str(args.get("url", "")).strip())
    connector = aiohttp.TCPConnector(resolver=_PublicOnlyResolver(), use_dns_cache=False)
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; yemot-gemini-bridge)", "Accept": "text/html,text/plain,*/*;q=0.5"}
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as session:
        for _ in range(4):  # follow at most 3 redirects, re-validating each hop
            async with session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                    url = _check_url(urljoin(url, resp.headers["Location"]))
                    continue
                ctype = resp.headers.get("Content-Type", "").lower()
                if resp.status >= 400:
                    return {"error": f"HTTP {resp.status}"}
                if not any(t in ctype for t in ("text/", "json", "xml")):
                    return {"error": f"unsupported content type {ctype or 'unknown'}"}
                body = bytearray()
                async for chunk in resp.content.iter_chunked(16384):
                    body += chunk
                    if len(body) >= FETCH_MAX_BYTES:
                        break
                text = bytes(body).decode(resp.get_encoding() or "utf-8", "replace")
                if "html" in ctype:
                    extractor = _TextExtractor()
                    extractor.feed(text)
                    text = " ".join(extractor.parts)
                text = re.sub(r"\s+", " ", text).strip()
                return {"url": str(resp.url), "text": text[:FETCH_MAX_CHARS], "truncated": len(text) > FETCH_MAX_CHARS}
    return {"error": "too many redirects"}


# ---------------------------------------------------------------------------
# call control
# ---------------------------------------------------------------------------

async def end_call(args: dict, ctx: ToolContext) -> dict:
    ctx.request_hangup(str(args.get("reason", "model requested hangup"))[:100])
    return {"result": "ok", "note": "השיחה תנותק מיד לאחר שסיימת לדבר"}


async def get_caller_info(args: dict, ctx: ToolContext) -> dict:
    return {"caller_number": ctx.caller_number or "unknown", "dialed_extension": ctx.called_user,
            "yemot_call_id": ctx.yemot_call_id}


def build_registry(*, enable_fetch_url: bool = True) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(
        "get_datetime",
        "Get the current local date, time, weekday and Hebrew date. Use for any question about 'now' or 'today'.",
        {"type": "object", "properties": {"timezone": {"type": "string",
                                                        "description": "IANA zone, default Asia/Jerusalem"}}},
        get_datetime))
    if enable_fetch_url:
        reg.register(Tool(
            "fetch_url",
            "Download a public web page (http/https) and return its readable text. "
            "Use after a search when you need details from a specific page.",
            {"type": "object", "properties": {"url": {"type": "string", "description": "Full http(s) URL"}},
             "required": ["url"]},
            fetch_url))
    reg.register(Tool(
        "get_caller_info",
        "Get the caller's phone number (if the line provides it) and the dialed extension.",
        {"type": "object", "properties": {}},
        get_caller_info))
    reg.register(Tool(
        "end_call",
        "Hang up the phone call. Say a short goodbye first, then call this.",
        {"type": "object", "properties": {"reason": {"type": "string", "description": "Why the call ends"}}},
        end_call))
    return reg
