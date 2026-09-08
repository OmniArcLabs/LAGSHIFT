# LAGSHIFT Security Policy

## Supported release

Only the newest public Stable release is supported. Release candidates are for
testing and must not be presented as production-ready.

## Reporting a vulnerability

The official publisher page is https://github.com/OmniArcLabs. The LAGSHIFT
repository must enable GitHub Private Vulnerability Reporting before Stable
release. Until that private channel is published, do not post security reports
or diagnostic archives in a public issue. Keep exported diagnostics local and
never include passwords, account tokens, private configuration links, or
screenshots that contain personal data.

## Security boundaries

- The desktop interface runs without administrator rights.
- A one-shot schema-limited helper requests elevation only for approved DNS
  changes and exact restoration.
- Update metadata must be HTTPS, Ed25519-signed, size-bounded, and SHA-256
  verified. An installer is launched only after a valid Authenticode check.
- Optional diagnostics are local-first and sanitized. Automatic upload is off.
- Coarse RouteDNA geography is opt-in. The app does not persist or display the
  public IP address.
- Public builds do not accept imported tunnels or subscriptions and do not ship
  Xray, sing-box, Wintun, or OpenVPN engines.

## Known release gates

- Current RC artifacts are unsigned. A publisher certificate and trusted
  timestamp are required before Stable distribution.
- The Cloudflare control plane, update keys, and public security address are not
  configured in source control.
- WARP and exclusive-fullscreen behavior require multi-network/device QA.

## Publisher checklist

1. Keep private signing keys offline and outside the repository.
2. Sign the application, privileged helper path, engine installer, and public
   bootstrapper; apply a trusted timestamp.
3. Publish the matching support/security address and retention policy.
4. Generate and archive the release SBOM, SHA-256 catalog, test report, and
   signed update manifest.
5. Never weaken verification to make a failed update or network test pass.
