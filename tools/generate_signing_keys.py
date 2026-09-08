"""Generate offline Ed25519 release keys in an explicitly selected private folder."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def raw_private(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output == Path(__file__).resolve().parents[1] or Path(__file__).resolve().parents[1] in output.parents:
        raise SystemExit("Private keys must be generated outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "lagshift-signing-keys.json"
    if target.exists():
        raise SystemExit("Refusing to overwrite existing signing keys")
    update = Ed25519PrivateKey.generate()
    profiles = Ed25519PrivateKey.generate()
    document = {
        "warning": "OFFLINE PRIVATE KEYS - DO NOT COMMIT OR UPLOAD",
        "update_private_key_b64": base64.b64encode(raw_private(update)).decode("ascii"),
        "update_public_key_b64": base64.b64encode(raw_public(update)).decode("ascii"),
        "profile_private_key_b64": base64.b64encode(raw_private(profiles)).decode("ascii"),
        "profile_public_key_b64": base64.b64encode(raw_public(profiles)).decode("ascii"),
    }
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
