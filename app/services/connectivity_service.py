"""سرویس تست اتصال، پایه‌ی Kill Switch و تست پینگ تانل"""
import time
import socket
import secrets
import struct
import statistics
import urllib.request
import urllib.error
import ipaddress
import psutil

from app.app_info import APP_NAME, APP_VERSION
from concurrent.futures import ThreadPoolExecutor, as_completed


DNS_TEST_DOMAINS = (
    "example.com",
    "store.steampowered.com",
    "steamcommunity.com",
    "epicgames.com",
    "riotgames.com",
)

NCSI_PROBE_URL = "http://www.msftconnecttest.com/connecttest.txt"
NCSI_EXPECTED_BODY = b"Microsoft Connect Test"


def detect_internet_scope(timeout_s: float = 2.5) -> dict:
    """Distinguish verified internet from captive, local-only and offline states."""
    request = urllib.request.Request(
        NCSI_PROBE_URL,
        headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=max(0.5, float(timeout_s))) as response:
            body = response.read(256).strip()
            final_url = str(getattr(response, "url", NCSI_PROBE_URL))
            status = int(getattr(response, "status", 200))
        if status == 200 and body == NCSI_EXPECTED_BODY and final_url == NCSI_PROBE_URL:
            return {"state": "online", "online": True, "captive": False,
                    "message": "دسترسی واقعی اینترنت تأیید شد"}
        return {"state": "captive", "online": False, "captive": True,
                "message": "پاسخ شبکه تغییر کرده؛ احتمال صفحه ورود عمومی وجود دارد"}
    except urllib.error.HTTPError as exc:
        captive = 300 <= exc.code < 500
        return {"state": "captive" if captive else "inconclusive",
                "online": False, "captive": captive,
                "message": "شبکه پاسخ استاندارد اینترنت را برنگرداند"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        try:
            local_reachable = socket.gethostbyname(socket.gethostname()) not in {
                "", "127.0.0.1", "::1"
            }
        except OSError:
            local_reachable = False
        return {
            "state": "local-only" if local_reachable else "offline",
            "online": False, "captive": False,
            "message": (
                "شبکه محلی برقرار است اما اینترنت تأیید نشد"
                if local_reachable else "اتصال شبکه در دسترس نیست"
            ),
        }


def evaluate_game_preflight(scope: dict, fallback_online: bool,
                            adapter_name: str) -> dict:
    """Turn network evidence into a fail-closed, mutation-free lobby decision."""
    scope = scope if isinstance(scope, dict) else {}
    if bool(scope.get("captive")):
        return {"ready": False, "reason": "captive",
                "message": "صفحه ورود شبکه شناسایی شد؛ اول ورود Wi‑Fi را کامل کن، هیچ تغییری اعمال نشد"}
    if not str(adapter_name).strip():
        return {"ready": False, "reason": "no-adapter",
                "message": "کارت شبکه فعال پیدا نشد؛ هیچ تغییری اعمال نشد"}
    if not bool(fallback_online):
        return {"ready": False, "reason": "offline",
                "message": "اینترنت عمومی تأیید نشد؛ بهینه‌سازی بدون تغییر شبکه متوقف شد"}
    message = str(scope.get("message") or "دسترسی اینترنت برقرار است")
    if not scope.get("online"):
        message = "اینترنت از مسیر جایگزین تأیید شد؛ تست استاندارد ویندوز قطعی نبود"
    return {"ready": True, "reason": "ready", "message": message}


def audit_ipv6_exposure(custom_ipv4_dns_active: bool = False) -> dict:
    """Report global IPv6 availability without claiming a remote DNS leak test."""
    global_addresses = []
    try:
        for addresses in psutil.net_if_addrs().values():
            for item in addresses:
                if item.family != socket.AF_INET6:
                    continue
                raw = str(item.address).split("%", 1)[0]
                try:
                    address = ipaddress.ip_address(raw)
                except ValueError:
                    continue
                if address.is_global:
                    global_addresses.append(address.compressed)
    except (OSError, RuntimeError):
        return {"available": False, "global_ipv6": False, "possible_dns_bypass": False,
                "message": "وضعیت IPv6 قابل خواندن نبود"}
    exposed = bool(global_addresses)
    possible = exposed and bool(custom_ipv4_dns_active)
    return {
        "available": True, "global_ipv6": exposed,
        "possible_dns_bypass": possible,
        "address_count": len(set(global_addresses)),
        "message": (
            "IPv6 عمومی فعال است؛ چون پروفایل فعلی DNS فقط IPv4 است، احتمال مسیر DNS جداگانه وجود دارد"
            if possible else "IPv6 عمومی فعال است؛ تست Leak خارجی هنوز انجام نشده"
            if exposed else "IPv6 عمومی روی کارت‌های فعلی دیده نشد"
        ),
    }


def is_connected(host: str = "1.1.1.1", timeout_ms: int = 1000) -> bool:
    """
    یک پینگ ساده به یک هاست معتبر می‌زنه تا ببینه اینترنت وصله یا نه.
    برای Kill Switch استفاده می‌شه: اگه اتصال قطع شد، باید DNS به حالت امن برگرده.
    """
    timeout = max(timeout_ms / 1000.0, 0.2)
    for target, port in ((host, 443), ("8.8.8.8", 443), ("9.9.9.9", 853)):
        try:
            with socket.create_connection((target, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def measure_latency_ms(host: str, port: int, timeout_s: float = 3.0) -> int:
    """
    تست لتنسی TCP handshake مستقیم به یک آدرس/پورت (مثلاً سرور بازی یا سرور تانل).
    برخلاف ICMP ping، از پورت واقعی TCP استفاده می‌کنه که برای تست سرورهای بازی دقیق‌تره.
    برمی‌گردونه: میلی‌ثانیه، یا -1 اگه وصل نشد.
    """
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return elapsed_ms
    except Exception:
        return -1


def _dns_packet(domain: str) -> tuple[int, bytes]:
    query_id = secrets.randbelow(65536)
    question = b"".join(bytes([len(label)]) + label.encode("ascii") for label in domain.split(".")) + b"\0"
    packet = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", 1, 1)
    return query_id, packet


def _valid_dns_response(response: bytes, query_id: int) -> bool:
    if len(response) < 12:
        return False
    response_id, flags, _, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
    return bool(
        response_id == query_id and flags & 0x8000 and not flags & 0x000F and answers >= 1
    )


def _dns_exchange(server: str, domain: str, timeout_s: float = 1.2) -> tuple[int, bytes]:
    query_id, packet = _dns_packet(domain)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        sock.sendto(packet, (server, 53))
        response, source = sock.recvfrom(4096)
    if not source or source[0] != server:
        raise OSError("پاسخ DNS از سرور دیگری دریافت شد")
    return query_id, response


def measure_dns_query_ms(server: str, domain: str = "example.com",
                         timeout_s: float = 1.2) -> int:
    """Measure one validated recursive UDP DNS answer."""
    started = time.perf_counter()
    try:
        query_id, response = _dns_exchange(server, domain, timeout_s)
        if not _valid_dns_response(response, query_id):
            return -1
        return int((time.perf_counter() - started) * 1000)
    except OSError:
        return -1


def detect_dns_hijacking(server: str, timeout_s: float = 1.5) -> dict:
    """Detect synthetic answers for RFC 2606's reserved `.invalid` namespace."""
    domain = f"lagshift-{secrets.token_hex(8)}.invalid"
    try:
        query_id, response = _dns_exchange(server, domain, timeout_s)
        if len(response) < 12:
            raise OSError("پاسخ DNS ناقص بود")
        response_id, flags, _, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
        if response_id != query_id or not flags & 0x8000:
            raise OSError("شناسه پاسخ DNS معتبر نبود")
        rcode = flags & 0x000F
        if rcode == 3 and answers == 0:
            return {"conclusive": True, "hijacked": False, "rcode": "NXDOMAIN",
                    "message": "دامنه نامعتبر به‌درستی رد شد"}
        if rcode == 0 and answers > 0:
            return {"conclusive": True, "hijacked": True, "rcode": "NOERROR",
                    "message": "DNS برای دامنه رزروشده پاسخ مصنوعی برگرداند"}
        return {"conclusive": False, "hijacked": False, "rcode": str(rcode),
                "message": "پاسخ منفی DNS قطعی نبود"}
    except OSError:
        return {"conclusive": False, "hijacked": False, "rcode": "timeout",
                "message": "سرور به تست ضد دستکاری پاسخ نداد"}


def measure_doh_query_ms(url: str, domain: str = "example.com",
                         timeout_s: float = 1.8) -> int:
    """Measure an RFC 8484 DNS-message POST and validate its DNS response."""
    if not url:
        return -1
    query_id, packet = _dns_packet(domain)
    request = urllib.request.Request(
        url, data=packet, method="POST",
        headers={
            "Accept": "application/dns-message",
            "Content-Type": "application/dns-message",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read(4096)
        if not _valid_dns_response(body, query_id):
            return -1
        return int((time.perf_counter() - started) * 1000)
    except Exception:
        return -1


def _endpoint_samples(server: str, domains=DNS_TEST_DOMAINS, rounds: int = 2) -> list[int]:
    if not server:
        return []
    # Warm-up is deliberately excluded so a cold first packet does not decide the winner.
    measure_dns_query_ms(server, domains[0])
    jobs = []
    with ThreadPoolExecutor(max_workers=max(1, len(domains) * rounds)) as executor:
        for _ in range(rounds):
            jobs.extend(executor.submit(measure_dns_query_ms, server, domain) for domain in domains)
        return [future.result() for future in jobs]


def _summarize_samples(samples: list[int]) -> dict:
    valid = [value for value in samples if value >= 0]
    total = len(samples)
    success_rate = (len(valid) * 100.0 / total) if total else 0.0
    if not valid:
        return {"median_ms": -1, "jitter_ms": -1, "success_rate": success_rate,
                "successes": 0, "attempts": total}
    median = float(statistics.median(valid))
    jitter = float(statistics.median(abs(value - median) for value in valid))
    return {
        "median_ms": round(median), "jitter_ms": round(jitter),
        "success_rate": round(success_rate, 1), "successes": len(valid), "attempts": total,
    }


def calculate_dns_score(median_ms: int, jitter_ms: int, success_rate: float,
                        secondary_ok: bool = True, doh_expected: bool = False,
                        doh_ok: bool = False) -> int:
    if median_ms < 0 or success_rate <= 0:
        return 0
    latency_score = max(0.0, min(100.0, 110.0 - median_ms * 0.55))
    stability_score = max(0.0, min(100.0, 100.0 - max(0, jitter_ms) * 2.2))
    score = success_rate * 0.50 + latency_score * 0.30 + stability_score * 0.20
    if not secondary_ok:
        score -= 7
    if doh_expected and not doh_ok:
        score -= 4
    return round(max(0.0, min(100.0, score)))


def benchmark_dns_profile(profile, domains=None, rounds: int = 2) -> dict:
    test_domains = tuple(domains or DNS_TEST_DOMAINS)
    rounds = max(1, min(4, int(rounds)))
    primary_samples = _endpoint_samples(profile.primary, test_domains, rounds=rounds)
    primary = _summarize_samples(primary_samples)
    secondary_samples = _endpoint_samples(profile.secondary, test_domains, rounds=1) if profile.secondary else []
    secondary = _summarize_samples(secondary_samples)
    if profile.doh_url:
        with ThreadPoolExecutor(max_workers=2) as executor:
            doh_samples = list(executor.map(
                lambda domain: measure_doh_query_ms(profile.doh_url, domain),
                test_domains[:2],
            ))
    else:
        doh_samples = []
    doh = _summarize_samples(doh_samples)
    secondary_ok = not profile.secondary or secondary["success_rate"] >= 60
    doh_ok = bool(doh_samples and doh["success_rate"] >= 50)
    score = calculate_dns_score(
        primary["median_ms"], primary["jitter_ms"], primary["success_rate"],
        secondary_ok, bool(profile.doh_url), doh_ok,
    )
    label = "عالی" if score >= 85 else "خوب" if score >= 70 else "متوسط" if score >= 50 else "ضعیف"
    return {
        "profile": profile, "name": profile.name, "score": score, "label": label,
        "median_ms": primary["median_ms"], "jitter_ms": primary["jitter_ms"],
        "success_rate": primary["success_rate"], "successes": primary["successes"],
        "attempts": primary["attempts"], "secondary_ok": secondary_ok,
        "secondary_median_ms": secondary["median_ms"],
        "doh_supported": bool(profile.doh_url), "doh_ok": doh_ok,
        "doh_median_ms": doh["median_ms"],
    }


def profiles_for_goal(profiles: list, goal: str = "balanced") -> list:
    """Return only DNS profiles relevant to the requested smart-connect goal."""
    if goal == "anti_sanction":
        return [profile for profile in profiles if profile.purpose == "anti_sanction"]
    if goal == "speed":
        return [profile for profile in profiles if profile.region == "global"]
    return list(profiles)


def rank_dns_profiles(profiles: list, progress=None,
                      preference: str = "balanced", goal: str = "balanced",
                      domains=None, rounds: int = 2) -> list[dict]:
    """Benchmark whole profiles concurrently and rank reliability before speed."""
    profiles = profiles_for_goal(profiles, goal)
    results = []
    with ThreadPoolExecutor(max_workers=min(len(profiles), 10) or 1) as executor:
        if domains:
            jobs = {
                executor.submit(benchmark_dns_profile, profile, domains): profile
                for profile in profiles
            } if rounds == 2 else {
                executor.submit(benchmark_dns_profile, profile, domains, rounds): profile
                for profile in profiles
            }
        else:
            jobs = {
                executor.submit(benchmark_dns_profile, profile): profile
                for profile in profiles
            } if rounds == 2 else {
                executor.submit(benchmark_dns_profile, profile, None, rounds): profile
                for profile in profiles
            }
        completed = 0
        for future in as_completed(jobs):
            completed += 1
            try:
                result = future.result()
            except Exception:
                continue
            results.append(result)
            if progress:
                progress({"completed": completed, "total": len(jobs), "name": result["name"]})
    healthy = [item for item in results if item["score"] > 0]
    reliable = [item for item in healthy if item["success_rate"] >= 70] or healthy
    if preference == "fastest":
        key = lambda item: (item["median_ms"], item["jitter_ms"], -item["success_rate"])
    elif preference == "stable":
        key = lambda item: (-item["success_rate"], item["jitter_ms"], item["median_ms"])
    else:
        key = lambda item: (-item["score"], -item["success_rate"], item["median_ms"])
    return sorted(reliable, key=key)


def select_fastest_dns(profiles: list):
    """Return (profile, latency) for the fastest DNS that answers a real query."""
    with ThreadPoolExecutor(max_workers=min(len(profiles), 8) or 1) as executor:
        jobs = {executor.submit(measure_dns_query_ms, profile.primary): profile for profile in profiles}
        healthy = []
        for future in as_completed(jobs):
            latency = future.result()
            if latency >= 0:
                healthy.append((latency, jobs[future]))
    if not healthy:
        return None, -1
    latency, profile = min(healthy, key=lambda row: row[0])
    return profile, latency
