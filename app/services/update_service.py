"""Fail-closed update checks with Ed25519 manifest and SHA-256 payload verification."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.app_info import (
    APP_NAME, APP_VERSION, UPDATE_CHANNEL, UPDATE_MANIFEST_URL,
    UPDATE_PUBLIC_KEY_B64,
)
from app.services import app_paths


MAX_MANIFEST_BYTES = 128 * 1024
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class UpdateCheck:
    configured: bool
    available: bool
    message: str
    manifest: dict | None = None


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("نسخه آپدیت باید با قالب x.y.z باشد")
    return tuple(int(part) for part in match.groups())


def _validate_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("آدرس آپدیت باید HTTPS معتبر باشد")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local
                    or address.is_reserved or address.is_unspecified):
        raise ValueError("آدرس محلی برای آپدیت پذیرفته نیست")
    return value


class _HttpsRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _HttpsRedirectsOnly(),
    )


def _canonical_payload(document: dict) -> bytes:
    signed = {key: value for key, value in document.items() if key != "signature"}
    return json.dumps(
        signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def verify_manifest(document: dict, public_key_b64: str,
                    channel: str = UPDATE_CHANNEL) -> dict:
    required = {"version", "channel", "url", "sha256", "size", "signature"}
    if not isinstance(document, dict) or not required.issubset(document):
        raise ValueError("مانیفست آپدیت ناقص است")
    if document["channel"] != channel:
        raise ValueError("کانال آپدیت با نسخه برنامه یکسان نیست")
    _version_tuple(str(document["version"]))
    _validate_https_url(str(document["url"]))
    digest = str(document["sha256"]).lower()
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("هش فایل آپدیت معتبر نیست")
    size = document["size"]
    if not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError("اندازه فایل آپدیت معتبر نیست")
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(str(document["signature"]), validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _canonical_payload(document)
        )
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("امضای دیجیتال آپدیت معتبر نیست") from exc
    normalized = dict(document)
    normalized["sha256"] = digest
    normalized["notes"] = str(document.get("notes", ""))[:4000]
    normalized["mandatory"] = bool(document.get("mandatory", False))
    return normalized


def check_for_update(manifest_url: str = UPDATE_MANIFEST_URL,
                     public_key_b64: str = UPDATE_PUBLIC_KEY_B64,
                     current_version: str = APP_VERSION,
                     channel: str = UPDATE_CHANNEL) -> UpdateCheck:
    if not manifest_url or not public_key_b64:
        return UpdateCheck(False, False, "کانال انتشار امن هنوز پیکربندی نشده است")
    if channel not in {"stable", "beta"}:
        return UpdateCheck(False, False, "کانال انتشار معتبر نیست")
    try:
        url = _validate_https_url(manifest_url)
        request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{current_version}"})
        with _opener().open(request, timeout=8) as response:
            payload = response.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise ValueError("مانیفست آپدیت بیش از حد بزرگ است")
        manifest = verify_manifest(
            json.loads(payload.decode("utf-8")), public_key_b64, channel
        )
        available = _version_tuple(manifest["version"]) > _version_tuple(current_version)
        message = (
            f"نسخه {manifest['version']} آماده دریافت است"
            if available else "LAGSHIFT به‌روز است"
        )
        return UpdateCheck(True, available, message, manifest if available else None)
    except Exception as exc:
        return UpdateCheck(True, False, f"بررسی امن آپدیت ناموفق بود: {str(exc)[:300]}")


def download_verified_installer(manifest: dict, destination: Path | None = None) -> Path:
    url = _validate_https_url(str(manifest["url"]))
    version = str(manifest["version"])
    _version_tuple(version)
    expected_size = int(manifest["size"])
    expected_hash = str(manifest["sha256"]).lower()
    if expected_size <= 0 or expected_size > MAX_INSTALLER_BYTES or not _SHA256_RE.fullmatch(expected_hash):
        raise ValueError("اطلاعات فایل آپدیت معتبر نیست")
    folder = destination or (app_paths.local_dir() / "updates")
    folder.mkdir(parents=True, exist_ok=True)
    final_path = folder / f"LAGSHIFT-{version}-Setup.exe"
    partial = final_path.with_suffix(".part")
    digest = hashlib.sha256()
    total = partial.stat().st_size if partial.exists() else 0
    if total > expected_size:
        partial.unlink(missing_ok=True)
        total = 0
    if total:
        with partial.open("rb") as existing:
            for chunk in iter(lambda: existing.read(1024 * 1024), b""):
                digest.update(chunk)
    headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
    if total:
        headers["Range"] = f"bytes={total}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        with _opener().open(request, timeout=20) as response:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            if total and status != 206:
                # A server may ignore Range. Restart safely instead of appending a
                # complete response to a partial file.
                total = 0
                digest = hashlib.sha256()
                mode = "wb"
            else:
                mode = "ab" if total else "wb"
            if status == 206:
                content_range = str(response.headers.get("Content-Range", ""))
                if not content_range.startswith(f"bytes {total}-"):
                    raise ValueError("پاسخ Resume با موقعیت فایل موقت سازگار نیست")
            with partial.open(mode) as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > expected_size or total > MAX_INSTALLER_BYTES:
                        raise ValueError("حجم دانلود با مانیفست سازگار نیست")
                    digest.update(chunk)
                    output.write(chunk)
        if total != expected_size or digest.hexdigest() != expected_hash:
            raise ValueError("هش یا اندازه فایل آپدیت تأیید نشد")
        os.replace(partial, final_path)
        return final_path
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        # Keep a bounded partial file for the next verified Range request.
        raise RuntimeError("دانلود متوقف شد؛ ادامه امن در تلاش بعدی انجام می‌شود") from exc
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def has_valid_authenticode(path: Path) -> bool:
    """Require a valid Windows publisher signature before launching an installer."""
    if os.name != "nt" or not path.is_file():
        return False
    escaped = str(path).replace("'", "''")
    script = f"(Get-AuthenticodeSignature -LiteralPath '{escaped}').Status"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "valid"
    except (OSError, subprocess.SubprocessError):
        return False


def launch_verified_installer(path: Path) -> tuple[bool, str]:
    if not has_valid_authenticode(path):
        return False, "امضای ناشر ویندوز معتبر نیست؛ نصب برای امنیت متوقف شد"
    try:
        subprocess.Popen([str(path)], close_fds=True)
        return True, "نصب‌کننده امن اجرا شد"
    except OSError as exc:
        return False, f"اجرای نصب‌کننده ممکن نشد: {exc}"
