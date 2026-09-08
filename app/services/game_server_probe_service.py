"""Beta probe for remote endpoints actually used by a running game process."""
from __future__ import annotations

import ipaddress
import re
import socket
import statistics
import struct
import subprocess
import time
import os
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import psutil

from app.services import connectivity_service, quality_service


ANTI_CHEAT_MARKERS = (
    "easyanticheat", "easyanticheat_eos", "beservice", "battleye",
    "vgc", "vgtray", "faceit", "equ8", "eac_launcher",
)


def detect_active_anti_cheat() -> list[str]:
    detected = set()
    try:
        processes = psutil.process_iter(["name"])
        for process in processes:
            name = (process.info.get("name") or "").lower()
            stem = Path(name).stem
            if any(marker in stem for marker in ANTI_CHEAT_MARKERS):
                detected.add(process.info.get("name") or stem)
    except (psutil.AccessDenied, OSError):
        pass
    return sorted(detected)


def discover_log_endpoints(process_name: str, limit: int = 8) -> list[dict]:
    """Opt-in scan of open game logs; only public IP:port pairs leave this function."""
    wanted = process_name.strip().lower()
    results = {}
    if not wanted:
        return []
    try:
        processes = [
            process for process in psutil.process_iter(["pid", "name"])
            if (process.info.get("name") or "").lower() == wanted
        ]
    except (psutil.AccessDenied, OSError):
        return []
    pattern = re.compile(rb"(?<!\d)((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})(?!\d)")
    for process in processes:
        try:
            paths = [Path(item.path) for item in process.open_files()]
        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
        for path in paths:
            if path.suffix.lower() not in {".log", ".txt"}:
                continue
            try:
                size = path.stat().st_size
                with path.open("rb") as handle:
                    handle.seek(max(0, size - 262144))
                    tail = handle.read(262144)
            except OSError:
                continue
            for host_raw, port_raw in pattern.findall(tail):
                host, port = host_raw.decode("ascii"), int(port_raw)
                try:
                    if not ipaddress.ip_address(host).is_global or port > 65535:
                        continue
                except ValueError:
                    continue
                key = (host, port, "unknown")
                results[key] = {
                    "host": host, "port": port, "transport": "unknown",
                    "priority": 10, "source": "game_log",
                }
                if len(results) >= limit:
                    return list(results.values())
    return list(results.values())


def discover_game_endpoints(process_name: str, limit: int = 8) -> list[dict]:
    """Find public endpoints owned by the game process or its child processes."""
    wanted = process_name.strip().lower()
    if not wanted:
        return []
    roots = [
        process for process in psutil.process_iter(["pid", "name"])
        if (process.info.get("name") or "").lower() == wanted
    ]
    pids = {process.info["pid"] for process in roots}
    # Launchers often hand the lobby/session socket to a child helper. We include
    # descendants, but never the parent launcher (it may own unrelated web traffic).
    for process in roots:
        try:
            pids.update(child.pid for child in process.children(recursive=True))
        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    if not pids:
        return []
    found = {}
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return []
    for connection in connections:
        if connection.pid not in pids or not connection.raddr:
            continue
        if hasattr(connection.raddr, "ip"):
            host, port = connection.raddr.ip, int(connection.raddr.port)
        else:
            host, port = connection.raddr[0], int(connection.raddr[1])
        try:
            if not ipaddress.ip_address(host).is_global:
                continue
        except ValueError:
            continue
        transport = "udp" if connection.type == socket.SOCK_DGRAM else "tcp"
        key = (host, port, transport)
        priority = (30 if transport == "udp" else 0) + (5 if port not in (80, 443) else 0)
        found[key] = {
            "host": host, "port": port, "transport": transport, "priority": priority,
            "owner_pid": connection.pid,
        }
    return sorted(found.values(), key=lambda item: -item["priority"])[:limit]


def _game_process_ids(process_name: str) -> set[int]:
    wanted = process_name.strip().lower()
    roots = [
        process for process in psutil.process_iter(["pid", "name"])
        if (process.info.get("name") or "").lower() == wanted
    ]
    pids = {int(process.info["pid"]) for process in roots}
    for process in roots:
        try:
            pids.update(child.pid for child in process.children(recursive=True))
        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    return pids


def game_udp_local_ports(process_name: str) -> set[int]:
    """Return UDP ports owned by the game family; Windows does expose these reliably."""
    pids = _game_process_ids(process_name)
    if not pids:
        return set()
    try:
        connections = psutil.net_connections(kind="udp")
    except (psutil.AccessDenied, OSError):
        return set()
    return {
        int(connection.laddr.port if hasattr(connection.laddr, "port") else connection.laddr[1])
        for connection in connections
        if connection.pid in pids and connection.laddr
    }


def _parse_ipv4_udp_packet(packet: bytes, local_ports: set[int]) -> dict | None:
    """Extract only addressing metadata from a raw IPv4 UDP packet."""
    if len(packet) < 28 or packet[0] >> 4 != 4 or packet[9] != socket.IPPROTO_UDP:
        return None
    header_length = (packet[0] & 0x0F) * 4
    if header_length < 20 or len(packet) < header_length + 8:
        return None
    source_port, destination_port = struct.unpack("!HH", packet[header_length:header_length + 4])
    source_ip = socket.inet_ntoa(packet[12:16])
    destination_ip = socket.inet_ntoa(packet[16:20])
    if source_port in local_ports:
        remote_ip, remote_port, local_port = destination_ip, destination_port, source_port
    elif destination_port in local_ports:
        remote_ip, remote_port, local_port = source_ip, source_port, destination_port
    else:
        return None
    try:
        if not ipaddress.ip_address(remote_ip).is_global:
            return None
    except ValueError:
        return None
    return {
        "host": remote_ip, "port": int(remote_port), "transport": "udp",
        "local_port": int(local_port), "priority": 45,
        "source": "process_port_capture",
    }


def capture_game_udp_endpoints(process_name: str, duration_s: float = 1.5,
                               limit: int = 8) -> list[dict]:
    """Observe UDP address metadata for unconnected game sockets using Windows raw capture.

    No payload is retained. Failure (including missing admin rights) safely returns an empty list.
    """
    local_ports = game_udp_local_ports(process_name)
    if not local_ports or not hasattr(socket, "SIO_RCVALL"):
        return []
    local_ipv4 = sorted({
        address.address for rows in psutil.net_if_addrs().values() for address in rows
        if address.family == socket.AF_INET and not address.address.startswith("127.")
    })
    found = {}
    deadline = time.monotonic() + max(0.2, min(4.0, duration_s))
    sockets = []
    try:
        for address in local_ipv4:
            try:
                raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
                raw.bind((address, 0))
                raw.settimeout(0.15)
                raw.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
                sockets.append(raw)
            except OSError:
                try:
                    raw.close()
                except (UnboundLocalError, OSError):
                    pass
        while sockets and time.monotonic() < deadline and len(found) < limit:
            for raw in sockets:
                try:
                    packet, _ = raw.recvfrom(65535)
                except (socket.timeout, OSError):
                    continue
                endpoint = _parse_ipv4_udp_packet(packet, local_ports)
                if endpoint:
                    found[(endpoint["host"], endpoint["port"])] = endpoint
    finally:
        for raw in sockets:
            try:
                raw.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
                raw.close()
            except OSError:
                pass
    captured = list(found.values())[:limit]
    return captured or capture_game_udp_endpoints_pktmon(process_name, duration_s, limit)


def _pcapng_ipv4_packets(path: Path):
    """Yield IPv4 packets from the small pcapng produced by Windows pktmon."""
    try:
        data = path.read_bytes()
    except OSError:
        return
    offset, endian, interfaces = 0, "<", []
    while offset + 12 <= len(data):
        raw_type = data[offset:offset + 4]
        if raw_type == b"\x0a\x0d\x0d\x0a" and offset + 12 <= len(data):
            magic = data[offset + 8:offset + 12]
            endian = "<" if magic == b"\x4d\x3c\x2b\x1a" else ">"
        try:
            block_type, block_length = struct.unpack_from(endian + "II", data, offset)
        except struct.error:
            break
        if block_length < 12 or offset + block_length > len(data):
            break
        body = offset + 8
        if block_type == 1 and body + 2 <= len(data):  # Interface Description Block
            interfaces.append(struct.unpack_from(endian + "H", data, body)[0])
        elif block_type == 6 and body + 20 <= len(data):  # Enhanced Packet Block
            interface_id = struct.unpack_from(endian + "I", data, body)[0]
            captured_length = struct.unpack_from(endian + "I", data, body + 12)[0]
            frame = data[body + 20:body + 20 + captured_length]
            link_type = interfaces[interface_id] if interface_id < len(interfaces) else 1
            packet = _ipv4_from_link_frame(frame, link_type)
            if packet:
                yield packet
        offset += block_length


def _ipv4_from_link_frame(frame: bytes, link_type: int) -> bytes | None:
    if link_type == 101:  # Raw IP
        return frame if frame and frame[0] >> 4 == 4 else None
    if link_type != 1 or len(frame) < 14:  # Ethernet
        return None
    cursor, ether_type = 14, struct.unpack("!H", frame[12:14])[0]
    if ether_type in (0x8100, 0x88A8) and len(frame) >= 18:
        ether_type, cursor = struct.unpack("!H", frame[16:18])[0], 18
    return frame[cursor:] if ether_type == 0x0800 else None


def capture_game_udp_endpoints_pktmon(process_name: str, duration_s: float = 1.5,
                                      limit: int = 8) -> list[dict]:
    """Fallback to Windows' signed Packet Monitor when raw sockets expose nothing."""
    local_ports = game_udp_local_ports(process_name)
    if not local_ports:
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        status = subprocess.run(
            ["pktmon", "status"], capture_output=True, text=True, timeout=3,
            creationflags=flags,
        )
        status_text = (status.stdout + status.stderr).lower()
        if status.returncode == 0 and any(word in status_text for word in ("running", "collecting")):
            return []  # Never interrupt another diagnostic capture.
    except (OSError, subprocess.SubprocessError):
        return []
    runtime = app_paths.runtime_dir()
    runtime.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    etl_path = runtime / f"udp-{token}.etl"
    pcap_path = runtime / f"udp-{token}.pcapng"
    started = False
    try:
        result = subprocess.run(
            ["pktmon", "start", "--capture", "--comp", "nics", "--pkt-size", "96",
             "--file-name", str(etl_path), "--file-size", "8", "--log-mode", "circular"],
            capture_output=True, text=True, timeout=5, creationflags=flags,
        )
        if result.returncode != 0:
            return []
        started = True
        time.sleep(max(0.3, min(4.0, duration_s)))
        subprocess.run(["pktmon", "stop"], capture_output=True, timeout=5,
                       creationflags=flags)
        started = False
        converted = subprocess.run(
            ["pktmon", "etl2pcap", str(etl_path), "--out", str(pcap_path)],
            capture_output=True, text=True, timeout=8, creationflags=flags,
        )
        if converted.returncode != 0 or not pcap_path.exists():
            return []
        found = {}
        for packet in _pcapng_ipv4_packets(pcap_path):
            endpoint = _parse_ipv4_udp_packet(packet, local_ports)
            if endpoint:
                endpoint["source"] = "process_port_pktmon"
                found[(endpoint["host"], endpoint["port"])] = endpoint
                if len(found) >= limit:
                    break
        return list(found.values())
    except (OSError, subprocess.SubprocessError):
        return []
    finally:
        if started:
            try:
                subprocess.run(["pktmon", "stop"], capture_output=True, timeout=5,
                               creationflags=flags)
            except (OSError, subprocess.SubprocessError):
                pass
        for path in (etl_path, pcap_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _icmp_sample(host: str, timeout_ms: int = 900) -> int:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), host],
            capture_output=True, text=True, timeout=(timeout_ms / 1000) + 1,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return -1
    if completed.returncode != 0:
        return -1
    match = re.search(r"[=<]\s*(\d+)\s*ms", completed.stdout, re.IGNORECASE)
    return int(match.group(1)) if match else -1


def benchmark_endpoint(endpoint: dict, attempts: int = 5,
                       mode: str = "balanced") -> dict:
    """Probe one observed destination. TCP is only a fallback when ICMP is blocked."""
    host, port = endpoint["host"], int(endpoint["port"])
    with ThreadPoolExecutor(max_workers=min(attempts, 5)) as executor:
        samples = list(executor.map(lambda _index: _icmp_sample(host), range(attempts)))
    method = "ICMP"
    if all(value < 0 for value in samples) and endpoint["transport"] == "tcp":
        method = "TCP handshake"
        samples = [
            connectivity_service.measure_latency_ms(host, port, timeout_s=1.2)
            for _ in range(attempts)
        ]
    valid = [value for value in samples if value >= 0]
    if not valid:
        return {**endpoint, "available": False, "samples": samples, "method": method}
    median = round(statistics.median(valid))
    jitter = round(statistics.median(abs(value - median) for value in valid))
    quality = quality_service.calculate_game_quality(
        median, jitter, len(valid), attempts, mode,
    )
    return {
        **endpoint, "available": True, "samples": samples, "method": method,
        "latency_ms": median, "jitter_ms": jitter,
        "loss": quality.packet_loss_pct, "score": quality.score, "label": quality.label,
    }


def probe_game_server(process_name: str, mode: str = "balanced") -> dict:
    endpoints = discover_game_endpoints(process_name)
    if not endpoints:
        return {
            "error": "هنوز مقصد اینترنتی متعلق به خود بازی دیده نشد؛ وارد منوی آنلاین یا مسابقه شو و دوباره تست کن."
        }
    results = [benchmark_endpoint(endpoint, mode=mode) for endpoint in endpoints[:3]]
    available = [item for item in results if item.get("available")]
    if not available:
        return {
            "error": "مقصدهای بازی پیدا شدند، اما پاسخ پینگ/اتصال آزمایشی را مسدود کردند.",
            "endpoints_seen": len(endpoints),
        }
    best = max(available, key=lambda item: (item["score"], -item["latency_ms"]))
    return {**best, "endpoints_seen": len(endpoints)}
from app.services import app_paths
