"""Fail the public release if forbidden engines or Python modules are packaged."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


FORBIDDEN_FILES = {"xray.exe", "sing-box.exe", "openvpn.exe", "wintun.dll"}
FORBIDDEN_MODULES = {
    "app.services.config_parser", "app.services.subscription_service",
    "app.services.tunnel_service", "app.services.tunnel_storage_service",
    "app.services.warp_service",
}


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path()
    executable = root / "LAGSHIFT.exe"
    if not executable.is_file():
        raise SystemExit("Public package executable was not found")
    found_files = {
        item.name.casefold() for item in root.rglob("*") if item.is_file()
    } & FORBIDDEN_FILES
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller.utils.cliutils.archive_viewer",
         "--recursive", "--brief", str(executable)],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=90,
    )
    if result.returncode != 0:
        raise SystemExit("PyInstaller archive could not be audited")
    names = {line.strip() for line in result.stdout.splitlines()}
    found_modules = names & FORBIDDEN_MODULES
    if found_files or found_modules:
        raise SystemExit(
            "Forbidden public payload: "
            + ", ".join(sorted(found_files | found_modules))
        )
    print("Public archive audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
