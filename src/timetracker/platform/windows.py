import threading, time, signal, ctypes
from ctypes import wintypes
import win32con, win32gui, win32api, win32ts
from ..core import ensure_mode, ensure_rollover
from ..db import connect, close_open_interval
from ..logging_setup import get_logger
from ..config import ASSET_ICON
try:
    from ..tray import start_tray, stop_tray
except Exception:
    start_tray = None
    stop_tray = None


WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
WM_TIMER = 0x0113
TIMER_ID = 1
TIMER_MS = 60_000

logger = get_logger("tt")

# ctypes wrappers for user32 SetTimer/KillTimer — used when pywin32 doesn't expose SetTimer
_user32 = ctypes.windll.user32
try:
    _user32.SetTimer.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.UINT, ctypes.c_void_p)
    _user32.SetTimer.restype = wintypes.UINT
    _user32.KillTimer.argtypes = (wintypes.HWND, wintypes.UINT)
    _user32.KillTimer.restype = wintypes.BOOL
    _CTYPES_AVAILABLE = True
except Exception:
    _CTYPES_AVAILABLE = False

def ctypes_set_timer(hwnd, timer_id, ms):
    if not _CTYPES_AVAILABLE:
        return False
    res = _user32.SetTimer(hwnd, timer_id, ms, None)
    return bool(res)

def ctypes_kill_timer(hwnd, timer_id):
    if not _CTYPES_AVAILABLE:
        return False
    return bool(_user32.KillTimer(hwnd, timer_id))

class HiddenWindow:
    def __init__(self):
        self.hinst = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.hInstance = self.hinst
        wc.lpszClassName = "TimeTrackerHiddenWindow"
        wc.lpfnWndProc = self._wndproc
        self.classAtom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(self.classAtom, "TT", 0, 0, 0, 0, 0, 0, 0, self.hinst, None)
        win32ts.WTSRegisterSessionNotification(self.hwnd, 0)
        # prefer native SetTimer via pywin32, then ctypes, otherwise fall back to thread
        self._timer_thread = None
        self._timer_stop = None
        self._using_ctypes_timer = False
        self._using_pywin32_timer = False
        try:
            # try pywin32 helper first
            win32gui.SetTimer(self.hwnd, TIMER_ID, TIMER_MS, None)
            self._using_pywin32_timer = True
            logger.info("Using win32gui.SetTimer for WM_TIMER (interval_ms=%d)", TIMER_MS)
        except Exception:
            # try ctypes native user32.SetTimer next
            try:
                if ctypes_set_timer(self.hwnd, TIMER_ID, TIMER_MS):
                    self._using_ctypes_timer = True
                    logger.info("Using ctypes user32.SetTimer for WM_TIMER (interval_ms=%d)", TIMER_MS)
                else:
                    raise RuntimeError("ctypes SetTimer failed")
            except Exception:
                logger.info("win32gui.SetTimer not available; starting thread fallback for WM_TIMER (interval_ms=%d)", TIMER_MS)
                # unele versiuni/instalări nu expun SetTimer; postăm WM_TIMER periodic din thread
                self._timer_stop = threading.Event()
                def _timer_loop():
                    interval = TIMER_MS / 1000.0
                    while not self._timer_stop.wait(interval):
                        try:
                            win32gui.PostMessage(self.hwnd, WM_TIMER, TIMER_ID, 0)
                        except Exception:
                            logger.exception("Error posting WM_TIMER from fallback thread")
                self._timer_thread = threading.Thread(target=_timer_loop, daemon=True)
                self._timer_thread.start()

        self.con = connect()
        ensure_rollover(self.con, logger)
        ensure_mode(self.con, "active", logger)
        logger.info("Tracker started hwnd=%s", self.hwnd)
        # Start tray icon if available so user can see the app is running
        if start_tray:
            try:
                # provide an exit callback that posts WM_CLOSE to the hidden window
                def _exit_cb():
                    try:
                        win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
                    except Exception:
                        logger.exception("Error posting WM_CLOSE from tray exit callback")

                start_tray(str(ASSET_ICON), title="TimeTracker", on_exit=_exit_cb)
                logger.info("Tray icon started: %s", ASSET_ICON)
            except Exception:
                logger.exception("Failed to start tray icon")

    def _wndproc(self, hWnd, msg, wParam, lParam):
        try:
            if msg == WM_WTSSESSION_CHANGE:
                if wParam == WTS_SESSION_LOCK:
                    logger.info("Session lock detected")
                    ensure_rollover(self.con, logger)
                    ensure_mode(self.con, "pause", logger)
                elif wParam == WTS_SESSION_UNLOCK:
                    logger.info("Session unlock detected")
                    ensure_rollover(self.con, logger)
                    ensure_mode(self.con, "active", logger)
            elif msg == WM_TIMER and wParam == TIMER_ID:
                ensure_rollover(self.con, logger)
            elif msg in (win32con.WM_CLOSE, win32con.WM_DESTROY):
                self.cleanup()
        except Exception:
            logger.exception("WndProc error")
        return win32gui.DefWindowProc(hWnd, msg, wParam, lParam)

    def cleanup(self):
        logger.info("Cleanup: closing DB")
        try:
            close_open_interval(self.con)
            self.con.close()
            win32ts.WTSUnRegisterSessionNotification(self.hwnd)
        except Exception:
            logger.exception("Cleanup error")
        # Stop tray if it was started
        if stop_tray:
            try:
                stop_tray()
                logger.info("Tray icon stopped")
            except Exception:
                logger.exception("Error stopping tray icon")
        # stop/kill timer (pywin32, ctypes) or fallback thread
        try:
            if getattr(self, '_using_pywin32_timer', False):
                try:
                    # KillTimer is provided by pywin32
                    win32gui.KillTimer(self.hwnd, TIMER_ID)
                    logger.info("Killed pywin32 timer")
                except Exception:
                    logger.exception("Error killing pywin32 timer")
            elif getattr(self, '_using_ctypes_timer', False):
                try:
                    if ctypes_kill_timer(self.hwnd, TIMER_ID):
                        logger.info("Killed ctypes timer")
                    else:
                        logger.warning("ctypes KillTimer reported failure")
                except Exception:
                    logger.exception("Error killing ctypes timer")
            else:
                # stop fallback thread if present
                if self._timer_stop:
                    try:
                        self._timer_stop.set()
                    except Exception:
                        logger.exception("Error setting timer stop event")
                if self._timer_thread:
                    try:
                        self._timer_thread.join(timeout=1.0)
                    except Exception:
                        logger.exception("Error joining timer thread")
        except Exception:
            logger.exception("Error stopping timer")

def run():
    wnd = HiddenWindow()

    def loop():
        try:
            # record the thread id so the main thread can post WM_QUIT to this message loop
            try:
                wnd._msg_thread_id = win32api.GetCurrentThreadId()
            except Exception:
                wnd._msg_thread_id = None
            win32gui.PumpMessages()
        finally:
            wnd.cleanup()

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Ctrl+C caught; closing...")
        try:
            win32gui.PostMessage(wnd.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            logger.exception("Error posting WM_CLOSE to window")
        # also post WM_QUIT to the message-loop thread if we recorded its id
        try:
            if getattr(wnd, '_msg_thread_id', None):
                win32api.PostThreadMessage(wnd._msg_thread_id, win32con.WM_QUIT, 0, 0)
        except Exception:
            logger.exception("Error posting WM_QUIT to message thread")
        t.join(timeout=5.0)
        if t.is_alive():
            logger.warning("Message loop thread did not exit after WM_QUIT; proceeding anyway")
