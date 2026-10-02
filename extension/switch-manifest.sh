#!/usr/bin/env bash
# Helper script to switch extension/manifest.json between Chrome and Firefox targets
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-chrome}"

if [ "$TARGET" = "chrome" ]; then
    cp "$DIR/manifest.chrome.json" "$DIR/manifest.json"
    echo "Switched extension/manifest.json to Chrome target (service_worker, downloads.ui, no webRequestBlocking)."
elif [ "$TARGET" = "firefox" ]; then
    cp "$DIR/manifest.firefox.json" "$DIR/manifest.json"
    echo "Switched extension/manifest.json to Firefox target (scripts, theme_icons, gecko ID, webRequestBlocking)."
else
    echo "Usage: $0 [chrome|firefox]"
    exit 1
fi
