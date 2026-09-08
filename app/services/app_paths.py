"""Product data paths with a non-destructive migration from the legacy name."""
from __future__ import annotations
import os
import shutil
from pathlib import Path

from app.app_info import DATA_FOLDER_NAME, LEGACY_DATA_FOLDER_NAME


def _base(environment_name: str) -> Path:
    fallback = os.environ.get("APPDATA", str(Path.home()))
    return Path(os.environ.get(environment_name, fallback))


def _data_dir(environment_name: str) -> Path:
    target = _base(environment_name) / DATA_FOLDER_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def roaming_dir() -> Path:
    return _data_dir("APPDATA")


def local_dir() -> Path:
    return _data_dir("LOCALAPPDATA")


def migrated_file(filename: str, *, local: bool = False) -> Path:
    """Return a LAGSHIFT path and copy a matching legacy file once if needed."""
    environment_name = "LOCALAPPDATA" if local else "APPDATA"
    target = _data_dir(environment_name) / filename
    legacy = _base(environment_name) / LEGACY_DATA_FOLDER_NAME / filename
    if not target.exists() and legacy.is_file():
        try:
            shutil.copy2(legacy, target)
        except OSError:
            pass
    return target


def runtime_dir() -> Path:
    folder = local_dir() / "runtime"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
