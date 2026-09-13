#!/bin/bash
set -Eeuo pipefail
trap 'status=$?; echo "::error title=macOS package command failed::${BASH_COMMAND} exited with ${status}"; exit "$status"' ERR

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
set +e
HEALTH_OUTPUT="$("$APP/Contents/MacOS/LAGSHIFT" --health-check 2>&1)"
HEALTH_STATUS=$?
set -e
if [[ $HEALTH_STATUS -ne 0 ]]; then
  HEALTH_OUTPUT="${HEALTH_OUTPUT//'%'/'%25'}"
  HEALTH_OUTPUT="${HEALTH_OUTPUT//$'\r'/'%0D'}"
  HEALTH_OUTPUT="${HEALTH_OUTPUT//$'\n'/'%0A'}"
  echo "::error title=Packaged Intel/ARM health check failed::${HEALTH_OUTPUT:0:3000}"
  exit "$HEALTH_STATUS"
fi

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
