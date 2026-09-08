"""Game-oriented path scoring based on latency, jitter, loss and stability."""
from __future__ import annotations

from dataclasses import dataclass


MODES = {
    "balanced": "متعادل",
    "competitive": "رقابتی (کمترین تأخیر)",
    "stability": "پایدار (کمترین پکت‌لاس)",
    "udp": "UDP سریع",
}


@dataclass(frozen=True)
class GameQuality:
    score: int
    latency_ms: int
    jitter_ms: int
    packet_loss_pct: float
    stability_pct: float
    label: str


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def calculate_game_quality(latency_ms: int, jitter_ms: int, successes: int,
                           attempts: int, mode: str = "balanced") -> GameQuality:
    """Return a conservative 0..100 score; availability alone never means quality."""
    attempts = max(1, int(attempts or 1))
    successes = max(0, min(attempts, int(successes or 0)))
    stability = successes * 100.0 / attempts
    loss = 100.0 - stability
    latency_component = _clamp(110.0 - max(latency_ms, 0) * 0.55)
    jitter_component = _clamp(105.0 - max(jitter_ms, 0) * 3.0)
    loss_component = _clamp(100.0 - loss * 4.0)

    weights = {
        "competitive": (0.45, 0.25, 0.25, 0.05),
        "stability": (0.20, 0.20, 0.45, 0.15),
        "udp": (0.35, 0.25, 0.30, 0.10),
        "balanced": (0.32, 0.23, 0.35, 0.10),
    }.get(mode, (0.32, 0.23, 0.35, 0.10))
    score = round(
        latency_component * weights[0]
        + jitter_component * weights[1]
        + loss_component * weights[2]
        + stability * weights[3]
    )
    label = "عالی" if score >= 85 else "خوب" if score >= 70 else "متوسط" if score >= 50 else "ضعیف"
    return GameQuality(score, latency_ms, jitter_ms, round(loss, 1), round(stability, 1), label)


def score_path(config, health, mode: str = "balanced") -> GameQuality:
    if not health.available:
        return GameQuality(0, -1, -1, 100.0, 0.0, "قطع")
    quality = calculate_game_quality(
        health.latency_ms, max(health.jitter_ms, 0), health.successes,
        health.attempts or health.successes or 1, mode,
    )
    # A tiny tie-breaker for transports designed around unreliable UDP; actual
    # measured quality remains dominant.
    if mode == "udp" and config.protocol in {"hysteria2", "tuic"}:
        return GameQuality(
            min(100, quality.score + 3), quality.latency_ms, quality.jitter_ms,
            quality.packet_loss_pct, quality.stability_pct, quality.label,
        )
    return quality
