"""אייקון מגש-מערכת (tray): נוכחות שקטה וקבועה ליד השעון, שמאפשרת לפתוח/
לשלוט באפליקציה בכל רגע - והופכת לאדום מהבהב כל עוד מישהו מחובר מרחוק
(או מחכה לאישור). בכוונה לא נוגעים בסרגל המשימות הרגיל של האפליקציה.

אם אין backend תקין למגש בסביבה הנוכחית (למשל לינוקס בלי desktop environment
תקין) - נכשלים בשקט ומדווחים ללוג; האפליקציה ממשיכה לרוץ כרגיל, פשוט בלי
האייקון. ה-import של pystray הוא lazy (לא בראש הקובץ) כי על לינוקס הוא בוחר
backend כבר בזמן ה-import ועלול לקרוס אם אין תצוגה (DISPLAY) - לא רוצים
שזה ימנע מהאפליקציה כולה לעלות.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("rdesk.tray")

_BLINK_INTERVAL = 0.6  # שניות

_IDLE_COLOR = (0, 120, 255)
_ALERT_BRIGHT_COLOR = (220, 38, 38)
_ALERT_DIM_COLOR = (120, 24, 24)


def _draw_icon(color):
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 6
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=14, fill=(*color, 255))
    d.rounded_rectangle([size * 0.26, size * 0.3, size * 0.74, size * 0.62], radius=4, fill=(255, 255, 255, 235))
    d.rectangle([size * 0.42, size * 0.62, size * 0.58, size * 0.7], fill=(255, 255, 255, 235))
    return img


class TrayIcon:
    """עוטף pystray.Icon. ``start()``/``stop()`` לא חוסמים, ו-``set_connected()``
    בטוח לקריאה מכל thread (כמו ``push()`` של ה-API)."""

    def __init__(self, on_open, on_disconnect, on_quit) -> None:
        self._on_open = on_open
        self._on_disconnect = on_disconnect
        self._on_quit = on_quit
        self._connected = False
        self._peer = ""
        self._blink_on = True
        self._blink_timer: threading.Timer | None = None
        self._icon = None
        self._icons = None
        self.available = False
        try:
            import pystray

            self._icons = {
                "idle": _draw_icon(_IDLE_COLOR),
                "alert_bright": _draw_icon(_ALERT_BRIGHT_COLOR),
                "alert_dim": _draw_icon(_ALERT_DIM_COLOR),
            }
            self._icon = pystray.Icon(
                "rdesk", self._icons["idle"], "RDesk - לא מחובר",
                menu=pystray.Menu(
                    pystray.MenuItem("פתח RDesk", self._handle_open, default=True),
                    pystray.MenuItem(self._status_text, None, enabled=False),
                    pystray.MenuItem("התנתק", self._handle_disconnect, enabled=lambda item: self._connected),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("יציאה", self._handle_quit),
                ),
            )
            self.available = True
        except Exception as e:
            log.warning("system tray icon unavailable: %s", e)

    def _status_text(self, item) -> str:
        return f"מחובר: {self._peer}" if self._connected else "לא מחובר"

    def _handle_open(self, icon=None, item=None) -> None:
        self._on_open()

    def _handle_disconnect(self, icon=None, item=None) -> None:
        self._on_disconnect()

    def _handle_quit(self, icon=None, item=None) -> None:
        self._on_quit()
        self.stop()

    def start(self) -> None:
        if not self.available:
            return
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception:
            log.exception("tray icon loop crashed")

    def stop(self) -> None:
        self._cancel_blink()
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def set_connected(self, connected: bool, peer: str = "") -> None:
        if not self.available:
            return
        self._connected = connected
        self._peer = peer
        try:
            self._icon.update_menu()
        except Exception:
            pass
        if connected:
            self._icon.title = f"RDesk - מחובר ל-{peer}" if peer else "RDesk - מחובר"
            self._start_blink()
        else:
            self._cancel_blink()
            self._set_icon_image(self._icons["idle"])
            self._icon.title = "RDesk - לא מחובר"

    def _set_icon_image(self, image) -> None:
        try:
            self._icon.icon = image
        except Exception:
            pass

    def _start_blink(self) -> None:
        self._blink_on = True
        self._set_icon_image(self._icons["alert_bright"])
        self._schedule_blink()

    def _schedule_blink(self) -> None:
        self._cancel_blink()
        self._blink_timer = threading.Timer(_BLINK_INTERVAL, self._tick_blink)
        self._blink_timer.daemon = True
        self._blink_timer.start()

    def _tick_blink(self) -> None:
        if not self._connected:
            return
        self._blink_on = not self._blink_on
        self._set_icon_image(self._icons["alert_bright"] if self._blink_on else self._icons["alert_dim"])
        self._schedule_blink()

    def _cancel_blink(self) -> None:
        if self._blink_timer is not None:
            self._blink_timer.cancel()
            self._blink_timer = None
