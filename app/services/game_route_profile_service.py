"""Local-only learning for per-game destinations, ports, quality and safe MTU."""
from __future__ import annotations

import ipaddress
import json
import subprocess
from datetime import datetime, timezone

from app.services import game_server_probe_service


PROFILE_VERSION = 1
MAX_ENDPOINTS = 64
MAX_SEEN_KEYS = 256
STALE_AFTER_DAYS = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _endpoint_key(item: dict) -> str:
    return f"{item.get('host')}:{int(item.get('port', 0))}/{item.get('transport', 'tcp')}"


def merge_observation(existing: dict | None, endpoints: list[dict],
                      measurements: list[dict] | None = None,
                      observed_at: str | None = None) -> dict:
    """Merge one local observation while retaining frequency and last-known quality."""
    now = observed_at or _utc_now()
    profile = dict(existing or {})
    known = {item["key"]: dict(item) for item in profile.get("endpoints", []) if item.get("key")}
    measured = {_endpoint_key(item): item for item in (measurements or [])}
    seen_keys = list(profile.get("seen_keys", []))
    seen_set = set(seen_keys)
    for endpoint in endpoints:
        key = _endpoint_key(endpoint)
        if key not in seen_set:
            seen_keys.append(key)
            seen_set.add(key)
        item = known.get(key, {
            "key": key, "host": endpoint["host"], "port": int(endpoint["port"]),
            "transport": endpoint.get("transport", "tcp"), "seen_count": 0,
            "first_seen": now,
        })
        item["source"] = endpoint.get("source", item.get("source", "live_connection"))
        item["seen_count"] = int(item.get("seen_count", 0)) + 1
        item["last_seen"] = now
        quality = measured.get(key, {})
        for field in ("latency_ms", "jitter_ms", "loss", "score", "label", "method"):
            if field in quality:
                item[field] = quality[field]
        known[key] = item
    ranked = sorted(
        known.values(),
        key=lambda item: (
            item.get("transport") != "udp", -int(item.get("seen_count", 0)),
            -int(item.get("score", 0)),
        ),
    )[:MAX_ENDPOINTS]
    observations = int(profile.get("observations", 0)) + 1
    udp_count = sum(item.get("transport") == "udp" for item in ranked)
    measured_count = sum("score" in item for item in ranked)
    confidence = min(95, 15 + observations * 10 + min(30, len(ranked) * 4)
                     + min(15, udp_count * 3) + min(15, measured_count * 3))
    return {
        **profile, "version": PROFILE_VERSION, "updated_at": now,
        "stale_after_days": STALE_AFTER_DAYS, "observations": observations,
        "confidence": confidence, "endpoints": ranked,
        "ports": sorted({int(item["port"]) for item in ranked}),
        "udp_ports": sorted({int(item["port"]) for item in ranked if item["transport"] == "udp"}),
        "tcp_ports": sorted({int(item["port"]) for item in ranked if item["transport"] == "tcp"}),
        "seen_keys": seen_keys[-MAX_SEEN_KEYS:],
    }


def discover_path_mtu(host: str) -> int | None:
    """Conservative IPv4 Path-MTU discovery using Windows' do-not-fragment ping."""
    try:
        if ipaddress.ip_address(host).version != 4:
            return 1280
    except ValueError:
        return None
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    low, high, best = 1172, 1472, None  # ICMP payload; add 28 bytes for IPv4+ICMP.
    while low <= high:
        middle = (low + high) // 2
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "700", "-f", "-l", str(middle), host],
                capture_output=True, timeout=1.5, creationflags=creation_flags,
            )
            success = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return None
        if success:
            best, low = middle, middle + 1
        else:
            high = middle - 1
    return max(1200, min(1500, best + 28)) if best is not None else None


def learn(process_name: str, existing: dict | None = None,
          mode: str = "balanced", context: str = "unknown",
          scan_open_logs: bool = True) -> dict:
    live_endpoints = game_server_probe_service.discover_game_endpoints(process_name, limit=12)
    if not live_endpoints:
        live_endpoints = game_server_probe_service.capture_game_udp_endpoints(
            process_name, duration_s=1.8, limit=12
        )
    log_endpoints = (
        game_server_probe_service.discover_log_endpoints(process_name, limit=6)
        if scan_open_logs else []
    )
    endpoint_map = {_endpoint_key(item): item for item in log_endpoints}
    endpoint_map.update({_endpoint_key(item): item for item in live_endpoints})
    endpoints = list(endpoint_map.values())
    if not endpoints:
        # A lobby can be fully online while Windows exposes no remote UDP address.
        # Keep a truthful waiting profile instead of treating that as a failure.
        now = _utc_now()
        profile = dict(existing or {})
        profile.update({
            "version": PROFILE_VERSION, "updated_at": now,
            "stale_after_days": STALE_AFTER_DAYS,
            "recommended_mtu": int(profile.get("recommended_mtu", 1400)),
            "endpoints": list(profile.get("endpoints", [])),
            "ports": list(profile.get("ports", [])),
            "udp_ports": list(profile.get("udp_ports", [])),
            "tcp_ports": list(profile.get("tcp_ports", [])),
            "observations": int(profile.get("observations", 0)),
            "confidence": int(profile.get("confidence", 10)),
            "lobby_waiting": True, "changed_endpoints": 0,
            "local_udp_ports": sorted(
                game_server_probe_service.game_udp_local_ports(process_name)
            )[:64],
            "anti_cheat": game_server_probe_service.detect_active_anti_cheat(),
            "log_hints": 0,
        })
        profile.setdefault("recommendations", {
            "packet_payload": 1320, "fec": False, "udp_priority": False, "low_mtu": False,
        })
        return profile
    measurements = [
        game_server_probe_service.benchmark_endpoint(item, attempts=3, mode=mode)
        for item in live_endpoints[:3]
    ]
    profile = merge_observation(existing, endpoints, measurements)
    profile["lobby_waiting"] = False
    target = next((item for item in measurements if item.get("available")), None)
    if target:
        mtu = discover_path_mtu(target["host"])
        if mtu:
            # Leave a small safety margin for variable routes and encapsulation.
            profile["recommended_mtu"] = max(1200, min(1420, mtu - 40))
            profile["path_mtu"] = mtu
    profile.setdefault("recommended_mtu", 1400)
    profile["changed_endpoints"] = sum(
        _endpoint_key(item) not in {old.get("key") for old in (existing or {}).get("endpoints", [])}
        for item in endpoints
    )
    old_count = max(1, len((existing or {}).get("endpoints", [])))
    profile["route_drift"] = bool(existing and profile["changed_endpoints"] / old_count >= 0.6)
    profile["log_hints"] = len(log_endpoints)
    profile["anti_cheat"] = game_server_probe_service.detect_active_anti_cheat()

    available = [item for item in measurements if item.get("available")]
    average_loss = round(sum(item.get("loss", 100) for item in available) / len(available), 1) if available else None
    average_jitter = round(sum(item.get("jitter_ms", 0) for item in available) / len(available)) if available else None
    mtu = int(profile["recommended_mtu"])
    profile["recommendations"] = {
        "packet_payload": max(1000, mtu - 80),
        "fec": bool(available and (average_loss >= 2 or average_jitter >= 15)),
        "udp_priority": bool(profile.get("udp_ports")),
        "low_mtu": mtu < 1380,
    }
    contexts = dict(profile.get("contexts", {}))
    current_context = dict(contexts.get(context, {}))
    current_context.update({
        "last_seen": profile["updated_at"],
        "observations": int(current_context.get("observations", 0)) + 1,
        "mtu": mtu,
    })
    if available:
        current_context.update({
            "latency_ms": min(item["latency_ms"] for item in available),
            "loss": average_loss, "jitter_ms": average_jitter,
        })
    contexts[context] = current_context
    profile["contexts"] = contexts
    history = list(profile.get("history", []))
    history.append({
        "at": profile["updated_at"], "context": context,
        "endpoints": len(endpoints), "new_endpoints": profile["changed_endpoints"],
        "latency_ms": current_context.get("latency_ms"),
        "jitter_ms": average_jitter, "loss": average_loss, "mtu": mtu,
    })
    profile["history"] = history[-50:]
    return profile


def summary(profile: dict | None) -> dict:
    if not profile:
        return {"available": False}
    try:
        updated = datetime.fromisoformat(profile["updated_at"])
        age_days = max(0, (datetime.now(timezone.utc) - updated).days)
    except (KeyError, TypeError, ValueError):
        age_days = STALE_AFTER_DAYS + 1
    confidence = int(profile.get("confidence", 0))
    if age_days > STALE_AFTER_DAYS:
        confidence = max(0, confidence - min(60, age_days - STALE_AFTER_DAYS))
    latencies = [
        item.get("latency_ms") for item in profile.get("history", [])
        if isinstance(item.get("latency_ms"), (int, float))
    ]
    last_latency = latencies[-1] if latencies else None
    distance_hint = (
        "مسیر نزدیک" if last_latency is not None and last_latency <= 55 else
        "مسیر میان‌برد" if last_latency is not None and last_latency <= 120 else
        "مسیر دور" if last_latency is not None else "نامشخص"
    )
    return {
        "available": True, "age_days": age_days, "stale": age_days > STALE_AFTER_DAYS,
        "confidence": confidence, "endpoints": len(profile.get("endpoints", [])),
        "udp_ports": profile.get("udp_ports", []), "tcp_ports": profile.get("tcp_ports", []),
        "mtu": int(profile.get("recommended_mtu", 1400)),
        "observations": int(profile.get("observations", 0)),
        "drift": bool(profile.get("route_drift", False)),
        "contexts": len(profile.get("contexts", {})),
        "history": len(profile.get("history", [])),
        "recommendations": profile.get("recommendations", {}),
        "anti_cheat": profile.get("anti_cheat", []),
        "log_hints": int(profile.get("log_hints", 0)),
        "distance_hint": distance_hint,
        "lobby_waiting": bool(profile.get("lobby_waiting", False)),
        "local_udp_ports": profile.get("local_udp_ports", []),
    }


def export_recipe(game_name: str, process_name: str, profile: dict) -> str:
    """Portable recipe with routing observations only; never contains tunnel credentials."""
    document = {
        "format": "LAGSHIFT-Route-Recipe", "version": 1,
        "game": game_name, "process": process_name,
        "profile": profile,
    }
    return json.dumps(document, ensure_ascii=False, indent=2)


def import_recipe(text: str) -> tuple[str, str, dict]:
    document = json.loads(text)
    if document.get("format") not in {"LAGSHIFT-Route-Recipe", "GameDNS-Route-Recipe"} or document.get("version") != 1:
        raise ValueError("فرمت Route Recipe معتبر نیست")
    profile = document.get("profile")
    if not isinstance(profile, dict) or not isinstance(profile.get("endpoints", []), list):
        raise ValueError("پروفایل Route Recipe ناقص است")
    if len(profile.get("endpoints", [])) > MAX_ENDPOINTS:
        raise ValueError("تعداد مقصدهای Route Recipe بیش از حد مجاز است")
    for endpoint in profile.get("endpoints", []):
        if not isinstance(endpoint, dict):
            raise ValueError("Route Recipe شامل مقصد نامعتبر است")
        host, port = endpoint.get("host", ""), int(endpoint.get("port", 0))
        if not ipaddress.ip_address(host).is_global or not 1 <= port <= 65535:
            raise ValueError("Route Recipe شامل مقصد نامعتبر است")
    profile["recommended_mtu"] = max(1200, min(1420, int(profile.get("recommended_mtu", 1400))))
    if not isinstance(profile.get("recommendations", {}), dict):
        profile["recommendations"] = {}
    if not isinstance(profile.get("contexts", {}), dict):
        profile["contexts"] = {}
    if not isinstance(profile.get("history", []), list):
        profile["history"] = []
    for field in ("udp_ports", "tcp_ports", "ports"):
        values = profile.get(field, [])
        profile[field] = [int(value) for value in values[:64]] if isinstance(values, list) else []
    seen_keys = profile.get("seen_keys", [])
    profile["seen_keys"] = [str(value)[:300] for value in seen_keys[:MAX_SEEN_KEYS]] \
        if isinstance(seen_keys, list) else []
    return str(document.get("game", "")).strip(), str(document.get("process", "")).strip(), profile
