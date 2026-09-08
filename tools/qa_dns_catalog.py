"""Create a reproducible live-health report for the bundled DNS catalog."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.network_adapter import DEFAULT_DNS_PROFILES
from app.services.connectivity_service import benchmark_dns_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rows = []
    for profile in DEFAULT_DNS_PROFILES:
        measured = benchmark_dns_profile(profile)
        rows.append({
            key: value for key, value in measured.items() if key != "profile"
        } | {
            "primary": profile.primary,
            "secondary": profile.secondary,
            "region": profile.region,
            "purpose": profile.purpose,
        })
        print(f"{profile.name}: {measured['score']}/100", flush=True)

    document = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "network_specific": True,
        "profiles": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if any(row["score"] > 0 for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
