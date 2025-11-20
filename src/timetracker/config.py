from pathlib import Path
import os
try:
    import yaml
except Exception as exc:  # pragma: no cover - user environment may miss PyYAML
    raise RuntimeError(
        "PyYAML is required to load configuration.\n"
        "Please install the project requirements: `python -m pip install -r requirements.txt`\n"
        "Or install PyYAML directly: `python -m pip install PyYAML`\n"
        f"Original error: {exc!r}"
    )

"""YAML-only configuration loader.

This module reads the repository `config.yaml` (or the file pointed to by
`TT_CONFIG`) and exposes canonical paths: `BASE_DIR`, `DB_PATH`, `LOG_PATH`,
`ASSET_DIR`, and `ASSET_ICON`.

It fails fast if the YAML file is missing or required keys are absent,
enforcing a single source-of-truth for configuration.
"""

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path() -> Path:
    # Use a single fixed config location in the repo root: `config.yaml`.
    return _repo_root() / "config.yaml"


CFG_PATH = _config_path()
if not CFG_PATH.exists():
    raise RuntimeError(f"Configuration file not found: {CFG_PATH}. Create it before running the app.")

with CFG_PATH.open("r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}

def _get(key: str) -> Path:
    if key not in cfg:
        raise RuntimeError(f"Missing config key '{key}' in {CFG_PATH}")
    return Path(cfg[key])


# Public constants (all derived from YAML)
BASE_DIR = _get("base_dir")
DB_PATH = _get("db_path")
LOG_PATH = _get("log_path")
ASSET_DIR = _get("asset_dir")
ASSET_ICON = _get("asset_icon")

# Ensure base dir exists
BASE_DIR.mkdir(parents=True, exist_ok=True)
