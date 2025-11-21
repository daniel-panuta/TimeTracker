import os
import threading
import time
import datetime as dt
from typing import Optional, Callable

import logging

from .db import connect, daily_totals

try:
    import pystray
    from PIL import Image
except Exception:
    pystray = None
    Image = None

logger = logging.getLogger("tt.tray")

_TRAY_ICON: Optional[object] = None
_TRAY_THREAD: Optional[threading.Thread] = None
_TITLE_THREAD: Optional[threading.Thread] = None
_TITLE_STOP: Optional[threading.Event] = None


def _fmt(sec: float) -> str:
    sec = int(round(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _active_today_sec() -> int:
    """Return active seconds for today, including open interval."""
    try:
        con = connect()
        today = dt.date.today().isoformat()
        rows = daily_totals(con, today, now_ts=time.time())
        con.close()
        if rows:
            # rows ordered DESC; today is the only/first when since=today
            return int(rows[0][1] or 0)
    except Exception:
        logger.exception("Failed to compute active seconds for today")
    return 0


def _load_tray_icon_image(icon_path: str | None):
    if Image is None:
        raise RuntimeError("Pillow is required for tray icons (install Pillow)")
    try:
        if icon_path and os.path.isfile(icon_path):
            return Image.open(icon_path)
    except Exception:
        logger.exception("Failed to load icon image")
    # fallback 16x16 transparent
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    return img


def start_tray(icon_path: str | None = None, title: str = "TimeTracker",
               on_exit: Optional[Callable[[], None]] = None,
               on_control: Optional[Callable[[], None]] = None) -> None:
    """Start a system tray icon with a minimal menu.

    Menu items:
    - Status: shows application is running (no-op)
    - Control: opens the control GUI (if callback provided)
    - Exit: stops the icon and sets application exit flag by raising SystemExit when selected
    """
    global _TRAY_ICON, _TRAY_THREAD, _TITLE_THREAD, _TITLE_STOP
    if pystray is None or Image is None:
        raise RuntimeError("pystray and Pillow are required to show a tray icon; install them first")
    if _TRAY_ICON is not None:
        return

    def _on_exit(icon, item):
        # Call optional application-level exit callback first
        try:
            if on_exit:
                try:
                    on_exit()
                except Exception:
                    logger.exception("on_exit callback raised")
        finally:
            try:
                icon.stop()
            except Exception:
                pass

    image = _load_tray_icon_image(icon_path)
    def _status_text(item):
        return f"Activ azi: {_fmt(_active_today_sec())}"

    items = [pystray.MenuItem(_status_text, None, enabled=False)]
    if on_control:
        def _on_control(icon, item):
            try:
                on_control()
            except Exception:
                logger.exception("on_control callback raised")
        # default=True -> double-click on tray icon triggers this; keep visible so user can also right-click it
        items.append(pystray.MenuItem("Open", _on_control, default=True, visible=True))
    items.append(pystray.MenuItem("Exit", _on_exit))

    menu = pystray.Menu(*items)
    _TRAY_ICON = pystray.Icon("timetracker", image, title, menu)

    def _run():
        try:
            _TRAY_ICON.run()
        except Exception:
            logger.exception("Tray thread failed")

    _TRAY_THREAD = threading.Thread(target=_run, daemon=True)
    _TRAY_THREAD.start()

    # Update tooltip/title every second so user sees elapsed active time
    def _title_loop():
        while _TITLE_STOP and not _TITLE_STOP.wait(1.0):
            try:
                secs = _active_today_sec()
                if _TRAY_ICON:
                    _TRAY_ICON.title = f"{title} - {_fmt(secs)}"
                    try:
                        _TRAY_ICON.update_menu()
                    except Exception:
                        logger.exception("Error updating tray menu")
            except Exception:
                logger.exception("Error updating tray title")

    _TITLE_STOP = threading.Event()
    _TITLE_THREAD = threading.Thread(target=_title_loop, daemon=True)
    _TITLE_THREAD.start()


def stop_tray(timeout: float = 2.0) -> None:
    global _TRAY_ICON, _TRAY_THREAD, _TITLE_THREAD, _TITLE_STOP
    if _TITLE_STOP:
        try:
            _TITLE_STOP.set()
        except Exception:
            logger.exception("Error stopping title updater")
    if _TITLE_THREAD:
        try:
            _TITLE_THREAD.join(timeout=timeout)
        except Exception:
            logger.exception("Error joining title thread")
    if _TRAY_ICON is None:
        return
    try:
        _TRAY_ICON.stop()
    except Exception:
        logger.exception("Error stopping tray icon")
    if _TRAY_THREAD is not None:
        try:
            _TRAY_THREAD.join(timeout=timeout)
        except Exception:
            logger.exception("Error joining tray thread")
    _TRAY_ICON = None
    _TRAY_THREAD = None
    _TITLE_THREAD = None
    _TITLE_STOP = None
