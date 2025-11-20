# tracker_macos.py
# Ascultă NSWorkspace notificări (unlock/lock), loghează ACTIVE/PAUSE în SQLite,
# rollover zilnic via NSTimer.
import os, time, sqlite3, datetime as dt
import sys
from pathlib import Path
from Cocoa import NSWorkspace, NSObject, NSRunLoop, NSDate, NSTimer
import objc

# Ensure `src/` is on sys.path when running the top-level script
repo_root = Path(__file__).resolve().parent
src_dir = repo_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from timetracker.config import DB_PATH
from timetracker.logging_setup import get_logger

DB = str(DB_PATH)
logger = get_logger("tt")

def now(): return time.time()
def today_str(): return dt.date.today().isoformat()

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
    return con

def close_open_interval(con):
    con.execute("UPDATE sessions SET end_ts=? WHERE end_ts IS NULL", (now(),))
    con.commit()

def start_interval(con, kind):
    con.execute("INSERT INTO sessions(day,start_ts,kind) VALUES(?,?,?)",
                (today_str(), now(), kind))
    con.commit()

def current_mode(con):
    row = con.execute(
        "SELECT kind FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None

def ensure_mode(con, desired):
    mode = current_mode(con)
    if mode != desired:
        close_open_interval(con)
        start_interval(con, desired)

def ensure_rollover(con):
    mode = current_mode(con)
    if not mode:
        start_interval(con, "active")
        return
    row = con.execute(
        "SELECT day FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_day = row[0] if row else today_str()
    if last_day != today_str():
        close_open_interval(con)
        start_interval(con, mode)

class Observer(NSObject):
    def init(self):
        self = objc.super(Observer, self).init()
        if self is None:
            return None
        self.con = open_db()
        ensure_rollover(self.con)
        ensure_mode(self.con, "active")  # la pornire considerăm activ
        # timer pentru rollover la fiecare 60s
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            60.0, self, objc.selector(self.tick_, signature=b'v@:@'), None, True
        )
        return self

    def tick_(self, _):
        try:
            ensure_rollover(self.con)
        except Exception:
            pass

    # Când sesiunea devine INACTIVĂ (lock/switch away)
    def sessionDidResignActive_(self, notif):
        ensure_rollover(self.con)
        ensure_mode(self.con, "pause")

    # Când revine ACTIVĂ (unlock/focus)
    def sessionDidBecomeActive_(self, notif):
        ensure_rollover(self.con)
        ensure_mode(self.con, "active")

def main():
    obs = Observer.alloc().init()
    ws = NSWorkspace.sharedWorkspace().notificationCenter()
    ws.addObserver_selector_name_object_(
        obs,
        objc.selector(Observer.sessionDidResignActive_, signature=b'v@:@'),
        "NSWorkspaceSessionDidResignActiveNotification",
        None
    )
    ws.addObserver_selector_name_object_(
        obs,
        objc.selector(Observer.sessionDidBecomeActive_, signature=b'v@:@'),
        "NSWorkspaceSessionDidBecomeActiveNotification",
        None
    )
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.distantFuture())

if __name__ == "__main__":
    main()
