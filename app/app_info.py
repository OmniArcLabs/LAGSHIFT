"""Single source of truth for product identity and release behavior."""

APP_NAME = "LAGSHIFT"
APP_DISPLAY_NAME = "LAGSHIFT — لگ‌شیفت"
APP_VERSION = "1.0.4"
BUILD_NUMBER = "1004"
BRAND_PUBLISHER = "OMNIARC"
# These values are intentionally empty until the owner approves public/legal
# identity. Release tooling must fail the Stable gate rather than invent them.
LEGAL_PUBLISHER_NAME = ""
SUPPORT_EMAIL = ""
SUPPORT_URL = "https://github.com/OmniArcLabs/LAGSHIFT/issues"
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

# LAGSHIFT 1.0 Stable is intentionally local-first. These switches are the
# release boundary, including when an old settings file still contains cloud
# preferences from a development build.
ALLOW_GAMELINK = EDITION == "developer"
ALLOW_REMOTE_BACKEND = EDITION == "developer"

# Signed static manifests are served from the public repository. The private
# Ed25519 key is kept offline; only this public verification key ships.
UPDATE_MANIFEST_URLS = {
    "stable": "https://raw.githubusercontent.com/OmniArcLabs/LAGSHIFT/main/update-manifest-stable.json",
    "beta": "https://raw.githubusercontent.com/OmniArcLabs/LAGSHIFT/main/update-manifest-beta.json",
}
UPDATE_MANIFEST_URL = UPDATE_MANIFEST_URLS["stable"]
UPDATE_PUBLIC_KEY_B64 = "rxoKwmIzSFhVzor4nRTNyJk0+PjR5M066MEKA/onKh4="
UPDATE_CHANNEL = "stable"

# Optional signed App Access policy catalog. A static HTTPS file on Cloudflare
# Pages or an equivalent host is sufficient; empty values fail closed.
APP_PROFILE_MANIFEST_URL = ""
APP_PROFILE_PUBLIC_KEY_B64 = ""

# Optional signed domestic-traffic eligibility catalog.  It stays empty until
# OMNIARC has a stable, auditable source; the UI then reports "unknown" instead
# of guessing from .ir or geolocation.
TARIFF_CATALOG_URL = ""
TARIFF_CATALOG_PUBLIC_KEY_B64 = ""
