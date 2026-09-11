# Changelog

All notable public changes to LAGSHIFT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No public changes yet.

## [1.1.0] - 2026-09-11

### Added

- Added a privacy-first domestic-tariff inspector that follows redirects,
  resolves the final IPv4/IPv6 destination, and produces a sanitized receipt.
- Added a signed, expiring tariff-catalog format that fails closed when no
  auditable source is configured.
- Added direct links to the official ITO lookup and the 195 billing-complaint
  service without silently sending user URLs to third parties.
- Added a guided first-run experience, unified health tools, system-tray
  controls, and a signed-package self-repair entry point.
- Added a privacy-safe GitHub issue handoff for manually submitted diagnostics.

### Changed

- Uses the official wording `domestic tariff` and no longer presents Iranian
  hosting or a `.ir` suffix as proof of a billing discount.
- Gives the final file server more weight than low-volume landing-page redirects.
- Signed download queries remain usable in volatile memory while tokens and
  fragments are excluded from results, history, and copied receipts.

### Security

- Rejects local/private redirect destinations, insecure catalog updates,
  tampered catalogs, and expired signed tariff data.
- Warns when HTTP, VPN, or WARP makes the observed route unsuitable as billing
  evidence.

## [1.0.4] - 2026-09-09

### Fixed

- Replaced fragile banner timeouts with bounded, severity-aware notification
  lifetimes and a deterministic expiry watchdog.
- Prevented repeated background messages from extending or reopening an expired
  notification.
- Kept the startup reveal animation from replacing the status banner's owned Qt
  opacity effect, which previously left later messages permanently visible.

## [1.0.3] - 2026-09-09

### Fixed

- Upgrades replace the packaged Qt/Python runtime as one tested unit, preventing
  a first-launch DLL mismatch after an in-app update.
- Failed installs remove a partial runtime before restoring the local rollback
  copy, so old and new DLL generations cannot be mixed.

### Security

- Release builds now fail unless they use the pinned Python 3.12, PySide6 6.8.3,
  and shiboken6 6.8.3 toolchain.

## [1.0.2] - 2026-09-09

### Fixed

- RouteDNA diagnostics now always reach a clear terminal state and recover the
  test button after failure or a bounded timeout.
- The public interface no longer exposes the obsolete saved-tunnel panel after
  custom tunnel support was removed.
- Cloudflare signature inspection now runs without a visible PowerShell/taskbar
  flash on Windows.

### Changed

- The WARP page now explains that Cloudflare exposes connection modes, not a
  selectable list of WARP servers that LAGSHIFT could save or rank.

## [1.0.1] - 2026-09-09

### Added

- Automatic background checks against separate signed Stable and Beta manifests.
- A polished in-app update journey with release notes, progress, pause/resume,
  retry, and install-and-restart actions.
- Offline Ed25519 manifest verification plus installer size and SHA-256 checks
  before and immediately before launch.

### Changed

- Unsigned Authenticode builds now require an explicit, plain-language consent
  after cryptographic manifest and payload verification.
- The release build stops immediately when tests or application packaging fail.
- AppRoute worker lifecycle is deterministic during shutdown and automated QA.

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

[Unreleased]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.4...v1.1.0
[1.0.4]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/OmniArcLabs/LAGSHIFT/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/OmniArcLabs/LAGSHIFT/releases/tag/v1.0.0
