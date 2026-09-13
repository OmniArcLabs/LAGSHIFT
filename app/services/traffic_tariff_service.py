"""Privacy-first analysis of Iranian domestic-traffic eligibility.

The service is intentionally conservative: Iranian hosting, a ``.ir`` suffix, or
an Iranian IP allocation is not proof that an operator will apply a discounted
tariff.  Only entries in a trusted catalog may produce a ``domestic`` result.
"""
from __future__ import annotations

import hashlib
import base64
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable

from app.services import app_paths
from app.app_info import TARIFF_CATALOG_PUBLIC_KEY_B64, TARIFF_CATALOG_URL
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MAX_REDIRECTS = 5
MAX_CATALOG_ENTRIES = 250_000
MAX_HISTORY_ITEMS = 30
MAX_CATALOG_BYTES = 4 * 1024 * 1024
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class TariffAnalysisError(ValueError):
    """A safe, user-presentable analysis failure."""


@dataclass(frozen=True)
class TariffCatalog:
    revision: str = "bundled-empty"
    source_name: str = "بدون فهرست رسمی"
    source_url: str = ""
    updated_at: str = ""
    expires_at: str = ""
    domestic_domains: frozenset[str] = frozenset()
    domestic_networks: tuple[ipaddress._BaseNetwork, ...] = ()

    @classmethod
    def from_document(cls, document: dict) -> "TariffCatalog":
        if not isinstance(document, dict) or document.get("version") != 1:
            raise TariffAnalysisError("نسخهٔ فهرست تعرفه معتبر نیست")
        domains = document.get("domestic_domains", [])
        networks = document.get("domestic_networks", [])
        if not isinstance(domains, list) or not isinstance(networks, list):
            raise TariffAnalysisError("ساختار فهرست تعرفه معتبر نیست")
        if len(domains) + len(networks) > MAX_CATALOG_ENTRIES:
            raise TariffAnalysisError("فهرست تعرفه بیش از حد بزرگ است")
        clean_domains = frozenset(_normalize_catalog_domain(value) for value in domains)
        try:
            clean_networks = tuple(ipaddress.ip_network(str(value), strict=True) for value in networks)
        except ValueError as exc:
            raise TariffAnalysisError("محدودهٔ IP فهرست تعرفه معتبر نیست") from exc
        return cls(
            revision=str(document.get("revision", ""))[:80],
            source_name=str(document.get("source_name", "فهرست تعرفه"))[:120],
            source_url=str(document.get("source_url", ""))[:500],
            updated_at=str(document.get("updated_at", ""))[:40],
            expires_at=str(document.get("expires_at", ""))[:40],
            domestic_domains=clean_domains,
            domestic_networks=clean_networks,
        )

    def matches(self, host: str, addresses: Iterable[str]) -> bool:
        normalized = host.casefold().rstrip(".")
        if any(normalized == item or normalized.endswith("." + item)
               for item in self.domestic_domains):
            return True
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if any(address.version == network.version and address in network
                   for network in self.domestic_networks):
                return True
        return False

    def evidence(self, host: str, addresses: Iterable[str]) -> tuple[str, ...]:
        """Return non-sensitive catalog evidence for one hop."""
        evidence: list[str] = []
        normalized = host.casefold().rstrip(".")
        if any(normalized == item or normalized.endswith("." + item)
               for item in self.domestic_domains):
            evidence.append("دامنه")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if any(address.version == network.version and address in network
                   for network in self.domestic_networks):
                evidence.append("IP")
                break
        return tuple(evidence)


@dataclass(frozen=True)
class IranNetworkCatalog:
    """Offline RIR allocation evidence; never treated as tariff proof."""

    revision: str = ""
    source_name: str = ""
    source_url: str = ""
    networks: tuple[ipaddress._BaseNetwork, ...] = ()

    def classify(self, addresses: Iterable[str]) -> str:
        flags: list[bool] = []
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            flags.append(any(
                address.version == network.version and address in network
                for network in self.networks
            ))
        if not flags:
            return "unknown"
        if all(flags):
            return "iran"
        if any(flags):
            return "mixed"
        return "foreign"


@dataclass(frozen=True)
class RedirectStep:
    url: str
    host: str
    addresses: tuple[str, ...]
    status: int
    content_length: int | None = None
    registered: bool = False
    evidence: tuple[str, ...] = field(default_factory=tuple)
    network_location: str = "unknown"


@dataclass(frozen=True)
class TariffResult:
    requested_url: str
    final_url: str
    classification: str
    title: str
    confidence: str
    reasons: tuple[str, ...]
    warning: str = ""
    content_length: int | None = None
    steps: tuple[RedirectStep, ...] = field(default_factory=tuple)
    catalog_revision: str = ""
    catalog_source: str = ""
    catalog_updated_at: str = ""
    catalog_source_url: str = ""
    network_catalog_revision: str = ""
    network_catalog_source: str = ""
    network_catalog_source_url: str = ""
    insecure_path: bool = False
    checked_at: str = ""
    operator_name: str = "نامشخص"
    operator_source: str = "manual"
    operator_confidence: str = "نامشخص"
    external_source: str = ""
    external_checked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _normalize_catalog_domain(value: object) -> str:
    text = str(value).strip().casefold().rstrip(".")
    if not text or len(text) > 253 or "/" in text or ":" in text or " " in text:
        raise TariffAnalysisError("دامنهٔ فهرست تعرفه معتبر نیست")
    try:
        return text.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise TariffAnalysisError("دامنهٔ فهرست تعرفه معتبر نیست") from exc


def sanitize_url(value: str) -> str:
    """Return a display-safe URL without credentials, query, or fragment."""
    parsed = urllib.parse.urlsplit(str(value).strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise TariffAnalysisError("آدرس باید با http یا https شروع شود")
    if parsed.username is not None or parsed.password is not None:
        raise TariffAnalysisError("لینک دارای نام کاربری یا رمز پذیرفته نیست")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").casefold().rstrip(".")
    except UnicodeError as exc:
        raise TariffAnalysisError("نام سایت معتبر نیست") from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise TariffAnalysisError("پورت لینک معتبر نیست") from exc
    if port not in {None, 80, 443}:
        raise TariffAnalysisError("فقط پورت‌های استاندارد وب بررسی می‌شوند")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((parsed.scheme.casefold(), netloc, path, "", ""))


def _request_url(value: str) -> str:
    """Validate a URL while keeping its query only in volatile memory.

    Signed download links frequently require a query token.  The public result,
    history and redirect receipt continue to use :func:`sanitize_url`, so that
    token is neither displayed nor persisted.
    """
    raw = str(value).strip()
    sanitize_url(raw)  # Applies scheme, credential, host and port validation.
    parsed = urllib.parse.urlsplit(raw)
    host = parsed.hostname.encode("idna").decode("ascii").casefold().rstrip(".")
    port = parsed.port
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urllib.parse.urlunsplit(
        (parsed.scheme.casefold(), netloc, parsed.path or "/", parsed.query, "")
    )


def history_identity(value: str) -> dict:
    """Produce a bounded local-history key without retaining a secret path."""
    safe = urllib.parse.urlsplit(sanitize_url(value))
    extension = Path(safe.path).suffix.casefold()[:12]
    digest = hashlib.sha256(safe.path.encode("utf-8")).hexdigest()[:16]
    return {"host": safe.hostname or "", "path_hash": digest, "extension": extension}


def _resolve_public(host: str) -> tuple[str, ...]:
    try:
        rows = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TariffAnalysisError("نام سایت به IP تبدیل نشد") from exc
    addresses = tuple(dict.fromkeys(row[4][0].split("%")[0] for row in rows))
    if not addresses:
        raise TariffAnalysisError("برای سایت هیچ IP معتبری پیدا نشد")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise TariffAnalysisError("پاسخ DNS معتبر نیست") from exc
        if not address.is_global:
            raise TariffAnalysisError("آدرس‌های محلی و خصوصی قابل بررسی نیستند")
    return addresses


def _content_length(headers) -> int | None:
    value = headers.get("Content-Length")
    if value and str(value).isdigit():
        return max(0, int(value))
    content_range = headers.get("Content-Range", "")
    if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
        return int(content_range.rsplit("/", 1)[1])
    return None


def _open_once(opener, url: str, timeout: float):
    headers = {"User-Agent": "LAGSHIFT-TrafficInsight/1", "Accept-Encoding": "identity"}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code not in {405, 501}:
            return exc
    request = urllib.request.Request(
        url, headers={**headers, "Range": "bytes=0-0"}, method="GET"
    )
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return exc


def analyze_url(
    value: str,
    catalog: TariffCatalog | None = None,
    *,
    iran_catalog: IranNetworkCatalog | None = None,
    warp_or_vpn_active: bool = False,
    operator_name: str = "نامشخص",
    operator_source: str = "manual",
    operator_confidence: str = "نامشخص",
    timeout: float = 5.0,
    total_timeout: float = 14.0,
    resolver: Callable[[str], tuple[str, ...]] = _resolve_public,
    opener=None,
) -> TariffResult:
    catalog = catalog or TariffCatalog()
    iran_catalog = iran_catalog or load_iran_network_catalog()
    opener = opener or urllib.request.build_opener(_NoRedirect())
    current_request = _request_url(value)
    requested = sanitize_url(value)
    steps: list[RedirectStep] = []
    visited: set[str] = set()
    deadline = time.monotonic() + max(3.0, min(30.0, float(total_timeout)))

    for _ in range(MAX_REDIRECTS + 1):
        current = sanitize_url(current_request)
        request_identity = hashlib.sha256(current_request.encode("utf-8")).hexdigest()
        if request_identity in visited:
            raise TariffAnalysisError("حلقهٔ تغییر مسیر در لینک پیدا شد")
        visited.add(request_identity)
        parsed = urllib.parse.urlsplit(current_request)
        host = parsed.hostname or ""
        addresses = tuple(resolver(host))
        # Custom resolvers used by the UI/tests still pass through the same guard.
        if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
            raise TariffAnalysisError("آدرس‌های محلی و خصوصی قابل بررسی نیستند")
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TariffAnalysisError("زمان بررسی مسیر تمام شد؛ لینک یا یکی از واسطه‌ها دیر پاسخ داد")
            response = _open_once(
                opener, current_request,
                max(0.5, min(float(timeout), 8.0, remaining)),
            )
        except (OSError, urllib.error.URLError) as exc:
            raise TariffAnalysisError("ارتباط امن با سایت برقرار نشد") from exc
        try:
            status = int(getattr(response, "status", None) or response.getcode())
            length = _content_length(response.headers)
            evidence = catalog.evidence(host, addresses)
            network_location = iran_catalog.classify(addresses)
            steps.append(RedirectStep(
                url=current,
                host=host,
                addresses=addresses,
                status=status,
                content_length=length,
                registered=bool(evidence),
                evidence=evidence,
                network_location=network_location,
            ))
            if status not in _REDIRECT_CODES:
                break
            location = response.headers.get("Location", "")
            if not location:
                raise TariffAnalysisError("پاسخ تغییر مسیر ناقص است")
            current_request = _request_url(urllib.parse.urljoin(current_request, location))
        finally:
            response.close()
    else:
        raise TariffAnalysisError("تعداد تغییر مسیرهای لینک بیش از حد مجاز است")

    matches = [step.registered for step in steps]
    if matches and all(matches):
        classification = "domestic"
        title = "در فهرست تعرفهٔ داخلی ثبت شده است"
        confidence = "بالا" if not warp_or_vpn_active else "محدود"
        reasons = ("همهٔ میزبان‌های مسیر در فهرست معتبر تعرفهٔ داخلی ثبت شده‌اند.",)
    elif matches and matches[-1]:
        classification = "domestic"
        title = "سرور نهایی فایل در فهرست تعرفهٔ داخلی ثبت شده است"
        confidence = "متوسط" if not warp_or_vpn_active else "محدود"
        reasons = (
            "میزبان تحویل‌دهندهٔ فایل ثبت شده است؛ بعضی صفحه‌ها یا تغییرمسیرهای کم‌حجم ثبت نشده‌اند.",
        )
    elif any(matches):
        classification = "mixed"
        title = "سرور نهایی فایل ثبت نشده است"
        confidence = "متوسط" if not warp_or_vpn_active else "محدود"
        reasons = (
            "بخشی از مسیر ثبت شده، اما میزبان تحویل‌دهندهٔ بایت‌های اصلی فایل تأیید نشده است.",
        )
    elif steps[-1].network_location == "iran":
        classification = "likely_domestic"
        title = "میزبان نهایی در محدودهٔ شبکه‌های ایران قرار دارد"
        confidence = "پایین" if not warp_or_vpn_active else "محدود"
        reasons = (
            "IP میزبان نهایی در فهرست آفلاین تخصیص‌های ایرانِ RIPE NCC قرار دارد.",
            "این نشانهٔ میزبانی ایران است، نه تأیید قطعی تعرفهٔ نیم‌بها توسط اپراتور.",
        )
    elif steps[-1].network_location == "foreign":
        classification = "likely_full"
        title = "این مسیر احتمالاً با تعرفهٔ عادی محاسبه می‌شود"
        confidence = "پایین" if not warp_or_vpn_active else "محدود"
        reasons = (
            "IP میزبان نهایی در تخصیص‌های ثبتی شبکه‌های ایران پیدا نشد.",
            "CDN و سیاست اپراتور می‌توانند نتیجه را تغییر دهند؛ این پاسخ تضمین صورتحساب نیست.",
        )
    else:
        classification = "unknown"
        title = "تعرفه از روی اطلاعات معتبر قابل تأیید نیست"
        confidence = "نامشخص"
        reasons = (
            "مقصد چند IP با موقعیت ثبتی متفاوت دارد یا اطلاعات کافی پیدا نشد.",
            "پسوند .ir یا میزبانی داخل ایران به‌تنهایی تضمین تعرفه نیست.",
        )
    warning = ""
    insecure_path = any(urllib.parse.urlsplit(step.url).scheme != "https" for step in steps)
    warnings: list[str] = []
    if warp_or_vpn_active:
        warnings.append("VPN یا WARP روشن است؛ مسیر دیده‌شده لزوماً همان مسیر صورتحساب اپراتور نیست.")
    if insecure_path:
        warnings.append("بخشی از مسیر از HTTP استفاده می‌کند؛ برای لینک حساس یا توکن‌دار توصیه نمی‌شود.")
    warning = " ".join(warnings)
    final_step = steps[-1]
    return TariffResult(
        requested_url=requested,
        final_url=final_step.url,
        classification=classification,
        title=title,
        confidence=confidence,
        reasons=reasons,
        warning=warning,
        content_length=final_step.content_length,
        steps=tuple(steps),
        catalog_revision=catalog.revision,
        catalog_source=catalog.source_name,
        catalog_updated_at=catalog.updated_at,
        catalog_source_url=catalog.source_url,
        network_catalog_revision=iran_catalog.revision,
        network_catalog_source=iran_catalog.source_name,
        network_catalog_source_url=iran_catalog.source_url,
        insecure_path=insecure_path,
        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        operator_name=str(operator_name).strip()[:40] or "نامشخص",
        operator_source=str(operator_source).strip()[:40] or "manual",
        operator_confidence=str(operator_confidence).strip()[:24] or "نامشخص",
    )


def load_bundled_catalog(path: Path | None = None) -> TariffCatalog:
    target = path or Path(__file__).resolve().parents[1] / "resources" / "domestic_traffic_catalog.json"
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
        catalog = TariffCatalog.from_document(document)
        if catalog.domestic_domains or catalog.domestic_networks:
            # A modified package resource must never turn into billing advice.
            # Non-empty data is accepted only through the signed catalog path.
            return verify_signed_catalog(document, TARIFF_CATALOG_PUBLIC_KEY_B64)
        return catalog
    except (OSError, json.JSONDecodeError, TariffAnalysisError):
        return TariffCatalog()


@lru_cache(maxsize=1)
def load_iran_network_catalog(path: Path | None = None) -> IranNetworkCatalog:
    target = path or Path(__file__).resolve().parents[1] / "resources" / "iran_network_allocations.json"
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
        values = document.get("networks", [])
        if document.get("version") != 1 or not isinstance(values, list):
            raise ValueError("invalid catalog")
        if not values or len(values) > 10_000:
            raise ValueError("invalid catalog size")
        networks = tuple(ipaddress.ip_network(str(value), strict=True) for value in values)
        return IranNetworkCatalog(
            revision=str(document.get("revision", ""))[:40],
            source_name=str(document.get("source_name", "RIPE NCC"))[:120],
            source_url=str(document.get("source_url", ""))[:500],
            networks=networks,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return IranNetworkCatalog()


def merge_external_evidence(result: TariffResult, evidence) -> TariffResult:
    """Merge third-party evidence without presenting it as an official catalog."""
    if not getattr(evidence, "available", False):
        return result
    source = str(getattr(evidence, "source", "منبع ثالث"))[:40]
    registered = bool(getattr(evidence, "registered", False))
    in_iran = bool(getattr(evidence, "in_iran", False))
    warning = result.warning
    if result.classification in {"unknown", "likely_domestic", "likely_full"} and registered:
        location_note = (
            "این پاسخ با نشانهٔ آفلاین موقعیت شبکه هم‌جهت است."
            if result.classification == "likely_domestic"
            else "این پاسخ از نشانهٔ صرفاً مکانی شبکه دقیق‌تر است."
        )
        return replace(
            result,
            classification="likely_domestic",
            title=f"{source} این میزبان را دارای ترافیک داخلی گزارش می‌کند",
            confidence="متوسط",
            reasons=(
                f"{source} میزبان نهایی را ثبت‌شده گزارش کرده است.",
                location_note,
                "این پاسخ منبع ثالث است و جای استعلام اپراتور یا فهرست رسمی را نمی‌گیرد.",
            ),
            external_source=source,
            external_checked=True,
        )
    if result.classification == "domestic" and not registered:
        extra = f"{source} با فهرست معتبر برنامه هم‌نظر نیست؛ نتیجه را با اپراتور بررسی کن."
        warning = " ".join(part for part in (warning, extra) if part)
    elif result.classification == "unknown" and in_iran:
        return replace(
            result,
            title="میزبان داخل ایران است، اما تعرفهٔ داخلی تأیید نشد",
            reasons=(
                f"{source} موقعیت میزبان را ایران گزارش کرده، اما آن را ثبت‌شده نمی‌داند.",
                "میزبانی داخل ایران به‌تنهایی تضمین نیم‌بها بودن نیست.",
            ),
            external_source=source,
            external_checked=True,
        )
    return replace(
        result, warning=warning, external_source=source, external_checked=True
    )


def _canonical_catalog(document: dict) -> bytes:
    return json.dumps(
        {key: value for key, value in document.items() if key != "signature"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def verify_signed_catalog(document: dict, public_key_b64: str) -> TariffCatalog:
    if not isinstance(document, dict) or not public_key_b64:
        raise TariffAnalysisError("اعتماد فهرست تعرفه پیکربندی نشده است")
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(str(document.get("signature", "")), validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _canonical_catalog(document)
        )
    except (ValueError, InvalidSignature) as exc:
        raise TariffAnalysisError("امضای فهرست تعرفه معتبر نیست") from exc
    catalog = TariffCatalog.from_document(document)
    if catalog.expires_at:
        try:
            expires = datetime.fromisoformat(catalog.expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise TariffAnalysisError("تاریخ اعتبار فهرست تعرفه معتبر نیست") from exc
        if expires <= datetime.now(timezone.utc):
            raise TariffAnalysisError("اعتبار فهرست تعرفه تمام شده است")
    return catalog


def _catalog_cache_path() -> Path:
    return app_paths.migrated_file("domestic_traffic_catalog.signed.json", local=True)


def refresh_catalog(url: str = TARIFF_CATALOG_URL,
                    public_key_b64: str = TARIFF_CATALOG_PUBLIC_KEY_B64) -> TariffCatalog:
    safe_url = sanitize_url(url)
    if not public_key_b64 or not safe_url.startswith("https://"):
        raise TariffAnalysisError("کانال امن فهرست تعرفه پیکربندی نشده است")
    _resolve_public(urllib.parse.urlsplit(safe_url).hostname or "")
    request = urllib.request.Request(safe_url, headers={"User-Agent": "LAGSHIFT-TrafficCatalog/1"})
    class SafeCatalogRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = sanitize_url(newurl)
            if not target.startswith("https://"):
                raise TariffAnalysisError("تغییر مسیر ناامن فهرست تعرفه مسدود شد")
            _resolve_public(urllib.parse.urlsplit(target).hostname or "")
            return super().redirect_request(req, fp, code, msg, headers, target)

    opener = urllib.request.build_opener(SafeCatalogRedirects())
    with opener.open(request, timeout=8) as response:
        payload = response.read(MAX_CATALOG_BYTES + 1)
    if len(payload) > MAX_CATALOG_BYTES:
        raise TariffAnalysisError("فهرست تعرفه بیش از حد بزرگ است")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TariffAnalysisError("پاسخ فهرست تعرفه معتبر نیست") from exc
    catalog = verify_signed_catalog(document, public_key_b64)
    temporary = _catalog_cache_path().with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    temporary.replace(_catalog_cache_path())
    return catalog


def load_trusted_catalog(public_key_b64: str = TARIFF_CATALOG_PUBLIC_KEY_B64) -> TariffCatalog:
    if public_key_b64:
        try:
            document = json.loads(_catalog_cache_path().read_text(encoding="utf-8"))
            return verify_signed_catalog(document, public_key_b64)
        except (OSError, json.JSONDecodeError, TariffAnalysisError):
            pass
    return load_bundled_catalog()


def _history_path() -> Path:
    return app_paths.migrated_file("traffic_insight_history.json", local=True)


def load_history() -> list[dict]:
    try:
        document = json.loads(_history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(document, list):
        return []
    clean = []
    for item in document[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host", ""))[:253]
        path_hash = str(item.get("path_hash", ""))[:16]
        classification = str(item.get("classification", "unknown"))
        if host and len(path_hash) == 16 and classification in {
            "domestic", "likely_domestic", "likely_full", "mixed", "unknown"
        }:
            clean.append({
                "host": host,
                "path_hash": path_hash,
                "extension": str(item.get("extension", ""))[:12],
                "classification": classification,
                "confidence": str(item.get("confidence", ""))[:24],
            })
    return clean


def remember_result(result: TariffResult) -> None:
    item = history_identity(result.requested_url)
    item.update({"classification": result.classification, "confidence": result.confidence})
    history = [row for row in load_history()
               if not (row["host"] == item["host"] and row["path_hash"] == item["path_hash"])]
    history.append(item)
    temporary = _history_path().with_suffix(".tmp")
    temporary.write_text(
        json.dumps(history[-MAX_HISTORY_ITEMS:], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(_history_path())


def clear_history() -> None:
    _history_path().unlink(missing_ok=True)
