"""GameLink control-plane contract and device identity.

The data plane continues to use audited transports. This module supplies the
per-device identity, short-lived access contract, quota response and health
bootstrap needed by a future GameLink server.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.app_info import ALLOW_GAMELINK, APP_NAME, APP_VERSION
from app.services import app_paths, secure_storage


def _identity_file() -> Path:
    return app_paths.migrated_file("device_identity.json")


def device_public_key() -> str:
    path = _identity_file()
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        private_raw = secure_storage.unprotect(document["private_key"])
        key = Ed25519PrivateKey.from_private_bytes(private_raw)
    else:
        key = Ed25519PrivateKey.generate()
        private_raw = key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        path.write_text(json.dumps({
            "version": 1, "private_key": secure_storage.protect(private_raw),
        }, indent=2), encoding="utf-8")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(public_raw).decode("ascii").rstrip("=")


def bootstrap(api_base: str, access_token: str = "") -> dict:
    if not ALLOW_GAMELINK:
        raise RuntimeError("GameLink در نسخه عمومی محلی LAGSHIFT غیرفعال است")
    if not api_base.strip():
        raise RuntimeError("آدرس سرور GameLink تنظیم نشده است")
    body = json.dumps({
        "device_public_key": device_public_key(),
        "capabilities": ["hysteria2", "reality", "masque", "quota-v1", "radar-v1"],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(
        api_base.rstrip("/") + "/v1/client/bootstrap", data=body, method="POST", headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    required = {"session_token", "expires_at", "quota", "routes"}
    if not required.issubset(result):
        raise RuntimeError("پاسخ GameLink ناقص است")
    return result


def xor_parity(packets: list[bytes]) -> tuple[bytes, list[int]]:
    """One-loss FEC primitive for the future shared-session Turbo data plane."""
    lengths = [len(packet) for packet in packets]
    parity = bytearray(max(lengths, default=0))
    for packet in packets:
        for index, value in enumerate(packet):
            parity[index] ^= value
    return bytes(parity), lengths


def recover_one(packets: list[bytes | None], parity: bytes, lengths: list[int]) -> bytes:
    missing = [index for index, packet in enumerate(packets) if packet is None]
    if len(missing) != 1 or len(packets) != len(lengths):
        raise ValueError("برای بازیابی دقیقاً یک بسته باید مفقود باشد")
    recovered = bytearray(parity)
    for packet in packets:
        if packet is None:
            continue
        for index, value in enumerate(packet):
            recovered[index] ^= value
    return bytes(recovered[:lengths[missing[0]]])
