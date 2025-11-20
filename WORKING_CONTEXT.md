# TimeTracker — Working Context & Current Status

> This file captures the current application purpose, recent changes, where work stopped, and the active bugs/issues to address. Use this as a quick on-ramp for continuing development.

---

## Project Purpose

TimeTracker is a tiny cross-platform activity tracker. Platform-specific daemons (`tracker_windows.py`, `tracker_macos.py`) log `active`/`pause` intervals into a local SQLite database using a shared schema:

- Table `sessions` with columns: `id`, `day`, `start_ts`, `end_ts`, `kind` where `kind` ∈ {`active`, `pause`}.

`tt_report.py` reads the DB to summarize active time per day.


## High-level Architecture / Files of Interest

- `config.yaml` (repo root): single source of configuration (BASE_DIR, DB_PATH, LOG_PATH, ASSET_ICON, etc.).
- `src/timetracker/config.py`: YAML-only loader that exposes resolved paths and config values.
- `src/timetracker/db.py`: SQLite DB helpers (connect, start interval, close open intervals, queries).
- `src/timetracker/logging_setup.py`: logger setup using `LOG_PATH` from config.
- `src/timetracker/tray.py`: tray helper using `pystray` + `Pillow`; provides `start_tray()` and `stop_tray()` and accepts an `on_exit` callback. Runs icon on a daemon thread.
- `src/timetracker/platform/windows.py`: Windows message-loop tracker implementation. Creates a hidden window, registers for session notifications, implements daily rollover via `WM_TIMER` (with fallbacks), and integrates `start_tray` so the application shows a tray icon with an Exit menu.
- `tracker_windows.py` / `tracker_macos.py`: top-level runner scripts (adapted to use `src/` package config when executed directly).
- `requirements.txt`: pins runtime dependencies (pywin32, PyYAML, pystray, Pillow, etc.).


## Recent Work (what was implemented)

- Centralized configuration into `config.yaml`. The loader `src/timetracker/config.py` enforces YAML presence and resolves paths.
- Added robust timer fallbacks in the Windows tracker:
  - Try `win32gui.SetTimer` (pywin32)
  - Fallback to `ctypes` `user32.SetTimer`/`KillTimer` if `pywin32` lacks `SetTimer`
  - Final fallback: a dedicated thread that posts `WM_TIMER` messages to the hidden window.
- Added `src/timetracker/tray.py` to provide a tray icon with a minimal menu (Status, Exit).
  - `start_tray(icon_path, title, on_exit)` accepts an `on_exit` callback. When Exit is selected, the tray helper calls `on_exit()` and then stops the icon.
- Integrated the tray icon into `src/timetracker/platform/windows.py` so Exit posts a `WM_CLOSE` to the hidden window.
- Improvements to logging and clearer runtime errors for missing dependencies (PyYAML / pystray / Pillow).
- Adjusted `requirements.txt` to use available pystray/Pillow versions and included PyYAML.


## Where we stopped (current work-in-progress)

The platform/tray functionality is mostly in place and unit-level imports succeed. The application starts, the hidden window is created, and the tray icon can be shown when dependencies are installed. However:

- A recurring runtime error prevents clean shutdown in some cases: `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread.`

This occurs when cleanup or DB update logic is executed from a different thread than the thread that originally created the SQLite connection. Typical cross-thread triggers are:

- Tray Exit menu (runs on the tray thread) invoking `on_exit` which posts `WM_CLOSE`, or
- The Windows message loop invoking cleanup handlers from the main window thread while some DB connection was opened earlier on another thread.

We need a small concurrency fix to ensure DB operations happen safely from the same thread that owns the connection, or to use a thread-safe access pattern.


## Active Errors / Bugs (observed during testing)

1. sqlite3.ProgrammingError: "SQLite objects created in a thread can only be used in that same thread." (High priority)
   - Symptom: On shutdown (tray Exit or Ctrl+C), DB close/update calls raise a ProgrammingError and may prevent `end_ts` from being written for the last open interval.
   - Cause: A sqlite3.Connection object is created on one thread and used on a different thread.
   - Repro steps: Start tracker (show tray), click Exit; check logs — stack traces show `sqlite3.ProgrammingError` during cleanup.

2. (Historical, mostly fixed) TypeError: `start_tray() got an unexpected keyword argument 'on_exit'` 
   - Symptom: Occurred when an older/duplicate tray implementation remained in the repository; fixed by consolidating `src/timetracker/tray.py` to one implementation that supports `on_exit`.

3. (Historical, fixed) ModuleNotFoundError: No module named 'yaml' (PyYAML missing)
   - Symptom: When PyYAML was not installed, `config.py` raised a raw ModuleNotFoundError. This was replaced with a clearer RuntimeError instructing to install requirements.

4. (Historical, fixed) pip failure due to unavailable `pystray` version on PyPI
   - Action: `requirements.txt` was updated to pin a published pystray version.


## Suggested Immediate Fixes (priority order)

A. Minimal, low-risk fix (recommended as first step)
- For cross-thread cleanup code (shutdown), open a fresh DB connection inside the cleanup handler and execute the final `UPDATE`/`close_open_interval` steps with that local connection, then close it. That avoids using a Connection object created on another thread.

Example (pseudo-code for `cleanup` in `src/timetracker/platform/windows.py`):

```python
from timetracker.config import DB_PATH
import sqlite3
import time

now = int(time.time())
conn = sqlite3.connect(DB_PATH)
try:
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET end_ts = ? WHERE end_ts IS NULL",
        (now,),
    )
    conn.commit()
finally:
    conn.close()
```

- Why: Minimal code change, low risk, and fixes the ProgrammingError in shutdown scenarios immediately.


B. Simpler concurrency approach (if you want more global safety)
- Use `sqlite3.connect(DB_PATH, check_same_thread=False)` and add a global `threading.Lock()` to serialize DB access in all DB helper functions. This requires auditing `src/timetracker/db.py` to acquire the lock around all DB operations.
- Pros: Allows Connection to be shared across threads safely (with locking).
- Cons: Slightly more invasive; must ensure every DB access uses the lock.


C. Robust long-term solution (recommended for maintainability)
- Implement a DB worker thread / queue: all DB operations are posted to a queue and executed by a single DB thread (which owns a single Connection). Responses can be handled via futures/promises or synchronous queue replies.
- Pros: Scales well, eliminates cross-thread misuse.
- Cons: More work to implement and test.


## Recommended Next Steps (practical immediate plan)

1. Apply the Minimal fix (A) for cleanup: modify the cleanup handler(s) that may run on other threads to use a local sqlite3 connection for the final close/update steps.
2. Re-run the tracker in the foreground, click tray Exit, and confirm logs show no sqlite3.ProgrammingError and that `end_ts` is set for the last session (inspect DB with `sqlite3` or `tt_report.py`).
3. If more concurrency issues are found or we find many cross-thread DB calls, refactor `src/timetracker/db.py` to either use `check_same_thread=False` + an access lock, or implement a DB worker thread.


## Quick run / verification commands (PowerShell)

Install requirements (if needed):

```powershell
python -m pip install -r ..\requirements.txt
```

Run tracker in foreground (Windows):

```powershell
# from src directory
python tracker_windows.py
# or if package entrypoint exists:
python -m timetracker start
```

Run the report (example: last 7 days):

```powershell
python -m timetracker report 7
```

Check DB contents quickly:

```powershell
sqlite3 "%ENV_OR_CONFIG_DB_PATH%" "SELECT * FROM sessions ORDER BY id DESC LIMIT 10;"
# Replace %ENV_OR_CONFIG_DB_PATH% with the DB path from `config.yaml` or `timetracker.config`.
```


## Notes / Contextual Observations

- The tray exit handler is already wired to post `WM_CLOSE` to the hidden window; the tray implementation calls an app-provided `on_exit` callback and then stops the icon. This behavior is correct: the issue is not the tray wiring but cross-thread DB usage during cleanup.
- Many issues observed earlier (missing PyYAML, duplicate tray implementations, pystray pinning) have been addressed.
- The single remaining blocker for reliable shutdown is the sqlite3 cross-thread ProgrammingError.


## Who to contact / file pointers for next edits

- Edit `src/timetracker/platform/windows.py` — where cleanup and tray `on_exit` are wired. Apply the minimal fix here to open a local sqlite3 connection for shutdown SQL.
- Inspect `src/timetracker/db.py` for global Connection usage if you prefer the global-lock approach.


---

If you'd like, I can now:

- Apply the minimal fix in `src/timetracker/platform/windows.py` (small patch) and run a focused test, or
- Implement the lock-based approach across `src/timetracker/db.py`.

Tell me which fix you prefer and I will implement it and run the verification steps.
