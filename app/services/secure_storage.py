"""Per-user protected storage using DPAPI or the macOS login Keychain."""
from __future__ import annotations

import base64
import ctypes
import getpass
import os
import secrets
import subprocess

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if os.name == "nt":
    from ctypes import wintypes
else:
    wintypes = None

from app.app_info import APP_NAME


if wintypes is not None:
    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    if wintypes is None:
        raise RuntimeError("DPAPI is available only on Windows")
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


_MAC_KEYCHAIN_SERVICE = "com.omniarc.lagshift.local-state"


def _mac_key() -> bytes:
    """Return a 256-bit local key without writing it to the filesystem."""
    account = getpass.getuser() or "LAGSHIFT"
    find = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-a", account,
         "-s", _MAC_KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True, timeout=8,
    )
    if find.returncode == 0:
        key = base64.b64decode(find.stdout.strip(), validate=True)
        if len(key) != 32:
            raise RuntimeError("کلید محلی Keychain معتبر نیست")
        return key
    key = secrets.token_bytes(32)
    encoded = base64.b64encode(key).decode("ascii")
    add = subprocess.run(
        ["/usr/bin/security", "add-generic-password", "-U", "-a", account,
         "-s", _MAC_KEYCHAIN_SERVICE, "-w", encoded],
        capture_output=True, text=True, timeout=8,
    )
    if add.returncode != 0:
        raise RuntimeError("ذخیره کلید محلی در Keychain ممکن نشد")
    return key


def protect(data: bytes) -> str:
    """Protect bytes for the current OS user and return portable text."""
    if os.name == "posix" and __import__("sys").platform == "darwin":
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(_mac_key()).encrypt(nonce, data, APP_NAME.encode("utf-8"))
        return "mac:" + base64.b64encode(nonce + encrypted).decode("ascii")
    if os.name != "nt":
        return "dev:" + base64.b64encode(data).decode("ascii")
    source, keepalive = _blob(data)
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(
        ctypes.byref(source), APP_NAME, None, None, None, 0x1, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(target.pbData, target.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def unprotect(value: str) -> bytes:
    if value.startswith("mac:"):
        if __import__("sys").platform != "darwin":
            raise RuntimeError("این داده فقط توسط همان حساب macOS قابل خواندن است")
        payload = base64.b64decode(value[4:], validate=True)
        if len(payload) < 29:
            raise RuntimeError("داده محافظت‌شده macOS ناقص است")
        return AESGCM(_mac_key()).decrypt(
            payload[:12], payload[12:], APP_NAME.encode("utf-8")
        )
    if value.startswith("dev:"):
        return base64.b64decode(value[4:])
    if os.name != "nt":
        raise RuntimeError("این داده فقط توسط همان حساب ویندوز قابل خواندن است")
    encrypted = base64.b64decode(value)
    source, keepalive = _blob(encrypted)
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
