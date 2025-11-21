import sqlite3
import time
from .config import DB_PATH
from .logging_setup import get_logger

logger = get_logger("tt.db")


def _ensure_schema(con: sqlite3.Connection):
    con.execute("""CREATE TABLE IF NOT EXISTS sessions(
        id INTEGER PRIMARY KEY,
        day TEXT NOT NULL,
        start_ts REAL NOT NULL,
        end_ts REAL,
        kind TEXT NOT NULL CHECK(kind in ('active','pause'))
    )""")
    con.commit()


def connect(timeout: float = 5.0, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (and initialize) the SQLite DB and return a connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=timeout, check_same_thread=check_same_thread)
    _ensure_schema(con)
    return con


def close_open_interval(con: sqlite3.Connection) -> None:
    ts = time.time()
    logger.info("Closing open intervals with end_ts=%s", ts)
    con.execute("UPDATE sessions SET end_ts=? WHERE end_ts IS NULL", (ts,))
    con.commit()


def start_interval(con: sqlite3.Connection, day: str, start_ts: float, kind: str) -> None:
    con.execute("INSERT INTO sessions(day,start_ts,kind) VALUES(?,?,?)", (day, start_ts, kind))
    con.commit()
    logger.info("Inserted interval: day=%s start_ts=%s kind=%s", day, start_ts, kind)


def current_mode(con: sqlite3.Connection):
    row = con.execute(
        "SELECT kind FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def current_day(con: sqlite3.Connection):
    row = con.execute(
        "SELECT day FROM sessions WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def daily_totals(con: sqlite3.Connection, since: str, now_ts: float | None = None):
    """Return the active seconds per zi, incluzând intervalul activ deschis (end_ts NULL)."""
    if now_ts is None:
        now_ts = time.time()
    rows = con.execute("""
        SELECT day,
               SUM(CASE
                       WHEN kind='active'
                         THEN (COALESCE(end_ts, ?) - start_ts)
                       ELSE 0
                   END) AS active_sec
        FROM sessions
        WHERE day >= ?
        GROUP BY day
        ORDER BY day DESC
    """, (now_ts, since)).fetchall()
    return rows
