"""Create the SIP account for the bridge and point a Yemot `type=sip` extension at it.

    sudo /opt/yemot-gemini-bridge/venv/bin/python -m bridge.yemot_setup \\
        --extension 5 --host <sip server from the 'מרכזיה עסקית' tab> --env /opt/yemot-gemini-bridge/.env

Needs a Yemot management token: an API KEY from the firewall (חומת האש) screen, or a `Login` token. Put it in
$YEMOT_API_TOKEN or type it when asked (hidden). Commands used (all documented in the Yemot API topic 55):
GetSipAccountsInCustomer, CreateSipAccount, SipToUdp, UpdateExtension. The account password is written straight
into the .env file and never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import stat
import sys

import aiohttp

DEFAULT_API = "https://www.call2all.co.il/ym/api"
ACCOUNT_NOTE = "gemini-bridge"


class SetupError(Exception):
    pass


async def api(session: aiohttp.ClientSession, base: str, token: str, command: str, **params) -> dict:
    # The token goes in the `authorization` header (preferred by Yemot), never in the URL.
    try:
        async with session.post(f"{base}/{command}", json=params, headers={"authorization": token}) as resp:
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise SetupError(f"{command}: request failed ({type(exc).__name__})") from None
    if data.get("responseStatus") != "OK":
        raise SetupError(f"{command}: {data.get('responseStatus')} {data.get('message', '')} "
                         f"(code {data.get('messageCode')})")
    return data


def update_env(path: str, values: dict[str, str]) -> None:
    """Set KEY=VALUE lines in an env file, keeping everything else, with 0600/0640-safe permissions."""
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    done: set[str] = set()
    out = []
    for line in lines:
        m = re.match(r"^\s*([A-Z0-9_]+)=", line)
        if m and m.group(1) in values:
            out.append(f"{m.group(1)}={values[m.group(1)]}")
            done.add(m.group(1))
        else:
            out.append(line)
    for k, v in values.items():
        if k not in done:
            out.append(f"{k}={v}")
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o600
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    if os.path.exists(path):
        st = os.stat(path)
        os.chown(tmp, st.st_uid, st.st_gid) if os.geteuid() == 0 else None
    os.replace(tmp, path)


async def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extension", required=True, help="extension to create/update, e.g. 5 (ivr2:5) or 1/3")
    ap.add_argument("--host", help="SIP server to register to (from the 'מרכזיה עסקית' tab)")
    ap.add_argument("--env", default=".env", help="bridge .env file to update (default ./.env)")
    ap.add_argument("--ext-number", type=int, help="internal extension number for the account (200-10000)")
    ap.add_argument("--use-account", help="reuse an existing SIP account (its username or account number) "
                                          "instead of creating one; its password is fetched from Yemot")
    ap.add_argument("--api-base", default=DEFAULT_API)
    ap.add_argument("--token-file", help="read the Yemot management token from this file (instead of asking)")
    ap.add_argument("--dial-timeout", type=int, default=30, help="sip_timeout for the extension, seconds")
    ap.add_argument("--no-extension", action="store_true", help="only create/reuse the account")
    ap.add_argument("--use-existing", action="store_true",
                    help="allow turning an extension that already exists into the Gemini line (changes its type)")
    args = ap.parse_args(argv)

    token = ""
    if args.token_file:
        with open(args.token_file, encoding="utf-8") as fh:
            token = fh.read().strip()
    token = token or os.environ.get("YEMOT_API_TOKEN") or getpass.getpass("Yemot API token (hidden): ")
    if not token:
        print("a token is required")
        return 2
    path = "ivr2:" + args.extension.strip().lstrip("/")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            if not args.no_extension:
                found = await api(session, args.api_base, token, "CheckIfFileExists", path=f"{path}/ext.ini")
                if found.get("fileExists"):
                    if not args.use_existing:
                        print(f"STOPPED: extension {path} already exists. Pick another number, or add --use-existing "
                              "to change that extension into the Gemini line (its type is replaced).")
                        return 3
                    print(f"Extension {path} exists; --use-existing given, its type will be changed to sip.")
                else:
                    print(f"Extension {path} does not exist yet; it will be created.")
            listing = await api(session, args.api_base, token, "GetSipAccountsInCustomer")
            accounts = listing.get("accounts", [])
            if args.use_account:
                wanted = args.use_account.strip()
                existing = next((a for a in accounts if a.get("id") == wanted or str(a.get("accountNumber")) == wanted),
                                None)
                if existing is None:
                    known = ", ".join(str(a.get("id")) for a in accounts) or "none"
                    raise SetupError(f"no SIP account '{wanted}' in this system (accounts: {known})")
            else:
                existing = next((a for a in accounts if a.get("extensionNote") == ACCOUNT_NOTE), None)
            if existing:
                account_number, user, password = existing["accountNumber"], existing["id"], existing["password"]
                print(f"Using the existing SIP account {user} (number {account_number}).")
            else:
                params = {"extensionNote": ACCOUNT_NOTE}
                if args.ext_number:
                    params["extNumber"] = args.ext_number
                made = await api(session, args.api_base, token, "CreateSipAccount", **params)
                account_number, user, password = made["accountNumber"], made["accountID"], made["PASS"]
                print(f"Created SIP account number {account_number}.")
            await api(session, args.api_base, token, "SipToUdp", accountNumber=account_number)
            print("Account transport set to UDP.")
            if not args.no_extension:
                await api(session, args.api_base, token, "UpdateExtension", path=path, type="sip",
                          account_dial_number=account_number, sip_timeout=args.dial_timeout,
                          title="Gemini")
                print(f"Extension {path} is now type=sip -> account {account_number}.")
        except SetupError as exc:
            print(f"FAILED: {exc}")
            return 1

    values = {"YEMOT_SIP_USER": user, "YEMOT_SIP_PASSWORD": password}
    if args.host:
        values["YEMOT_REGISTER_HOST"] = args.host
    update_env(args.env, values)
    print(f"Wrote {', '.join(values)} to {args.env} (password not shown).")
    if not args.host and "YEMOT_REGISTER_HOST" not in open(args.env, encoding="utf-8").read():
        print("Still missing: YEMOT_REGISTER_HOST (the SIP server shown in the site's business-switchboard tab).")
    print("Next: sudo systemctl restart yemot-gemini-bridge && sudo journalctl -u yemot-gemini-bridge -f")
    return 0


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
