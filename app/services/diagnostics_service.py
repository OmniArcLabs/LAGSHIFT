"""Privacy-preserving local diagnostics; never exports configs or credentials."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.app_info import APP_NAME
from app.services import app_paths


def _base_dir() -> Path:
    return app_paths.local_dir()


def _anonymous_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:10]


def _sanitize_error(text: str) -> str:
    text = re.sub(r"https?://\S+", "[url]", text or "")
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", text)
    return text[-500:]


def build_report(configs: list, last_quality: dict | None = None) -> Path:
    protocols = Counter(item.protocol for item in configs)
    sources = Counter(item.source for item in configs)
    error_file = _base_dir() / "last_connection_error.log"
    last_error = ""
    if error_file.exists():
        try:
            last_error = _sanitize_error(error_file.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    safe_quality = {
        key: (last_quality or {}).get(key)
        for key in ("score", "latency", "jitter", "loss", "mode", "protocol")
        if key in (last_quality or {})
    }
    report = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "system": {"os": platform.system(), "release": platform.release(), "arch": platform.machine()},
        "configs": {"count": len(configs), "protocols": protocols, "sources": sources},
        "config_ids": [_anonymous_id(item.id) for item in configs],
        "last_quality": safe_quality,
        "last_error": last_error,
        "privacy": "No server address, link, token, key, username, process list or public IP is included.",
    }
    folder = _base_dir() / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{APP_NAME}-report-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    return path
