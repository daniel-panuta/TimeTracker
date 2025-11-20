import os
import threading
from typing import Optional, Callable

import logging

try:
    import pystray
    from PIL import Image
except Exception:
    pystray = None
    Image = None

logger = logging.getLogger("tt.tray")

_TRAY_ICON: Optional[object] = None
_TRAY_THREAD: Optional[threading.Thread] = None


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


def start_tray(icon_path: str | None = None, title: str = "TimeTracker", on_exit: Optional[Callable[[], None]] = None) -> None:
    """Start a system tray icon with a minimal menu.

    Menu items:
    - Status: shows application is running (no-op)
    - Exit: stops the icon and sets application exit flag by raising SystemExit when selected
    """
    global _TRAY_ICON, _TRAY_THREAD
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

    def on_status(icon, item):
        # no-op; could be extended to show a dialog
        logger.info("Tray status requested")

    image = _load_tray_icon_image(icon_path)
    menu = pystray.Menu(
        pystray.MenuItem("Status", on_status),
        pystray.MenuItem("Exit", _on_exit),
    )
    _TRAY_ICON = pystray.Icon("timetracker", image, title, menu)

    def _run():
        try:
            _TRAY_ICON.run()
        except Exception:
            logger.exception("Tray thread failed")

    _TRAY_THREAD = threading.Thread(target=_run, daemon=True)
    _TRAY_THREAD.start()


def stop_tray(timeout: float = 2.0) -> None:
    global _TRAY_ICON, _TRAY_THREAD
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
