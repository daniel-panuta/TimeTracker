import os
from pathlib import Path
from dotenv import load_dotenv

"""Environment-only configuration loader.

Reads settings from `.env` (if present) or environment variables:
- BASE_DIR
- DB_PATH
- LOG_PATH
- ASSET_DIR
- ASSET_ICON

If a variable is missing, sensible defaults under `~/.timetracker` are used.
"""

# Allow overriding the .env location via TT_ENV_FILE (useful for tests).
_ENV_FILE = os.environ.get("TT_ENV_FILE")
if _ENV_FILE:
    load_dotenv(Path(_ENV_FILE).expanduser(), override=False)
else:
    load_dotenv()

DEFAULT_BASE = Path.home() / ".timetracker"


def _path_env(key: str, default: Path) -> Path:
    val = os.environ.get(key)
    if not val:
        return default
    expanded = os.path.expandvars(val)
    return Path(expanded).expanduser()


BASE_DIR = _path_env("BASE_DIR", DEFAULT_BASE)
DB_PATH = _path_env("DB_PATH", BASE_DIR / "sessions.db")
LOG_PATH = _path_env("LOG_PATH", BASE_DIR / "timetracker.log")
ASSET_DIR = _path_env("ASSET_DIR", BASE_DIR / "assets")
ASSET_ICON = _path_env("ASSET_ICON", ASSET_DIR / "icon.ico")

# Ensure base dir exists
BASE_DIR.mkdir(parents=True, exist_ok=True)
