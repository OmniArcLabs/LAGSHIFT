"""Fail-closed signed updates for App Access destinations and process hints."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import replace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.app_info import APP_NAME, APP_VERSION, APP_PROFILE_MANIFEST_URL, APP_PROFILE_PUBLIC_KEY_B64
from app.models.app_access import AppAccessProfile, DEFAULT_APP_ACCESS_PROFILES
from app.services import app_paths


MAX_CATALOG_BYTES = 256 * 1024
_HOST_RE = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_PROCESS_RE = re.compile(r"^[^\\/:*?\"<>|]{1,80}\.exe$", re.IGNORECASE)


def _validate_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("آدرس کاتالوگ باید HTTPS عمومی باشد")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("آدرس محلی برای کاتالوگ پذیرفته نیست")
    return str(value)


class _HttpsRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _HttpsRedirectsOnly(),
    )


def _canonical(document: dict) -> bytes:
    return json.dumps(
        {key: value for key, value in document.items() if key != "signature"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _domains(values) -> tuple[str, ...]:
    if not isinstance(values, list) or len(values) > 24:
        raise ValueError("فهرست مقصدهای پروفایل معتبر نیست")
    normalized = tuple(dict.fromkeys(str(value).strip().casefold() for value in values))
    if not normalized or any(not _HOST_RE.fullmatch(value) for value in normalized):
        raise ValueError("نام مقصد پروفایل معتبر نیست")
    return normalized


def verify_catalog(document: dict, public_key_b64: str = APP_PROFILE_PUBLIC_KEY_B64) -> dict:
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("نسخه کاتالوگ پشتیبانی نمی‌شود")
    changes = document.get("profiles")
    if not isinstance(changes, list) or len(changes) > len(DEFAULT_APP_ACCESS_PROFILES):
        raise ValueError("کاتالوگ پروفایل‌ها معتبر نیست")
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(str(document.get("signature", "")), validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _canonical(document))
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("امضای کاتالوگ پروفایل‌ها معتبر نیست") from exc

    known = {profile.id for profile in DEFAULT_APP_ACCESS_PROFILES}
    normalized = []
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or change.get("id") not in known or change["id"] in seen:
            raise ValueError("شناسه پروفایل راه دور معتبر نیست")
        seen.add(change["id"])
        processes = change.get("process_names", [])
        if not isinstance(processes, list) or len(processes) > 16 or any(
            not _PROCESS_RE.fullmatch(str(value)) for value in processes
        ):
            raise ValueError("نام پردازش راه دور معتبر نیست")
        registries = change.get("registry_names", [])
        if not isinstance(registries, list) or len(registries) > 16 or any(
            not 1 <= len(str(value).strip()) <= 80 for value in registries
        ):
            raise ValueError("نشانه نصب راه دور معتبر نیست")
        normalized.append({
            "id": change["id"],
            "login_domains": _domains(change.get("login_domains", [])),
            "download_domains": _domains(change.get("download_domains", [])),
            "service_domains": _domains(change.get("service_domains", [])),
            "process_names": tuple(str(value).casefold() for value in processes),
            "registry_names": tuple(str(value).strip().casefold() for value in registries),
        })
    return {"version": 1, "revision": str(document.get("revision", ""))[:80],
            "profiles": normalized, "signature": document["signature"]}


def _cache_path():
    return app_paths.migrated_file("app_profiles.signed.json", local=True)


def cache_catalog(document: dict, public_key_b64: str = APP_PROFILE_PUBLIC_KEY_B64) -> None:
    verify_catalog(document, public_key_b64)
    path = _cache_path()
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_profiles(public_key_b64: str = APP_PROFILE_PUBLIC_KEY_B64) -> tuple[AppAccessProfile, ...]:
    if not public_key_b64:
        return DEFAULT_APP_ACCESS_PROFILES
    try:
        document = json.loads(_cache_path().read_text(encoding="utf-8"))
        verified = verify_catalog(document, public_key_b64)
    except (OSError, ValueError, TypeError):
        return DEFAULT_APP_ACCESS_PROFILES
    changes = {item["id"]: item for item in verified["profiles"]}
    return tuple(
        replace(profile, **changes[profile.id]) if profile.id in changes else profile
        for profile in DEFAULT_APP_ACCESS_PROFILES
    )


def refresh(url: str = APP_PROFILE_MANIFEST_URL,
            public_key_b64: str = APP_PROFILE_PUBLIC_KEY_B64) -> bool:
    if not url or not public_key_b64:
        return False
    request = urllib.request.Request(
        _validate_url(url), headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
    )
    with _opener().open(request, timeout=8) as response:
        payload = response.read(MAX_CATALOG_BYTES + 1)
    if len(payload) > MAX_CATALOG_BYTES:
        raise ValueError("کاتالوگ پروفایل‌ها بیش از حد بزرگ است")
    document = json.loads(payload.decode("utf-8"))
    cache_catalog(document, public_key_b64)
    return True
