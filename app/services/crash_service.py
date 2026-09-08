"""Local-first, privacy-preserving crash recorder with a future backend envelope."""
from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import platform
import re
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.app_info import APP_NAME, APP_VERSION, BUILD_NUMBER
from app.services import app_paths, secure_storage

SCHEMA_VERSION = 1
MAX_REPORTS = 20
MAX_BREADCRUMBS = 80
_LOCK = threading.RLock()
_BREADCRUMBS: deque[dict] = deque(maxlen=MAX_BREADCRUMBS)
_ENABLED = True
_MARKER: Path | None = None
_FAULT_FILE = None
_ORIGINAL_SYS_HOOK = sys.excepthook
_ORIGINAL_THREAD_HOOK = getattr(threading, "excepthook", None)
_last_heartbeat = time.monotonic()
_hang_recorded = False


def _folder() -> Path:
    path = app_paths.local_dir() / "blackbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _queue_folder() -> Path:
    path = _folder() / "queue"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize(value, limit: int = 1200) -> str:
    text = str(value or "")
    text = re.sub(r"https?://\S+", "[url]", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", text)
    text = re.sub(
        r"(?<![\w])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:.%]*(?![\w])",
        "[ip]", text,
    )
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", "[mac]", text)
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", "[email]", text)
    text = re.sub(r"(?i)([a-z]:\\users\\)[^\\\s]+", r"\1[user]", text)
    text = re.sub(
        r"(?i)\b(token|secret|password|private[_ -]?key|license)\s*[:=]\s*[^\s,;]+",
        r"\1=[removed]", text,
    )
    return text[-limit:]


def add_breadcrumb(category: str, message: str, **safe_data) -> None:
    if not _ENABLED:
        return
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "category": sanitize(category, 40), "message": sanitize(message, 240),
    }
    if safe_data:
        row["data"] = {sanitize(key, 40): sanitize(value, 120) for key, value in safe_data.items()}
    with _LOCK:
        _BREADCRUMBS.append(row)


def _fingerprint(kind: str, error_type: str, stack: str) -> str:
    stable = "\n".join(line.strip() for line in stack.splitlines() if line.strip())[-3000:]
    return hashlib.sha256(f"{kind}|{error_type}|{stable}".encode("utf-8", "ignore")).hexdigest()[:16]


def _write_report(kind: str, error_type: str, message: str, stack: str = "") -> Path | None:
    if not _ENABLED:
        return None
    clean_stack = sanitize(stack, 10000)
    report = {
        "schema": SCHEMA_VERSION,
        "report_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": sanitize(kind, 60), "error_type": sanitize(error_type, 100),
        "message": sanitize(message, 1200),
        "fingerprint": _fingerprint(kind, error_type, clean_stack),
        "release": {"version": APP_VERSION, "build": BUILD_NUMBER},
        "system": {
            "os": platform.system(), "release": platform.release(),
            "architecture": platform.machine(), "python": platform.python_version(),
        },
        "stack": clean_stack,
        "breadcrumbs": list(_BREADCRUMBS),
        "privacy": "sanitized-local-report; no automatic upload",
    }
    encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    protected = secure_storage.protect(encoded)
    target = _queue_folder() / f"{report['created_at'][:10]}-{report['report_id']}.lsc"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(protected, encoding="ascii")
    os.replace(temporary, target)
    _prune()
    return target


def capture_exception(exc_type, exc_value, exc_traceback, *, kind: str = "unhandled_exception"):
    try:
        stack = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        return _write_report(kind, getattr(exc_type, "__name__", "Exception"), str(exc_value), stack)
    except Exception:
        return None


def capture_event(kind: str, message: str, error_type: str = "RuntimeEvent"):
    try:
        return _write_report(kind, error_type, message)
    except Exception:
        return None


def _sys_hook(exc_type, exc_value, exc_traceback):
    capture_exception(exc_type, exc_value, exc_traceback)
    _ORIGINAL_SYS_HOOK(exc_type, exc_value, exc_traceback)


def _thread_hook(args):
    capture_exception(args.exc_type, args.exc_value, args.exc_traceback, kind="thread_exception")
    if _ORIGINAL_THREAD_HOOK:
        _ORIGINAL_THREAD_HOOK(args)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _prune() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    files = sorted(_queue_folder().glob("*.lsc"), key=lambda item: item.stat().st_mtime, reverse=True)
    for index, item in enumerate(files):
        too_old = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc) < cutoff
        if index >= MAX_REPORTS or too_old:
            try:
                item.unlink()
            except OSError:
                pass


def initialize(enabled: bool = True) -> bool:
    global _ENABLED, _MARKER, _FAULT_FILE
    _ENABLED = bool(enabled)
    marker = _folder() / "session.json"
    previous_unclean = False
    if marker.is_file():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
            previous_unclean = not _pid_alive(int(previous.get("pid", 0)))
        except (OSError, ValueError, TypeError):
            previous_unclean = True
    _MARKER = marker
    marker.write_text(json.dumps({
        "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
    }), encoding="utf-8")
    if _ENABLED:
        sys.excepthook = _sys_hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = _thread_hook
        try:
            _FAULT_FILE = (_folder() / "native-fault.log").open("a", encoding="utf-8")
            faulthandler.enable(_FAULT_FILE, all_threads=True)
        except (OSError, RuntimeError):
            _FAULT_FILE = None
        if previous_unclean:
            capture_event(
                "unclean_shutdown",
                "اجرای قبلی بدون ثبت خروج عادی پایان یافته است.",
                "UnexpectedShutdown",
            )
    return previous_unclean


def set_enabled(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = bool(enabled)
    add_breadcrumb("privacy", "local blackbox preference changed", enabled=enabled)


def heartbeat() -> None:
    global _last_heartbeat, _hang_recorded
    _last_heartbeat = time.monotonic()
    _hang_recorded = False


def start_watchdog(timeout_s: float = 10.0) -> None:
    def monitor():
        global _hang_recorded
        while _MARKER is not None:
            time.sleep(2.0)
            if _ENABLED and not _hang_recorded and time.monotonic() - _last_heartbeat > timeout_s:
                _hang_recorded = True
                capture_event("ui_hang", "رابط کاربری برای بیش از ده ثانیه پاسخ نداده است.", "UiHang")
    threading.Thread(target=monitor, name="LAGSHIFT-BlackBox", daemon=True).start()


def pending_count() -> int:
    return len(list(_queue_folder().glob("*.lsc")))


def preview_pending() -> dict:
    """Return the exact sanitized payload that manual export would write."""
    reports = []
    for item in sorted(_queue_folder().glob("*.lsc")):
        try:
            reports.append(json.loads(secure_storage.unprotect(item.read_text(encoding="ascii"))))
        except (OSError, ValueError, TypeError):
            continue
    return {
        "schema": SCHEMA_VERSION, "automatic_upload": False,
        "report_count": len(reports), "reports": reports,
    }


def export_pending() -> Path:
    payload = preview_pending()
    target_dir = app_paths.local_dir() / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{APP_NAME}-blackbox-{datetime.now():%Y%m%d-%H%M%S}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def clear_pending() -> int:
    removed = 0
    for item in _queue_folder().glob("*.lsc"):
        try:
            item.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def mark_clean_shutdown() -> None:
    global _MARKER, _FAULT_FILE
    marker, _MARKER = _MARKER, None
    if marker:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
    if _FAULT_FILE:
        try:
            faulthandler.disable()
            _FAULT_FILE.close()
        except (OSError, RuntimeError):
            pass
        _FAULT_FILE = None
