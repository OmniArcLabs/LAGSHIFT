"""Encrypted, bounded recovery journal with no adapter or endpoint identity."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.services import app_paths, secure_storage


_ALLOWED_ACTIONS = {
    "dns-change", "dns-restore", "qos-change", "qos-restore",
    "warp-connect", "warp-restore", "emergency-reset"
}
_ALLOWED_OUTCOMES = {"started", "success", "failed", "partial"}


def _path():
    return app_paths.local_dir() / "recovery-journal.dpapi"


def _warp_path():
    return app_paths.local_dir() / "warp-recovery.dpapi"


def _load() -> list[dict]:
    try:
        raw = secure_storage.unprotect(_path().read_text(encoding="ascii"))
        rows = json.loads(raw.decode("utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def record(action: str, outcome: str, detail: str = "") -> None:
    if action not in _ALLOWED_ACTIONS or outcome not in _ALLOWED_OUTCOMES:
        raise ValueError("رویداد بازیابی معتبر نیست")
    from app.services.crash_service import sanitize
    safe_detail = "".join(
        ch for ch in sanitize(detail, 120)
        if ch.isalnum() or ch in " -_،؛[]"
    )
    rows = _load()[-49:]
    rows.append({
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "action": action,
        "outcome": outcome,
        "detail": safe_detail,
    })
    path = _path()
    temporary = path.with_suffix(".tmp")
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    temporary.write_text(secure_storage.protect(payload), encoding="ascii")
    os.replace(temporary, path)


def safe_record(action: str, outcome: str, detail: str = "") -> bool:
    """Best-effort journal write that can never mask a network operation result."""
    try:
        record(action, outcome, detail)
        return True
    except (OSError, ValueError, TypeError):
        return False


def receipt(limit: int = 8) -> dict:
    rows = _load()
    selected = rows[-max(1, min(20, int(limit))):]
    pending_dns = False
    pending_qos = False
    pending_warp = bool(warp_intent())
    for row in rows:
        if row.get("action") == "dns-change" and row.get("outcome") == "success":
            pending_dns = True
        elif row.get("action") in {"dns-restore", "emergency-reset"} and row.get("outcome") == "success":
            pending_dns = False
        if row.get("action") == "qos-change" and row.get("outcome") == "success":
            pending_qos = True
        elif row.get("action") in {"qos-restore", "emergency-reset"} and row.get("outcome") == "success":
            pending_qos = False
    return {"events": selected, "pending_dns": pending_dns,
            "pending_qos": pending_qos, "pending_warp": pending_warp,
            "count": len(rows)}


def set_warp_intent(original_mode: str, original_protocol: str, expected_mode: str) -> bool:
    allowed_modes = {"warp", "warp+doh", "warp+dot", "tunnel_only", "doh", "dot", "proxy", ""}
    allowed_protocols = {"masque", "wireguard", "dns", ""}
    mode = str(original_mode).casefold()
    protocol = str(original_protocol).casefold()
    expected = str(expected_mode).casefold()
    if not expected or expected not in allowed_modes:
        return False
    # An older official client may not report its original preference. The
    # expected app-owned mode must be exact; unknown restoration preferences
    # are stored as empty and never guessed.
    mode = mode if mode in allowed_modes else ""
    protocol = protocol if protocol in allowed_protocols else ""
    document = {
        "schema": 1, "original_mode": mode,
        "original_protocol": protocol, "expected_mode": expected,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    try:
        payload = json.dumps(document, sort_keys=True).encode("utf-8")
        temporary = _warp_path().with_suffix(".tmp")
        temporary.write_text(secure_storage.protect(payload), encoding="ascii")
        os.replace(temporary, _warp_path())
        return True
    except OSError:
        return False


def warp_intent() -> dict:
    try:
        payload = secure_storage.unprotect(_warp_path().read_text(encoding="ascii"))
        document = json.loads(payload.decode("utf-8"))
        if document.get("schema") != 1:
            return {}
        return {key: str(document.get(key, ""))[:60] for key in (
            "original_mode", "original_protocol", "expected_mode", "created_at"
        )}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def clear_warp_intent() -> None:
    _warp_path().unlink(missing_ok=True)


def clear() -> None:
    _path().unlink(missing_ok=True)
    clear_warp_intent()
