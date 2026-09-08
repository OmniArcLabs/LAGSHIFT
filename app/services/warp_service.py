"""Legacy WARP/WireGuard registration used only by the developer edition.

The endpoint is not a supported public integration contract. Public releases
must use official-client discovery and real Cloudflare trace verification.
"""
import base64
import json
import uuid as uuid_lib

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None

from app.models.tunnel_config import TunnelConfig

API_BASE = "https://api.cloudflareclient.com/v0a2158"
# Cloudflare's documented WireGuard ingress order: default, then fallbacks.
WIREGUARD_PORTS = (2408, 500, 1701, 4500)


def _generate_wg_keypair():
    """
    تولید یه جفت کلید WireGuard (private/public) با کتابخونه‌ی cryptography.
    اگه نصب نبود، به یه پیام خطای واضح برمی‌گردیم به‌جای کرش کردن.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        private_key = X25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return (
            base64.b64encode(private_bytes).decode(),
            base64.b64encode(public_bytes).decode(),
        )
    except ImportError:
        raise RuntimeError(
            "کتابخونه‌ی cryptography نصب نیست. برای Warp اجرا کن: pip install cryptography"
        )


def register_warp_account() -> TunnelConfig:
    """
    ساخت پروفایل قدیمی توسعه‌دهنده؛ در نسخه عمومی نباید فراخوانی شود.
    """
    if urllib is None:
        raise RuntimeError("ماژول urllib در دسترس نیست")

    private_key, public_key = _generate_wg_keypair()

    payload = json.dumps({
        "key": public_key,
        "tos": "2023-01-01T00:00:00.000Z",
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/reg",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "okhttp/3.12.1",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise RuntimeError(f"اتصال به سرویس Warp ناموفق بود: {e}")

    try:
        client_id = data["config"]["client_id"]
        addresses = data["config"]["interface"]["addresses"]
        client_ipv4 = addresses["v4"]
        client_ipv6 = addresses.get("v6", "")
        peer = data["config"]["peers"][0]
        peer_public_key = peer["public_key"]
        endpoint_host = peer["endpoint"]["host"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"ساختار پاسخ Warp غیرمنتظره بود (احتمالاً API تغییر کرده): {e}")

    endpoint_addr, _, endpoint_port = endpoint_host.rpartition(":")
    endpoint_addr = endpoint_addr.strip("[]")
    try:
        reserved = list(base64.b64decode(client_id))
    except Exception:
        reserved = []

    if "/" not in client_ipv4:
        client_ipv4 += "/32"
    if client_ipv6 and "/" not in client_ipv6:
        client_ipv6 += "/128"

    return TunnelConfig(
        id=str(uuid_lib.uuid4()),
        name="Cloudflare WARP (رایگان)",
        protocol="wireguard",
        address=endpoint_addr or endpoint_host,
        port=int(endpoint_port) if endpoint_port.isdigit() else 2408,
        raw_link="",
        extra={
            "private_key": private_key,
            "public_key": peer_public_key,
            "client_ipv4": client_ipv4,
            "client_ipv6": client_ipv6,
            "client_id": client_id,
            "reserved": reserved,
            "mtu": 1280,
        },
        source="warp",
    )
