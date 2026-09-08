"""Reliable core management, TUN configuration and path verification."""
from __future__ import annotations

import json
import os
import socket
import statistics
import subprocess
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Optional

from app.models.tunnel_config import TunnelConfig
from app.app_info import APP_NAME, APP_VERSION
from app.services import app_paths


SOCKS_PORT = 10808
HTTP_PORT = 10809
CANARY_URLS = (
    "https://cp.cloudflare.com/generate_204",
    "https://www.gstatic.com/generate_204",
)


@dataclass
class PathHealth:
    available: bool
    latency_ms: int = -1
    jitter_ms: int = -1
    successes: int = 0
    attempts: int = 0
    error: str = ""

    @property
    def packet_loss_pct(self) -> float:
        if self.attempts <= 0:
            return 100.0 if not self.available else 0.0
        return round((self.attempts - self.successes) * 100.0 / self.attempts, 1)

    @property
    def score(self) -> int:
        if not self.available:
            return -1
        from app.services.quality_service import calculate_game_quality
        return calculate_game_quality(
            self.latency_ms, max(self.jitter_ms, 0), self.successes,
            self.attempts or self.successes or 1,
        ).score


def _root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _xray_executable_path() -> Optional[Path]:
    local = _root() / "xray.exe"
    if local.exists():
        return local
    found = which("xray") or which("xray.exe")
    return Path(found) if found else None


def _sing_box_executable_path() -> Optional[Path]:
    local = _root() / "sing-box.exe"
    if local.exists():
        return local
    found = which("sing-box") or which("sing-box.exe")
    return Path(found) if found else None


def engine_for(config: TunnelConfig) -> str:
    if config.protocol == "tuic":
        return "sing-box"
    if config.protocol == "hysteria2" and (config.extra.get("obfs") or config.extra.get("ports")):
        return "sing-box"
    return "xray"


def _stream_settings(config: TunnelConfig) -> dict:
    extra = config.extra
    network = extra.get("network", "tcp") or "tcp"
    stream = {"network": network}
    security = extra.get("security", "")
    if security == "reality":
        stream.update({
            "security": "reality",
            "realitySettings": {
                "serverName": extra.get("sni") or config.address,
                "fingerprint": extra.get("fingerprint", "chrome"),
                "publicKey": extra.get("public_key", ""),
                "shortId": extra.get("short_id", ""),
                "spiderX": extra.get("spider_x", "/"),
            },
        })
    elif security == "tls" or extra.get("tls"):
        tls = {
            "serverName": extra.get("sni") or extra.get("host") or config.address,
            "allowInsecure": bool(extra.get("allow_insecure", False)),
        }
        if extra.get("fingerprint"):
            tls["fingerprint"] = extra["fingerprint"]
        if extra.get("alpn"):
            tls["alpn"] = [item for item in extra["alpn"].split(",") if item]
        stream.update({"security": "tls", "tlsSettings": tls})

    if network == "ws":
        stream["wsSettings"] = {
            "path": extra.get("path", "/") or "/",
            "headers": {"Host": extra.get("host") or config.address},
        }
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": extra.get("path", "").lstrip("/")}
    elif network in {"http", "h2"}:
        stream["httpSettings"] = {
            "path": extra.get("path", "/") or "/",
            "host": [extra.get("host") or config.address],
        }
    return stream


def _xray_outbound(config: TunnelConfig) -> dict:
    extra = config.extra
    outbound = {"tag": "proxy", "protocol": config.protocol, "mux": {"enabled": False}}
    if config.protocol in {"vmess", "vless"}:
        user = {"id": extra.get("uuid", "")}
        if config.protocol == "vmess":
            user.update({"alterId": int(extra.get("alter_id", 0)),
                         "security": extra.get("cipher", "auto")})
        else:
            user.update({"encryption": "none", "flow": extra.get("flow", "")})
        outbound["settings"] = {"vnext": [{
            "address": config.address, "port": config.port, "users": [user]
        }]}
        outbound["streamSettings"] = _stream_settings(config)
    elif config.protocol == "trojan":
        outbound["settings"] = {"servers": [{
            "address": config.address,
            "port": config.port,
            "password": extra.get("password", ""),
        }]}
        outbound["streamSettings"] = _stream_settings(config)
    elif config.protocol == "shadowsocks":
        outbound["settings"] = {"servers": [{
            "address": config.address, "port": config.port,
            "method": extra.get("method", "aes-256-gcm"),
            "password": extra.get("password", ""),
        }]}
    elif config.protocol == "socks":
        server = {"address": config.address, "port": config.port}
        if extra.get("username"):
            server["users"] = [{"user": extra["username"], "pass": extra.get("password", "")}]
        outbound["settings"] = {"servers": [server]}
    elif config.protocol == "wireguard":
        addresses = [extra.get("client_ipv4", "")]
        if extra.get("client_ipv6"):
            addresses.append(extra["client_ipv6"])
        settings = {
            "secretKey": extra.get("private_key", ""),
            "address": [item for item in addresses if item],
            "peers": [{
                "publicKey": extra.get("public_key", ""),
                "endpoint": f"{config.address}:{config.port}",
                "keepAlive": 25,
                "allowedIPs": ["0.0.0.0/0", "::/0"],
            }],
            "mtu": int(extra.get("mtu", 1280)),
            "noKernelTun": True,
            "domainStrategy": "ForceIPv4v6",
        }
        if extra.get("reserved"):
            settings["reserved"] = extra["reserved"]
        outbound["settings"] = settings
    elif config.protocol == "hysteria2":
        outbound["protocol"] = "hysteria"
        outbound["settings"] = {
            "version": 2, "address": config.address, "port": config.port,
        }
        outbound["streamSettings"] = {
            "method": "hysteria",
            "security": "tls",
            "tlsSettings": {
                "serverName": extra.get("sni") or config.address,
                "allowInsecure": bool(extra.get("allow_insecure", False)),
            },
            "hysteriaSettings": {
                "version": 2, "auth": extra.get("password", ""), "udpIdleTimeout": 60,
            },
        }
    else:
        raise ValueError(f"پروتکل {config.protocol} با هسته Xray سازگار نیست")
    return outbound


def build_xray_config(config: TunnelConfig, mode: str = "proxy",
                      socks_port: int = SOCKS_PORT, http_port: int = HTTP_PORT,
                      process_names: Optional[list[str]] = None,
                      mtu: int = 1400) -> dict:
    inbounds = [
        {"tag": "socks-in", "port": socks_port, "listen": "127.0.0.1",
         "protocol": "socks", "settings": {"udp": True}},
        {"tag": "http-in", "port": http_port, "listen": "127.0.0.1",
         "protocol": "http", "settings": {}},
    ]
    if mode == "tun":
        inbounds.insert(0, {
            "tag": "tun-in",
            "port": 0,
            "protocol": "tun",
            "settings": {
                "name": "gamedns",
                "desc": APP_NAME,
                "mtu": max(1200, min(1500, int(mtu))),
                "gateway": ["10.66.0.1/30", "fd66::1/126"],
                "dns": ["1.1.1.1", "8.8.8.8"],
                "autoSystemRoutingTable": ["0.0.0.0/0", "::/0"],
                "autoOutboundsInterface": "auto",
            },
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
        })
    rules = [
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
        {"type": "field", "ip": ["geoip:ir"], "outboundTag": "direct"},
    ]
    cleaned_processes = [
        name[:-4] if name.lower().endswith(".exe") else name
        for name in (process_names or []) if name.strip()
    ]
    if mode == "tun" and cleaned_processes:
        rules.extend([
            {"type": "field", "inboundTag": ["tun-in"], "process": cleaned_processes,
             "outboundTag": "proxy"},
            {"type": "field", "inboundTag": ["tun-in"], "network": "tcp,udp",
             "outboundTag": "direct"},
        ])
    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["1.1.1.1", "8.8.8.8", "localhost"]},
        "inbounds": inbounds,
        "outbounds": [_xray_outbound(config), {"protocol": "freedom", "tag": "direct"},
                      {"protocol": "blackhole", "tag": "block"}],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": rules,
        },
    }


def _sing_box_outbound(config: TunnelConfig) -> dict:
    extra = config.extra
    if config.protocol == "hysteria2":
        outbound = {
            "type": "hysteria2", "tag": "proxy", "server": config.address,
            "server_port": config.port, "password": extra.get("password", ""),
            "tls": {"enabled": True, "server_name": extra.get("sni") or config.address,
                    "insecure": bool(extra.get("allow_insecure", False))},
        }
        if extra.get("obfs"):
            outbound["obfs"] = {"type": extra["obfs"], "password": extra.get("obfs_password", "")}
        if extra.get("ports"):
            outbound["server_ports"] = [extra["ports"]]
        return outbound
    if config.protocol == "tuic":
        return {
            "type": "tuic", "tag": "proxy", "server": config.address,
            "server_port": config.port, "uuid": extra.get("uuid", ""),
            "password": extra.get("password", ""),
            "congestion_control": extra.get("congestion_control", "bbr"),
            "udp_relay_mode": extra.get("udp_relay_mode", "native"),
            "tls": {"enabled": True, "server_name": extra.get("sni") or config.address,
                    "insecure": bool(extra.get("allow_insecure", False))},
        }
    raise ValueError(f"پروتکل {config.protocol} با هسته sing-box تنظیم نشده است")


def build_sing_box_config(config: TunnelConfig, mode: str = "proxy",
                          socks_port: int = SOCKS_PORT, http_port: int = HTTP_PORT,
                          process_names: Optional[list[str]] = None,
                          mtu: int = 1400) -> dict:
    inbounds = [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1",
                 "listen_port": http_port}]
    if mode == "tun":
        inbounds.insert(0, {
            "type": "tun", "tag": "tun-in", "interface_name": APP_NAME,
            "address": ["10.67.0.1/30", "fd67::1/126"],
            "mtu": max(1200, min(1500, int(mtu))), "auto_route": True, "strict_route": True,
        })
    cleaned_processes = [
        Path(name.strip()).stem for name in (process_names or []) if name.strip()
    ]
    route = {"auto_detect_interface": True, "final": "proxy"}
    if mode == "tun" and cleaned_processes:
        route["rules"] = [{"process_name": cleaned_processes, "outbound": "proxy"}]
        route["final"] = "direct"
    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": [_sing_box_outbound(config), {"type": "direct", "tag": "direct"}],
        "route": route,
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TunnelProcess:
    """Owns one core process and never reports success before it survives startup."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._config_path: Optional[Path] = None
        self._log_path: Optional[Path] = None
        self._log_handle = None
        self.mode = "proxy"
        self.engine = ""

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _runtime_dir(self) -> Path:
        return app_paths.runtime_dir()

    def _last_error(self) -> str:
        try:
            text = self._log_path.read_text(encoding="utf-8", errors="ignore")
            return text.strip().splitlines()[-1][-300:] if text.strip() else ""
        except Exception:
            return ""

    def _record_failure(self, message: str) -> None:
        """Keep a secret-free diagnostic after disposable runtime files are removed."""
        try:
            path = self._runtime_dir().parent / "last_connection_error.log"
            path.write_text(message.strip()[-1200:], encoding="utf-8")
        except OSError:
            pass

    def start(self, config: TunnelConfig, mode: str = "tun",
              socks_port: int = SOCKS_PORT, http_port: int = HTTP_PORT,
              process_names: Optional[list[str]] = None,
              mtu: int = 1400) -> tuple[bool, str]:
        self.stop()
        self.mode = mode
        self.engine = engine_for(config)
        executable = _xray_executable_path() if self.engine == "xray" else _sing_box_executable_path()
        if executable is None:
            message = f"هسته {self.engine} در کنار برنامه پیدا نشد"
            self._record_failure(message)
            return False, message

        try:
            document = (build_xray_config(
                            config, mode, socks_port, http_port,
                            process_names=process_names, mtu=mtu
                        )
                        if self.engine == "xray"
                        else build_sing_box_config(
                            config, mode, socks_port, http_port,
                            process_names=process_names, mtu=mtu
                        ))
        except Exception as exc:
            message = f"ساخت کانفیگ ناموفق بود: {exc}"
            self._record_failure(message)
            return False, message

        runtime = self._runtime_dir()
        token = uuid.uuid4().hex
        self._config_path = runtime / f"{self.engine}-{token}.json"
        self._log_path = runtime / f"{self.engine}-{token}.log"
        self._config_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

        check_cmd = ([str(executable), "run", "-test", "-c", str(self._config_path)]
                     if self.engine == "xray"
                     else [str(executable), "check", "-c", str(self._config_path)])
        checked = subprocess.run(check_cmd, capture_output=True, text=True, encoding="utf-8",
                                 errors="ignore", timeout=10,
                                 creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        if checked.returncode != 0:
            detail = (checked.stderr or checked.stdout).strip().splitlines()
            message = "کانفیگ توسط هسته رد شد" + (f": {detail[-1][-240:]}" if detail else "")
            self._record_failure(message)
            self._cleanup_runtime_files()
            return False, message

        command = ([str(executable), "run", "-c", str(self._config_path)]
                   if self.engine == "xray"
                   else [str(executable), "run", "-c", str(self._config_path)])
        try:
            self._log_handle = self._log_path.open("w", encoding="utf-8")
            self._process = subprocess.Popen(
                command, stdout=self._log_handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            deadline = time.monotonic() + (4.0 if mode == "tun" else 2.0)
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    error = self._last_error()
                    message = f"هسته هنگام شروع متوقف شد{': ' + error if error else ''}"
                    self._record_failure(message)
                    self.stop()
                    return False, message
                if mode == "proxy" and _port_open("127.0.0.1", http_port):
                    break
                time.sleep(0.1)
            if mode == "proxy" and not _port_open("127.0.0.1", http_port):
                message = "پراکسی محلی در زمان مقرر آماده نشد"
                self._record_failure(message)
                self.stop()
                return False, message
        except Exception as exc:
            message = f"اجرای هسته ناموفق بود: {exc}"
            self._record_failure(message)
            self.stop()
            return False, message

        label = "TUN سراسری" if mode == "tun" else "پراکسی آزمایشی"
        return True, f"{label} با هسته {self.engine} فعال شد"

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        self._process = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        self._cleanup_runtime_files()

    def _cleanup_runtime_files(self):
        for path in (self._config_path, self._log_path):
            if path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        self._config_path = None
        self._log_path = None


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def measure_http_path(proxy_port: Optional[int] = None, attempts: int = 2,
                      timeout_s: float = 4.0) -> PathHealth:
    handler = (urllib.request.ProxyHandler({
        "http": f"http://127.0.0.1:{proxy_port}",
        "https": f"http://127.0.0.1:{proxy_port}",
    }) if proxy_port else urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(handler)
    samples = []
    errors = []
    for index in range(attempts):
        url = CANARY_URLS[index % len(CANARY_URLS)]
        started = time.perf_counter()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            with opener.open(request, timeout=timeout_s) as response:
                response.read(64)
            samples.append(int((time.perf_counter() - started) * 1000))
        except Exception as exc:
            detail = str(exc).strip()
            errors.append(f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__)
    if not samples:
        return PathHealth(False, attempts=attempts, error=errors[-1] if errors else "no response")
    jitter = int(statistics.pstdev(samples)) if len(samples) > 1 else 0
    return PathHealth(True, int(statistics.median(samples)), jitter, len(samples), attempts)


def probe_config(config: TunnelConfig, attempts: int = 2,
                 timeout_s: float = 4.0) -> PathHealth:
    """Start a disposable local proxy and verify real HTTPS bytes through it."""
    port = _free_port()
    process = TunnelProcess()
    ok, message = process.start(config, mode="proxy", socks_port=_free_port(), http_port=port)
    if not ok:
        return PathHealth(False, error=message)
    try:
        health = measure_http_path(proxy_port=port, attempts=attempts, timeout_s=timeout_s)
        if not health.available:
            process._record_failure(f"آزمون HTTPS از داخل تانل ناموفق بود: {health.error}")
        return health
    finally:
        process.stop()


def trial_config(config: TunnelConfig, duration_s: float = 30.0,
                 interval_s: float = 2.5) -> PathHealth:
    """Keep one disposable proxy alive and sample it throughout a trial window."""
    port = _free_port()
    process = TunnelProcess()
    ok, message = process.start(config, mode="proxy", socks_port=_free_port(), http_port=port)
    if not ok:
        return PathHealth(False, error=message)
    samples = []
    attempts = 0
    errors = []
    deadline = time.monotonic() + max(1.0, duration_s)
    try:
        while time.monotonic() < deadline:
            cycle_started = time.monotonic()
            health = measure_http_path(proxy_port=port, attempts=1, timeout_s=min(4.0, interval_s))
            attempts += 1
            if health.available:
                samples.append(health.latency_ms)
            elif health.error:
                errors.append(health.error)
            remaining = interval_s - (time.monotonic() - cycle_started)
            if remaining > 0 and time.monotonic() + remaining < deadline:
                time.sleep(remaining)
    finally:
        process.stop()
    if not samples:
        return PathHealth(False, successes=0, attempts=attempts,
                          error=errors[-1] if errors else "بدون پاسخ")
    jitter = int(statistics.pstdev(samples)) if len(samples) > 1 else 0
    return PathHealth(
        True, int(statistics.median(samples)), jitter, len(samples), attempts,
        errors[-1] if errors else "",
    )
