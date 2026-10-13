"""בונה את קובץ ההפעלה עם PyInstaller (רץ על מערכת ההפעלה הנוכחית).

    cd webui && npm ci && npm run build && cd ..
    python build_exe.py            # -> dist/RDesk(.exe)
ל-Windows יש להריץ על Windows (או ב-GitHub Actions, ראו .github/workflows).
חייבים לבנות את webui/dist לפני כן - הממשק (React) ארוז בתוך ה-EXE כקבצים סטטיים.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBUI_DIST = ROOT / "webui" / "dist"

# sv_ttk/darkdetect: ל-tkinter הישן (--legacy-ui). webview: חלון הדפדפן המקומי
# לממשק ה-React - על Windows צריך גם clr_loader/pythonnet עבור WebView2.
COLLECT_ALL = ["aiortc", "aioice", "pylibsrtp", "av", "pyee", "google_crc32c",
               "sv_ttk", "darkdetect", "webview", "clr_loader", "pystray"]
SUBMODULES = ["pynput", "mss", "websockets", "rdesk"]
if sys.platform.startswith("linux"):
    SUBMODULES.append("Xlib")     # backend של pynput ב-X11
if sys.platform == "win32":
    SUBMODULES += ["clr_loader", "pythonnet"]
# pynput בוחר backend בזמן ריצה (import דינמי), ו-PyInstaller לא מזהה אותם לבד
HIDDEN = ["PIL._tkinter_finder", "bidi"] + [
    f"pynput.{kind}._{be}" for kind in ("keyboard", "mouse") for be in ("win32", "darwin", "xorg", "base", "dummy")
] + ["pynput._util.win32", "pynput._util.win32_vks", "pynput._util.darwin",
     "pynput._util.xorg", "pynput._util.xorg_keysyms", "pynput._util.uinput",
     "webview.platforms.edgechromium", "webview.platforms.winforms", "webview.platforms.cocoa",
     "webview.platforms.gtk", "webview.platforms.qt"]


def main(extra: list[str]) -> int:
    if not (WEBUI_DIST / "index.html").exists():
        print(f"שגיאה: {WEBUI_DIST} לא קיים. הריצו קודם: cd webui && npm ci && npm run build",
              file=sys.stderr)
        return 1

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
           "--name", "RDesk", "--collect-data", "bidi",
           "--add-data", f"{WEBUI_DIST}{os_sep()}webui_dist"]
    if sys.platform == "win32":
        cmd.append("--windowed")      # בלי חלון קונסול
        icon = ROOT / "rdesk_icon.ico"
        if icon.exists():
            cmd += ["--icon", str(icon)]
    for m in COLLECT_ALL:
        cmd += ["--collect-all", m]
    for m in SUBMODULES:
        cmd += ["--collect-submodules", m]
    for m in HIDDEN:
        cmd += ["--hidden-import", m]
    cmd += extra + ["run_app.py"]
    print(" ".join(cmd))
    return subprocess.call(cmd)


def os_sep() -> str:
    # --add-data על Windows דורש ';' בין מקור ליעד, ובשאר המערכות ':'
    return ";" if sys.platform == "win32" else ":"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
