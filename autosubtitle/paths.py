"""
paths.py — resolves the correct user-data directory whether the app is running
from source or from a PyInstaller bundle, and exposes the presets file path.
"""

import os
import sys
from pathlib import Path


AUTHOR = "Kormány EditorTarou Róbert Károly  •  2026 04 21"


def _get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            d = Path(appdata) / "AutoSubtitle"
        else:
            d = Path.home() / ".autosubtitle"
    else:
        d = Path(os.path.dirname(os.path.abspath(__file__))).parent

    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path.home()

    return d


APP_DIR      = _get_data_dir()
PRESETS_FILE = APP_DIR / "presets.json"
