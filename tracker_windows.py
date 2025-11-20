# tracker_windows.py
# Pornește la login, înregistrează intervale ACTIVE/PAUSE în SQLite,
# se oprește la LOCK și reia la UNLOCK. Face rollover zilnic.
import os, time, sqlite3, datetime as dt
import sys
from pathlib import Path
import win32con, win32gui, win32api, win32ts
import threading
import signal

# If this script is run from the repo root, make sure `src/` is on sys.path
repo_root = Path(__file__).resolve().parent
src_dir = repo_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from timetracker.config import DB_PATH, LOG_PATH, ASSET_ICON
from timetracker.logging_setup import get_logger

WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
WM_TIMER = 0x0113
TIMER_ID = 1
TIMER_MS = 60_000  # verificare rollover la 60s

DB = str(DB_PATH)

logger = get_logger(name='tt')

def now():
    t = time.time()
    logger.debug("now() -> %s", t)
    return t


def today_str():
    s = dt.date.today().isoformat()
    logger.debug("today_str() -> %s", s)
    return s

def open_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=5)
    con.execute("""CREATE TABLE IF NOT EXISTS sessions(
        id INTEGER PRIMARY KEY,
        day TEXT NOT NULL,
        start_ts REAL NOT NULL,
        end_ts REAL,
        kind TEXT NOT NULL CHECK(kind in ('active','pause'))
    )""")
    logger.info("Opened DB at %s", DB)
    return con

def close_open_interval(con):
    ts = now()
    logger.info("Closing open intervals with end_ts=%s", ts)
    con.execute("UPDATE sessions SET end_ts=? WHERE end_ts IS NULL", (ts,))
    con.commit()

def start_interval(con, kind):
    s = today_str()
    ts = now()
    logger.info("Starting interval: day=%s start_ts=%s kind=%s", s, ts, kind)
    con.execute("INSERT INTO sessions(day,start_ts,kind) VALUES(?,?,?)",
                (s, ts, kind))
    con.commit()

def current_mode(con):
    row = con.execute(
        "SELECT kind FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    mode = row[0] if row else None
    logger.debug("current_mode() -> %s", mode)
    return mode

def ensure_mode(con, desired):
    mode = current_mode(con)
    if mode != desired:
        logger.info("ensure_mode: switching from %s to %s", mode, desired)
        close_open_interval(con)
        start_interval(con, desired)

def ensure_rollover(con):
    # dacă ziua s-a schimbat, închidem intervalul curent și deschidem unul nou cu același mod
    mode = current_mode(con)
    if not mode:
        logger.info("No open interval found; starting default active interval")
        start_interval(con, "active")
        return
    row = con.execute(
        "SELECT day FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_day = row[0] if row else today_str()
    if last_day != today_str():
        logger.info("Rollover detected: last_day=%s current_day=%s, closing and starting new interval (kind=%s)", last_day, today_str(), mode)
        close_open_interval(con)
        start_interval(con, mode)

class HiddenWindow:
    def __init__(self):
        self.hinst = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.hInstance = self.hinst
        wc.lpszClassName = "TimeTrackerHiddenWindow"
        wc.lpfnWndProc = self._wndproc
        self.classAtom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            self.classAtom, "TT", 0, 0, 0, 0, 0, 0, 0, self.hinst, None
        )
        # înregistrăm notificări de sesiune
        win32ts.WTSRegisterSessionNotification(self.hwnd, 0)
        logger.info("HiddenWindow created hwnd=%s", self.hwnd)

        # timer pentru rollover: prefer SetTimer, fallback la thread dacă nu e disponibil
        self._timer_thread = None
        self._timer_stop = None
        try:
            win32gui.SetTimer(self.hwnd, TIMER_ID, TIMER_MS, None)
            logger.info("Using win32gui.SetTimer for WM_TIMER (interval_ms=%d)", TIMER_MS)
        except AttributeError:
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
        # DB + stare inițială: dacă suntem logați, considerăm activ
        self.con = open_db()
        logger.info("DB opened for HiddenWindow (con=%s)", getattr(self.con, 'in_transaction', 'conn'))
        ensure_rollover(self.con)
        ensure_mode(self.con, "active")  # la pornire, considerăm activ
        logger.info("Initial mode after startup: %s", current_mode(self.con))

    def _wndproc(self, hWnd, msg, wParam, lParam):
        try:
            if msg == WM_WTSSESSION_CHANGE:
                if wParam == WTS_SESSION_LOCK:
                    logger.info("Session lock detected (WTS_SESSION_LOCK)")
                    ensure_rollover(self.con)
                    ensure_mode(self.con, "pause")
                elif wParam == WTS_SESSION_UNLOCK:
                    logger.info("Session unlock detected (WTS_SESSION_UNLOCK)")
                    ensure_rollover(self.con)
                    ensure_mode(self.con, "active")
            elif msg == WM_TIMER and wParam == TIMER_ID:
                logger.debug("WM_TIMER received (TIMER_ID=%s)", wParam)
                ensure_rollover(self.con)
            elif msg == win32con.WM_CLOSE or msg == win32con.WM_DESTROY:
                self._cleanup()
        except Exception:
            # nu oprim aplicația la excepții necritice; doar continuăm
            pass
        return win32gui.DefWindowProc(hWnd, msg, wParam, lParam)

    def _cleanup(self):
        logger.info("Cleanup: closing DB and stopping timer thread if any")
        close_open_interval(self.con)
        self.con.close()
        try:
            win32ts.WTSUnRegisterSessionNotification(self.hwnd)
        except Exception:
            logger.exception("Error unregistering session notification")
        # oprim thread-ul timer dacă a fost pornit
        try:
            if self._timer_stop:
                self._timer_stop.set()
            if self._timer_thread:
                self._timer_thread.join(timeout=1.0)
        except Exception:
            logger.exception("Error stopping timer thread")

if __name__ == "__main__":
    wnd = HiddenWindow()

    # Handle Ctrl+C (SIGINT) by posting WM_CLOSE to the hidden window so the
    # message loop exits and cleanup runs on the main thread.
    def _sigint_handler(signum, frame):
        logger.info("SIGINT received, posting WM_CLOSE to hidden window")
        try:
            win32gui.PostMessage(wnd.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            logger.exception("Failed to post WM_CLOSE on SIGINT")

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        win32gui.PumpMessages()
    finally:
        wnd._cleanup()
