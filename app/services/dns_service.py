"""Safe Windows DNS changes with crash recovery and exact restoration."""
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Optional

from app.services import app_paths, secure_storage, recovery_service


_last_error = ""


def _set_last_error(message: str) -> None:
    global _last_error
    _last_error = message.strip()


def get_last_error() -> str:
    return _last_error


def _process_error(result: subprocess.CompletedProcess, fallback: str) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    if detail:
        return detail.splitlines()[-1][-400:]
    return fallback


def _state_file() -> Path:
    return app_paths.migrated_file("dns_backup.dpapi", local=True)


def _legacy_state_file() -> Path:
    return app_paths.migrated_file("dns_backup.json", local=True)


def _read_backup() -> dict:
    path = _state_file()
    if path.is_file():
        payload = secure_storage.unprotect(path.read_text(encoding="ascii"))
        value = json.loads(payload.decode("utf-8"))
        if isinstance(value, dict):
            return value
        raise ValueError("نسخه پشتیبان DNS معتبر نیست")
    legacy = _legacy_state_file()
    if legacy.is_file():
        value = json.loads(legacy.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("نسخه پشتیبان قدیمی DNS معتبر نیست")
        _write_backup(value)
        legacy.unlink(missing_ok=True)
        return value
    raise FileNotFoundError("نسخه پشتیبان DNS وجود ندارد")


def _write_backup(state: dict) -> None:
    path = _state_file()
    protected = secure_storage.protect(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_text(protected, encoding="ascii")
    os.replace(temporary, path)


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def _powershell(script: str, adapter_name: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["GAMEDNS_ADAPTER"] = adapter_name
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def _read_current_state(adapter_name: str) -> dict:
    script = r"""
$ErrorActionPreference='Stop'
$alias=$env:GAMEDNS_ADAPTER
$adapter=Get-NetAdapter -Name $alias
$guid=[string]$adapter.InterfaceGuid
if(-not $guid.StartsWith('{')){$guid="{$guid}"}
$key="HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$guid"
$configured=(Get-ItemProperty -LiteralPath $key -Name NameServer -ErrorAction SilentlyContinue).NameServer
$servers=@((Get-DnsClientServerAddress -InterfaceAlias $alias -AddressFamily IPv4).ServerAddresses)
[pscustomobject]@{adapter=$alias; mode=$(if([string]::IsNullOrWhiteSpace($configured)){'automatic'}else{'static'}); servers=$servers} | ConvertTo-Json -Compress
"""
    result = _powershell(script, adapter_name)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "خواندن تنظیم DNS ممکن نشد")
    return json.loads(result.stdout)


def _save_backup_once(adapter_name: str) -> None:
    path = _state_file()
    if path.exists() or _legacy_state_file().exists():
        try:
            existing = _read_backup()
            if existing.get("adapter") == adapter_name:
                return
        except Exception:
            pass
    state = _read_current_state(adapter_name)
    _write_backup(state)


def set_dns(adapter_name: str, primary: str, secondary: Optional[str] = None,
            doh_url: str = "") -> bool:
    if os.name == "nt":
        from app.services import privileged_helper
        if not privileged_helper.is_admin():
            servers = [primary] + ([secondary] if secondary else [])
            ok, error = privileged_helper.request(
                "set_dns", adapter_name, servers=servers, doh_url=doh_url
            )
            _set_last_error(error)
            return ok
    return _set_dns_direct(adapter_name, primary, secondary, doh_url)


def _set_dns_direct(adapter_name: str, primary: str, secondary: Optional[str] = None,
                    doh_url: str = "") -> bool:
    _set_last_error("")
    servers = [primary] + ([secondary] if secondary else [])
    try:
        for item in servers:
            socket.inet_pton(socket.AF_INET, item)
        _save_backup_once(adapter_name)
        environment = os.environ.copy()
        environment["GAMEDNS_ADAPTER"] = adapter_name
        environment["GAMEDNS_SERVERS"] = ",".join(servers)
        script = (
            "$ErrorActionPreference='Stop'; $s=$env:GAMEDNS_SERVERS.Split(','); "
            "Set-DnsClientServerAddress -InterfaceAlias $env:GAMEDNS_ADAPTER -ServerAddresses $s"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode != 0:
            _set_last_error(_process_error(result, "ویندوز تغییر DNS را نپذیرفت"))
            recovery_service.safe_record("dns-change", "failed")
            return False
        if doh_url:
            enable_doh(primary, doh_url)
        _run(["ipconfig", "/flushdns"])
        recovery_service.safe_record("dns-change", "success")
        return True
    except Exception as exc:
        _set_last_error(str(exc) or "خطای ناشناخته هنگام تغییر DNS")
        recovery_service.safe_record("dns-change", "failed")
        return False


def restore_original_dns(adapter_name: str | None = None) -> bool:
    if os.name == "nt":
        from app.services import privileged_helper
        if not privileged_helper.is_admin():
            if not has_pending_restore():
                return True
            target = adapter_name
            if not target:
                try:
                    target = _read_backup().get("adapter")
                except Exception:
                    target = ""
            ok, error = privileged_helper.request("restore_dns", target or "")
            _set_last_error(error)
            return ok
    return _restore_original_dns_direct(adapter_name)


def _restore_original_dns_direct(adapter_name: str | None = None) -> bool:
    _set_last_error("")
    path = _state_file()
    if not has_pending_restore():
        return True
    try:
        state = _read_backup()
        target = state.get("adapter") or adapter_name
        if adapter_name and target != adapter_name:
            _set_last_error("نسخه پشتیبان DNS مربوط به یک کارت شبکه دیگر است")
            return False
        environment = os.environ.copy()
        environment["GAMEDNS_ADAPTER"] = target
        if state.get("mode") == "static" and state.get("servers"):
            environment["GAMEDNS_SERVERS"] = ",".join(state["servers"])
            script = (
                "$ErrorActionPreference='Stop'; $s=$env:GAMEDNS_SERVERS.Split(','); "
                "Set-DnsClientServerAddress -InterfaceAlias $env:GAMEDNS_ADAPTER -ServerAddresses $s"
            )
        else:
            script = (
                "$ErrorActionPreference='Stop'; "
                "Set-DnsClientServerAddress -InterfaceAlias $env:GAMEDNS_ADAPTER -ResetServerAddresses"
            )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode == 0:
            _run(["ipconfig", "/flushdns"])
            path.unlink(missing_ok=True)
            _legacy_state_file().unlink(missing_ok=True)
            recovery_service.safe_record("dns-restore", "success")
            return True
        _set_last_error(_process_error(result, "ویندوز بازگردانی DNS را نپذیرفت"))
        recovery_service.safe_record("dns-restore", "failed")
        return False
    except Exception as exc:
        _set_last_error(str(exc) or "خطای ناشناخته هنگام بازگردانی DNS")
        recovery_service.safe_record("dns-restore", "failed")
        return False


def reset_dns_to_dhcp(adapter_name: str) -> bool:
    """Backward-compatible name; restores the exact original mode and servers."""
    return restore_original_dns(adapter_name)


def has_pending_restore() -> bool:
    return _state_file().exists() or _legacy_state_file().exists()


def enable_doh(server_ip: str, doh_template: str) -> bool:
    result = _run([
        "netsh", "dns", "add", "encryption", f"server={server_ip}",
        f"dohtemplate={doh_template}", "autoupgrade=yes", "udpfallback=no",
    ])
    return result.returncode == 0


def verify_doh_no_downgrade(server_ip: str, expected_template: str = "") -> dict:
    """Read Windows' installed DoH policy and require UDP fallback to be disabled."""
    try:
        socket.inet_pton(socket.AF_INET, server_ip)
    except OSError:
        return {"configured": False, "no_downgrade": False,
                "message": "نشانی DNS معتبر نیست"}
    result = _run(["netsh", "dns", "show", "encryption", f"server={server_ip}"])
    text = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode != 0:
        return {"configured": False, "no_downgrade": False,
                "message": "ویندوز سیاست DoH را گزارش نکرد"}
    template_ok = not expected_template or expected_template.lower() in text
    # netsh output is localized on some Windows builds, so accept the stable
    # command tokens and fail inconclusively instead of claiming protection.
    no_fallback = any(token in text for token in (
        "udp fallback: no", "fallback to udp: no", "udpfallback=no"
    ))
    configured = template_ok and ("https://" in text or bool(expected_template))
    return {
        "configured": configured,
        "no_downgrade": configured and no_fallback,
        "message": (
            "DoH بدون بازگشت UDP در ویندوز ثبت شده است"
            if configured and no_fallback else
            "ثبت DoH پیدا شد اما غیرفعال‌بودن بازگشت UDP تأیید نشد"
            if configured else "قانون DoH مورد انتظار در ویندوز پیدا نشد"
        ),
    }


def apply_dns_with_fallback(adapter_name: str, profiles: list) -> tuple:
    for profile in profiles:
        if set_dns(adapter_name, profile.primary, profile.secondary or None, profile.doh_url):
            return True, profile
    return False, None
