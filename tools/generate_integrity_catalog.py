"""Generate a deterministic SHA-256 catalog for a completed one-folder build."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


CATALOG_RELATIVE = Path("_internal") / "docs" / "integrity-catalog.json"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_catalog(root: Path) -> dict:
    root = root.resolve()
    catalog_path = (root / CATALOG_RELATIVE).resolve()
    rows = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path.resolve() == catalog_path:
            continue
        relative = path.relative_to(root).as_posix()
        rows.append({
            "path": relative,
            "size": path.stat().st_size,
            "sha256": digest_file(path),
        })
    return {
        "schema": 1,
        "product": "LAGSHIFT",
        "algorithm": "SHA-256",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "entries": rows,
        "trust": "Catalog detects accidental/tampered files; Authenticode remains the release trust root.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir() or not (root / "LAGSHIFT.exe").is_file():
        raise SystemExit("A completed LAGSHIFT distribution directory is required")
    destination = root / CATALOG_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(build_catalog(root), ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    print(f"Integrity catalog ready: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
