"""Sign a reviewed AppRoute catalog without storing its private key in the repo."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.app_profile_catalog_service import _canonical, verify_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    source.pop("signature", None)
    source.setdefault("version", 1)
    encoded = os.environ.get("LAGSHIFT_PROFILE_PRIVATE_KEY_B64", "")
    if not encoded:
        raise SystemExit("LAGSHIFT_PROFILE_PRIVATE_KEY_B64 is not set")
    try:
        private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded, validate=True))
    except Exception as exc:
        raise SystemExit("The profile signing key is invalid") from exc
    source["signature"] = base64.b64encode(private.sign(_canonical(source))).decode("ascii")
    public = private.public_key().public_bytes_raw()
    verify_catalog(source, base64.b64encode(public).decode("ascii"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
