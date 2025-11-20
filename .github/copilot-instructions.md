# TimeTracker — Copilot / AI Agent Instructions

Purpose
- This repo is a tiny cross-platform activity tracker: two platform-specific daemons (`tracker_windows.py`, `tracker_macos.py`) log `active`/`pause` intervals into a local SQLite DB. `tt_report.py` reads the DB to summarize active time.

Big picture
- Two platform-specific listeners write to the same DB schema:
  - `tracker_windows.py` uses Win32 APIs (pywin32) and a hidden window to receive session lock/unlock and a periodic timer for daily rollover.
  - `tracker_macos.py` uses Cocoa (`NSWorkspace`) + NSTimer for the same semantics.
- Shared data model: single `sessions` table (fields: `id, day, start_ts, end_ts, kind`), where `kind` ∈ {`active`, `pause`}.
- `tt_report.py` reads whichever DB exists (Windows or macOS path) and computes per-day active seconds.

Key files to reference
- `tracker_windows.py` — Windows message loop, WTS session notifications, rollover logic.
- `tracker_macos.py` — Cocoa observer, NSTimer-based rollover.
- `tt_report.py` — reporting example and DB query patterns.
- `requirements.txt` — declares `pywin32==311` (Windows). macOS requires PyObjC but is not listed here.

Run / dev workflows
- Windows (interactive check):
  - Install `requirements.txt` in a venv: `pip install -r requirements.txt`
  - Quick import test: `python -c "import win32gui; print(hasattr(win32gui,'SetTimer'))"` (some pywin32 installs don't expose `SetTimer`).
  - Run the tracker (this creates a hidden window and pumps messages; run in background or as your choice):

    ```powershell
    python tracker_windows.py
    ```

- macOS:
  - PyObjC is required; run with a Python that has `pyobjc` installed.
  - Run:

    ```bash
    python tracker_macos.py
    ```

- Report:
  - Display last N days (default 30):

    ```bash
    python tt_report.py 14
    ```

Patterns and conventions (project-specific)
- DB locations:
  - Default: platform-specific app data locations (Windows `LOCALAPPDATA`, macOS `~/Library/Application Support`).
  - Override: set `TT_DB_PATH` (full path) or create `config.yaml` at the repo root with `db_path:`.
- Schema and semantics are authoritative in the trackers. To modify behavior, update both platform scripts.
- Rollover: both trackers close the current open interval when the date changes and start a new interval with the same `kind`.
- Robustness pattern: message handlers swallow noncritical exceptions (see `try/except` in `_wndproc` and Cocoa `tick_`) — keep changes conservative.

Platform integration details
- Windows:
  - Uses `win32ts.WTSRegisterSessionNotification(hwnd, 0)` to receive lock/unlock events (handled in window proc via `WM_WTSSESSION_CHANGE`).
  - A `WM_TIMER` is used to run daily rollover checks every 60s. Some environments may not expose `win32gui.SetTimer`; code now falls back to a daemon thread that posts `WM_TIMER` to the hidden window.
  - The message pump is `win32gui.PumpMessages()` — any long-running work must not block the window thread.
- macOS:
  - Uses `NSWorkspace` notification center and an `NSTimer` scheduled on the runloop.

Common edits an agent might do
- Add feature: modify DB schema — update both `tracker_windows.py` and `tracker_macos.py` in one change and include a migration if needed.
- Fix Windows-specific Win32 interactions: check for attribute availability (e.g., `SetTimer`) and supply fallbacks (thread-based message posting is accepted here).
- Keep changes minimal and symmetrical across platforms to preserve semantics.

Checks & debugging tips
- To inspect the DB quickly:

  ```bash
  # If you use the default location, get it from the config loader or TT_DB_PATH
  sqlite3 "%ENV_OR_CONFIG_DB_PATH%" "SELECT * FROM sessions ORDER BY id DESC LIMIT 10;"
  ```
  Replace `%ENV_OR_CONFIG_DB_PATH%` with the value from `TT_DB_PATH` or the `db_path` entry in `config.yaml`.

- If Windows tracker fails with `AttributeError: module 'win32gui' has no attribute 'SetTimer'`, prefer the fallback already present (thread posting `WM_TIMER`) — verify with:

  ```powershell
  python -c "import win32gui; print(hasattr(win32gui,'SetTimer'))"
  ```

- To test behavior of lock/unlock handlers, you can simulate WM_TIMER posts:

  ```python
  import win32gui
  win32gui.PostMessage(hwnd, 0x0113, TIMER_ID, 0)  # posts WM_TIMER
  ```

Non-goals / Do not assume
- There are no unit tests or CI configured — avoid creating large test suites unless requested.
- The repo does not include an installer or service wrapper; running the scripts directly is the expected development workflow.

If anything above is unclear or you want me to:
- Merge additional guidance into this file from other docs,
- Add a short `README.md` with run/installation steps for each OS, or
- Add a simple health-check script for the DB and message loop,
please tell me which you'd prefer and I will proceed.
