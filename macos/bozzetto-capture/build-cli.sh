#!/bin/bash
# Bozzetto: builds bozzetto-capture (Apple Object Capture helper) with swiftc.
# Works with the Command Line Tools alone (no Xcode). Output: macos/bozzetto-capture/dist/bozzetto-capture
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
cd "$(dirname "$0")"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
mkdir -p dist
xcrun swiftc -O -sdk "$SDK" -target "$(uname -m)-apple-macos13.0" \
  Sources/BozzettoCapture/*.swift -o dist/bozzetto-capture
echo "Built $(pwd)/dist/bozzetto-capture"
