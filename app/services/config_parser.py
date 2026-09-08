"""Parser and normalizer for share links used by common desktop clients."""
from __future__ import annotations

import base64
import binascii
import json
import uuid as uuid_lib
from urllib.parse import parse_qs, unquote, urlparse

from app.models.tunnel_config import TunnelConfig


SUPPORTED_SCHEMES = {
    "vmess", "vless", "trojan", "ss", "socks", "socks5",
    "hy2", "hysteria2", "tuic",
}


def _b64_decode(data: str) -> str:
    data = unquote(data.strip())
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("داده‌ی Base64 لینک معتبر نیست") from exc


def _name(fragment: str, fallback: str = "بدون نام") -> str:
    value = unquote(fragment or "").strip()
    return value[:120] or fallback


def _port(value, default: int) -> int:
    try:
        port = int(value or default)
    except (TypeError, ValueError) as exc:
        raise ValueError("پورت کانفیگ معتبر نیست") from exc
    if not 1 <= port <= 65535:
        raise ValueError("پورت باید بین ۱ تا ۶۵۵۳۵ باشد")
    return port


def _validate(config: TunnelConfig) -> TunnelConfig:
    if not config.address.strip() or any(ch.isspace() for ch in config.address):
        raise ValueError("آدرس سرور معتبر نیست")
    _port(config.port, config.port)
    if config.protocol in {"vless", "vmess"}:
        value = config.extra.get("uuid", "")
        try:
            uuid_lib.UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("UUID کانفیگ معتبر نیست") from exc
    return config


def parse_link(link: str) -> TunnelConfig:
    link = link.strip()
    if not link:
        raise ValueError("لینک خالی است")
    scheme = link.split(":", 1)[0].lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(
            "فرمت پشتیبانی نمی‌شود؛ لینک باید VLESS، VMess، Trojan، "
            "Shadowsocks، SOCKS5، Hysteria2 یا TUIC باشد"
        )
    parsers = {
        "vmess": _parse_vmess,
        "vless": _parse_vless,
        "trojan": _parse_trojan,
        "ss": _parse_shadowsocks,
        "socks": _parse_socks,
        "socks5": _parse_socks,
        "hy2": _parse_hysteria2,
        "hysteria2": _parse_hysteria2,
        "tuic": _parse_tuic,
    }
    return _validate(parsers[scheme](link))


def _common_stream(query: dict) -> dict:
    return {
        "network": query.get("type", query.get("net", ["tcp"]))[0],
        "security": query.get("security", ["none"])[0],
        "path": query.get("path", [""])[0],
        "host": query.get("host", [""])[0],
        "sni": query.get("sni", query.get("serverName", [""]))[0],
        "flow": query.get("flow", [""])[0],
        "alpn": query.get("alpn", [""])[0],
        "fingerprint": query.get("fp", ["chrome"])[0],
        "public_key": query.get("pbk", [""])[0],
        "short_id": query.get("sid", [""])[0],
        "spider_x": query.get("spx", ["/"])[0],
        "allow_insecure": query.get("allowInsecure", query.get("insecure", ["0"]))[0] in {"1", "true"},
    }


def _parse_vmess(link: str) -> TunnelConfig:
    try:
        data = json.loads(_b64_decode(link[len("vmess://"):]))
    except json.JSONDecodeError as exc:
        raise ValueError("ساختار VMess معتبر نیست") from exc
    extra = {
        "uuid": data.get("id", ""),
        "alter_id": int(data.get("aid", 0) or 0),
        "network": data.get("net", "tcp") or "tcp",
        "path": data.get("path", ""),
        "host": data.get("host", ""),
        "sni": data.get("sni", ""),
        "security": "tls" if data.get("tls") == "tls" else "none",
        "cipher": data.get("scy", "auto") or "auto",
        "fingerprint": data.get("fp", "chrome") or "chrome",
    }
    return TunnelConfig(str(uuid_lib.uuid4()), _name(data.get("ps", "")), "vmess",
                        str(data.get("add", "")), _port(data.get("port"), 443), link, extra)


def _parse_vless(link: str) -> TunnelConfig:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    extra = _common_stream(query)
    extra["uuid"] = unquote(parsed.username or "")
    return TunnelConfig(str(uuid_lib.uuid4()), _name(parsed.fragment), "vless",
                        parsed.hostname or "", _port(parsed.port, 443), link, extra)


def _parse_trojan(link: str) -> TunnelConfig:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    extra = _common_stream(query)
    extra["password"] = unquote(parsed.username or "")
    if not extra["password"]:
        raise ValueError("رمز Trojan خالی است")
    return TunnelConfig(str(uuid_lib.uuid4()), _name(parsed.fragment), "trojan",
                        parsed.hostname or "", _port(parsed.port, 443), link, extra)


def _parse_shadowsocks(link: str) -> TunnelConfig:
    payload = link[len("ss://"):]
    main, _, fragment = payload.partition("#")
    if "@" not in main:
        main = _b64_decode(main)
    credentials, separator, endpoint = main.rpartition("@")
    if not separator:
        raise ValueError("ساختار Shadowsocks معتبر نیست")
    try:
        decoded_credentials = _b64_decode(credentials)
    except ValueError:
        decoded_credentials = unquote(credentials)
    method, separator, password = decoded_credentials.partition(":")
    if not separator or not method or not password:
        raise ValueError("روش رمزنگاری یا رمز Shadowsocks خالی است")
    parsed = urlparse(f"ss://{endpoint}")
    return TunnelConfig(str(uuid_lib.uuid4()), _name(fragment), "shadowsocks",
                        parsed.hostname or "", _port(parsed.port, 8388), link,
                        {"method": method, "password": password})


def _parse_socks(link: str) -> TunnelConfig:
    scheme, payload = link.split("://", 1)
    if "@" not in payload:
        fragmentless, marker, fragment = payload.partition("#")
        decoded = _b64_decode(fragmentless)
        if "://" not in decoded:
            decoded = f"{scheme}://{decoded}"
        if marker:
            decoded += f"#{fragment}"
        return _parse_socks(decoded)
    parsed = urlparse(link)
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if username and not password:
        try:
            decoded = _b64_decode(username)
            decoded_user, separator, decoded_password = decoded.partition(":")
            if separator:
                username, password = decoded_user, decoded_password
        except ValueError:
            pass
    return TunnelConfig(str(uuid_lib.uuid4()), _name(parsed.fragment), "socks",
                        parsed.hostname or "", _port(parsed.port, 1080), link,
                        {"username": username, "password": password})


def _parse_hysteria2(link: str) -> TunnelConfig:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    password = unquote(parsed.username or "")
    if parsed.password:
        password = f"{password}:{unquote(parsed.password)}"
    extra = {
        "password": password,
        "sni": query.get("sni", [parsed.hostname or ""])[0],
        "obfs": query.get("obfs", [""])[0],
        "obfs_password": query.get("obfs-password", query.get("obfsPassword", [""]))[0],
        "allow_insecure": query.get("insecure", ["0"])[0] in {"1", "true"},
        "ports": query.get("ports", query.get("mport", [""]))[0],
    }
    return TunnelConfig(str(uuid_lib.uuid4()), _name(parsed.fragment), "hysteria2",
                        parsed.hostname or "", _port(parsed.port, 443), link, extra)


def _parse_tuic(link: str) -> TunnelConfig:
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    extra = {
        "uuid": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "sni": query.get("sni", [parsed.hostname or ""])[0],
        "congestion_control": query.get("congestion_control", query.get("congestion", ["bbr"]))[0],
        "udp_relay_mode": query.get("udp_relay_mode", ["native"])[0],
        "allow_insecure": query.get("allow_insecure", ["0"])[0] in {"1", "true"},
    }
    if not extra["uuid"]:
        raise ValueError("UUID کانفیگ TUIC خالی است")
    return TunnelConfig(str(uuid_lib.uuid4()), _name(parsed.fragment), "tuic",
                        parsed.hostname or "", _port(parsed.port, 443), link, extra)
