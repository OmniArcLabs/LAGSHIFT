# Changelog

All notable public changes to LAGSHIFT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No public changes yet. Development is feature-frozen while 1.0 receives
multi-device and multi-network validation.

## [1.0.0] - 2026-09-08

### Added

- Smart DNS selection using measured response, variation, stability, and intent.
- AppRoute profiles for twenty supported applications and launchers.
- Local RouteDNA memory, network-change detection, data budget, and route
  explanation.
- Game detection, route profiles, MTU checks, limited QoS, and session recovery.
- Optional control of the official Cloudflare WARP client with explicit
  device-wide warnings and route verification.
- Sanitized local diagnostics, fail-closed update verification, SBOM, checksum
  catalog, and privacy-first settings.
- Lightweight and self-contained Windows installers.

### Security

- The main interface runs without administrator rights.
- Elevated work is restricted to schema-validated, one-shot network operations.
- The public build excludes imported tunnels, subscriptions, Xray, sing-box,
  Wintun, and OpenVPN engines.

### Known limitations

- Version 1.0.0 executables are not Authenticode-signed.
- WARP and exclusive-fullscreen behavior are not validated across multiple ISPs
  and devices.
- GameLink relay, public backend, remote geography, anonymous radar, and remote
  bandwidth tests are disabled in the public build.

[Unreleased]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/OmniArcLabs/LAGSHIFT/releases/tag/v1.0.0
