"""Provide a bundled, platform-independent CA trust path for HTTPS probes."""
from __future__ import annotations

import os


def configure_tls_trust() -> str:
    """Use Mozilla's bundled CA file without overriding an explicit admin choice."""
    try:
        import certifi

        path = certifi.where()
    except (ImportError, OSError):
        return ""
    os.environ.setdefault("SSL_CERT_FILE", path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", path)
    return path
