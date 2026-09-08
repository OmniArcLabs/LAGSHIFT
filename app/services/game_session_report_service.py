"""Privacy-safe post-session summary derived from local measurement history."""
from __future__ import annotations

import statistics
from datetime import datetime, timezone


def begin(game) -> dict:
    history = (getattr(game, "route_profile", {}) or {}).get("history", [])
    return {
        "game": str(getattr(game, "name", "بازی"))[:120],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "history_index": len(history) if isinstance(history, list) else 0,
    }


def finish(game, session: dict, route: str = "direct") -> dict:
    profile = getattr(game, "route_profile", {}) or {}
    history = profile.get("history", []) if isinstance(profile, dict) else []
    start = max(0, int(session.get("history_index", 0) or 0))
    rows = [row for row in history[start:] if isinstance(row, dict)]
    try:
        started = datetime.fromisoformat(str(session.get("started_at", "")))
        duration_s = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    except (TypeError, ValueError):
        duration_s = 0

    def values(field):
        return [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]

    latency = values("latency_ms")
    jitter = values("jitter_ms")
    loss = values("loss")
    return {
        "game": str(session.get("game") or getattr(game, "name", "بازی"))[:120],
        "duration_s": duration_s,
        "samples": len(rows),
        "route": route if route in {"direct", "dns", "warp", "game-mode"} else "direct",
        "median_ms": round(statistics.median(latency)) if latency else None,
        "best_ms": round(min(latency)) if latency else None,
        "worst_ms": round(max(latency)) if latency else None,
        "jitter_ms": round(statistics.mean(jitter), 1) if jitter else None,
        "loss_pct": round(statistics.mean(loss), 1) if loss else None,
        "route_events": sum(max(0, int(row.get("new_endpoints", 0) or 0)) for row in rows),
        "conclusive": bool(latency),
        "privacy": "local aggregate; no endpoint addresses",
    }
