"""Consistent hidden-process options for background Windows helpers.

CREATE_NO_WINDOW normally prevents a console, while STARTF_USESHOWWINDOW is a
second guard for tools that try to activate a window or flash the taskbar.
Keeping this in one place also makes future platform adapters straightforward.
"""
from __future__ import annotations

import os
import subprocess


def hidden_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def hidden_popen_kwargs() -> dict:
    """Popen variant; detached UI processes should not use this helper."""
    return hidden_process_kwargs()
