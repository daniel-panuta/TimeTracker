import os
from pathlib import Path

# Ensure pytest has a usable temp directory even on restricted setups.
_root_tmp = Path(__file__).resolve().parent / ".tmp"
_root_tmp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMP", str(_root_tmp))
os.environ.setdefault("TEMP", str(_root_tmp))
