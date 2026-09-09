"""Safe bridge to the signed, official Cloudflare WARP client on Windows."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
DOWNLOAD_URL = "https://one.one.one.one/"
_WINDOWS_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Cloudflare" / "Cloudflare WARP" / "warp-cli.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Cloudflare" / "Cloudflare WARP" / "warp-cli.exe",
)
MODE_LABELS = {
    "doh": "فقط DNS امن (HTTPS)",
    "dot": "فقط DNS امن (TLS)",
    "warp": "ترافیک و DNS (UDP)",
    "warp+doh": "ترافیک و DNS (HTTPS)",
    "warp+dot": "ترافیک و DNS (TLS)",
    "tunnel_only": "فقط ترافیک",
}
_SETTING_MODE_MAP = {
    "warp": "warp", "doh": "doh", "warp+doh": "warp+doh", "dot": "dot",
    "warp+dot": "warp+dot", "tunnel only": "tunnel_only", "tunnel_only": "tunnel_only",
    "dnsoverhttps": "doh", "dnsovertls": "dot",
    "warpwithdnsoverhttps": "warp+doh", "warpwithdnsovertls": "warp+dot",
    "tunnelonly": "tunnel_only", "proxy": "proxy",
}


@dataclass
class OfficialWarpStatus:
    installed: bool = False
    cli_path: Path | None = None
    service_running: bool = False
    trace_active: bool = False
    connected: bool = False
    signature_valid: bool = False
    cli_status: str = ""
    mode: str = ""
    protocol: str = ""
    detail: str = ""


def find_cli() -> Path | None:
    for candidate in _WINDOWS_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("warp-cli") or shutil.which("warp-cli.exe")
    return Path(found) if found else None


def _run_cli(cli_path: Path, arguments: list[str], timeout_s: float = 16.0):
    return subprocess.run(
        [str(cli_path), "--no-ansi", "--no-paginate", *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _service_is_running() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["sc.exe", "query", "CloudflareWARP"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and b"RUNNING" in result.stdout.upper()
    except (OSError, subprocess.SubprocessError):
        return False


def _signature_is_cloudflare(cli_path: Path) -> bool:
    if os.name != "nt":
        return False
    escaped = str(cli_path).replace("'", "''")
    security_module = str(
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" /
        "WindowsPowerShell" / "v1.0" / "Modules" /
        "Microsoft.PowerShell.Security" / "Microsoft.PowerShell.Security.psd1"
    ).replace("'", "''")
    script = (
        f"Import-Module '{security_module}' -ErrorAction Stop;"
        f"$s=Get-AuthenticodeSignature -LiteralPath '{escaped}';"
        "if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Cloudflare'){exit 0};exit 7"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _cli_output(cli_path: Path, arguments: list[str]) -> str:
    try:
        result = _run_cli(cli_path, arguments)
    except (OSError, subprocess.SubprocessError):
        return ""
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def _setting_value(settings: str, key: str) -> str:
    wanted = key.casefold()
    for raw_line in settings.splitlines():
        line = raw_line.strip()
        if ":" in line:
            name, value = line.split(":", 1)
            if name.strip().casefold().endswith(wanted):
                return value.strip()
    return ""


def _normalize_mode(value: str) -> str:
    key = " ".join(value.strip().casefold().replace("_", " ").split())
    return _SETTING_MODE_MAP.get(key, value.strip().casefold().replace(" ", "_"))


def _is_cli_connected(status_text: str) -> bool:
    lowered = status_text.casefold()
    return "status update: connected" in lowered or "status: connected" in lowered


def trace_says_warp_on(timeout_s: float = 4.0) -> bool:
    try:
        request = urllib.request.Request(TRACE_URL, headers={"User-Agent": "LAGSHIFT/1"})
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            text = response.read(8192).decode("utf-8", errors="replace")
        return any(line.strip().casefold() == "warp=on" for line in text.splitlines())
    except (OSError, ValueError):
        return False


def inspect() -> OfficialWarpStatus:
    cli_path = find_cli()
    if cli_path is None:
        return OfficialWarpStatus(detail="کلاینت رسمی Cloudflare نصب نیست.")
    signature_valid = _signature_is_cloudflare(cli_path)
    if not signature_valid:
        return OfficialWarpStatus(
            installed=True, cli_path=cli_path, service_running=_service_is_running(),
            signature_valid=False, detail="امضای فایل رسمی Cloudflare تأیید نشد.",
        )
    status_text = _cli_output(cli_path, ["status"])
    settings = _cli_output(cli_path, ["settings"])
    connected = _is_cli_connected(status_text)
    mode = _normalize_mode(_setting_value(settings, "Mode"))
    protocol = _setting_value(settings, "WARP tunnel protocol")
    trace_active = trace_says_warp_on() if connected and mode not in {"doh", "dot"} else False
    if connected and mode in {"doh", "dot"}:
        detail = f"{MODE_LABELS.get(mode, mode)} فعال است."
    elif trace_active:
        detail = "مسیر رسمی Cloudflare فعال و از بیرون تأیید شد."
    elif connected:
        detail = "کلاینت متصل است، اما مسیر عمومی WARP هنوز تأیید نشده است."
    else:
        detail = "کلاینت رسمی آماده آزمایش است."
    return OfficialWarpStatus(
        installed=True, cli_path=cli_path, service_running=_service_is_running(),
        trace_active=trace_active, connected=connected, signature_valid=True,
        cli_status=status_text, mode=mode, protocol=protocol, detail=detail,
    )


def _dns_works() -> bool:
    try:
        return bool(socket.getaddrinfo("cloudflare.com", 443, type=socket.SOCK_STREAM))
    except OSError:
        return False


def _restore_preferences(cli_path: Path, mode: str, protocol: str) -> None:
    if mode in MODE_LABELS or mode == "proxy":
        _run_cli(cli_path, ["mode", mode])
    if protocol.casefold() in {"masque", "wireguard"}:
        _run_cli(cli_path, ["tunnel", "protocol", "set", protocol])


def connect_best(
    modes: Iterable[str] = ("warp+doh", "warp+dot", "warp"),
    protocols: Iterable[str] = ("MASQUE", "WireGuard"),
    progress: Callable[[str], None] | None = None,
    max_attempts: int = 6,
    total_budget_s: float = 55.0,
    verify_attempts: int = 4,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    from app.services import recovery_service

    progress = progress or (lambda _message: None)
    cancelled = cancelled or (lambda: False)
    before = inspect()
    base = {
        "installed": before.installed,
        "signature_valid": before.signature_valid,
        "service_running": before.service_running,
    }
    if not before.installed or before.cli_path is None:
        recovery_service.safe_record("warp-connect", "failed", "client unavailable")
        return {**base, "ok": False, "active": False,
                "error": "ابتدا کلاینت رسمی Cloudflare را نصب کن."}
    if not before.signature_valid:
        recovery_service.safe_record("warp-connect", "failed", "signature invalid")
        return {**base, "ok": False, "active": False,
                "error": "امضای کلاینت Cloudflare معتبر نیست؛ اجرا متوقف شد."}
    if before.connected:
        return {
            **base, "ok": True, "active": True, "started_by_app": False,
            "mode": before.mode, "protocol": before.protocol,
            "message": "اتصال رسمی از قبل فعال بود و دست‌نخورده باقی ماند.",
        }

    cli_path = before.cli_path
    original_mode, original_protocol = before.mode, before.protocol
    failures: list[str] = []
    last_status = ""
    started_at = time.monotonic()
    attempts_used = 0
    cancel_requested = False
    valid_modes = tuple(dict.fromkeys(mode for mode in modes if mode in MODE_LABELS))
    valid_protocols = tuple(dict.fromkeys(
        protocol for protocol in protocols
        if protocol.casefold() in {"masque", "wireguard"}
    )) or ("MASQUE", "WireGuard")
    try:
        for mode in valid_modes:
            transports = ("",) if mode in {"doh", "dot"} else valid_protocols
            for protocol in transports:
                if cancelled():
                    cancel_requested = True
                    break
                if attempts_used >= max(1, int(max_attempts)):
                    failures.append("attempt-budget-exhausted")
                    break
                if time.monotonic() - started_at >= max(8.0, float(total_budget_s)):
                    failures.append("time-budget-exhausted")
                    break
                attempts_used += 1
                label = MODE_LABELS[mode]
                suffix = f" با {protocol}…" if protocol else "…"
                progress(f"در حال آزمایش «{label}»{suffix}")
                _run_cli(cli_path, ["disconnect"])
                mode_result = _run_cli(cli_path, ["mode", mode])
                if mode_result.returncode != 0:
                    failures.append(f"{mode}: mode={mode_result.returncode}")
                    continue
                if protocol:
                    protocol_result = _run_cli(
                        cli_path, ["tunnel", "protocol", "set", protocol]
                    )
                    if protocol_result.returncode != 0:
                        failures.append(f"{mode}/{protocol}: protocol={protocol_result.returncode}")
                        continue
                connect_result = _run_cli(cli_path, ["connect"])
                if connect_result.returncode != 0:
                    failures.append(f"{mode}/{protocol or 'dns'}: connect={connect_result.returncode}")
                    continue
                for _attempt in range(max(1, int(verify_attempts))):
                    if cancelled():
                        cancel_requested = True
                        break
                    time.sleep(1.0)
                    cli_status = _cli_output(cli_path, ["status"])
                    last_status = cli_status
                    connected = _is_cli_connected(cli_status)
                    verification = _dns_works() if mode in {"doh", "dot"} else trace_says_warp_on()
                    if connected and verification:
                        recovery_service.set_warp_intent(
                            original_mode, original_protocol, mode
                        )
                        recovery_service.safe_record("warp-connect", "success", mode)
                        return {
                            **base, "ok": True, "active": True,
                            "trace_active": mode not in {"doh", "dot"},
                            "started_by_app": True, "mode": mode, "mode_label": label,
                            "protocol": protocol or "DNS", "original_mode": original_mode,
                            "original_protocol": original_protocol,
                            "message": f"{label} با موفقیت فعال و تأیید شد.",
                        }
                status_reason = " | ".join(line.strip() for line in last_status.splitlines()[:3])
                failures.append(
                    f"{mode}/{protocol or 'dns'}: " + (status_reason or "verification-timeout")
                )
                if cancel_requested:
                    break
            if cancel_requested or attempts_used >= max(1, int(max_attempts)) or (
                time.monotonic() - started_at >= max(8.0, float(total_budget_s))
            ):
                break
    except (OSError, subprocess.SubprocessError) as exc:
        failures.append(type(exc).__name__)

    try:
        _run_cli(cli_path, ["disconnect"])
        _restore_preferences(cli_path, original_mode, original_protocol)
    except (OSError, subprocess.SubprocessError):
        failures.append("restore-failed")
    lowered_status = last_status.casefold()
    if cancel_requested:
        friendly_error = "آزمایش WARP لغو شد و تنظیم قبلی Cloudflare بازگردانده شد."
    elif "dns lookup failed" in lowered_status:
        friendly_error = (
            "خود کلاینت Cloudflare در این اینترنت نتوانست آدرس سرورش را پیدا کند؛ "
            "اتصال قبلی برگشت. یک اینترنت یا دی‌ان‌اس دیگر را امتحان کن."
        )
    elif "happy eyeballs" in lowered_status or "route to the dns endpoint" in lowered_status:
        friendly_error = (
            "نصب Cloudflare سالم است، اما این اینترنت به درگاه WARP مسیر نداد. "
            "هیچ اتصالی روشن نماند و تنظیم قبلی برگردانده شد؛ با یک اپراتور دیگر دوباره آزمایش کن."
        )
    else:
        friendly_error = (
            "کلاینت رسمی با حالت‌های انتخاب‌شده متصل نشد؛ اینترنت به وضعیت قبل برگشت."
        )
    recovery_service.safe_record("warp-connect", "failed", "verification failed")
    return {
        **base, "ok": False, "active": False,
        "error": friendly_error,
        "cancelled": cancel_requested,
        "attempts": attempts_used,
        "technical": "; ".join(failures)[:1500],
    }


def disconnect_if_started(
    started_by_app: bool,
    original_mode: str = "",
    original_protocol: str = "",
) -> dict:
    from app.services import recovery_service

    status = inspect()
    base = {
        "installed": status.installed,
        "signature_valid": status.signature_valid,
        "service_running": status.service_running,
    }
    if not started_by_app:
        return {
            **base, "ok": True, "active": status.connected,
            "started_by_app": False, "mode": status.mode, "protocol": status.protocol,
            "message": "اتصال خارج از LAGSHIFT ساخته شده و دست‌نخورده ماند.",
        }
    if status.cli_path is None or not status.signature_valid:
        recovery_service.safe_record("warp-restore", "failed", "client unavailable")
        return {**base, "ok": False, "active": status.connected,
                "error": "کلاینت رسمی معتبر در دسترس نیست."}
    try:
        result = _run_cli(status.cli_path, ["disconnect"])
        if result.returncode != 0:
            recovery_service.safe_record("warp-restore", "failed")
            return {**base, "ok": False, "active": True,
                    "error": "قطع اتصال رسمی کامل نشد."}
        _restore_preferences(status.cli_path, original_mode, original_protocol)
        recovery_service.clear_warp_intent()
        recovery_service.safe_record("warp-restore", "success")
        return {
            **base, "ok": True, "active": False, "started_by_app": False,
            "message": "اتصال قطع شد و تنظیم قبلی Cloudflare بازگردانده شد.",
        }
    except (OSError, subprocess.SubprocessError):
        recovery_service.safe_record("warp-restore", "failed")
        return {**base, "ok": False, "active": True,
                "error": "قطع اتصال رسمی کامل نشد."}
