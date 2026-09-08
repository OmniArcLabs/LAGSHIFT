"""تشخیص محلی و سنجش واقعی مقصدهای برنامه‌ها؛ بدون ادعای VPN یا رله."""
from __future__ import annotations

import os
import ipaddress
import re
import socket
import ssl
import subprocess
import time
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from app.models.app_access import AppAccessProfile
from app.services import app_profile_catalog_service


def available_profiles() -> tuple[AppAccessProfile, ...]:
    return app_profile_catalog_service.load_profiles()


def get_profile(profile_id: str) -> AppAccessProfile | None:
    key = str(profile_id or "").strip().lower()
    return next((item for item in available_profiles() if item.id == key), None)


def running_process_records() -> list[dict]:
    try:
        import psutil
        rows = []
        for process in psutil.process_iter(["name", "exe"]):
            name = str(process.info.get("name") or "").strip().lower()
            if name:
                rows.append({"name": name, "path": str(process.info.get("exe") or "").strip()})
        return rows
    except Exception:
        return []


def running_process_names() -> set[str]:
    return {row["name"] for row in running_process_records()}


def installed_app_records() -> list[dict]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    records: list[dict] = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    paths = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for root in roots:
        for path in paths:
            try:
                with winreg.OpenKey(root, path) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as item:
                                value, _ = winreg.QueryValueEx(item, "DisplayName")
                                if not value:
                                    continue
                                try:
                                    icon, _ = winreg.QueryValueEx(item, "DisplayIcon")
                                except OSError:
                                    icon = ""
                                try:
                                    location, _ = winreg.QueryValueEx(item, "InstallLocation")
                                except OSError:
                                    location = ""
                                icon_path = _clean_icon_path(icon)
                                records.append({
                                    "name": str(value).strip().lower(),
                                    "icon_path": icon_path,
                                    "install_location": os.path.expandvars(str(location or "").strip()),
                                })
                        except OSError:
                            continue
            except OSError:
                continue
    return records


def _clean_icon_path(raw_value) -> str:
    value = os.path.expandvars(str(raw_value or "").strip())
    if value.startswith('"') and '"' in value[1:]:
        value = value[1:value.find('"', 1)]
    else:
        value = re.sub(r",\s*-?\d+\s*$", "", value).strip().strip('"')
    return value


def _profile_executable(profile: AppAccessProfile, record: dict | None) -> str:
    if not record:
        return ""
    icon_path = _clean_icon_path(record.get("icon_path", ""))
    if icon_path and os.path.isfile(icon_path):
        return icon_path
    location = Path(str(record.get("install_location") or ""))
    if not location.is_dir():
        return ""
    for executable in profile.process_names:
        for candidate in (location / executable, *location.glob(f"*/{executable}"),
                          *location.glob(f"*/*/{executable}")):
            if candidate.is_file():
                return str(candidate)
    return ""


def installed_display_names() -> set[str]:
    return {row["name"] for row in installed_app_records()}


def catalog_status(installed_names: set[str] | None = None,
                   process_names: set[str] | None = None,
                   installed_records: list[dict] | None = None) -> list[dict]:
    installed_records = (
        installed_app_records() if installed_records is None and installed_names is None
        else list(installed_records or [])
    )
    installed = installed_names if installed_names is not None else {
        row["name"] for row in installed_records
    }
    process_records = running_process_records() if process_names is None else [
        {"name": name.lower(), "path": ""} for name in process_names
    ]
    running = {row["name"] for row in process_records}
    result = []
    for profile in available_profiles():
        is_running = any(name.lower() in running for name in profile.process_names)
        is_installed = is_running or any(
            hint.lower() in display_name
            for hint in profile.registry_names for display_name in installed
        )
        executable_path = next((
            row["path"] for row in process_records
            if row["name"] in profile.process_names and row.get("path")
        ), "")
        if not executable_path:
            match = next((
                row for row in installed_records
                if any(hint.lower() in row["name"] for hint in profile.registry_names)
            ), None)
            if match:
                executable_path = _profile_executable(profile, match)
        row = asdict(profile)
        row.update({
            "installed": is_installed, "running": is_running,
            "executable_path": executable_path,
        })
        result.append(row)
    return result


def active_profile_ids(process_names: set[str] | None = None) -> set[str]:
    running = (
        {str(name).strip().lower() for name in process_names}
        if process_names is not None else running_process_names()
    )
    return {
        profile.id for profile in available_profiles()
        if any(name.lower() in running for name in profile.process_names)
    }


def profile_connection_evidence(profile: AppAccessProfile) -> dict:
    """Observe public sockets owned by the selected app without reading payloads."""
    try:
        import psutil
        wanted = {name.casefold() for name in profile.process_names}
        pids = set()
        for process in psutil.process_iter(["pid", "name"]):
            if str(process.info.get("name") or "").casefold() in wanted:
                pids.add(int(process.info["pid"]))
        endpoints = []
        for connection in psutil.net_connections(kind="inet"):
            if connection.pid not in pids or not connection.raddr:
                continue
            host = str(getattr(connection.raddr, "ip", connection.raddr[0]))
            port = int(getattr(connection.raddr, "port", connection.raddr[1]))
            try:
                address = ipaddress.ip_address(host.split("%", 1)[0])
                if not address.is_global:
                    continue
            except ValueError:
                continue
            transport = "tcp" if connection.type == socket.SOCK_STREAM else "udp"
            endpoints.append({"host": host, "port": port, "transport": transport})
        unique = list({(row["host"], row["port"], row["transport"]): row for row in endpoints}.values())
        return {
            "running": bool(pids), "processes": len(pids),
            "connections": len(unique), "endpoints": unique[:24],
            "has_session_evidence": bool(unique),
        }
    except Exception:
        return {"running": False, "processes": 0, "connections": 0,
                "endpoints": [], "has_session_evidence": False}


def launch_profile(profile_id: str) -> tuple[bool, str]:
    """Launch only a locally discovered executable or a bundled HTTPS URL."""
    profile = get_profile(profile_id)
    if profile is None:
        return False, "پروفایل برنامه معتبر نیست"
    row = next((item for item in catalog_status() if item.get("id") == profile.id), {})
    executable = Path(str(row.get("executable_path") or ""))
    if executable.is_file() and executable.suffix.casefold() == ".exe":
        try:
            subprocess.Popen(
                [str(executable)], cwd=str(executable.parent), close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True, f"{profile.name} اجرا شد"
        except OSError:
            return False, "اجرای برنامه ممکن نشد"
    if profile.launch_url.startswith("https://") and os.name == "nt":
        try:
            os.startfile(profile.launch_url)
            return True, f"{profile.name} در مرورگر باز شد"
        except OSError:
            return False, "بازکردن سرویس ممکن نشد"
    return False, "فایل اجرایی برنامه روی ویندوز پیدا نشد"


def probe_domains(domains: Iterable[str], timeout_s: float = 1.4) -> dict:
    """Resolve each destination and verify a real TCP plus TLS/SNI handshake."""
    targets = tuple(dict.fromkeys(
        str(item).strip().lower() for item in domains if item
    ))[:8]
    tls_context = ssl.create_default_context()

    def probe_one(domain: str) -> dict:
        resolved = False
        address = ""
        latency_ms = -1
        tcp_ok = False
        tls_ok = False
        error = ""
        try:
            addresses = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
            address = addresses[0][4][0] if addresses else ""
            resolved = bool(address)
        except OSError as exc:
            error = str(exc)[:160]
        if resolved:
            started = time.perf_counter()
            try:
                with socket.create_connection((domain, 443), timeout=timeout_s) as stream:
                    tcp_ok = True
                    with tls_context.wrap_socket(stream, server_hostname=domain):
                        tls_ok = True
                        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
            except OSError as exc:
                error = str(exc)[:160]
        return {
            "domain": domain, "resolved": resolved, "address": address,
            "tcp_ok": tcp_ok, "tls_ok": tls_ok,
            "latency_ms": latency_ms, "error": error,
        }

    with ThreadPoolExecutor(max_workers=min(8, len(targets)) or 1) as executor:
        rows = list(executor.map(probe_one, targets))
    reachable = [row for row in rows if row["tcp_ok"]]
    secured = [row for row in rows if row["tls_ok"]]
    resolved = [row for row in rows if row["resolved"]]
    resolved_addresses = [row["address"] for row in resolved if row.get("address")]
    unique_addresses = tuple(dict.fromkeys(resolved_addresses))
    private_sink = False
    if len(resolved_addresses) >= 2 and len(unique_addresses) == 1 and not reachable:
        try:
            private_sink = not ipaddress.ip_address(unique_addresses[0].split("%", 1)[0]).is_global
        except ValueError:
            private_sink = False
    latencies = sorted(row["latency_ms"] for row in secured)
    median = latencies[len(latencies) // 2] if latencies else -1
    return {
        "targets": rows,
        "attempted": len(rows),
        "resolved": len(resolved),
        "reachable": len(reachable),
        "tls_ok": len(secured),
        "median_ms": median,
        "unique_addresses": list(unique_addresses),
        # Several unrelated public hostnames resolving to one non-public address
        # with no TCP path is strong evidence of a dead DNS proxy/sinkhole.
        "suspected_sinkhole": private_sink,
        "healthy": bool(rows) and len(secured) >= max(1, (len(rows) + 1) // 2),
    }


def probe_profile(profile: AppAccessProfile, mission: str) -> dict:
    domains = profile.domains_for(mission)
    result = probe_domains(domains)
    result.update({"profile_id": profile.id, "app_name": profile.name,
                   "mission": mission, "domains": list(domains)})
    return result
