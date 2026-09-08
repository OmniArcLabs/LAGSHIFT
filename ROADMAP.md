# LAGSHIFT Roadmap

This roadmap describes direction, not a promise or release date. A capability is
public only after implementation, reversible network testing, privacy review,
and validation on real devices and networks.

## Current — stabilize 1.0

- Validate clean install, upgrade, uninstall, and recovery on Windows 10 and 11.
- Test DNS and supported application profiles on several Iranian ISPs.
- Validate WARP behavior, UAC frequency, sleep/resume, and network switching.
- Improve accessibility and RTL rendering from real user reports.
- Keep all backend-dependent functionality disabled until production services
  and retention rules exist.

## Next — evidence-driven reliability

- Publish reproducible compatibility results without claiming universal access.
- Expand supported application profiles only when login, API, and CDN checks can
  be verified safely.
- Add signed update delivery after a production endpoint and offline release key
  process are ready.
- Pursue trusted Windows code signing when sustainable for the project.

## Later — infrastructure-dependent work

- Deploy the privacy-minimized control plane for signed catalogs and coarse,
  opt-in network hints.
- Evaluate GameLink relay infrastructure only after security, cost, abuse, and
  legal reviews.
- Consider anonymous aggregate route learning with explicit consent, minimal
  retention, and public documentation.

## Explicitly out of scope for the public edition

- General-purpose VPN service.
- Imported tunnel configurations or subscriptions.
- Claims of guaranteed ping reduction, universal access, or identical behavior
  across operators.
- Silent collection of public IP addresses, credentials, browsing history, or
  application content.
