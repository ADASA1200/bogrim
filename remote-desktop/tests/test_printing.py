"""בדיקות ל-printing.py: הזיהוי של קובץ-הדפסה, ולוגיקת ה-watch() (בלי
צורך במדפסת/Windows אמיתיים - רק קבצים רגילים על הדיסק)."""
import asyncio

import pytest

from rdesk.printing import PRINT_NAME_PREFIX, PrinterPort, is_print_job


def test_is_print_job_recognizes_prefix():
    assert is_print_job(f"{PRINT_NAME_PREFIX}document.pdf")
    assert not is_print_job("document.pdf")
    assert not is_print_job("rdesk-print.pdf")  # בלי המקף שאחרי


async def test_watch_waits_for_file_to_stop_growing(tmp_path):
    port = PrinterPort(tmp_path)
    seen = []

    async def on_new_file(p):
        seen.append(p.name)

    watch_task = asyncio.ensure_future(port.watch(on_new_file))
    try:
        growing = tmp_path / "growing.pdf"
        growing.write_bytes(b"a" * 10)
        await asyncio.sleep(1.2)   # הסקר הראשון תופס גודל 10 - עדיין לא מדווח
        assert "growing.pdf" not in seen
        growing.write_bytes(b"a" * 20)  # עדיין "גדל" - הגודל השתנה בין שני סקרים
        await asyncio.sleep(1.2)   # הסקר השני תופס גודל 20 (שונה מ-10) - עדיין לא מדווח
        assert "growing.pdf" not in seen
        await asyncio.sleep(1.2)   # הסקר השלישי תופס 20 שוב (זהה) - עכשיו מדווח
        assert seen.count("growing.pdf") == 1   # ומדווח פעם אחת בלבד, לא על כל סקר נוסף
    finally:
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass


async def test_watch_reports_stable_file_once(tmp_path):
    port = PrinterPort(tmp_path)
    seen = []

    async def on_new_file(p):
        seen.append(p.name)

    watch_task = asyncio.ensure_future(port.watch(on_new_file))
    try:
        stable = tmp_path / "stable.pdf"
        stable.write_bytes(b"done" * 100)
        await asyncio.sleep(2.5)
        assert seen.count("stable.pdf") == 1   # לא מדווח פעמיים
    finally:
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass


async def test_watch_ignores_empty_files(tmp_path):
    port = PrinterPort(tmp_path)
    seen = []

    async def on_new_file(p):
        seen.append(p.name)

    watch_task = asyncio.ensure_future(port.watch(on_new_file))
    try:
        (tmp_path / "empty.pdf").touch()
        await asyncio.sleep(2.5)
        assert "empty.pdf" not in seen
    finally:
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass


def test_printer_port_unsupported_on_non_windows():
    import sys
    port = PrinterPort("/tmp/does-not-matter")
    if sys.platform != "win32":
        assert not port.supported
        assert port.install() is False
