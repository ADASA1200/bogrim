"""בונה את קובץ ההפעלה עם PyInstaller (רץ על מערכת ההפעלה הנוכחית).

    python build_exe.py            # -> dist/RDesk(.exe)
ל-Windows יש להריץ על Windows (או ב-GitHub Actions, ראו .github/workflows).
"""
import subprocess
import sys

COLLECT_ALL = ["aiortc", "aioice", "pylibsrtp", "av", "pyee", "google_crc32c"]
SUBMODULES = ["pynput", "mss", "websockets", "rdesk"]
if sys.platform.startswith("linux"):
    SUBMODULES.append("Xlib")     # backend של pynput ב-X11
# pynput בוחר backend בזמן ריצה (import דינמי), ו-PyInstaller לא מזהה אותם לבד
HIDDEN = ["PIL._tkinter_finder", "bidi"] + [
    f"pynput.{kind}._{be}" for kind in ("keyboard", "mouse") for be in ("win32", "darwin", "xorg", "base", "dummy")
] + ["pynput._util.win32", "pynput._util.win32_vks", "pynput._util.darwin",
     "pynput._util.xorg", "pynput._util.xorg_keysyms", "pynput._util.uinput"]


def main(extra: list[str]) -> int:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
           "--name", "RDesk", "--collect-data", "bidi"]
    if sys.platform == "win32":
        cmd.append("--windowed")      # בלי חלון קונסול
    for m in COLLECT_ALL:
        cmd += ["--collect-all", m]
    for m in SUBMODULES:
        cmd += ["--collect-submodules", m]
    for m in HIDDEN:
        cmd += ["--hidden-import", m]
    cmd += extra + ["run_app.py"]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
