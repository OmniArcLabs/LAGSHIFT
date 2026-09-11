"""
سرویس ذخیره‌ی تنظیمات ساده‌ی برنامه (مثل رفتار Tray) در یک فایل JSON.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

from app.app_info import (
    ALLOW_GAMELINK, ALLOW_REMOTE_BACKEND, PRIVACY_VERSION, TERMS_VERSION,
)
from app.services import app_paths

DEFAULTS: Dict[str, Any] = {
    "minimize_to_tray": True,   # پیش‌فرض: بستن پنجره = رفتن به Tray
    "overlay_enabled": False,
    "auto_failover": True,
    "emergency_mode": True,
    "anonymous_radar": False,
    "turbo_mode": False,
    "gamelink_api_url": "",
    "local_quota_mb": 20480,
    "game_detection_enabled": True,
    "game_detection_sound": True,
    "ignored_game_processes": [],
    "dns_selection_mode": "balanced",
    "dns_usage_goal": "balanced",
    "game_server_probe_beta": True,
    "route_auto_rollback": False,
    "air_lite_enabled": True,
    "route_latency_budget_ms": 160,
    "route_standby_count": 2,
    "game_qos_enabled": False,
    "reduce_motion": False,
    "startup_animation_enabled": True,
    "brand_intro_seen": False,
    "automatic_update_checks": True,
    "update_channel": "stable",
    "blackbox_enabled": True,
    "route_dna_enabled": True,
    "route_dna_probe_mode": "light",
    "route_dna_remote_geo": False,
    "route_dna_share_aggregate": False,
    "route_dna_daily_budget_mb": 25,
    "traffic_insight_history": False,
    "last_update_check": "",
    "terms_accepted_version": "",
    "privacy_acknowledged_version": "",
    "terms_accepted_at": "",
}
_LOCK = threading.RLock()


def _settings_file() -> Path:
    return app_paths.migrated_file("settings.json")


def has_current_legal_acceptance(settings: Dict[str, Any] | None = None) -> bool:
    values = settings or load_settings()
    return (
        values.get("terms_accepted_version") == TERMS_VERSION
        and values.get("privacy_acknowledged_version") == PRIVACY_VERSION
    )


def load_settings() -> Dict[str, Any]:
    with _LOCK:
        path = _settings_file()
        if not path.exists():
            save_settings(DEFAULTS)
            return dict(DEFAULTS)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = dict(DEFAULTS)
            merged.update(data)
            if not ALLOW_GAMELINK:
                merged["turbo_mode"] = False
                merged["gamelink_api_url"] = ""
            if not ALLOW_REMOTE_BACKEND:
                merged["anonymous_radar"] = False
                merged["route_dna_remote_geo"] = False
                merged["route_dna_share_aggregate"] = False
            return merged
        except Exception:
            return dict(DEFAULTS)


def save_settings(settings: Dict[str, Any]) -> None:
    with _LOCK:
        path = _settings_file()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)


def set_value(key: str, value: Any) -> Dict[str, Any]:
    with _LOCK:
        if key == "turbo_mode" and not ALLOW_GAMELINK:
            value = False
        if key == "gamelink_api_url" and not ALLOW_GAMELINK:
            value = ""
        if key in {
            "anonymous_radar", "route_dna_remote_geo", "route_dna_share_aggregate",
        } and not ALLOW_REMOTE_BACKEND:
            value = False
        settings = load_settings()
        settings[key] = value
        save_settings(settings)
        return settings
