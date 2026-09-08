"""Honest local network diagnostics used by Route Lab and AIR Lite."""
from __future__ import annotations

import ipaddress
import re
import socket
import statistics
import subprocess
import time

import psutil

from app.services import connectivity_service, game_server_probe_service
from app.app_info import APP_NAME


def _summary(samples: list[int]) -> dict:
    valid = [value for value in samples if value >= 0]
    if not valid:
        return {"available": False, "median_ms": -1, "jitter_ms": -1,
                "loss": 100.0, "samples": samples}
    median = round(statistics.median(valid))
    jitter = round(statistics.median(abs(value - median) for value in valid))
    return {"available": True, "median_ms": median, "jitter_ms": jitter,
            "loss": round((len(samples) - len(valid)) * 100 / max(1, len(samples)), 1),
            "samples": samples}


def _udp_sample(host: str, port: int, timeout_s: float = 0.7) -> int:
    """A reply proves UDP reachability; silence is reported as unknown, never as packet loss."""
    family = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
    started = time.perf_counter()
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout_s)
            sock.sendto(f"{APP_NAME}-UDP-Probe".encode("ascii"), (host, port))
            sock.recvfrom(256)
        return int((time.perf_counter() - started) * 1000)
    except OSError:
        return -1


def ping_matrix(endpoint: dict, attempts: int = 3) -> dict:
    host, port = str(endpoint["host"]), int(endpoint["port"])
    ip_version = ipaddress.ip_address(host).version
    icmp = _summary([game_server_probe_service._icmp_sample(host) for _ in range(attempts)])
    tcp = _summary([
        connectivity_service.measure_latency_ms(host, port, timeout_s=1.0)
        for _ in range(attempts)
    ])
    udp = _summary([_udp_sample(host, port) for _ in range(attempts)])
    udp["conclusive"] = udp["available"]
    udp["note"] = (
        "پاسخ UDP واقعی دریافت شد" if udp["available"] else
        "بدون پاسخ؛ سرور بازی ممکن است پروب ناشناس را عمداً نادیده بگیرد"
    )
    return {"host": host, "port": port, "ip_version": ip_version,
            "observed_transport": endpoint.get("transport", "unknown"),
            "icmp": icmp, "tcp": tcp, "udp": udp}


def default_gateway() -> str:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True,
            timeout=3, creationflags=creation_flags,
        )
        matches = re.findall(
            r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+((?:\d{1,3}\.){3}\d{1,3})\s+",
            result.stdout, re.MULTILINE,
        )
        return matches[0] if matches else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def adapter_health() -> list[dict]:
    stats, addresses = psutil.net_if_stats(), psutil.net_if_addrs()
    rows = []
    for name, stat in stats.items():
        ips = [item.address for item in addresses.get(name, [])
               if item.family in (socket.AF_INET, socket.AF_INET6)]
        if stat.isup and ips:
            rows.append({"name": name, "up": True, "speed_mbps": int(stat.speed or 0),
                         "mtu": int(stat.mtu or 0), "addresses": ips[:3]})
    return rows


def wifi_link_info(adapter_name: str = "") -> dict:
    """Read the local WLAN radio state without storing SSID/BSSID values."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
            timeout=3, creationflags=creation_flags, errors="replace",
        )
        text = result.stdout or ""
        # Netsh labels can be localized, so numeric signal/rate patterns are
        # attempted first and unknown is preferable to an invented value.
        signal = re.search(r"(?:Signal|سیگنال)\s*:\s*(\d{1,3})\s*%", text, re.I)
        rx = re.search(r"(?:Receive rate|Rx rate)[^:]*:\s*([\d.]+)", text, re.I)
        tx = re.search(r"(?:Transmit rate|Tx rate)[^:]*:\s*([\d.]+)", text, re.I)
        quality = int(signal.group(1)) if signal else None
        return {
            "available": quality is not None,
            "signal_pct": max(0, min(100, quality)) if quality is not None else None,
            "rx_mbps": float(rx.group(1)) if rx else None,
            "tx_mbps": float(tx.group(1)) if tx else None,
            "weak": quality is not None and quality < 45,
            # Deliberately omit SSID, BSSID and profile name.
        }
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"available": False, "signal_pct": None, "rx_mbps": None,
                "tx_mbps": None, "weak": False}


def gateway_quality(attempts: int = 3) -> dict:
    gateway = default_gateway()
    if not gateway:
        return {"available": False, "median_ms": -1, "jitter_ms": -1,
                "loss": 100.0, "samples": []}
    return _summary([
        game_server_probe_service._icmp_sample(gateway)
        for _ in range(max(1, min(5, int(attempts))))
    ])


def _cgnat_from_hops(hops: list[str]) -> str:
    """Return a conservative hint; traceroute can suggest but never prove CGNAT."""
    for value in hops[1:4]:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version == 4 and address in ipaddress.ip_network("100.64.0.0/10"):
            return "probable"
    private_hops = 0
    for value in hops[:4]:
        try:
            if ipaddress.ip_address(value).is_private:
                private_hops += 1
        except ValueError:
            pass
    return "possible-double-nat" if private_hops >= 2 else "unknown"


def cgnat_hint() -> str:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["tracert", "-d", "-h", "4", "-w", "350", "1.1.1.1"],
            capture_output=True, text=True, timeout=4,
            creationflags=creation_flags, errors="replace",
        )
        hops = re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", result.stdout or "")
        return _cgnat_from_hops(hops)
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def traffic_pressure(sample_seconds: float = 0.5) -> dict:
    before = psutil.net_io_counters(pernic=True)
    time.sleep(max(0.1, sample_seconds))
    after = psutil.net_io_counters(pernic=True)
    stats = psutil.net_if_stats()
    rows = []
    for name, end in after.items():
        start, stat = before.get(name), stats.get(name)
        if not start or not stat or not stat.isup:
            continue
        down = max(0, end.bytes_recv - start.bytes_recv) * 8 / sample_seconds / 1_000_000
        up = max(0, end.bytes_sent - start.bytes_sent) * 8 / sample_seconds / 1_000_000
        capacity = float(stat.speed or 0)
        utilization = ((down + up) * 100 / capacity) if capacity > 0 else None
        rows.append({"name": name, "down_mbps": round(down, 2), "up_mbps": round(up, 2),
                     "utilization_pct": round(utilization, 1) if utilization is not None else None})
    active = max(rows, key=lambda item: item["down_mbps"] + item["up_mbps"], default=None)
    return {"active": active, "adapters": rows}


def route_breakdown(endpoint: dict, relay_host: str = "") -> dict:
    gateway = default_gateway()
    gateway_rtt = game_server_probe_service._icmp_sample(gateway) if gateway else -1
    direct = game_server_probe_service.benchmark_endpoint(endpoint, attempts=3)
    relay_rtt = game_server_probe_service._icmp_sample(relay_host) if relay_host else -1
    return {
        "gateway": gateway, "gateway_ms": gateway_rtt,
        "destination_ms": direct.get("latency_ms", -1),
        "destination_method": direct.get("method", "unavailable"),
        "relay_ms": relay_rtt,
        "accelerated_ms": -1,
        "accelerated_note": "فقط پس از پروب داخل مسیر GameLink قابل اندازه‌گیری قطعی است",
    }


def run(process_name: str, relay_host: str = "") -> dict:
    endpoints = game_server_probe_service.discover_game_endpoints(process_name, limit=4)
    if not endpoints:
        # Lobby readiness deliberately uses a neutral reachability reference and
        # never labels it as the game server.
        reference = {"host": "1.1.1.1", "port": 443, "transport": "tcp"}
        gateway = default_gateway()
        return {
            "lobby_mode": True, "endpoint_count": 0,
            "matrix": ping_matrix(reference),
            "breakdown": {
                "gateway": gateway,
                "gateway_ms": game_server_probe_service._icmp_sample(gateway) if gateway else -1,
                "destination_ms": -1, "destination_method": "waiting_for_game_session",
                "relay_ms": game_server_probe_service._icmp_sample(relay_host) if relay_host else -1,
                "accelerated_ms": -1,
                "accelerated_note": "مقصد بازی پس از ساخته‌شدن نشست آنلاین اضافه می‌شود",
            },
            "adapters": adapter_health(), "pressure": traffic_pressure(),
        }
    return {
        "endpoint_count": len(endpoints), "matrix": ping_matrix(endpoints[0]),
        "breakdown": route_breakdown(endpoints[0], relay_host),
        "adapters": adapter_health(), "pressure": traffic_pressure(),
    }


def run_for_endpoint(endpoint: dict, relay_host: str = "") -> dict:
    """Refresh the lab with an endpoint already captured from an unconnected UDP socket."""
    return {
        "lobby_mode": False, "endpoint_count": 1,
        "matrix": ping_matrix(endpoint),
        "breakdown": route_breakdown(endpoint, relay_host),
        "adapters": adapter_health(), "pressure": traffic_pressure(),
    }


def truth_engine(baseline: dict | None, current: dict | None,
                 process_scoped: bool = False) -> dict:
    if not baseline or not current:
        return {"verdict": "unknown", "trusted": False, "reason": "نمونه قبل و بعد کامل نیست"}
    if process_scoped:
        return {"verdict": "indirect", "trusted": False,
                "reason": "پروب برنامه خارج از تانل اختصاصی پروسه اجرا می‌شود"}
    latency_delta = current.get("latency_ms", 0) - baseline.get("latency_ms", 0)
    loss_delta = current.get("loss", 0) - baseline.get("loss", 0)
    verdict = "better" if latency_delta <= -8 or loss_delta <= -2 else (
        "worse" if latency_delta >= 15 or loss_delta >= 3 else "same"
    )
    return {"verdict": verdict, "trusted": True, "latency_delta": latency_delta,
            "loss_delta": round(loss_delta, 1)}
