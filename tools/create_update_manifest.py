"""Create a signed release manifest without ever storing the private key in the repo."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.update_service import _canonical_payload, _validate_https_url, _version_tuple


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("installer", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    parser.add_argument("--url", required=True)
    parser.add_argument("--release-url", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--mandatory", action="store_true")
    args = parser.parse_args()

    installer = args.installer.resolve()
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        raise SystemExit("A Windows installer file is required")
    _version_tuple(args.version)
    _validate_https_url(args.url)
    if args.release_url:
        _validate_https_url(args.release_url)
    encoded_key = os.environ.get("LAGSHIFT_UPDATE_PRIVATE_KEY_B64", "")
    if not encoded_key:
        raise SystemExit("LAGSHIFT_UPDATE_PRIVATE_KEY_B64 is not set")
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(encoded_key, validate=True)
        )
    except Exception as exc:
        raise SystemExit("The update signing key is invalid") from exc

    digest = hashlib.sha256()
    with installer.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    document = {
        "version": args.version,
        "channel": args.channel,
        "url": args.url,
        "sha256": digest.hexdigest(),
        "size": installer.stat().st_size,
        "notes": args.notes[:4000],
        "mandatory": args.mandatory,
    }
    if args.release_url:
        document["release_url"] = args.release_url
    document["signature"] = base64.b64encode(
        private_key.sign(_canonical_payload(document))
    ).decode("ascii")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
