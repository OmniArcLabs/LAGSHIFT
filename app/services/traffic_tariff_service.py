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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
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


@dataclass(frozen=True)
class RedirectStep:
    url: str
    host: str
    addresses: tuple[str, ...]
    status: int
    content_length: int | None = None


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
    warp_or_vpn_active: bool = False,
    timeout: float = 5.0,
    resolver: Callable[[str], tuple[str, ...]] = _resolve_public,
    opener=None,
) -> TariffResult:
    catalog = catalog or TariffCatalog()
    opener = opener or urllib.request.build_opener(_NoRedirect())
    current = sanitize_url(value)
    requested = current
    steps: list[RedirectStep] = []
    visited: set[str] = set()

    for _ in range(MAX_REDIRECTS + 1):
        if current in visited:
            raise TariffAnalysisError("حلقهٔ تغییر مسیر در لینک پیدا شد")
        visited.add(current)
        parsed = urllib.parse.urlsplit(current)
        host = parsed.hostname or ""
        addresses = tuple(resolver(host))
        # Custom resolvers used by the UI/tests still pass through the same guard.
        if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
            raise TariffAnalysisError("آدرس‌های محلی و خصوصی قابل بررسی نیستند")
        try:
            response = _open_once(opener, current, max(1.0, min(float(timeout), 12.0)))
        except (OSError, urllib.error.URLError) as exc:
            raise TariffAnalysisError("ارتباط امن با سایت برقرار نشد") from exc
        try:
            status = int(getattr(response, "status", None) or response.getcode())
            length = _content_length(response.headers)
            steps.append(RedirectStep(current, host, addresses, status, length))
            if status not in _REDIRECT_CODES:
                break
            location = response.headers.get("Location", "")
            if not location:
                raise TariffAnalysisError("پاسخ تغییر مسیر ناقص است")
            current = sanitize_url(urllib.parse.urljoin(current, location))
        finally:
            response.close()
    else:
        raise TariffAnalysisError("تعداد تغییر مسیرهای لینک بیش از حد مجاز است")

    matches = [catalog.matches(step.host, step.addresses) for step in steps]
    if matches and all(matches):
        classification = "domestic"
        title = "ثبت‌شده در فهرست ترافیک داخلی"
        confidence = "بالا" if not warp_or_vpn_active else "محدود"
        reasons = ("همهٔ میزبان‌های مسیر در فهرست معتبر داخلی ثبت شده‌اند.",)
    elif any(matches):
        classification = "mixed"
        title = "مسیر ترکیبی؛ احتمال محاسبهٔ بخشی با تعرفهٔ عادی"
        confidence = "متوسط" if not warp_or_vpn_active else "محدود"
        reasons = ("فقط بخشی از زنجیرهٔ دانلود در فهرست داخلی ثبت شده است.",)
    else:
        classification = "unknown"
        title = "تعرفه از روی اطلاعات معتبر قابل تأیید نیست"
        confidence = "نامشخص"
        reasons = (
            "دامنه یا IP نهایی در فهرست معتبر داخلی پیدا نشد.",
            "پسوند .ir یا میزبانی داخل ایران به‌تنهایی تضمین تعرفه نیست.",
        )
    warning = ""
    if warp_or_vpn_active:
        warning = "VPN یا WARP روشن است؛ مسیر دیده‌شده لزوماً همان مسیر صورتحساب اپراتور نیست."
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
    return TariffCatalog.from_document(document)


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
        if host and len(path_hash) == 16 and classification in {"domestic", "mixed", "unknown"}:
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
