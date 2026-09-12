"""Bounded, read-only adapter for LinkIrani's public preview endpoint."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.services.traffic_tariff_service import sanitize_url


PREVIEW_ENDPOINT = "https://api.linkirani.ir/shortlink/preview"
MAX_RESPONSE_BYTES = 16 * 1024


@dataclass(frozen=True)
class LinkIraniEvidence:
    available: bool = False
    registered: bool = False
    in_iran: bool = False
    host: str = ""
    country_code: str = ""
    source: str = "LinkIrani"
    error: str = ""


def _origin_only(value: str) -> str:
    """Return only scheme and host; paths, query strings and tokens stay local."""
    safe = urllib.parse.urlsplit(sanitize_url(value))
    host = safe.hostname or ""
    netloc = f"[{host}]" if ":" in host else host
    if safe.port is not None:
        netloc += f":{safe.port}"
    return urllib.parse.urlunsplit((safe.scheme, netloc, "/", "", ""))


def check(value: str, *, enabled: bool = True, timeout_s: float = 4.0,
          opener=None) -> LinkIraniEvidence:
    if not enabled:
        return LinkIraniEvidence(error="disabled")
    origin = _origin_only(value)
    expected_host = urllib.parse.urlsplit(origin).hostname or ""
    query = urllib.parse.urlencode({"url": origin})
    request = urllib.request.Request(
        f"{PREVIEW_ENDPOINT}?{query}", method="GET",
        headers={"Accept": "application/json", "User-Agent": "LAGSHIFT/1"},
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=max(1.0, min(7.0, float(timeout_s)))) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            return LinkIraniEvidence(error="response-too-large")
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            return LinkIraniEvidence(error="invalid-response")
        link = document.get("link") if isinstance(document.get("link"), dict) else {}
        netloc = link.get("netloc") if isinstance(link.get("netloc"), dict) else {}
        returned_host = str(netloc.get("value", "")).casefold().rstrip(".")
        if returned_host != expected_host.casefold().rstrip("."):
            return LinkIraniEvidence(error="host-mismatch")
        registered = document.get("isRegistered")
        in_iran = document.get("isInIran")
        if not isinstance(registered, bool) or not isinstance(in_iran, bool):
            return LinkIraniEvidence(error="invalid-response")
        return LinkIraniEvidence(
            available=True, registered=registered, in_iran=in_iran,
            host=expected_host,
            country_code=str(document.get("ipCountryCode", ""))[:2].casefold(),
        )
    except Exception:
        return LinkIraniEvidence(error="unavailable")
