"""Opt-in anonymous path-health queue with an optional GameLink endpoint."""
from __future__ import annotations

import json
import platform
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app.app_info import ALLOW_REMOTE_BACKEND, APP_NAME, APP_VERSION
from app.services import app_paths


def _queue_file() -> Path:
    return app_paths.migrated_file("anonymous_radar_queue.json", local=True)


def record_sample(sample: dict, enabled: bool) -> None:
    if not ALLOW_REMOTE_BACKEND or not enabled:
        return
    context = sample.get("route_dna") if isinstance(sample.get("route_dna"), dict) else {}
    geo = context.get("geo") if isinstance(context.get("geo"), dict) else {}
    allowed = {key: sample.get(key) for key in (
        "score", "latency", "jitter", "loss", "mode", "protocol"
    )}
    allowed.update({
        "hour": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00Z"),
        "os": platform.system(),
        "country": str(geo.get("country", ""))[:2],
        "asn": str(context.get("asn", ""))[:16],
        "adapter_kind": str(context.get("adapter_kind", ""))[:16],
        "purpose": str(context.get("purpose", ""))[:16],
    })
    path = _queue_file()
    try:
        queue = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        queue = []
    queue = (queue + [allowed])[-100:]
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def flush(api_base: str, enabled: bool) -> tuple[bool, str]:
    if not ALLOW_REMOTE_BACKEND:
        return False, "ارسال رادار در نسخه عمومی محلی غیرفعال است"
    if not enabled or not api_base.strip():
        return False, "رادار غیرفعال است یا سرور GameLink تنظیم نشده"
    path = _queue_file()
    if not path.exists():
        return True, "داده‌ای برای ارسال وجود ندارد"
    payload = path.read_bytes()
    from app.services import route_dna_service
    base = route_dna_service._public_https_base(api_base)
    if not base:
        return False, "آدرس امن و عمومی GameLink تنظیم نشده"
    request = urllib.request.Request(
        base + "/v1/radar/batch", data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if not 200 <= response.status < 300:
                return False, f"HTTP {response.status}"
        path.unlink(missing_ok=True)
        return True, "ارسال شد"
    except Exception as exc:
        return False, str(exc)
