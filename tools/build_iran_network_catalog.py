"""Build LAGSHIFT's offline Iran network-location catalog from RIPE stats.

This catalog answers only whether an address is allocated to IR in the public
RIR statistics.  It is deliberately kept separate from the tariff catalog:
network allocation is useful evidence, but it is not proof of discounted
billing by an operator.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path


def build(source: Path) -> dict:
    networks: list[ipaddress._BaseNetwork] = []
    revision = "unknown"
    for raw in source.read_text(encoding="utf-8", errors="strict").splitlines():
        if raw.startswith("2|ripencc|"):
            fields = raw.split("|")
            if len(fields) >= 6:
                revision = fields[5]
            continue
        if not raw.startswith("ripencc|IR|"):
            continue
        fields = raw.split("|")
        if len(fields) < 7 or fields[6] not in {"allocated", "assigned"}:
            continue
        kind, start, value = fields[2], fields[3], fields[4]
        if kind == "ipv4":
            first = ipaddress.IPv4Address(start)
            count = int(value)
            if count <= 0:
                continue
            last = ipaddress.IPv4Address(int(first) + count - 1)
            networks.extend(ipaddress.summarize_address_range(first, last))
        elif kind == "ipv6":
            networks.append(ipaddress.IPv6Network(f"{start}/{int(value)}", strict=True))

    collapsed = [
        *ipaddress.collapse_addresses(network for network in networks if network.version == 4),
        *ipaddress.collapse_addresses(network for network in networks if network.version == 6),
    ]
    return {
        "version": 1,
        "revision": revision,
        "source_name": "RIPE NCC delegated statistics",
        "source_url": "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-latest",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notice_fa": (
            "این فهرست فقط تخصیص ثبتی IP به ایران را نشان می‌دهد و اثبات تعرفهٔ نیم‌بها نیست."
        ),
        "networks": [str(network) for network in collapsed],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = build(args.source)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(document['networks'])} networks ({document['revision']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
