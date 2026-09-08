"""Single source of truth for product identity and release behavior."""

APP_NAME = "LAGSHIFT"
APP_DISPLAY_NAME = "LAGSHIFT — لگ‌شیفت"
APP_VERSION = "1.0.0"
BUILD_NUMBER = "dev"
BRAND_PUBLISHER = "OMNIARC"
# These values are intentionally empty until the owner approves public/legal
# identity. Release tooling must fail the Stable gate rather than invent them.
LEGAL_PUBLISHER_NAME = ""
SUPPORT_EMAIL = ""
SUPPORT_URL = "https://github.com/OmniArcLabs"
DATA_FOLDER_NAME = "LAGSHIFT"
LEGACY_DATA_FOLDER_NAME = "GameDNS"
TERMS_VERSION = "1.3"
PRIVACY_VERSION = "1.3"

# Public builds intentionally expose only the game-focused product surface.
# The future private developer build replaces this value during its own build.
EDITION = "public"
ALLOW_CUSTOM_TUNNELS = EDITION == "developer"
ALLOW_SYSTEM_WIDE_TUNNEL = EDITION == "developer"
# The legacy device-registration path depends on an undocumented third-party
# endpoint and is never shipped as a public feature.
ALLOW_LEGACY_WARP_REGISTRATION = EDITION == "developer"

# Filled by the release pipeline after the production update host and offline
# Ed25519 signing key are created. Empty values intentionally disable networking.
UPDATE_MANIFEST_URL = ""
UPDATE_PUBLIC_KEY_B64 = ""
UPDATE_CHANNEL = "stable"

# Optional signed App Access policy catalog. A static HTTPS file on Cloudflare
# Pages or an equivalent host is sufficient; empty values fail closed.
APP_PROFILE_MANIFEST_URL = ""
APP_PROFILE_PUBLIC_KEY_B64 = ""
