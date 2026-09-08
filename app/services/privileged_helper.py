"""Narrow, one-shot Windows elevation boundary for approved network actions."""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import uuid
import re
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

from app.services import app_paths


HELPER_FLAG = "--privileged-helper"
_ALLOWED_OPERATIONS = {"set_dns", "restore_dns", "select_dns", "emergency_reset"}


def _validate_doh_url(value: str) -> None:
    parsed = urlparse(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or len(value) > 500):
        raise ValueError("آدرس DoH معتبر نیست")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (not address.is_global or address.is_unspecified):
        raise ValueError("آدرس محلی DoH پذیرفته نیست")


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _inside_runtime(path: Path) -> bool:
    try:
        path.resolve().relative_to(app_paths.runtime_dir().resolve())
        return path.suffix.lower() == ".json"
    except (OSError, ValueError):
        return False


def _validate_request(document: dict) -> None:
    if document.get("version") != 1 or document.get("operation") not in _ALLOWED_OPERATIONS:
        raise ValueError("درخواست دسترسی ناشناخته است")
    nonce = document.get("nonce", "")
    adapter = document.get("adapter", "")
    allowed_fields = {
        "set_dns": {"version", "nonce", "operation", "adapter", "servers", "doh_url"},
        "restore_dns": {"version", "nonce", "operation", "adapter"},
        "select_dns": {"version", "nonce", "operation", "adapter", "candidates", "domains"},
        "emergency_reset": {"version", "nonce", "operation", "adapter"},
    }[document["operation"]]
    if set(document) - allowed_fields:
        raise ValueError("درخواست دسترسی شامل فیلد ناشناخته است")
    if not isinstance(nonce, str) or len(nonce) != 32:
        raise ValueError("شناسه درخواست معتبر نیست")
    if (document["operation"] != "emergency_reset" and
            (not isinstance(adapter, str) or not adapter.strip() or len(adapter) > 256)):
        raise ValueError("نام کارت شبکه معتبر نیست")
    if isinstance(adapter, str) and any(ord(ch) < 32 for ch in adapter):
        raise ValueError("نام کارت شبکه شامل کاراکتر کنترلی است")
    if document["operation"] == "emergency_reset" and adapter not in {"", None}:
        raise ValueError("بازیابی اضطراری کارت شبکه دلخواه نمی‌پذیرد")
    if document["operation"] == "set_dns":
        servers = document.get("servers")
        if not isinstance(servers, list) or not 1 <= len(servers) <= 2:
            raise ValueError("فهرست DNS معتبر نیست")
        for server in servers:
            socket.inet_pton(socket.AF_INET, server)
        doh_url = document.get("doh_url", "")
        if doh_url:
            _validate_doh_url(doh_url)
    elif document["operation"] == "select_dns":
        candidates = document.get("candidates")
        domains = document.get("domains")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 6:
            raise ValueError("نامزدهای DNS معتبر نیستند")
        if not isinstance(domains, list) or not 1 <= len(domains) <= 8:
            raise ValueError("مقصدهای آزمایش معتبر نیستند")
        for domain in domains:
            if not isinstance(domain, str) or len(domain) > 253 or not re.fullmatch(
                r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
                domain,
            ):
                raise ValueError("نام مقصد آزمایش معتبر نیست")
        for candidate in candidates:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str):
                raise ValueError("نامزد DNS معتبر نیست")
            if set(candidate) - {"name", "servers", "doh_url"}:
                raise ValueError("نامزد DNS شامل فیلد ناشناخته است")
            if not 1 <= len(candidate["name"]) <= 80:
                raise ValueError("نام DNS معتبر نیست")
            if any(ord(ch) < 32 for ch in candidate["name"]):
                raise ValueError("نام DNS شامل کاراکتر کنترلی است")
            servers = candidate.get("servers")
            if not isinstance(servers, list) or not 1 <= len(servers) <= 2:
                raise ValueError("سرور DNS معتبر نیست")
            for server in servers:
                socket.inet_pton(socket.AF_INET, server)
            doh_url = candidate.get("doh_url", "")
            if doh_url:
                _validate_doh_url(doh_url)


def _write_result(path: Path, document: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def run_helper(request_path: str, response_path: str) -> int:
    """Elevated entry point. It can execute only the fixed schema above."""
    request = Path(request_path)
    response = Path(response_path)
    if not is_admin() or not _inside_runtime(request) or not _inside_runtime(response):
        return 2
    result = {"ok": False, "error": "عملیات انجام نشد"}
    try:
        document = json.loads(request.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("nonce"), str):
            result["nonce"] = document["nonce"]
        _validate_request(document)
        from app.services import dns_service

        if document["operation"] == "set_dns":
            servers = document["servers"]
            ok = dns_service._set_dns_direct(
                document["adapter"], servers[0],
                servers[1] if len(servers) > 1 else None,
                document.get("doh_url", ""),
            )
            result = {
                "ok": bool(ok),
                "error": "" if ok else (dns_service.get_last_error() or "ویندوز عملیات را نپذیرفت"),
                "nonce": document["nonce"],
            }
        elif document["operation"] == "restore_dns":
            ok = dns_service._restore_original_dns_direct(document["adapter"])
            result = {
                "ok": bool(ok),
                "error": "" if ok else (dns_service.get_last_error() or "ویندوز عملیات را نپذیرفت"),
                "nonce": document["nonce"],
            }
        elif document["operation"] == "select_dns":
            from app.services import app_access_service

            candidates = document["candidates"]
            progress_path = request.with_name(f"priv-{document['nonce']}-progress.json")
            failures = []
            selected = None
            last_probe = None
            tested = 0
            started = time.monotonic()
            for index, candidate in enumerate(candidates, start=1):
                if time.monotonic() - started > 35:
                    failures.append("بودجه زمانی آزمایش DNS تمام شد")
                    break
                _write_result(progress_path, {
                    "nonce": document["nonce"], "index": index,
                    "count": len(candidates), "name": candidate["name"],
                })
                servers = candidate["servers"]
                applied = dns_service._set_dns_direct(
                    document["adapter"], servers[0],
                    servers[1] if len(servers) > 1 else None,
                    candidate.get("doh_url", ""),
                )
                if not applied:
                    failures.append(
                        f"{candidate['name']}: {dns_service.get_last_error() or 'اعمال نشد'}"
                    )
                    continue
                probe = app_access_service.probe_domains(document["domains"], timeout_s=1.15)
                tested = index
                last_probe = probe
                if probe.get("healthy"):
                    selected = {"name": candidate["name"], "probe": probe, "index": index}
                    break
                failures.append(f"{candidate['name']}: مسیر کامل نشد")
            if selected:
                result = {
                    "ok": True, "nonce": document["nonce"],
                    "selected": selected, "failures": failures[-3:],
                }
            else:
                restored = dns_service._restore_original_dns_direct(document["adapter"])
                result = {
                    "ok": False, "nonce": document["nonce"], "restored": bool(restored),
                    "error": "هیچ‌کدام از DNSهای برتر مسیر کامل برنامه را باز نکردند.",
                    "failures": failures[-3:], "tested": tested,
                    "candidate_count": len(candidates), "last_probe": last_probe,
                }
        else:
            from app.services import game_qos_service, recovery_service
            dns_ok = dns_service._restore_original_dns_direct(None)
            qos_ok = game_qos_service.remove_all()
            outcome = "success" if dns_ok and qos_ok else "partial"
            recovery_service.safe_record("emergency-reset", outcome)
            result = {
                "ok": bool(dns_ok and qos_ok), "nonce": document["nonce"],
                "dns_restored": bool(dns_ok), "qos_removed": bool(qos_ok),
                "error": "" if dns_ok and qos_ok else
                         "بخشی از بازیابی انجام نشد؛ جزئیات در سپر امنیت ثبت شد",
            }
    except Exception as exc:
        result["error"] = str(exc)[:500] or "درخواست دسترسی نامعتبر بود"
    try:
        _write_result(response, result)
    except OSError:
        return 3
    finally:
        try:
            request.unlink(missing_ok=True)
        except OSError:
            pass
    return 0 if result.get("ok") else 1


def request(operation: str, adapter: str, servers: list[str] | None = None,
            doh_url: str = "", timeout_s: float = 35.0) -> tuple[bool, str]:
    """Ask Windows to run one validated operation, then read its signed-by-nonce result."""
    if sys.platform != "win32":
        return False, "دسترسی محدود شبکه فقط در ویندوز قابل استفاده است"
    nonce = uuid.uuid4().hex
    runtime = app_paths.runtime_dir()
    request_path = runtime / f"priv-{nonce}.json"
    response_path = runtime / f"priv-{nonce}-result.json"
    document = {
        "version": 1,
        "nonce": nonce,
        "operation": operation,
        "adapter": adapter,
    }
    if operation == "set_dns":
        document["servers"] = list(servers or [])
        document["doh_url"] = doh_url
    try:
        _validate_request(document)
        request_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = [HELPER_FLAG, str(request_path), str(response_path)]
        else:
            executable = sys.executable
            args = [str(Path(sys.argv[0]).resolve()), HELPER_FLAG,
                    str(request_path), str(response_path)]
        code = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, subprocess.list2cmdline(args),
            str(Path(executable).resolve().parent), 0,
        )
        if code <= 32:
            return False, "درخواست دسترسی ادمین لغو شد یا ویندوز آن را اجرا نکرد"
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if response_path.exists():
                result = json.loads(response_path.read_text(encoding="utf-8"))
                if result.get("nonce") != nonce:
                    return False, "پاسخ دستیار امنیتی معتبر نبود"
                return bool(result.get("ok")), str(result.get("error", ""))
            time.sleep(0.1)
        return False, "پاسخ دستیار امنیتی در زمان مقرر دریافت نشد"
    except Exception as exc:
        return False, str(exc) or "اجرای دستیار امنیتی ممکن نشد"
    finally:
        for path in (request_path, response_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def select_dns(adapter: str, candidates: list[dict], domains: list[str],
               progress=None, timeout_s: float = 55.0) -> dict:
    """Apply and verify several DNS candidates inside one bounded UAC session."""
    progress = progress or (lambda _row: None)
    if sys.platform != "win32":
        return {"ok": False, "error": "انتخاب امن DNS فقط در ویندوز قابل استفاده است"}
    nonce = uuid.uuid4().hex
    runtime = app_paths.runtime_dir()
    request_path = runtime / f"priv-{nonce}.json"
    response_path = runtime / f"priv-{nonce}-result.json"
    progress_path = runtime / f"priv-{nonce}-progress.json"
    document = {
        "version": 1, "nonce": nonce, "operation": "select_dns",
        "adapter": adapter, "candidates": candidates, "domains": domains,
    }
    last_progress = None
    try:
        _validate_request(document)
        request_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = [HELPER_FLAG, str(request_path), str(response_path)]
        else:
            executable = sys.executable
            args = [str(Path(sys.argv[0]).resolve()), HELPER_FLAG,
                    str(request_path), str(response_path)]
        code = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, subprocess.list2cmdline(args),
            str(Path(executable).resolve().parent), 0,
        )
        if code <= 32:
            return {"ok": False, "error": "درخواست دسترسی ادمین لغو شد"}
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if progress_path.exists():
                try:
                    row = json.loads(progress_path.read_text(encoding="utf-8"))
                    marker = (row.get("index"), row.get("name"))
                    if row.get("nonce") == nonce and marker != last_progress:
                        last_progress = marker
                        progress(row)
                except (OSError, ValueError, TypeError):
                    pass
            if response_path.exists():
                result = json.loads(response_path.read_text(encoding="utf-8"))
                if result.get("nonce") != nonce:
                    return {"ok": False, "error": "پاسخ دستیار امنیتی معتبر نبود"}
                return result
            time.sleep(0.1)
        return {"ok": False, "error": "آزمایش DNS در زمان مجاز تمام نشد"}
    except Exception as exc:
        return {"ok": False, "error": str(exc) or "اجرای انتخاب امن DNS ممکن نشد"}
    finally:
        for path in (request_path, response_path, progress_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
