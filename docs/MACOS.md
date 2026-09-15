# LAGSHIFT for macOS (Preview)

The macOS edition is a native, reduced product surface for macOS 13 or newer.
Separate packages are built and tested for Intel (`x86_64`) and Apple Silicon
(`arm64`). It does not include the Windows game tab or Windows-only driver and
launcher profiles.

## Included in the preview

- FusionDNS Hybrid selection across Iranian and global resolvers, with exact
  restoration of the selected macOS network service
- App Access profiles with per-destination DNS/TCP/TLS checks
- Official Cloudflare WARP discovery and control through Cloudflare's signed app
- RouteDNA local measurements and privacy-first local history
- Traffic Insight and Iranian traffic-status checks
- Keychain-protected rollback state and local crash reports

The application does not provide a proprietary relay or VPN. App Access may
change the selected network service's DNS or ask the separately installed,
official Cloudflare WARP client to connect. It does not inject into apps or read
their traffic content. FusionDNS compares resolver families and applies one
verified profile at a time; it is not a simultaneous split-DNS proxy.

## Installation and Gatekeeper

The project does not use a paid Apple Developer certificate and is not notarized.
CI packages are ad-hoc signed to seal the bundle, but macOS can still display an
unidentified-developer warning. Download only from the official GitHub Releases
page, compare the published SHA-256 value, drag `LAGSHIFT.app` to Applications,
then use **System Settings → Privacy & Security → Open Anyway** if macOS blocks
the first launch.

Do not disable Gatekeeper globally. Automatic in-app updates are intentionally
disabled in the preview so a Windows installer can never be offered on macOS.

## Test checklist

1. Launch the app and complete the privacy screen.
2. Confirm that no Games tab or Windows-only app profiles are visible.
3. Select the active Wi-Fi or Ethernet service, apply a DNS profile, then
   disconnect and confirm the original automatic/static DNS is restored.
4. If Cloudflare WARP is installed, verify its signature is accepted and test
   connect/disconnect without repeated password prompts.
5. Run a light RouteDNA check and Traffic Insight lookup.
6. Quit and reopen the app, then export a local support report if anything fails.

Test DNS restoration on both an Intel Mac and an Apple Silicon Mac before calling
the preview stable.
