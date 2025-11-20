import time
import datetime as dt
from .db import current_mode, current_day, close_open_interval, start_interval

def now(): return time.time()
def today_str(): return dt.date.today().isoformat()

def ensure_rollover(con, logger):
    """Închide sesiunea curentă dacă s-a schimbat ziua."""
    mode = current_mode(con)
    last_day = current_day(con)
    if not mode:
        logger.info("No open interval found; starting default active interval")
        start_interval(con, today_str(), now(), "active")
        return
    if last_day != today_str():
        logger.info("Rollover detected: %s → %s", last_day, today_str())
        close_open_interval(con)
        start_interval(con, today_str(), now(), mode)

def ensure_mode(con, desired, logger):
    """Comută între modurile active/pause dacă e nevoie."""
    mode = current_mode(con)
    if mode != desired:
        logger.info("Switching from %s to %s", mode, desired)
        close_open_interval(con)
        start_interval(con, today_str(), now(), desired)
