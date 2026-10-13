"""הדפסה מרחוק (כמו Remote Print של AnyDesk) - גרסה בלי דרייבר מדפסת משלנו.

דרייבר מדפסת אמיתי דורש חתימה (WHQL / EV code-signing מול מיקרוסופט -
תהליך בתשלום ומאושר, לא דבר שאפשר "לעקוף"). במקום זה, בצד המארח (Windows
בלבד) יוצרים תור הדפסה שמשתמש בדרייבר ה"Microsoft Print to PDF" הקיים
והחתום של Windows עצמו, עם Local Port (סוג פורט מובנה, לא זקוק לחתימה
משלו) שמפנה את הפלט לקובץ בתיקייה שאנחנו משגיחים עליה. גם AnyDesk האמיתי
דורש הרשאות מנהל להתקין את ה-Remote Print שלו (מתועד); זה לא שונה.

קובץ ה-PDF שנוצר נשלח לצופה דרך ערוץ הקבצים הקיים (files.py) - לא ערוץ
חדש - עם תחילית שם מוסכמת (PRINT_NAME_PREFIX) שגורמת לצופה להדפיס אותו
אוטומטית למדפסת שלו במקום רק להודיע "התקבל קובץ".

לא מאומת על Windows אמיתי - כמו שאר הפיצ'רים הספציפיים ל-Windows בפרויקט
הזה; ה-CI/בדיקה ידנית על Windows אמיתי הם הבדיקה האמיתית. יצירת המדפסת
עצמה (install()) דורשת הרשאות מנהל ועלולה להיכשל בלי אותן הרשאות - ראו
README לגבי הרצת RDesk כמנהל פעם אחת כדי להפעיל את התכונה הזו.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("rdesk.printing")

PRINT_NAME_PREFIX = "rdesk-print-"
PRINTER_NAME = "RDesk Remote Printer"
POLL_SECONDS = 1.0


def is_print_job(filename: str) -> bool:
    return filename.startswith(PRINT_NAME_PREFIX)


def print_received_file(path: str) -> bool:
    """מדפיס קובץ שהתקבל (PDF) למדפסת-ברירת-המחדל. נכשל בשקט (מחזיר
    False) אם אין API מתאים/מדפסת - הקובץ כבר נשמר כרגיל ואפשר לפתוח
    ולהדפיס אותו ידנית."""
    try:
        if sys.platform == "win32":
            import os
            os.startfile(path, "print")  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["lpr", path], check=True, timeout=10)
        else:
            subprocess.run(["lp", path], check=True, timeout=10)
        return True
    except Exception:
        log.exception("failed to print received file %s", path)
        return False


class PrinterPort:
    """בצד המארח: יוצר/מסיר את תור ההדפסה הווירטואלי (Windows בלבד) ומשגיח
    על תיקיית הפלט שלו לקבצים חדשים ויציבים (לא עדיין בכתיבה)."""

    def __init__(self, work_dir: Path | str) -> None:
        self.dir = Path(work_dir)
        self._seen: set[str] = set()

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def install(self) -> bool:
        if not self.supported:
            return False
        self.dir.mkdir(parents=True, exist_ok=True)
        port_path = str(self.dir / "out.pdf")
        try:
            subprocess.run(
                ["rundll32.exe", "printui.dll,PrintUIEntry", "/if", "/b", PRINTER_NAME,
                 "/m", "Microsoft Print To PDF", "/r", f"LocalPort:{port_path}", "/z"],
                check=True, timeout=20,
            )
            return True
        except Exception:
            log.exception("failed to install virtual printer (needs administrator?)")
            return False

    def uninstall(self) -> None:
        if not self.supported:
            return
        try:
            subprocess.run(
                ["rundll32.exe", "printui.dll,PrintUIEntry", "/dl", "/n", PRINTER_NAME, "/q"],
                check=False, timeout=15,
            )
        except Exception:
            log.exception("failed to remove virtual printer")

    async def watch(self, on_new_file: Callable[[Path], Awaitable[None]]) -> None:
        """בודק מדי POLL_SECONDS שניות קבצים חדשים; קובץ נחשב "יציב" (סיים
        להיכתב) כשגודלו זהה בשני סקרים רצופים - בלי sleep חוסם בתוך הלולאה."""
        sizes: dict[str, int] = {}
        while True:
            await asyncio.sleep(POLL_SECONDS)
            try:
                for p in sorted(self.dir.glob("*.pdf")):
                    if p.name in self._seen:
                        continue
                    try:
                        size = p.stat().st_size
                    except OSError:
                        continue
                    if size > 0 and sizes.get(p.name) == size:
                        self._seen.add(p.name)
                        sizes.pop(p.name, None)
                        await on_new_file(p)
                    else:
                        sizes[p.name] = size
            except Exception:
                log.exception("print output watch failed")
