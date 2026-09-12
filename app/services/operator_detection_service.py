"""Privacy-minimized, best-effort ISP detection for Traffic Insight.

The fixed Cloudflare metadata endpoint naturally sees the request address, as
every internet server does.  LAGSHIFT deliberately discards the returned IP and
keeps only coarse ASN/operator/country fields.  Failure is always non-fatal and
manual selection remains authoritative.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


METADATA_URL = "https://speed.cloudflare.com/meta"
MAX_RESPONSE_BYTES = 16 * 1024


@dataclass(frozen=True)
class OperatorHint:
    name: str = "نامشخص"
    organization: str = ""
    asn: str = ""
    country: str = ""
    region: str = ""
    source: str = "unavailable"
    confidence: str = "نامشخص"


_ALIASES = (
    (("mobile communication company of iran", "mci", "hamrah aval"), "همراه اول"),
    (("irancell", "mtn irancell", "iran cell"), "ایرانسل"),
    (("rightel", "rightel communication"), "رایتل"),
    (("telecommunication company of iran", "tci", "mokhaberat"), "مخابرات"),
    (("shatel", "aryan sat"), "شاتل"),
    (("asiatech", "asia tech"), "آسیاتک"),
    (("mobinnet",), "مبین‌نت"),
    (("pars online", "parsonline"), "پارس‌آنلاین"),
    (("pishgaman",), "پیشگامان"),
)


def friendly_operator(organization: str) -> str:
    value = " ".join(str(organization or "").casefold().replace("-", " ").split())
    for aliases, label in _ALIASES:
        if any(alias in value for alias in aliases):
            return label
    return str(organization or "").strip()[:80] or "نامشخص"


def _clean_asn(value) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("AS"):
        text = text[2:]
    return f"AS{text}" if text.isdigit() and 0 < int(text) <= 4_294_967_295 else ""


def detect(*, enabled: bool = True, tunnel_active: bool = False,
           timeout_s: float = 3.5, opener=None) -> OperatorHint:
    if not enabled:
        return OperatorHint(source="disabled")
    if tunnel_active:
        return OperatorHint(source="tunnel-active")
    request = urllib.request.Request(
        METADATA_URL,
        method="GET",
        # The metadata endpoint rejects generic non-browser requests unless the
        # public speed-test origin is supplied. Keep an honest product UA while
        # using the same origin contract as Cloudflare's own page.
        headers={
            "Accept": "application/json",
            "User-Agent": "LAGSHIFT/1 (+https://github.com/OmniArcLabs/LAGSHIFT)",
            "Origin": "https://speed.cloudflare.com",
            "Referer": "https://speed.cloudflare.com/",
        },
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=max(1.0, min(6.0, float(timeout_s)))) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            return OperatorHint(source="invalid-response")
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            return OperatorHint(source="invalid-response")
        # Never expose, return, log, or persist clientIp/clientIP/ip fields.
        organization = str(document.get("asOrganization", "")).strip()[:80]
        country = str(document.get("country", "")).strip().upper()[:2]
        region = str(document.get("region", "")).strip()[:64]
        asn = _clean_asn(document.get("asn"))
        if not organization and not asn:
            return OperatorHint(country=country, region=region, source="cloudflare-edge")
        return OperatorHint(
            name=friendly_operator(organization), organization=organization,
            asn=asn, country=country, region=region,
            source="cloudflare-edge", confidence="متوسط",
        )
    except Exception:
        return OperatorHint(source="unavailable")
