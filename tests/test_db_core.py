import importlib
import sys
import datetime as dt
from pathlib import Path


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def _setup_env(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMP", str(tmp_dir))
    monkeypatch.setenv("TEMP", str(tmp_dir))

    # Isolate dotenv to a temp file to avoid picking up repo .env
    local_env = tmp_path / ".env"
    local_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("TT_ENV_FILE", str(local_env))

    base = tmp_path / "tt_db"
    env = {
        "BASE_DIR": str(base),
        "DB_PATH": str(base / "sessions.db"),
        "LOG_PATH": str(base / "timetracker.log"),
        "ASSET_DIR": str(base / "assets"),
        "ASSET_ICON": str(base / "assets" / "icon.ico"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    for mod in ("timetracker.config", "timetracker.db", "timetracker.core"):
        sys.modules.pop(mod, None)

    import timetracker.config as config
    importlib.reload(config)
    import timetracker.db as db
    importlib.reload(db)
    import timetracker.core as core
    importlib.reload(core)
    return config, db, core, base


def test_db_schema_and_mode_switch(tmp_path, monkeypatch):
    _, db, core, base = _setup_env(monkeypatch, tmp_path)
    con = db.connect(check_same_thread=False)

    # ensure schema exists (no exception) and ensure_mode opens an active interval
    logger = DummyLogger()
    core.ensure_mode(con, "active", logger)
    row = con.execute("SELECT kind, end_ts FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "active"
    assert row[1] is None

    # switching to pause closes active and opens pause
    core.ensure_mode(con, "pause", logger)
    rows = con.execute("SELECT kind, end_ts FROM sessions ORDER BY id DESC").fetchall()
    assert rows[0][0] == "pause"
    assert rows[0][1] is None
    # previous row (active) should be closed
    assert rows[1][0] == "active"
    assert rows[1][1] is not None


def test_rollover_closes_previous_day(tmp_path, monkeypatch):
    _, db, core, _, = _setup_env(monkeypatch, tmp_path)
    con = db.connect(check_same_thread=False)
    logger = DummyLogger()

    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    noon = dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), dt.time(12, 0)).timestamp()
    # insert an open interval for yesterday
    con.execute(
        "INSERT INTO sessions(day,start_ts,kind) VALUES(?,?,?)",
        (yesterday, noon, "active"),
    )
    con.commit()

    core.ensure_rollover(con, logger)

    rows = con.execute("SELECT day, end_ts, kind FROM sessions ORDER BY id").fetchall()
    assert len(rows) == 2
    # first row is yesterday, should be closed
    assert rows[0][0] == yesterday
    assert rows[0][1] is not None
    # second row is today, same mode, open
    assert rows[1][0] == dt.date.today().isoformat()
    assert rows[1][2] == "active"
    assert rows[1][1] is None
