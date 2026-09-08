"""Run a reversible live test of the signed Cloudflare WARP client."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import official_warp_service


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    before = official_warp_service.inspect()
    document: dict = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "before": {
            "installed": before.installed,
            "signature_valid": before.signature_valid,
            "service_running": before.service_running,
            "connected": before.connected,
            "mode": before.mode,
            "protocol": before.protocol,
        },
    }
    result: dict = {}
    try:
        result = official_warp_service.connect_best(
            modes=("warp+doh", "warp+dot", "warp", "tunnel_only", "doh", "dot"),
            protocols=("MASQUE", "WireGuard"),
            progress=lambda message: print(message, flush=True),
        )
        document["result"] = result
    finally:
        if result.get("started_by_app"):
            document["cleanup"] = official_warp_service.disconnect_if_started(
                True,
                result.get("original_mode", before.mode),
                result.get("original_protocol", before.protocol),
            )
        after = official_warp_service.inspect()
        document["after"] = {
            "connected": after.connected,
            "mode": after.mode,
            "protocol": after.protocol,
            "detail": after.detail,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
