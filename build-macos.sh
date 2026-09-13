#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 tools/create_macos_icon.py
python3 -m PyInstaller --noconfirm --clean LAGSHIFT-macos.spec

APP="$ROOT/dist/LAGSHIFT.app"
if [[ ! -d "$APP" ]]; then
  echo "LAGSHIFT.app was not produced" >&2
  exit 12
fi

# Free ad-hoc signing seals every nested binary. It is not Apple notarization.
/usr/bin/codesign --force --deep --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/LAGSHIFT" --health-check

ARCH="$(uname -m)"
ZIP="$ROOT/dist/LAGSHIFT-1.2.0-macOS-$ARCH.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/lagshift-dmg.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
/usr/bin/ditto "$APP" "$STAGE/LAGSHIFT.app"
ln -s /Applications "$STAGE/Applications"
/usr/bin/hdiutil create -volname "LAGSHIFT 1.2.0" -srcfolder "$STAGE" \
  -ov -format UDZO "$ROOT/dist/LAGSHIFT-1.2.0-macOS-$ARCH.dmg"

/usr/bin/shasum -a 256 "$ZIP" "$ROOT/dist/LAGSHIFT-1.2.0-macOS-$ARCH.dmg"
