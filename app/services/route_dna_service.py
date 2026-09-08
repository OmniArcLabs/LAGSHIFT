"""Privacy-first, fail-open personalization for LAGSHIFT connection choices.

RouteDNA never changes the network itself.  It observes bounded local facts,
keeps only a hashed network identity, and supplies small ranking hints.  The
real before/after probe remains the authority for every connection decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import ipaddress
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import psutil

from app.app_info import ALLOW_REMOTE_BACKEND
from app.services import app_paths, network_lab_service


SCHEMA_VERSION = 1
HISTORY_LIMIT = 360
MAX_AGE_DAYS = 30
_VALID_PURPOSES = {"game", "login", "download", "voice", "access", "stable", "smart"}
_BANDWIDTH_BYTES = {"light": 512 * 1024, "standard": 3 * 1024 * 1024,
                    "deep": 4 * 1024 * 1024}


def bandwidth_budget_kb(mode: str) -> int:
    return _BANDWIDTH_BYTES.get(mode, _BANDWIDTH_BYTES["light"]) // 1024


def _history_path():
    return app_paths.migrated_file("route_dna_history.json", local=True)


def _budget_path():
    return app_paths.migrated_file("route_dna_budget.json", local=True)


def _adapter_kind(name: str) -> str:
    value = str(name or "").casefold()
    if any(token in value for token in (
        "wwan", "cellular", "mobile", "lte", "5g", "4g", "modem", "همراه",
    )):
        return "mobile"
    if any(token in value for token in ("wi-fi", "wifi", "wireless", "wlan")):
        return "wifi"
    if any(token in value for token in ("ethernet", "lan")):
        return "ethernet"
    if any(token in value for token in ("warp", "tun", "tap", "vpn", "loopback", "virtual")):
        return "virtual"
    return "other"


def _system_geo_hint() -> dict:
    """Return a low-confidence OS hint; never claim IP geolocation."""
    zone = " ".join(time.tzname).casefold()
    if "iran" in zone or "tehran" in zone:
        return {"country": "IR", "region": "ایران (تقریبی)", "source": "system-timezone",
                "confidence": "low"}
    return {"country": "", "region": "نامشخص", "source": "none", "confidence": "none"}


def _network_fingerprint(adapter_name: str, kind: str, mtu: int, gateway: str) -> str:
    # Gateway is used only as ephemeral input and is never written to disk.
    material = f"{adapter_name.casefold()}|{kind}|{int(mtu)}|{gateway}"
    return hashlib.sha256(material.encode("utf-8", "ignore")).hexdigest()[:20]


def _network_group(context: dict) -> str:
    """Group coarse operator/region hints without persisting their readable values."""
    material = "|".join((
        str(context.get("asn", "")),
        str((context.get("geo") or {}).get("country", "")),
        str(context.get("adapter_kind", "other")),
    ))
    if not str(context.get("asn", "")):
        return ""
    return hashlib.sha256(material.encode("utf-8", "ignore")).hexdigest()[:12]


def snapshot(adapter_name: str, purpose: str = "smart", *, sample_pressure: bool = True,
             remote_hint: dict | None = None, sample_gateway: bool = False) -> dict:
    """Collect bounded local network context. Every probe is optional/fail-open."""
    purpose = purpose if purpose in _VALID_PURPOSES else "smart"
    kind = _adapter_kind(adapter_name)
    try:
        stats = psutil.net_if_stats().get(adapter_name)
        addresses = psutil.net_if_addrs().get(adapter_name, [])
    except Exception:
        stats, addresses = None, []
    ipv4 = [row.address for row in addresses if row.family == socket.AF_INET]
    ipv6 = [row.address for row in addresses if row.family == socket.AF_INET6]
    mtu = int(getattr(stats, "mtu", 0) or 0)
    link_mbps = int(getattr(stats, "speed", 0) or 0)
    gateway = ""
    try:
        gateway = network_lab_service.default_gateway()
    except Exception:
        pass
    pressure = {"active": None, "adapters": []}
    if sample_pressure:
        try:
            pressure = network_lab_service.traffic_pressure(0.15)
        except Exception:
            pass
    active = pressure.get("active") or {}
    utilization = active.get("utilization_pct")
    busy = bool(
        (utilization is not None and utilization >= 65)
        or float(active.get("down_mbps", 0) or 0) >= 15
        or float(active.get("up_mbps", 0) or 0) >= 5
    )
    wifi = network_lab_service.wifi_link_info(adapter_name) if kind == "wifi" else {
        "available": False, "signal_pct": None, "rx_mbps": None,
        "tx_mbps": None, "weak": False,
    }
    gateway_quality = network_lab_service.gateway_quality() if sample_gateway else {
        "available": False, "median_ms": -1, "jitter_ms": -1, "loss": 0.0,
    }
    hint = sanitize_remote_hint(remote_hint)
    return {
        "version": SCHEMA_VERSION,
        "network": _network_fingerprint(adapter_name, kind, mtu, gateway),
        "adapter_kind": kind,
        "ipv4": bool(ipv4), "ipv6": bool(ipv6),
        # Traceroute can only provide a conservative probability, never proof.
        "cgnat": network_lab_service.cgnat_hint() if sample_gateway else "unknown",
        "mtu": mtu, "link_mbps": link_mbps,
        "wifi_signal_pct": wifi.get("signal_pct"),
        "wifi_weak": bool(wifi.get("weak")),
        "gateway_quality": gateway_quality,
        "pressure": "busy" if busy else "normal",
        "down_mbps": float(active.get("down_mbps", 0) or 0),
        "up_mbps": float(active.get("up_mbps", 0) or 0),
        "purpose": purpose,
        "geo": hint.get("geo") or _system_geo_hint(),
        "asn": hint.get("asn", ""), "operator": hint.get("operator", ""),
        "remote_geo_used": bool(hint),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def summarize(context: dict) -> str:
    labels = {"wifi": "Wi‑Fi", "ethernet": "کابل", "mobile": "اینترنت همراه",
              "virtual": "کارت مجازی", "other": "شبکه"}
    family = "IPv4/IPv6" if context.get("ipv4") and context.get("ipv6") else (
        "IPv6" if context.get("ipv6") else "IPv4" if context.get("ipv4") else "IP نامشخص"
    )
    load = "شبکه پرترافیک است؛ تست سبک اجرا می‌شود" if context.get("pressure") == "busy" else "فشار شبکه عادی است"
    weak = " · سیگنال Wi‑Fi ضعیف" if context.get("wifi_weak") else ""
    operator = f" · {context.get('operator')}" if context.get("operator") else ""
    return f"{labels.get(context.get('adapter_kind'), 'شبکه')} · {family} · {load}{weak}{operator}"


def _public_https_base(api_base: str) -> str:
    value = str(api_base or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"}:
        return ""
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            return ""
    except ValueError:
        pass
    return value


def sanitize_remote_hint(value: dict | None) -> dict:
    """Allow only coarse metadata; never accept or return an IP address."""
    if not isinstance(value, dict):
        return {}
    country = str(value.get("country", "")).upper()
    region = str(value.get("region", ""))[:64]
    city = str(value.get("city", ""))[:64]
    operator = str(value.get("operator", ""))[:80]
    try:
        asn_number = int(value.get("asn", 0) or 0)
    except (TypeError, ValueError):
        asn_number = 0
    if len(country) != 2 or not country.isalpha():
        country = ""
    asn = f"AS{asn_number}" if 0 < asn_number <= 4_294_967_295 else ""
    if not any((country, region, city, operator, asn)):
        return {}
    area = "، ".join(part for part in (city, region) if part) or country or "نامشخص"
    return {"geo": {"country": country, "region": area, "source": "edge",
                    "confidence": "medium"}, "asn": asn, "operator": operator}


def fetch_remote_hint(api_base: str, enabled: bool, timeout_s: float = 4.0) -> dict:
    """Fetch opt-in coarse edge metadata. The client never sends its IP in a payload."""
    if not ALLOW_REMOTE_BACKEND:
        return {}
    base = _public_https_base(api_base)
    if not enabled or not base:
        return {}
    request = urllib.request.Request(
        base + "/v1/network/hint", method="GET",
        headers={"Accept": "application/json", "User-Agent": "LAGSHIFT/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, min(8.0, timeout_s))) as response:
            payload = response.read(4097)
        if len(payload) > 4096:
            return {}
        return sanitize_remote_hint(json.loads(payload.decode("utf-8")))
    except Exception:
        return {}


def measure_controlled_bandwidth(api_base: str, mode: str, *, deep_confirmed: bool = False,
                                 network_busy: bool = False, timeout_s: float = 15.0) -> dict:
    """Perform a bounded download-only probe against the configured LAGSHIFT edge."""
    mode = mode if mode in _BANDWIDTH_BYTES else "light"
    if network_busy:
        return {"ok": False, "skipped": True, "reason": "network-busy", "mode": mode}
    if mode == "deep" and not deep_confirmed:
        return {"ok": False, "skipped": True, "reason": "confirmation-required", "mode": mode}
    if not ALLOW_REMOTE_BACKEND:
        return {"ok": False, "skipped": True, "reason": "local-stable", "mode": mode}
    base = _public_https_base(api_base)
    if not base:
        return {"ok": False, "skipped": True, "reason": "backend-unconfigured", "mode": mode}
    size = _BANDWIDTH_BYTES[mode]
    url = f"{base}/v1/probe/download?bytes={size}"
    started = time.perf_counter()
    received = 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "LAGSHIFT/1"})
        with urllib.request.urlopen(request, timeout=max(3.0, min(30.0, timeout_s))) as response:
            while received <= size:
                chunk = response.read(min(64 * 1024, size + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
        elapsed = max(0.001, time.perf_counter() - started)
        if received != size:
            return {"ok": False, "skipped": False, "reason": "incomplete",
                    "mode": mode, "bytes": received}
        return {"ok": True, "skipped": False, "mode": mode, "bytes": received,
                "seconds": round(elapsed, 3),
                "download_mbps": round(received * 8 / elapsed / 1_000_000, 2)}
    except Exception as exc:
        return {"ok": False, "skipped": False, "reason": type(exc).__name__,
                "mode": mode, "bytes": received}


def enrich_probe(context: dict, probe: dict | None) -> dict:
    result = dict(context or {})
    probe = probe or {}
    result["probe"] = {
        "attempted": int(probe.get("attempted", 0) or 0),
        "resolved": int(probe.get("resolved", 0) or 0),
        "reachable": int(probe.get("reachable", 0) or 0),
        "tls_ok": int(probe.get("tls_ok", 0) or 0),
        "median_ms": int(probe.get("median_ms", -1) or -1),
        "suspected_sinkhole": bool(probe.get("suspected_sinkhole")),
    }
    return result


def route_score(*, success: bool, latency_ms: int = -1, jitter_ms: int = -1,
                loss: float = 0.0, purpose: str = "smart") -> int:
    if not success:
        return 0
    latency = 50 if latency_ms < 0 else max(0, min(100, 108 - latency_ms * 0.45))
    stability = max(0, min(100, 100 - max(0, jitter_ms) * 2 - max(0.0, loss) * 5))
    latency_weight = 0.60 if purpose in {"game", "voice"} else 0.35
    stability_weight = 1.0 - latency_weight
    return round(latency * latency_weight + stability * stability_weight)


def load_history() -> list[dict]:
    try:
        document = json.loads(_history_path().read_text(encoding="utf-8"))
        rows = document.get("events", []) if isinstance(document, dict) else []
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        kept = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                if datetime.fromisoformat(str(row["at"])) >= cutoff:
                    kept.append(row)
            except (KeyError, TypeError, ValueError):
                continue
        return kept[-HISTORY_LIMIT:]
    except (OSError, ValueError, TypeError):
        return []


def record(context: dict, *, target: str, route: str, success: bool,
           latency_ms: int = -1, jitter_ms: int = -1, loss: float = 0.0) -> None:
    """Persist only bounded, anonymous observations; never public/local IPs."""
    event = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": str(context.get("network", ""))[:20],
        "network_group": _network_group(context),
        "target": str(target)[:64], "purpose": str(context.get("purpose", "smart"))[:16],
        "route": str(route)[:40], "ok": bool(success),
        "score": route_score(success=success, latency_ms=latency_ms,
                             jitter_ms=jitter_ms, loss=loss,
                             purpose=str(context.get("purpose", "smart"))),
        "latency_ms": int(latency_ms) if isinstance(latency_ms, (int, float)) else -1,
        "hour_bucket": datetime.now().hour // 4,
    }
    rows = load_history()
    rows.append(event)
    path = _history_path()
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps({"version": SCHEMA_VERSION, "events": rows[-HISTORY_LIMIT:]},
                                        ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prior(context: dict, target: str, route: str) -> dict:
    matches = [row for row in load_history()
               if row.get("network") == context.get("network")
               and row.get("target") == target and row.get("purpose") == context.get("purpose")
               and row.get("route") == route]
    group_fallback = False
    if not matches and _network_group(context):
        group_fallback = True
        matches = [row for row in load_history()
                   if row.get("network_group") == _network_group(context)
                   and row.get("target") == target
                   and row.get("purpose") == context.get("purpose")
                   and row.get("route") == route]
    if not matches:
        return {"samples": 0, "confidence": "experimental", "score": 0,
                "success_rate": 0.0, "scope": "none"}
    recent = matches[-12:]
    now = datetime.now(timezone.utc)
    weighted = []
    for row in recent:
        try:
            age_days = max(0.0, (now - datetime.fromisoformat(str(row["at"]))).total_seconds() / 86400)
        except (KeyError, TypeError, ValueError):
            age_days = MAX_AGE_DAYS
        weight = max(0.10, 0.5 ** (age_days / 10.0))
        weighted.append((row, weight))
    success_weight = sum(weight for row, weight in weighted if row.get("ok"))
    total_weight = sum(weight for _, weight in weighted) or 1.0
    score = round(sum(int(row.get("score", 0)) * weight for row, weight in weighted) / total_weight)
    confidence = "high" if len(recent) >= 6 else "medium" if len(recent) >= 3 else "experimental"
    if group_fallback:
        confidence = "experimental"
        score = round(score * 0.6)
    return {"samples": len(recent), "confidence": confidence, "score": score,
            "success_rate": round(success_weight * 100 / total_weight, 1),
            "scope": "operator-group" if group_fallback else "network"}


def score_candidate(candidate: dict, purpose: str = "smart") -> int:
    """One honest scoring surface shared by DNS, app, game, voice and download."""
    if not candidate.get("available", candidate.get("success", False)):
        return 0
    latency = int(candidate.get("latency_ms", candidate.get("median_ms", -1)) or -1)
    jitter = int(candidate.get("jitter_ms", 0) or 0)
    loss = float(candidate.get("loss", candidate.get("packet_loss_pct", 0)) or 0)
    reliability = float(candidate.get("success_rate", 100) or 0)
    tls_ratio = float(candidate.get("tls_ratio", 1.0) or 0)
    download = float(candidate.get("download_mbps", 0) or 0)
    base = route_score(success=True, latency_ms=latency, jitter_ms=jitter,
                       loss=loss, purpose=purpose)
    if purpose == "download":
        throughput_score = min(100.0, download * 4) if download > 0 else 45.0
        result = base * 0.20 + reliability * 0.30 + throughput_score * 0.50
    elif purpose in {"login", "access"}:
        result = base * 0.25 + reliability * 0.35 + max(0, min(100, tls_ratio * 100)) * 0.40
    else:
        result = base * 0.75 + reliability * 0.25
    return round(max(0.0, min(100.0, result)))


def tournament(candidates: list[dict], purpose: str = "smart", limit: int = 3) -> dict:
    """Remove failed candidates, rank the live evidence and retain finalists."""
    ranked = []
    for candidate in candidates:
        row = dict(candidate)
        row["route_dna_score"] = score_candidate(row, purpose)
        if row["route_dna_score"] > 0:
            ranked.append(row)
    ranked.sort(key=lambda row: (-row["route_dna_score"],
                                 int(row.get("latency_ms", row.get("median_ms", 999999)) or 999999)))
    finalists = ranked[:max(1, min(5, int(limit)))]
    return {"tested": len(candidates), "healthy": len(ranked), "finalists": finalists,
            "winner": finalists[0] if finalists else None}


def personalize_ranked_dns(ranking: list[dict], context: dict, target: str) -> list[dict]:
    """Use memory only as a tie-breaker; live benchmark remains dominant."""
    decorated = []
    for index, row in enumerate(ranking):
        profile = row.get("profile")
        memory = prior(context, target, f"dns:{getattr(profile, 'name', '')}")
        live = float(row.get("score", 0) or 0)
        bonus = min(4.0, memory["samples"] * 0.5) if memory["success_rate"] >= 70 else 0.0
        decorated.append((-(live + bonus), index, row))
    return [row for _, _, row in sorted(decorated)]


def should_switch(active_score: int, candidate_score: int, bad_samples: int,
                  *, minimum_gain: int = 8, confirmations: int = 2) -> bool:
    """Hysteresis: one noisy sample must never cause a route handoff."""
    return bad_samples >= confirmations and candidate_score >= active_score + minimum_gain


def detect_drift(previous: dict | None, current: dict | None) -> dict:
    previous, current = previous or {}, current or {}
    if not previous:
        return {"changed": False, "reason": "نمونه قبلی وجود ندارد"}
    if previous.get("network") != current.get("network"):
        return {"changed": True, "reason": "شبکه یا Gateway تغییر کرده است"}
    if previous.get("adapter_kind") != current.get("adapter_kind"):
        return {"changed": True, "reason": "نوع اتصال تغییر کرده است"}
    if (previous.get("ipv4"), previous.get("ipv6")) != (current.get("ipv4"), current.get("ipv6")):
        return {"changed": True, "reason": "خانواده IP تغییر کرده است"}
    return {"changed": False, "reason": "مسیر ورودی پایدار است"}


def candidate_registry(*, dns_names=(), warp_available: bool = False,
                       direct_available: bool = True) -> list[dict]:
    rows = []
    if direct_available:
        rows.append({"id": "direct", "kind": "direct", "label": "مسیر فعلی"})
    rows.extend({"id": f"dns:{name}", "kind": "dns", "label": str(name)}
                for name in dns_names)
    if warp_available:
        rows.extend({"id": f"warp:{mode}", "kind": "warp", "label": mode}
                    for mode in ("warp+doh", "warp+dot", "warp", "tunnel_only", "doh", "dot"))
    return rows


def explain_choice(context: dict, *, route: str, probe: dict | None = None,
                   target: str = "") -> str:
    probe = probe or {}
    memory = prior(context, target, route) if target else {
        "samples": 0, "confidence": "experimental", "success_rate": 0.0,
    }
    confidence_labels = {"high": "اطمینان بالا", "medium": "اطمینان متوسط",
                         "experimental": "آزمایشی"}
    facts = []
    if int(probe.get("tls_ok", 0) or 0):
        facts.append(f"{probe.get('tls_ok')} مقصد امن پاسخ داد")
    if int(probe.get("median_ms", -1) or -1) >= 0:
        facts.append(f"پاسخ معمول {probe.get('median_ms')}ms")
    if memory.get("samples"):
        scope = "گروه ناشناس همین اپراتور" if memory.get("scope") == "operator-group" else "همین شبکه"
        facts.append(f"{memory['samples']} نتیجه قبلی {scope}")
    if not facts:
        facts.append("انتخاب فقط پس از تست زنده تأیید می‌شود")
    return f"{'، '.join(facts)} · {confidence_labels.get(memory.get('confidence'), 'آزمایشی')}"


def probe_policy(context: dict, *, game_running: bool = False,
                 requested: str = "light") -> dict:
    mode = requested if requested in {"light", "standard", "deep"} else "light"
    if game_running or context.get("pressure") == "busy":
        mode = "light"
    budgets = {
        "light": {"seconds": 4, "max_kb": 96,
                  "download_kb": _BANDWIDTH_BYTES["light"] // 1024, "rounds": 1},
        "standard": {"seconds": 10, "max_kb": 512,
                     "download_kb": _BANDWIDTH_BYTES["standard"] // 1024, "rounds": 2},
        "deep": {"seconds": 25, "max_kb": 4096,
                 "download_kb": _BANDWIDTH_BYTES["deep"] // 1024, "rounds": 4},
    }
    return {"mode": mode, **budgets[mode], "reason": (
        "بازی یا ترافیک سنگین؛ آزمایش سبک" if mode == "light" and
        (game_running or context.get("pressure") == "busy") else "بودجه انتخاب‌شده"
    )}


def reserve_probe_budget(requested_kb: int, daily_limit_mb: int = 25) -> dict:
    """Atomically reserve an estimated probe allowance; fail closed to light mode."""
    today = datetime.now(timezone.utc).date().isoformat()
    limit_kb = max(1, min(500, int(daily_limit_mb))) * 1024
    requested = max(0, min(8192, int(requested_kb)))
    path = _budget_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError, TypeError):
        document = {}
    used = int(document.get("used_kb", 0) or 0) if document.get("day") == today else 0
    allowed = used + requested <= limit_kb
    reserved = requested if allowed else min(96, max(0, limit_kb - used))
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps({"version": 1, "day": today,
                                         "used_kb": used + reserved}), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"allowed": allowed, "reserved_kb": reserved,
            "remaining_kb": max(0, limit_kb - used - reserved), "limit_kb": limit_kb}


def probe_budget_status(daily_limit_mb: int = 25) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    limit_kb = max(1, min(500, int(daily_limit_mb))) * 1024
    try:
        document = json.loads(_budget_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        document = {}
    used = int(document.get("used_kb", 0) or 0) if document.get("day") == today else 0
    return {"used_kb": max(0, used), "remaining_kb": max(0, limit_kb - used),
            "limit_kb": limit_kb}
