#!/usr/bin/env python3
"""Open the bridge's UDP ports in the Oracle Cloud network (Security List of the instance's subnet).

Run it in OCI Cloud Shell (the terminal icon at the top-right of the Oracle Console; it is already logged in
and has the `oci` CLI). Make sure Cloud Shell is in the same region as the server (Israel Central, Jerusalem).

    python3 oracle_open_ports.py                 # add UDP 5060 and 10000-10199 for the instance 'telegram-detector'
    python3 oracle_open_ports.py --dry-run       # only show what would change

Existing rules (SSH etc.) are kept; a backup of the old rules is saved next to the script before any change.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time


def oci(*args: str) -> dict:
    proc = subprocess.run(["oci", *args, "--output", "json"], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"`oci {' '.join(args[:3])} ...` failed:\n{proc.stderr.strip()[:600]}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def camel(obj):
    """The CLI prints kebab-case keys but expects camelCase JSON back; drop nulls."""
    if isinstance(obj, dict):
        return {re.sub(r"-([a-z])", lambda m: m.group(1).upper(), k): camel(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [camel(v) for v in obj]
    return obj


def udp_rule(lo: int, hi: int, source: str, description: str) -> dict:
    return {"protocol": "17", "source": source, "sourceType": "CIDR_BLOCK", "isStateless": False,
            "description": description, "udpOptions": {"destinationPortRange": {"min": lo, "max": hi}}}


def covers(rule: dict, lo: int, hi: int, source: str) -> bool:
    """Does an existing ingress rule already allow UDP lo..hi from `source`?"""
    if rule.get("protocol") not in ("17", "all") or rule.get("source") not in (source, "0.0.0.0/0"):
        return False
    if rule["protocol"] == "all":
        return True
    rng = (rule.get("udpOptions") or {}).get("destinationPortRange")
    return rng is None or (rng["min"] <= lo and rng["max"] >= hi)


def find_instance(name: str) -> str:
    res = oci("search", "resource", "structured-search", "--query-text",
              f"query instance resources where displayName = '{name}'")
    running = [i for i in res.get("data", {}).get("items", []) if i.get("lifecycle-state") == "RUNNING"]
    if len(running) != 1:
        sys.exit(f"expected exactly one RUNNING instance named '{name}' in this region, found {len(running)}. "
                 "Is Cloud Shell in the right region? Use --name for another instance name.")
    return running[0]["identifier"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="telegram-detector", help="instance display name")
    ap.add_argument("--sip-port", type=int, default=5060)
    ap.add_argument("--rtp", default="10000-10199")
    ap.add_argument("--source", default="0.0.0.0/0")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rtp_lo, rtp_hi = (int(x) for x in args.rtp.split("-"))
    wanted = [(args.sip_port, args.sip_port, "Yemot-Gemini bridge SIP"), (rtp_lo, rtp_hi, "Yemot-Gemini bridge RTP")]

    instance = find_instance(args.name)
    vnics = oci("compute", "instance", "list-vnics", "--instance-id", instance)["data"]
    vnic = next((v for v in vnics if v.get("is-primary")), vnics[0])
    print(f"Instance {args.name}: public IP {vnic.get('public-ip')}, subnet {vnic['subnet-id'][-12:]}")
    if vnic.get("nsg-ids"):
        print("NOTE: this VNIC also uses Network Security Groups; rules are added to the subnet's Security List, "
              "which is enough unless an NSG-only setup blocks you.")
    subnet = oci("network", "subnet", "get", "--subnet-id", vnic["subnet-id"])["data"]
    list_ids = subnet["security-list-ids"]
    if not list_ids:
        sys.exit("the subnet has no Security List; add the rules in an NSG instead.")
    sl_id = list_ids[0]
    sl = oci("network", "security-list", "get", "--security-list-id", sl_id)["data"]
    existing = camel(sl["ingress-security-rules"])

    missing = [udp_rule(lo, hi, args.source, desc) for lo, hi, desc in wanted
               if not any(covers(r, lo, hi, args.source) for r in existing)]
    if not missing:
        print(f"Already open: UDP {args.sip_port} and {args.rtp}. Nothing to do.")
        return
    print("Adding ingress rules:", ", ".join(f"UDP {r['udpOptions']['destinationPortRange']['min']}-"
                                             f"{r['udpOptions']['destinationPortRange']['max']} from {r['source']}"
                                             for r in missing))
    print(f"Keeping {len(existing)} existing rule(s) in Security List '{sl['display-name']}'.")
    if args.dry_run:
        return
    backup = f"security-list-backup-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with open(backup, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=1)
    print(f"Backup of the old rules: {backup}")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(existing + missing, fh)
    oci("network", "security-list", "update", "--security-list-id", sl_id, "--force",
        "--ingress-security-rules", f"file://{fh.name}")
    after = camel(oci("network", "security-list", "get", "--security-list-id", sl_id)["data"]["ingress-security-rules"])
    ok = all(any(covers(r, lo, hi, args.source) for r in after) for lo, hi, _ in wanted)
    print("DONE: the ports are open." if ok else "WARNING: the rules do not show up after the update; check the console.")


if __name__ == "__main__":
    main()
