"""BASE_DIR: the app's own bundled code/templates/static assets (read-only, ships with the app).
DATA_DIR: where user data lives — db, uploads, backups (read-write, must survive updates).

DATA_DIR defaults to "." (current working directory) — unset, this is byte-identical to every
path this app has ever computed relative to CWD. Only Docker (optionally) and the desktop
launcher (always) set INVENTORY_DATA_DIR to something else.
"""
import os
import sys
from pathlib import Path


def _detect_base_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)  # set by PyInstaller (onefile and onedir)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


BASE_DIR: Path = _detect_base_dir()
DATA_DIR: Path = Path(os.environ.get("INVENTORY_DATA_DIR", "."))

# True only inside a PyInstaller-frozen desktop build (launcher.py) — never for uvicorn CLI/
# Docker/systemd, which import main:app directly and have no _MEIPASS.
IS_DESKTOP: bool = getattr(sys, "_MEIPASS", None) is not None
