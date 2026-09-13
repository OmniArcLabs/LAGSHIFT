"""Bounded macOS DNS changes with an exact, encrypted rollback record."""
from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
from pathlib import Path

from app.services import app_paths, recovery_service, secure_storage


_last_error = ""


def _set_error(value: str) -> None:
    global _last_error
    _last_error = str(value).strip()[:500]


def get_last_error() -> str:
    return _last_error


def _backup_path() -> Path:
    return app_paths.migrated_file("dns_backup_macos.secure", local=True)


def _validate_service(service: str) -> str:
    value = str(service).strip()
    if not value or len(value) > 200 or any(ord(ch) < 32 for ch in value):
        raise ValueError("نام سرویس شبکه macOS معتبر نیست")
    return value


def _networksetup(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/sbin/networksetup", *arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15,
    )


def _run_admin(arguments: list[str]) -> subprocess.CompletedProcess:
    command = shlex.join(["/usr/sbin/networksetup", *arguments])
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return subprocess.run(
        ["/usr/bin/osascript", "-e",
         f'do shell script "{escaped}" with administrator privileges'],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
    )


def _read_state(service: str) -> dict:
    service = _validate_service(service)
    result = _networksetup("-getdnsservers", service)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "خواندن DNS در macOS ممکن نشد")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    automatic = any("aren't any dns servers" in line.casefold() for line in lines)
    return {"service": service, "mode": "automatic" if automatic else "static",
            "servers": [] if automatic else lines[:4]}


def _write_backup(state: dict) -> None:
    protected = secure_storage.protect(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    path = _backup_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(protected, encoding="ascii")
    os.replace(temporary, path)


def _read_backup() -> dict:
    path = _backup_path()
    value = json.loads(secure_storage.unprotect(path.read_text(encoding="ascii")))
    if not isinstance(value, dict):
        raise ValueError("نسخه پشتیبان DNS مک معتبر نیست")
    return value


def set_dns(service: str, primary: str, secondary: str | None = None) -> bool:
    _set_error("")
    created_backup = False
    try:
        service = _validate_service(service)
        servers = [primary] + ([secondary] if secondary else [])
        for server in servers:
            socket.inet_pton(socket.AF_INET, server)
        if _backup_path().exists():
            existing = _read_backup()
            if _validate_service(existing.get("service", "")) != service:
                raise ValueError(
                    "ابتدا DNS سرویس قبلی را قطع و بازیابی کن؛ تغییر هم‌زمان دو سرویس مجاز نیست"
                )
        else:
            _write_backup(_read_state(service))
            created_backup = True
        result = _run_admin(["-setdnsservers", service, *servers])
        if result.returncode != 0:
            if created_backup:
                _backup_path().unlink(missing_ok=True)
            _set_error(result.stderr or "macOS تغییر DNS را نپذیرفت")
            return False
        recovery_service.safe_record("dns-set", "success")
        return True
    except Exception as exc:
        _set_error(str(exc) or "تغییر DNS در macOS ممکن نشد")
        recovery_service.safe_record("dns-set", "failed")
        return False


def restore_original_dns(service: str | None = None) -> bool:
    _set_error("")
    path = _backup_path()
    if not path.exists():
        return True
    try:
        state = _read_backup()
        target = _validate_service(state.get("service") or service or "")
        if service and _validate_service(service) != target:
            raise ValueError("نسخه پشتیبان به سرویس شبکه دیگری تعلق دارد")
        arguments = ["-setdnsservers", target]
        arguments.extend(state.get("servers") or ["Empty"])
        result = _run_admin(arguments)
        if result.returncode != 0:
            _set_error(result.stderr or "بازگردانی DNS در macOS کامل نشد")
            recovery_service.safe_record("dns-restore", "failed")
            return False
        path.unlink(missing_ok=True)
        recovery_service.safe_record("dns-restore", "success")
        return True
    except Exception as exc:
        _set_error(str(exc) or "بازگردانی DNS در macOS ممکن نشد")
        recovery_service.safe_record("dns-restore", "failed")
        return False


def has_pending_restore() -> bool:
    return _backup_path().exists()
