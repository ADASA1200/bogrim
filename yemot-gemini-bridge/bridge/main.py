"""Entry point: python -m bridge.main"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

from aiohttp import web

from .call import CallManager
from .config import Config, ConfigError
from .sip import Registration, SipEndpoint
from .tools import build_registry

log = logging.getLogger("bridge")


async def start_status_server(cfg: Config, manager: CallManager, started: float) -> web.AppRunner:
    token = cfg.status_token

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def status(req: web.Request) -> web.Response:
        import hmac
        supplied = req.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            return web.Response(status=401, text="unauthorized")
        reg = manager.registration
        return web.json_response({
            "uptime_s": int(time.time() - started),
            "active_calls": len(manager.calls),
            "total_calls": manager.total_calls,
            "max_calls": cfg.max_calls,
            "registered": bool(reg and reg.registered),
            "model": cfg.gemini_model,
            "calls": [{"id": c.call_id[:8], "seconds": int(time.monotonic() - c.started),
                       "tool_calls": c.gemini.tool_calls if c.gemini else 0} for c in manager.calls.values()],
        })

    app = web.Application()
    app.add_routes([web.get("/healthz", health), web.get("/status", status)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", cfg.status_port).start()
    return runner


async def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}")

    started = time.time()
    manager = CallManager(cfg, build_registry(enable_fetch_url=cfg.enable_fetch_url))
    endpoint = SipEndpoint(cfg.public_ip, cfg.sip_port, manager)
    manager.endpoint = endpoint
    await endpoint.start(cfg.sip_bind)
    log.info("SIP listening on %s:%d (public %s), model=%s, tools=%s%s", cfg.sip_bind, cfg.sip_port, cfg.public_ip,
             cfg.gemini_model, ", ".join(manager.registry.names),
             " + google_search" if cfg.enable_google_search else "")

    if cfg.register_host:
        manager.registration = Registration(endpoint, cfg.register_host, cfg.register_port, cfg.register_user,
                                            cfg.register_password, cfg.register_expires)
        manager.registration.start()

    runner = await start_status_server(cfg, manager, started) if cfg.status_port else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("shutting down")
    if manager.registration:
        await manager.registration.stop()
    await manager.shutdown()
    endpoint.close()
    if runner:
        await runner.cleanup()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
