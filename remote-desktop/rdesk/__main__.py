"""נקודת כניסה:  python -m rdesk {server|host|viewer|unattended} [אפשרויות]"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys

from . import config, protocol as P, strings as S


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rdesk", description=S.CLI_DESC)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd")   # בלי פקודה = האפליקציה המלאה

    a = sub.add_parser("app", help=S.CLI_APP)
    a.add_argument("--server")

    s = sub.add_parser("server", help=S.CLI_SERVER)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--certfile"); s.add_argument("--keyfile")

    h = sub.add_parser("host", help=S.CLI_HOST)
    h.add_argument("--server")
    h.add_argument("--headless", action="store_true", help=S.CLI_HEADLESS)
    h.add_argument("--turn", help=S.CLI_TURN)

    v = sub.add_parser("viewer", help=S.CLI_VIEWER)
    v.add_argument("--server")

    u = sub.add_parser("unattended", help=S.CLI_SETPW)
    u.add_argument("--off", action="store_true", help=S.CLI_CLEARPW)

    args = ap.parse_args(argv)
    _setup_logging(args.verbose)

    if args.cmd in (None, "app"):
        from .gui_host import HostApp
        HostApp(getattr(args, "server", None)).run()
    elif args.cmd == "server":
        from .signaling_server import run_forever
        asyncio.run(run_forever(args.host, args.port, args.certfile, args.keyfile))
    elif args.cmd == "host":
        if args.headless:
            asyncio.run(_headless_host(args))
        else:
            from .gui_host import HostApp
            HostApp(args.server).run()
    elif args.cmd == "unattended":
        _set_unattended(args.off)
    else:
        from .gui_viewer import ViewerApp
        ViewerApp(args.server).run()


def _setup_logging(verbose: bool) -> None:
    """ב-EXE ללא קונסול (--windowed) אין stdout; כותבים ללוג בקובץ."""
    level = logging.DEBUG if verbose else logging.INFO
    if getattr(sys, "frozen", False) or sys.stdout is None:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=level, filename=str(config.CONFIG_DIR / "rdesk.log"),
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        sys.excepthook = lambda *a: logging.getLogger("rdesk").critical("crash", exc_info=a)
    else:
        logging.basicConfig(level=level)


def _set_unattended(off: bool) -> None:
    cfg = config.load()
    if off:
        config.clear_unattended(cfg)
        print(S.CLI_PW_CLEARED)
        return
    pw = getpass.getpass(S.CLI_PW_PROMPT)
    if len(pw) < config.MIN_UNATTENDED_LEN:
        sys.exit(S.CLI_PW_SHORT)
    if getpass.getpass(S.CLI_PW_AGAIN) != pw:
        sys.exit(S.CLI_PW_MISMATCH)
    _, perms = config.get_unattended(cfg)
    config.set_unattended(cfg, pw, perms)
    print(S.CLI_PW_SET)


def _show(kind: str, **kw) -> None:
    label = S.EV.get(kind, kind)
    if kind == "session_start":
        mode = "ללא אישור" if kw.get("mode") == "unattended" else "באישור המשתמש"
        print(f"[{label}] {mode} · קוד אבטחה: {kw.get('code')}", flush=True)
    elif kind == "chat":
        print(f"[{label}] {kw.get('text')}")
    elif kind in ("status", "session_end", "file_sent", "file_received"):
        print(f"[{label}] " + " ".join(f"{v}" for v in kw.values()))
    elif kind in ("alert", "error", "file_error"):
        print(f"[{label}] {S.reason(kw.get('reason', ''))}")


async def _headless_host(args) -> None:
    from .host import HostService, make_rtc_config
    cfg = config.load()
    hid = config.host_identity(cfg)
    key, uperms = config.get_unattended(cfg)
    turn = None
    if args.turn:
        url, user, cred = args.turn.split(",", 2)
        turn = {"url": url, "username": user, "credential": cred}

    async def approval(info):
        ans = await asyncio.get_running_loop().run_in_executor(
            None, input, S.CLI_ASK.format(peer=info["peer"]))
        return P.Permissions() if ans.strip().lower() in S.CLI_YES else None

    svc = HostService(config.server_url(args.server), hid, approval=approval, on_event=_show,
                      rtc_config=make_rtc_config(turn=turn),
                      unattended_key=key, unattended_perms=uperms)
    print(S.CLI_ID_LINE.format(id=P.format_id(hid)), flush=True)
    print(S.CLI_UNATT_ON if key else S.CLI_UNATT_OFF, flush=True)
    await svc.run()


if __name__ == "__main__":
    main()
