# LAGSHIFT 1.1 Release Checklist

Last reviewed: 2026-09-11

This checklist separates reproducible project checks from validation that must
be performed on independent Windows devices and networks. An unchecked external
item is a disclosed compatibility boundary, not a hidden product claim.

## Reproducible project checks

- [x] Unit and security-adversarial suite passes: 162 tests.
- [x] GitHub CI and CodeQL workflows pass on `main`.
- [x] Public source excludes bundled VPN/tunnel engines and imported-config UI.
- [x] Full and Light installers are published with SHA-256 checksums.
- [x] Matching source, MPL-2.0 license, third-party notices, and SBOM are public.
- [x] Stable/Beta manifests are Ed25519-signed and update payloads are verified
      by size and SHA-256 before launch; backend-dependent paths fail closed.
- [x] Privacy policy, security policy, support guide, issue forms, and private
      vulnerability reporting are available.
- [x] Release limitations and unsigned Authenticode status are disclosed.

## Verified on the reference build host

- [x] Isolated install, packaged launch, and clean uninstall.
- [x] DPI checks at 100%, 125%, 150%, and 200%.
- [x] Twenty supported profiles passed DNS/TCP/TLS checks on the reference
      network at the documented test date.
- [x] Network recovery, crash recovery, and sanitized diagnostic tests.

## Independent compatibility validation

- [ ] Clean install, upgrade, and uninstall on an independent Windows 10 device.
- [ ] Clean install, upgrade, and uninstall on two independent Windows 11 devices.
- [ ] DNS and AppRoute validation on multiple Iranian fixed and mobile ISPs.
- [ ] WARP validation across sleep/resume, Wi-Fi switching, and unsupported-client
      states on multiple devices.
- [ ] Exclusive-fullscreen, anti-cheat coexistence, and game detection on varied
      GPU/driver configurations.
- [ ] SmartScreen and third-party antivirus reputation monitoring after public
      downloads accumulate.

## Release decision

Version 1.1.0 is a local-first Stable release with the limitations above. Do not
represent unchecked compatibility items as universally verified. New features
remain frozen until blocking 1.0 defects are resolved.
