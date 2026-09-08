"""Session-only Windows QoS marking with explicit rollback."""
from __future__ import annotations

import hashlib
import re
import subprocess

from app.app_info import APP_NAME
from app.services import recovery_service


def _safe_process_name(process_name: str) -> str:
    value = process_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_. -]{1,180}\.exe", value, re.IGNORECASE):
        raise ValueError("نام پروسه برای QoS معتبر نیست")
    return value


def policy_name(process_name: str) -> str:
    digest = hashlib.sha256(process_name.lower().encode("utf-8")).hexdigest()[:10]
    return f"{APP_NAME}-{digest}"


def _powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=8,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def apply(process_name: str, dscp: int = 46) -> tuple[bool, str]:
    process = _safe_process_name(process_name)
    name = policy_name(process)
    dscp = max(0, min(63, int(dscp)))
    script = (
        f"Remove-NetQosPolicy -Name '{name}' -PolicyStore ActiveStore -Confirm:$false "
        f"-ErrorAction SilentlyContinue; New-NetQosPolicy -Name '{name}' "
        f"-AppPathNameMatchCondition '{process}' -IPProtocolMatchCondition Both "
        f"-DSCPAction {dscp} -NetworkProfile All -PolicyStore ActiveStore -ErrorAction Stop | Out-Null"
    )
    try:
        result = _powershell(script)
    except (OSError, subprocess.SubprocessError) as exc:
        recovery_service.safe_record("qos-change", "failed")
        return False, str(exc)
    recovery_service.safe_record(
        "qos-change", "success" if result.returncode == 0 else "failed"
    )
    return (True, f"QoS موقت DSCP {dscp} فقط برای {process} فعال شد") if result.returncode == 0 else (
        False, (result.stderr or "Windows QoS در این نسخه/سطح دسترسی فعال نشد").strip()
    )


def remove(process_name: str) -> bool:
    try:
        name = policy_name(_safe_process_name(process_name))
        result = _powershell(
            f"Remove-NetQosPolicy -Name '{name}' -PolicyStore ActiveStore "
            "-Confirm:$false -ErrorAction SilentlyContinue"
        )
        ok = result.returncode == 0
        recovery_service.safe_record("qos-restore", "success" if ok else "failed")
        return ok
    except (ValueError, OSError, subprocess.SubprocessError):
        recovery_service.safe_record("qos-restore", "failed")
        return False


def remove_all() -> bool:
    """Remove only session policies owned by LAGSHIFT."""
    script = (
        f"Get-NetQosPolicy -PolicyStore ActiveStore -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Name -like '{APP_NAME}-*' }} | "
        "Remove-NetQosPolicy -PolicyStore ActiveStore -Confirm:$false -ErrorAction Stop"
    )
    try:
        ok = _powershell(script).returncode == 0
        recovery_service.safe_record("qos-restore", "success" if ok else "failed")
        return ok
    except (OSError, subprocess.SubprocessError):
        recovery_service.safe_record("qos-restore", "failed")
        return False
