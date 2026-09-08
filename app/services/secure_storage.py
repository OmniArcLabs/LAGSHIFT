"""Small Windows DPAPI wrapper used for LAGSHIFT secrets."""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

from app.app_info import APP_NAME


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect(data: bytes) -> str:
    """Protect bytes for the current Windows user and return Base64 text."""
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
