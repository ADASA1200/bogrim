"""תאימות מול libwebrtc: צופה בדפדפן Chromium (אותו מנוע כמו באנדרואיד) מיישם את אותו פרוטוקול
כמו אפליקציית ה-Kotlin ומתחבר למארח האמיתי. נדלג אם אין node/playwright."""
import asyncio
import http.server
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from rdesk import protocol as P
from rdesk.capture import SyntheticScreen
from rdesk.clipboard import MemoryClipboard
from rdesk.host import HostService, make_rtc_config
from rdesk.inject import NullInjector
from rdesk.signaling_server import serve
from test_end_to_end import free_port, wait_for

PROBE = Path(__file__).parent / "interop" / "viewer_probe.js"


def _have_playwright() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _have_playwright(), reason="node + playwright + chromium נדרשים")


@pytest.fixture
def page_server():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(b"<!doctype html><title>probe</title>")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://localhost:{srv.server_address[1]}/"
    srv.shutdown()


async def run_probe(page_url, ws_url, host_id, password=""):
    proc = await asyncio.create_subprocess_exec(
        "node", str(PROBE), page_url, ws_url, host_id, password,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(PROBE.parent), env=None)
    out, err = await asyncio.wait_for(proc.communicate(), 120)
    last = [l for l in out.decode().splitlines() if l.startswith("{")][-1]
    return json.loads(last)


@pytest.fixture
async def stack(tmp_path):
    port = free_port()
    server = await serve("127.0.0.1", port)
    inj, clip, events, approvals = NullInjector(), MemoryClipboard("host-clip"), [], []

    async def approve(info):
        approvals.append(info)
        return P.Permissions()

    host = HostService(f"ws://127.0.0.1:{port}", "555666777", screen=SyntheticScreen(), injector=inj,
                       clipboard=clip, approval=approve, on_event=lambda k, **kw: events.append((k, kw)),
                       download_dir=tmp_path / "recv", rtc_config=make_rtc_config([]))
    task = asyncio.ensure_future(host.run())
    await asyncio.wait_for(host.registered.wait(), 5)

    class S: pass
    s = S()
    s.url, s.host, s.inj, s.clip, s.events, s.approvals, s.tmp = f"ws://127.0.0.1:{port}", host, inj, clip, events, approvals, tmp_path
    yield s
    await host.stop(); task.cancel(); server.close(); await server.wait_closed()


async def test_chromium_viewer_with_user_approval(stack, page_server):
    r = await run_probe(page_server, stack.url, "555666777")
    assert "error" not in r, r
    assert r["mode"] == "interactive" and len(stack.approvals) == 1
    assert r["frames"] >= 5, "no decoded video frames in Chromium"
    assert r["hello"]["monitors"][0]["width"] == 640
    # קוד האבטחה זהה בשני הצדדים
    host_code = next(kw["code"] for k, kw in stack.events if k == "session_start")
    assert r["code"] == host_code
    # קלט הגיע למארח
    assert ("move", 319, 89) in stack.inj.events
    assert ("button", "left", True) in stack.inj.events and ("scroll", 0, 1) in stack.inj.events
    assert ("key", "a", True) in stack.inj.events
    assert any(k == "chat" and kw["text"] == "שלום מהדפדפן" for k, kw in stack.events)
    assert stack.clip.text == "clip from probe"
    # קובץ
    assert (stack.tmp / "recv" / "probe.bin").read_bytes() == bytes(i % 251 for i in range(40000))
    assert await wait_for(lambda: stack.host.session is None)


async def test_chromium_viewer_unattended_password(stack, page_server):
    stack.host.set_unattended(P.derive_key("permanent-pass"), P.Permissions(files=False))

    async def must_not_ask(info): raise AssertionError("no approval expected")
    stack.host.approval = must_not_ask
    r = await run_probe(page_server, stack.url, "555666777", "permanent-pass")
    assert "error" not in r, r
    assert r["mode"] == "unattended" and r["frames"] >= 5
    assert not (stack.tmp / "recv" / "probe.bin").exists()     # הרשאת קבצים כבויה
    host_code = next(kw["code"] for k, kw in stack.events if k == "session_start")
    assert r["code"] == host_code


async def test_chromium_viewer_wrong_password(stack, page_server):
    stack.host.set_unattended(P.derive_key("permanent-pass"))
    r = await run_probe(page_server, stack.url, "555666777", "wrong-password")
    assert r.get("error") == "bad password"
