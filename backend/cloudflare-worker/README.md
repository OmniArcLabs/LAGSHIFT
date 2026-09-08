# LAGSHIFT control plane

This Worker is the deployable, low-cost control plane for signed releases,
signed AppRoute catalogs, short-lived device bootstrap sessions, and strictly
opt-in anonymous path-health samples.

RouteDNA also exposes two privacy-bounded endpoints:

- `GET /v1/network/hint` returns only Cloudflare's coarse country, region,
  city, ASN and AS organization metadata. The response never includes the
  requester IP and is marked `private, no-store`.
- `GET /v1/probe/download?bytes=...` accepts only 512 KiB, 3 MiB or 4 MiB and
  returns non-cacheable zero bytes for an explicitly initiated bandwidth test.

It is intentionally **not** a game traffic relay. Cloudflare Workers do not
turn the current local GameLink engine into a UDP relay, and `/health` reports
`relay: false` so clients and operators cannot confuse control-plane readiness
with accelerated-route availability.

It is also intentionally **not** presented as a DNS-leak detector. Workers do
not receive authoritative DNS query events, so resolver-leak proof needs the
separate privacy-reviewed design in `../../DNS_LEAK_AUDIT_DESIGN.md`.

## Safe deployment

1. Copy `wrangler.toml.example` to `wrangler.toml` and create the KV namespace.
2. Store a random 32-byte-or-longer `SESSION_SIGNING_SECRET` with `wrangler secret put`.
3. Optionally store `BOOTSTRAP_ACCESS_TOKEN`; without it bootstrap is public.
4. Keep `RADAR_ENABLED=false` until privacy text, retention, and abuse limits are approved.
5. Upload only offline-signed JSON as `update-manifest` and `app-profile-manifest` KV keys.
6. Put the final HTTPS endpoints and Ed25519 public keys in `app/app_info.py`, rebuild, and test.

The platform can still observe request IPs in transient infrastructure logs.
Disable Worker logs or configure the shortest practical retention before
enabling geographic hints in production. LAGSHIFT never sends an IP field and
never writes the returned readable operator/region into local route history;
only a one-way operator-group hash can be used as a low-confidence local prior.

The offline Ed25519 private key must never be uploaded to Cloudflare or committed
to this repository. The Worker merely serves signed public documents.
