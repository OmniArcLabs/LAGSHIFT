"""Locale-independent Windows network adapter discovery."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from typing import List

from app.models.network_adapter import NetworkAdapter
from app.services.process_service import hidden_process_kwargs


def list_adapters() -> List[NetworkAdapter]:
    if sys.platform == "darwin":
        return _list_macos_services()
    script = r"""
$ErrorActionPreference='Stop'
$items=@(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object {
  $alias=$_.Name
  $dns=@((Get-DnsClientServerAddress -InterfaceAlias $alias -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses)
  [pscustomobject]@{name=$alias; description=$_.InterfaceDescription; enabled=$true; dns=$dns}
})
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20,
        **hidden_process_kwargs(),
    )
    if result.returncode != 0:
        return _fallback_adapters()
    raw = json.loads(result.stdout or "[]")
    if isinstance(raw, dict):
        raw = [raw]
    return [NetworkAdapter(
        name=item.get("name", ""),
        description=item.get("description", ""),
        is_enabled=bool(item.get("enabled", True)),
        current_dns=list(item.get("dns") or []),
    ) for item in raw if item.get("name")]


def _networksetup(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/sbin/networksetup", *arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=12,
    )


def _default_macos_interface() -> str:
    try:
        result = subprocess.run(
            ["/sbin/route", "-n", "get", "default"], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().casefold() == "interface":
                return value.strip()
    return ""


def _macos_service_devices() -> dict[str, str]:
    """Map network service names to BSD devices from stable service-order output."""
    listed = _networksetup("-listnetworkserviceorder")
    if listed.returncode != 0:
        return {}
    mapping: dict[str, str] = {}
    pending = ""
    for raw in listed.stdout.splitlines():
        line = raw.strip()
        if line.startswith("(") and ")" in line and "Device:" not in line:
            pending = line.split(")", 1)[1].strip()
            if pending.startswith("*"):
                pending = ""
        elif pending and "Device:" in line:
            device = line.split("Device:", 1)[1].split(")", 1)[0].strip()
            if device:
                mapping[pending] = device
            pending = ""
    return mapping


def _list_macos_services() -> List[NetworkAdapter]:
    """Return enabled macOS network services using stable networksetup output."""
    try:
        listed = _networksetup("-listallnetworkservices")
        if listed.returncode != 0:
            return []
        result: list[NetworkAdapter] = []
        default_interface = _default_macos_interface()
        service_devices = _macos_service_devices()
        for raw in listed.stdout.splitlines():
            service = raw.strip()
            if not service or service.startswith("An asterisk") or service.startswith("*"):
                continue
            info = _networksetup("-getinfo", service)
            if info.returncode != 0:
                continue
            text = info.stdout.casefold()
            is_default = bool(
                default_interface and service_devices.get(service) == default_interface
            )
            if not is_default and (
                "ip address: none" in text or "ip address: 0.0.0.0" in text
            ):
                continue
            dns = _networksetup("-getdnsservers", service)
            servers = [
                line.strip() for line in dns.stdout.splitlines()
                if line.strip() and "aren't any dns servers" not in line.casefold()
            ] if dns.returncode == 0 else []
            result.append(NetworkAdapter(
                name=service, description="سرویس شبکه macOS",
                is_enabled=True, current_dns=servers,
            ))
        # Put the actual default route first so DNS applies to the connection
        # carrying the user's traffic even when multiple services are active.
        result.sort(
            key=lambda item: service_devices.get(item.name) != default_interface
        )
        return result
    except (OSError, subprocess.SubprocessError):
        return []


def _fallback_adapters() -> List[NetworkAdapter]:
    """Non-admin fallback; psutil is locale independent but cannot expose DNS origin."""
    try:
        import psutil
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
    except Exception as exc:
        raise RuntimeError("خواندن آداپتورهای شبکه ممکن نشد") from exc
    result = []
    for name, entries in addresses.items():
        state = stats.get(name)
        if not state or not state.isup:
            continue
        has_ip = any(entry.family in {socket.AF_INET, socket.AF_INET6} for entry in entries)
        if not has_ip or name.lower().startswith(("loopback", "gamedns")):
            continue
        result.append(NetworkAdapter(name=name, description="آداپتور فعال", is_enabled=True))
    return result


def get_dns_for_adapter(adapter_name: str) -> List[str]:
    for adapter in list_adapters():
        if adapter.name == adapter_name:
            return adapter.current_dns
    return []
