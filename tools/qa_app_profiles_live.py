"""Run a privacy-safe live reachability matrix for every bundled app profile."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import app_access_service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = []
    for profile in app_access_service.available_profiles():
        result = app_access_service.probe_profile(profile, "smart")
        rows.append({
            "profile": profile.id,
            "attempted": int(result.get("attempted", 0)),
            "resolved": int(result.get("resolved", 0)),
            "reachable": int(result.get("reachable", 0)),
            "tls_ok": int(result.get("tls_ok", 0)),
            "median_ms": int(result.get("median_ms", -1)),
            "healthy": bool(result.get("healthy", False)),
            "suspected_sinkhole": bool(result.get("suspected_sinkhole", False)),
        })
    document = {
        "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "current-network-only",
        "privacy": "No IP addresses or domain names are stored in this report.",
        "profiles": rows,
        "healthy": sum(1 for row in rows if row["healthy"]),
        "total": len(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
