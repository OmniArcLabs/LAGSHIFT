"""Read-only verification of the build-time package hash catalog."""
from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
from pathlib import Path


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_QUICK_FILES = {
    "LAGSHIFT.exe",
    "_internal/python312.dll",
    "_internal/PySide6/Qt6Core.dll",
    "_internal/PySide6/Qt6Gui.dll",
    "_internal/PySide6/Qt6Widgets.dll",
}


def package_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_catalog(*, root: Path | None = None, catalog_path: Path | None = None,
                   full: bool = False) -> dict:
    root = (root or package_root())
    if root is None:
        return {"available": False, "healthy": False, "reason": "development-mode",
                "checked": 0, "total": 0, "failures": []}
    root = root.resolve()
    catalog_path = (catalog_path or root / "_internal" / "docs" /
                    "integrity-catalog.json").resolve()
    try:
        catalog_path.relative_to(root)
        if catalog_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("catalog-too-large")
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
        entries = document.get("entries")
        if document.get("schema") != 1 or document.get("algorithm") != "SHA-256":
            raise ValueError("catalog-schema")
        if not isinstance(entries, list) or not entries or len(entries) > 5000:
            raise ValueError("catalog-entries")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"available": False, "healthy": False, "reason": str(exc)[:80],
                "checked": 0, "total": 0, "failures": ["catalog"]}

    failures = []
    checked = 0
    catalog_names = [
        str(row.get("path", "")).replace("\\", "/")
        for row in entries if isinstance(row, dict)
    ]
    if len(catalog_names) != len(set(catalog_names)):
        failures.append("catalog-duplicate-path")
    if not full and not _QUICK_FILES.issubset(set(catalog_names)):
        failures.append("critical-set-incomplete")
    for row in entries:
        if not isinstance(row, dict):
            failures.append("catalog-row")
            continue
        relative = str(row.get("path", "")).replace("\\", "/")
        if not full and relative not in _QUICK_FILES:
            continue
        expected = str(row.get("sha256", "")).lower()
        expected_size = row.get("size")
        try:
            candidate = (root / relative).resolve()
            candidate.relative_to(root)
            if not relative or Path(relative).is_absolute() or not _SHA256.fullmatch(expected):
                raise ValueError("invalid-entry")
            if not isinstance(expected_size, int) or expected_size < 0:
                raise ValueError("invalid-size")
            checked += 1
            if (not candidate.is_file() or candidate.stat().st_size != expected_size
                    or _digest(candidate) != expected):
                failures.append(relative)
        except (OSError, ValueError):
            failures.append(relative or "invalid-entry")
    if not full and checked < len(_QUICK_FILES) and "critical-set-incomplete" not in failures:
        failures.append("critical-set-incomplete")
    return {
        "available": True,
        "healthy": not failures,
        "reason": "ok" if not failures else "mismatch",
        "checked": checked,
        "total": len(entries),
        "failures": failures[:20],
        "trust": "unsigned-catalog-until-authenticode",
    }


def _read_acl(root: Path) -> dict:
    environment = os.environ.copy()
    environment["LAGSHIFT_ACL_ROOT"] = str(root)
    script = r"""
$ErrorActionPreference='Stop'
$acl=Get-Acl -LiteralPath $env:LAGSHIFT_ACL_ROOT
[pscustomobject]@{
  owner=[string]$acl.Owner
  protected=[bool]$acl.AreAccessRulesProtected
  rules=@($acl.Access | ForEach-Object {
    [pscustomobject]@{identity=[string]$_.IdentityReference; rights=[string]$_.FileSystemRights; type=[string]$_.AccessControlType}
  })
} | ConvertTo-Json -Depth 4 -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        timeout=8, env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise OSError((result.stderr or "ACL query failed")[-240:])
    return json.loads(result.stdout)


def audit_package_acl(root: Path | None = None) -> dict:
    """Report whether broad non-admin principals can modify the package root."""
    root = root or package_root()
    if root is None or os.name != "nt":
        return {"available": False, "safe": False, "reason": "development-mode"}
    try:
        document = _read_acl(root.resolve())
        rules = document.get("rules") or []
        if isinstance(rules, dict):
            rules = [rules]
        dangerous = []
        for row in rules:
            identity = str(row.get("identity", "")).casefold()
            rights = str(row.get("rights", "")).casefold()
            allowed = str(row.get("type", "")).casefold() == "allow"
            broad = any(name in identity for name in (
                "everyone", "authenticated users", "builtin\\users", "\\users",
            ))
            writable = any(name in rights for name in (
                "write", "modify", "fullcontrol", "createdirectories", "createfiles",
            ))
            if allowed and broad and writable:
                dangerous.append(str(row.get("identity", ""))[:80])
        return {
            "available": True, "safe": not dangerous,
            "owner": str(document.get("owner", ""))[:120],
            "dangerous": dangerous[:8],
            "reason": "ok" if not dangerous else "broad-write-access",
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"available": False, "safe": False, "reason": str(exc)[:120]}
