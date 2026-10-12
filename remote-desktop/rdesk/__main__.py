"""נקודת כניסה:  python -m rdesk {server|host|viewer} [אפשרויות]"""
from __future__ import annotations

import argparse
import asyncio
import logging

from . import config, protocol as P


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rdesk", description="RDesk - שליטה מרחוק")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("server", help="שרת איתות")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--certfile"); s.add_argument("--keyfile")

    h = sub.add_parser("host", help="המחשב שנשלט")
    h.add_argument("--server", default=P.DEFAULT_SERVER)
    h.add_argument("--headless", action="store_true", help="בלי ממשק גרפי")
    h.add_argument("--unattended", action="store_true", help="ללא בקשת אישור (דורש --headless)")
    h.add_argument("--turn", help="url,username,credential לשרת TURN")

    v = sub.add_parser("viewer", help="המחשב ששולט")
    v.add_argument("--server", default=P.DEFAULT_SERVER)

    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.cmd == "server":
        from .signaling_server import run_forever
        asyncio.run(run_forever(args.host, args.port, args.certfile, args.keyfile))
    elif args.cmd == "host":
        if args.headless:
            asyncio.run(_headless_host(args))
        else:
            from .gui_host import HostApp
            HostApp(args.server).run()
    else:
        from .gui_viewer import ViewerApp
        ViewerApp(args.server).run()


async def _headless_host(args) -> None:
    from .host import HostService, make_rtc_config
    cfg = config.load()
    hid, pw = config.host_identity(cfg)
    turn = None
    if args.turn:
        url, user, cred = args.turn.split(",", 2)
        turn = {"url": url, "username": user, "credential": cred}

    async def approval(info):
        if args.unattended:
            return P.Permissions()
        ans = await asyncio.get_running_loop().run_in_executor(
            None, input, f"\n>> בקשת חיבור מ-{info['peer']}. לאשר? [y/N] ")
        return P.Permissions() if ans.strip().lower() == "y" else None

    svc = HostService(args.server, hid, pw, approval=approval,
                      on_event=lambda k, **kw: print(f"[{k}] {kw}"),
                      rtc_config=make_rtc_config(turn=turn))
    print(f"מזהה: {P.format_id(hid)}   סיסמה: {pw}")
    await svc.run()


if __name__ == "__main__":
    main()
