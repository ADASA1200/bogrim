"""deploy/oracle_open_ports.py against a fake `oci` CLI that keeps a tiny in-memory Security List."""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "oracle_open_ports.py"

FAKE_OCI = r'''#!/usr/bin/env python3
import json, sys
state_file = sys.argv[0] + ".state"
args = sys.argv[1:]
def out(data): print(json.dumps({"data": data}))
state = json.load(open(state_file))
cmd = " ".join(args[:3])
if cmd.startswith("search resource"):
    out({"items": state["instances"]})
elif cmd == "compute instance list-vnics":
    out([{"is-primary": True, "public-ip": "129.159.157.8", "subnet-id": "ocid1.subnet.oc1.il.aaaaaaaasubnet", "nsg-ids": []}])
elif cmd == "network subnet get":
    out({"security-list-ids": ["ocid1.securitylist.oc1.il.aaaaaaaa1", "ocid1.securitylist.oc1.il.aaaaaaaa2"]})
elif cmd == "network security-list get":
    out({"display-name": "Default Security List", "ingress-security-rules": state["rules"]})
elif cmd == "network security-list update":
    path = args[args.index("--ingress-security-rules") + 1].removeprefix("file://")
    assert "--force" in args
    state["rules"] = json.load(open(path))          # the CLI would now hold camelCase rules; keep as-is
    state["updated"] = True
    json.dump(state, open(state_file, "w"))
    out({})
else:
    sys.exit("unexpected oci call: " + " ".join(args))
'''

SSH_RULE = {"protocol": "6", "source": "0.0.0.0/0", "source-type": "CIDR_BLOCK", "is-stateless": False,
            "description": None, "tcp-options": {"destination-port-range": {"min": 22, "max": 22},
                                                 "source-port-range": None},
            "udp-options": None, "icmp-options": None}


def setup(tmp_path, rules, instances=None):
    fake = tmp_path / "oci"
    fake.write_text(FAKE_OCI)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    state = {"rules": rules, "updated": False,
             "instances": instances if instances is not None else
             [{"identifier": "ocid1.instance.oc1.il.aaaaaaaainst", "lifecycle-state": "RUNNING"}]}
    (tmp_path / "oci.state").write_text(json.dumps(state))
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    return env, tmp_path / "oci.state"


def run(tmp_path, env, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), *extra], cwd=tmp_path, env=env, capture_output=True,
                          text=True)


def test_adds_missing_udp_rules_keeps_ssh_and_writes_backup(tmp_path):
    env, state_file = setup(tmp_path, [SSH_RULE])
    res = run(tmp_path, env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "DONE: the ports are open." in res.stdout
    rules = json.loads(state_file.read_text())["rules"]
    assert len(rules) == 3
    ssh = rules[0]
    assert ssh["protocol"] == "6" and ssh["tcpOptions"]["destinationPortRange"] == {"min": 22, "max": 22}
    assert "udpOptions" not in ssh and "sourcePortRange" not in ssh["tcpOptions"]  # nulls dropped, camelCase keys
    udp = {(r["udpOptions"]["destinationPortRange"]["min"], r["udpOptions"]["destinationPortRange"]["max"])
           for r in rules[1:]}
    assert udp == {(5060, 5060), (10000, 10199)}
    assert all(r["protocol"] == "17" and r["source"] == "0.0.0.0/0" and r["isStateless"] is False for r in rules[1:])
    assert list(tmp_path.glob("security-list-backup-*.json"))


def test_dry_run_changes_nothing(tmp_path):
    env, state_file = setup(tmp_path, [SSH_RULE])
    res = run(tmp_path, env, "--dry-run")
    assert res.returncode == 0 and "Adding ingress rules" in res.stdout
    assert json.loads(state_file.read_text())["updated"] is False


def test_already_open_is_a_noop(tmp_path):
    open_rules = [SSH_RULE,
                  {"protocol": "17", "source": "0.0.0.0/0", "source-type": "CIDR_BLOCK", "is-stateless": False,
                   "udp-options": {"destination-port-range": {"min": 5060, "max": 5060}}},
                  {"protocol": "17", "source": "0.0.0.0/0", "source-type": "CIDR_BLOCK", "is-stateless": False,
                   "udp-options": {"destination-port-range": {"min": 9000, "max": 12000}}}]
    env, state_file = setup(tmp_path, open_rules)
    res = run(tmp_path, env)
    assert "Nothing to do" in res.stdout and json.loads(state_file.read_text())["updated"] is False


def test_partial_overlap_adds_only_what_is_missing(tmp_path):
    only_sip = [SSH_RULE, {"protocol": "17", "source": "0.0.0.0/0", "source-type": "CIDR_BLOCK",
                           "is-stateless": False,
                           "udp-options": {"destination-port-range": {"min": 5060, "max": 5060}}}]
    env, state_file = setup(tmp_path, only_sip)
    res = run(tmp_path, env)
    rules = json.loads(state_file.read_text())["rules"]
    assert res.returncode == 0 and len(rules) == 3
    assert rules[-1]["udpOptions"]["destinationPortRange"] == {"min": 10000, "max": 10199}


def test_no_or_many_instances_is_a_clear_error(tmp_path):
    env, _ = setup(tmp_path, [SSH_RULE], instances=[])
    res = run(tmp_path, env)
    assert res.returncode != 0 and "found 0" in (res.stdout + res.stderr)
