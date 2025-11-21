import os
import io
import sys
import importlib
import datetime as dt
from contextlib import redirect_stdout
from pathlib import Path


def test_report_last_7_days(tmp_path, monkeypatch):
    # Ensure a usable temp directory to avoid platform TMP issues
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMP", str(tmp_dir))
    monkeypatch.setenv("TEMP", str(tmp_dir))

    # Isolate dotenv to a temp file to avoid picking up repo .env
    local_env = tmp_path / ".env"
    local_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("TT_ENV_FILE", str(local_env))

    # Ensure package import works by adding repo/src to sys.path.
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))

    # Configure environment before importing the package.
    base = tmp_path / "timetracker"
    env = {
        "BASE_DIR": str(base),
        "DB_PATH": str(base / "sessions.db"),
        "LOG_PATH": str(base / "timetracker.log"),
        "ASSET_DIR": str(base / "assets"),
        "ASSET_ICON": str(base / "assets" / "icon.ico"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Reload config-dependent modules with the test env.
    import timetracker.config as config
    importlib.reload(config)
    import timetracker.db as db
    importlib.reload(db)
    import timetracker.report as report
    importlib.reload(report)

    con = db.connect(check_same_thread=False)
    today = dt.date.today()
    one_hour = 3600.0
    for i in range(7):
        day = today - dt.timedelta(days=i)
        ts = dt.datetime.combine(day, dt.time(12, 0)).timestamp()
        con.execute(
            "INSERT INTO sessions(day,start_ts,end_ts,kind) VALUES(?,?,?,?)",
            (day.isoformat(), ts, ts + one_hour, "active"),
        )
    con.commit()

    buf = io.StringIO()
    with redirect_stdout(buf):
        report.run(days=7)

    output = buf.getvalue()
    assert "Timp activ" in output
    assert today.isoformat() in output
