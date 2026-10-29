"""Build the ready-to-upload install bundle (a zip with code + prepared .env + secrets).

The secrets come from environment variables and end up ONLY inside the zip; never commit the result.

    GEMINI_API_KEY=... YEMOT_API_TOKEN=... PUBLIC_IP=203.0.113.7 SIP_ACCOUNT=086693864 EXT=1522 \\
        python3 deploy/make_bundle.py --out yemot-gemini-bundle.zip
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "yemot-gemini-bundle"
SKIP_DIRS = {"__pycache__", ".pytest_cache", "tests", "venv", ".git"}


def env_file(gemini_key: str, public_ip: str) -> str:
    keep = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.split("=", 1)[0] in ("GEMINI_API_KEY", "PUBLIC_IP", "ACCESS_TOKEN"):
            continue
        keep.append(s)
    # YEMOT_REGISTER_HOST / USER / PASSWORD are added together by bridge.yemot_setup during install.
    head = [f"GEMINI_API_KEY={gemini_key}", f"PUBLIC_IP={public_ip}", f"ACCESS_TOKEN={secrets.token_urlsafe(24)}"]
    return "\n".join(head + keep) + "\n"


def add(zf: zipfile.ZipFile, name: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(f"{TOP}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    need = {k: os.environ.get(k, "") for k in ("GEMINI_API_KEY", "YEMOT_API_TOKEN", "PUBLIC_IP", "SIP_ACCOUNT", "EXT")}
    missing = [k for k, v in need.items() if not v]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    host = os.environ.get("SIP_HOST", "sip.yemot.co.il")

    with zipfile.ZipFile(args.out, "w") as zf:
        for rel in ("bridge", "deploy"):
            for path in sorted((ROOT / rel).rglob("*")):
                if path.is_dir() or SKIP_DIRS & set(path.relative_to(ROOT).parts):
                    continue
                if path.parts[-2:] == ("bundle", "install_all.sh") or path.name == "README_HE.txt" and "bundle" in path.parts:
                    continue  # these two go to the bundle root below
                mode = 0o755 if path.suffix in (".sh",) else 0o644
                add(zf, str(path.relative_to(ROOT)), path.read_bytes(), mode)
        for name in ("requirements.txt", ".env.example", "README.md"):
            add(zf, name, (ROOT / name).read_bytes(), 0o644)
        add(zf, "install_all.sh", (ROOT / "deploy/bundle/install_all.sh").read_bytes(), 0o755)
        add(zf, "README_HE.txt", (ROOT / "deploy/bundle/README_HE.txt").read_bytes(), 0o644)
        add(zf, "BUILD", f"bundle build {time.strftime('%Y-%m-%d %H:%M')}  (yemot_setup handles 'already UDP': "
                         f"{'yes' if 'already UDP' in (ROOT / 'bridge/yemot_setup.py').read_text(encoding='utf-8') else 'NO'})\n".encode(), 0o644)
        add(zf, "bundle.conf", f'EXT="{need["EXT"]}"\nACCOUNT="{need["SIP_ACCOUNT"]}"\nSIP_HOST="{host}"\n'.encode(), 0o644)
        add(zf, ".env", env_file(need["GEMINI_API_KEY"], need["PUBLIC_IP"]).encode(), 0o600)
        add(zf, "secrets/yemot_api_token", (need["YEMOT_API_TOKEN"] + "\n").encode(), 0o600)
    print(f"wrote {args.out} ({Path(args.out).stat().st_size} bytes)")


if __name__ == "__main__":
    main()
