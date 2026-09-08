"""Locale-independent Windows network adapter discovery."""
from __future__ import annotations

import json
import socket
import subprocess
from typing import List

from app.models.network_adapter import NetworkAdapter


def _flags() -> int:
    return subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def list_adapters() -> List[NetworkAdapter]:
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
        creationflags=_flags(),
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
