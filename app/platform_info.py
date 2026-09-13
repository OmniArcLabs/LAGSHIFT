"""Small, dependency-free platform capability map used by the UI and services."""
from __future__ import annotations

import platform
import sys


IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
MACHINE = platform.machine().strip().lower()
IS_APPLE_SILICON = IS_MACOS and MACHINE in {"arm64", "aarch64"}
IS_INTEL_MAC = IS_MACOS and MACHINE in {"x86_64", "amd64"}

# The macOS product deliberately omits gaming/session hooks.  DNS, AppRoute,
# Traffic Insight and the official Cloudflare client remain useful there.
SUPPORTS_GAMES = IS_WINDOWS
SUPPORTS_SYSTEM_DNS = IS_WINDOWS or IS_MACOS
SUPPORTS_OFFICIAL_WARP = IS_WINDOWS or IS_MACOS
PLATFORM_LABEL = (
    "macOS · Apple Silicon" if IS_APPLE_SILICON else
    "macOS · Intel" if IS_INTEL_MAC else
    "Windows" if IS_WINDOWS else platform.system() or "Unknown"
)
