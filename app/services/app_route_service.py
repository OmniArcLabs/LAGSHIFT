"""Local AppRoute decisions, failure diagnosis and privacy-safe learning."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

from app.services import app_paths


HISTORY_LIMIT = 240
VALID_ROUTES = {"current", "dns", "warp", "failed"}
DEFAULT_WARP_MODES = ("warp+doh", "warp+dot", "warp", "tunnel_only", "doh", "dot")


def diagnose(probe: dict | None) -> dict:
    """Turn low-level probe evidence into an honest, user-facing diagnosis."""
    probe = probe or {}
    attempted = max(0, int(probe.get("attempted", 0) or 0))
    resolved = max(0, int(probe.get("resolved", 0) or 0))
    reachable = max(0, int(probe.get("reachable", 0) or 0))
    tls_ok = max(0, int(probe.get("tls_ok", reachable) or 0))
    if attempted == 0:
        return {"code": "no-target", "title": "مقصدی برای آزمایش ثبت نشده",
                "hint": "پروفایل این برنامه باید به‌روزرسانی شود."}
    if resolved == 0:
        return {"code": "dns", "title": "نام سرویس پیدا نشد",
                "hint": "تعویض DNS یا DNS امن می‌تواند این مشکل را برطرف کند."}
    if probe.get("suspected_sinkhole"):
        return {
            "code": "dns-sinkhole",
            "title": "پاسخ DNS به یک مسیر بسته هدایت شده است",
            "hint": (
                "چند مقصد مستقل به یک IP خصوصی و غیرقابل‌دسترسی رسیده‌اند؛ "
                "در این شبکه DNS تنها کافی نیست و یک مسیر ترافیکی سالم لازم است."
            ),
        }
    if reachable == 0:
        return {"code": "transport", "title": "مسیر شبکه بسته است",
                "hint": "DNS پاسخ می‌دهد اما اتصال امن به مقصد شکل نمی‌گیرد؛ WARP می‌تواند آزمایش شود."}
    if tls_ok == 0:
        return {"code": "tls", "title": "ارتباط امن کامل نشد",
                "hint": "شبکه تا سرور می‌رسد اما دست‌دادن TLS تأیید نشد."}
    required = max(1, (attempted + 1) // 2)
    if tls_ok < required:
        return {"code": "partial", "title": "فقط بخشی از سرویس در دسترس است",
                "hint": "بعضی مقصدهای ورود، API یا دانلود هنوز پاسخ معتبر ندارند."}
    return {"code": "healthy", "title": "مسیر سرویس سالم است",
            "hint": "DNS، اتصال و TLS مقصدهای کافی تأیید شدند؛ نتیجه ورود داخل برنامه مشخص می‌شود."}


def network_key(adapter_name: str) -> str:
    """Hash the local adapter label so history does not retain network identity."""
    normalized = " ".join(str(adapter_name or "unknown").strip().casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _history_path():
    return app_paths.migrated_file("app_route_history.json", local=True)


def load_history() -> list[dict]:
    try:
        document = json.loads(_history_path().read_text(encoding="utf-8"))
        rows = document.get("events", []) if isinstance(document, dict) else []
        return [row for row in rows if isinstance(row, dict)][-HISTORY_LIMIT:]
    except (OSError, ValueError, TypeError):
        return []


def record_outcome(*, profile_id: str, mission: str, adapter_name: str,
                   route: str, ok: bool, mode: str = "", median_ms: int = -1,
                   diagnosis: str = "") -> None:
    route = route if route in VALID_ROUTES else "failed"
    event = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile": str(profile_id)[:48],
        "mission": str(mission)[:20],
        "network": network_key(adapter_name),
        "route": route,
        "ok": bool(ok),
        "mode": str(mode)[:24],
        "median_ms": int(median_ms) if isinstance(median_ms, (int, float)) else -1,
        "diagnosis": str(diagnosis)[:32],
    }
    rows = load_history()
    rows.append(event)
    path = _history_path()
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps({"version": 1, "events": rows[-HISTORY_LIMIT:]}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def preferred_warp_modes(profile_id: str, mission: str, adapter_name: str) -> tuple[str, ...]:
    """Put locally successful modes first while retaining every safe fallback."""
    key = network_key(adapter_name)
    successes = [
        row for row in reversed(load_history())
        if row.get("profile") == profile_id and row.get("mission") == mission
        and row.get("network") == key and row.get("route") == "warp"
        and row.get("ok") and row.get("mode") in DEFAULT_WARP_MODES
    ]
    learned = tuple(dict.fromkeys(row["mode"] for row in successes))
    mission_default = {
        "login": ("warp+doh", "warp+dot", "warp", "doh", "dot", "tunnel_only"),
        "download": ("warp", "tunnel_only", "warp+doh", "warp+dot", "doh", "dot"),
        "smart": DEFAULT_WARP_MODES,
    }.get(mission, DEFAULT_WARP_MODES)
    return tuple(dict.fromkeys((*learned, *mission_default)))


def last_success(profile_id: str, mission: str, adapter_name: str) -> dict | None:
    key = network_key(adapter_name)
    return next((
        row for row in reversed(load_history())
        if row.get("profile") == profile_id and row.get("mission") == mission
        and row.get("network") == key and row.get("ok")
    ), None)


def warp_retry_allowed(profile_id: str, mission: str, adapter_name: str,
                       cooldown_minutes: int = 30) -> bool:
    """Avoid repeating a known-dead WARP tournament on every app click."""
    key = network_key(adapter_name)
    latest = next((
        row for row in reversed(load_history())
        if row.get("profile") == profile_id and row.get("mission") == mission
        and row.get("network") == key
    ), None)
    if not latest or latest.get("mode") != "warp-unavailable":
        return True
    try:
        failed_at = datetime.fromisoformat(str(latest["at"]))
    except (KeyError, TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - failed_at >= timedelta(
        minutes=max(1, int(cooldown_minutes))
    )
