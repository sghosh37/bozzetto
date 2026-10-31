#!/bin/bash
# Builds PhotoScan.app (and the photoscan-cli tool) into ./dist
# Uses swiftc directly, so it works with only the Command Line Tools (no Xcode needed).
set -euo pipefail
cd "$(dirname "$0")"

if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "Swift isn't installed. Run:  xcode-select --install   then run this script again."
  exit 1
fi

SDK="$(xcrun --sdk macosx --show-sdk-path)"
ARCH="$(uname -m)"                      # arm64 on Apple Silicon, x86_64 on Intel
TARGET="${ARCH}-apple-macos13.0"
SWIFTC=(xcrun swiftc -O -sdk "$SDK" -target "$TARGET")

# Everything is compiled as one module, so drop the "import PhotoScanCore" lines in a temp copy
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/core" "$WORK/app" "$WORK/cli"
cp Sources/PhotoScanCore/*.swift "$WORK/core/"
sed '/^import PhotoScanCore$/d' Sources/PhotoScan/PhotoScanApp.swift > "$WORK/app/PhotoScanApp.swift"
sed '/^import PhotoScanCore$/d' Sources/PhotoScanCLI/main.swift > "$WORK/cli/main.swift"

mkdir -p dist
echo "Building the app (about a minute)…"
"${SWIFTC[@]}" -parse-as-library "$WORK"/core/*.swift "$WORK/app/PhotoScanApp.swift" -o "$WORK/PhotoScan"

echo "Building the command-line tool…"
"${SWIFTC[@]}" "$WORK"/core/*.swift "$WORK/cli/main.swift" -o dist/photoscan-cli

APP="dist/PhotoScan.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$WORK/PhotoScan" "$APP/Contents/MacOS/PhotoScan"
cp Resources/Info.plist "$APP/Contents/Info.plist"

# Local ad-hoc signature so macOS will launch it on this Mac
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo
echo "Done:"
echo "  App:  $(pwd)/$APP   (drag it into Applications)"
echo "  CLI:  $(pwd)/dist/photoscan-cli"
open dist
