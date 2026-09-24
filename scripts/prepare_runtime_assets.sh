#!/usr/bin/env bash
# Prepares a clean runtime assets directory containing only essential application assets.
# Strictly excludes promotional banners, screenshots, website badges, and foreign-architecture binaries.
set -euo pipefail

TARGET_DIR="$1"
ARCH="${2:-$(uname -m)}"

# Normalize architecture string
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    TARGET_ARCH="x86_64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    TARGET_ARCH="aarch64"
else
    TARGET_ARCH="$ARCH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_ASSETS="$ROOT_DIR/assets"

rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

# 1. Essential runtime directories
if [ -d "$SRC_ASSETS/fonts" ]; then
    cp -r "$SRC_ASSETS/fonts" "$TARGET_DIR/"
fi

if [ -d "$SRC_ASSETS/icons" ]; then
    cp -r "$SRC_ASSETS/icons" "$TARGET_DIR/"
fi

if [ -d "$SRC_ASSETS/translations" ]; then
    cp -r "$SRC_ASSETS/translations" "$TARGET_DIR/"
fi

# 2. Target architecture binary only (strictly exclude foreign-architecture binaries)
if [ -d "$SRC_ASSETS/bin/linux/$TARGET_ARCH" ]; then
    mkdir -p "$TARGET_DIR/bin/linux/$TARGET_ARCH"
    cp "$SRC_ASSETS/bin/linux/$TARGET_ARCH/aria2c" "$TARGET_DIR/bin/linux/$TARGET_ARCH/" 2>/dev/null || true
    chmod +x "$TARGET_DIR/bin/linux/$TARGET_ARCH/aria2c" 2>/dev/null || true
elif [ -d "$SRC_ASSETS/bin/$TARGET_ARCH" ]; then
    mkdir -p "$TARGET_DIR/bin/$TARGET_ARCH"
    cp "$SRC_ASSETS/bin/$TARGET_ARCH/aria2c" "$TARGET_DIR/bin/$TARGET_ARCH/" 2>/dev/null || true
    chmod +x "$TARGET_DIR/bin/$TARGET_ARCH/aria2c" 2>/dev/null || true
fi

# 3. Essential brand icons, logo, tray icons, and desktop entry
# (Notice: promotional posters, screenshots, and website SVG badges are intentionally omitted)
for f in logo.svg logo.png bengal-download-manager.png bd.com.zihad.BengalDownloadManager.png \
         icons/tray/tray_monochrome_dark.png icons/tray/tray_monochrome_dark.svg \
         icons/tray/tray_monochrome_light.png icons/tray/tray_monochrome_light.svg \
         tray_monochrome_dark.png tray_monochrome_dark.svg \
         tray_monochrome_light.png tray_monochrome_light.svg \
         bd.com.zihad.BengalDownloadManager.desktop; do
    if [ -f "$SRC_ASSETS/$f" ]; then
        cp "$SRC_ASSETS/$f" "$TARGET_DIR/$(basename "$f")"
    fi
done
