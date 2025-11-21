import importlib
import sys
from pathlib import Path


def _reload_config(monkeypatch, tmp_path, env=None, home_override=None):
    """Helper to reload config with a controlled environment/base path."""
    # Make sure repo/src is on sys.path
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))

    # Avoid picking up the real project .env by working in an isolated cwd.
    monkeypatch.chdir(tmp_path)
    # Place an empty .env and point TT_ENV_FILE to it so config.py loads only this file.
    local_env = tmp_path / ".env"
    local_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("TT_ENV_FILE", str(local_env))

    # Ensure a usable temp directory for any stdlib temp use
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMP", str(tmp_dir))
    monkeypatch.setenv("TEMP", str(tmp_dir))

    # Clear env keys used by config
    for key in ("BASE_DIR", "DB_PATH", "LOG_PATH", "ASSET_DIR", "ASSET_ICON"):
        monkeypatch.delenv(key, raising=False)

    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    if home_override:
        monkeypatch.setattr(Path, "home", lambda: home_override)

    # Drop cached modules so reload uses the new env
    for mod in ("timetracker.config",):
        sys.modules.pop(mod, None)

    import timetracker.config as config
    importlib.reload(config)
    return config


def test_config_env_override(tmp_path, monkeypatch):
    base = tmp_path / "tt_env"
    env = {
        "BASE_DIR": str(base),
        "DB_PATH": str(base / "sessions.db"),
        "LOG_PATH": str(base / "timetracker.log"),
        "ASSET_DIR": str(base / "assets"),
        "ASSET_ICON": str(base / "assets" / "icon.ico"),
    }
    config = _reload_config(monkeypatch, tmp_path, env=env)

    assert config.BASE_DIR == base
    assert config.DB_PATH == base / "sessions.db"
    assert config.LOG_PATH == base / "timetracker.log"
    assert config.ASSET_DIR == base / "assets"
    assert config.ASSET_ICON == base / "assets" / "icon.ico"
    assert config.BASE_DIR.exists()  # auto-created


def test_config_defaults_use_home(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    config = _reload_config(monkeypatch, tmp_path, home_override=fake_home)

    expected_base = fake_home / ".timetracker"
    assert config.BASE_DIR == expected_base
    assert config.DB_PATH == expected_base / "sessions.db"
    assert config.LOG_PATH == expected_base / "timetracker.log"
    assert config.ASSET_DIR == expected_base / "assets"
    assert config.ASSET_ICON == expected_base / "assets" / "icon.ico"
    assert config.BASE_DIR.exists()
