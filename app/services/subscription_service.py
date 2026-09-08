"""Safe import of standard HAPP/V2Ray subscription URLs."""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import urllib.parse
import urllib.request

from app.app_info import ALLOW_CUSTOM_TUNNELS, APP_NAME, APP_VERSION

from app.services import config_parser


MAX_SUBSCRIPTION_BYTES = 2 * 1024 * 1024
MAX_CONFIGS = 500
MAX_LINK_LENGTH = 16_384
LINK_PATTERN = re.compile(
    r"(?:vmess|vless|trojan|ss|socks5?|hy2|hysteria2|tuic)://[^\s\"'<>]+",
    re.IGNORECASE,
)


def _decode_possible_base64(text: str) -> str:
    if LINK_PATTERN.search(text):
        return text
    compact = "".join(text.split())
    try:
        return base64.urlsafe_b64decode(compact + "=" * (-len(compact) % 4)).decode("utf-8")
    except Exception:
        return text


def parse_document(text: str) -> list:
    text = text.lstrip("\ufeff").strip()
    candidates = []
    try:
        document = json.loads(text)
        if isinstance(document, list):
            candidates = [item for item in document if isinstance(item, str)]
        elif isinstance(document, dict):
            for key in ("links", "configs", "servers"):
                if isinstance(document.get(key), list):
                    candidates.extend(item for item in document[key] if isinstance(item, str))
    except json.JSONDecodeError:
        pass
    if not candidates:
        candidates = LINK_PATTERN.findall(_decode_possible_base64(text))
    configs = []
    errors = []
    for link in candidates[:MAX_CONFIGS]:
        if len(link) > MAX_LINK_LENGTH:
            errors.append("طول یکی از کانفیگ‌ها بیشتر از حد مجاز است")
            continue
        try:
            item = config_parser.parse_link(link)
            item.source = "subscription"
            configs.append(item)
        except ValueError as exc:
            errors.append(str(exc))
    if not configs:
        raise ValueError(errors[0] if errors else "هیچ کانفیگ پشتیبانی‌شده‌ای در اشتراک پیدا نشد")
    return configs


def _validated_subscription_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("آدرس اشتراک باید HTTPS باشد")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("آدرس اشتراک معتبر نیست")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    ):
        raise ValueError("آدرس اشتراک نباید به شبکه محلی اشاره کند")
    return urllib.parse.urlunsplit(parsed)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return super().redirect_request(
            request, fp, code, message, headers,
            _validated_subscription_url(new_url),
        )


def fetch(url: str) -> list:
    if not ALLOW_CUSTOM_TUNNELS:
        raise ValueError("نسخه عمومی امکان دریافت Subscription خارجی ندارد")
    url = _validated_subscription_url(url)
    request = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        "Accept": "text/plain, application/json",
    })
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=15) as response:
        data = response.read(MAX_SUBSCRIPTION_BYTES + 1)
    if len(data) > MAX_SUBSCRIPTION_BYTES:
        raise ValueError("حجم اشتراک بیشتر از حد مجاز است")
    return parse_document(data.decode("utf-8", errors="replace"))
