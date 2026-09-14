#!/usr/bin/env bash
# Bengal Download Manager - Windows Build Script (Bash / Git-Bash / CI)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINDOWS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$(cd "$WINDOWS_DIR/.." && pwd)"
ROOT_DIR="$(cd "$BUILD_DIR/.." && pwd)"

cd "$ROOT_DIR"

VERSION=$(cat VERSION 2>/dev/null || echo "0.2.46")
VERSION="${VERSION#v}"

echo "========================================================"
echo " Building Bengal Download Manager Windows Release v$VERSION"
echo "========================================================"

mkdir -p "$WINDOWS_DIR/bin" "$ROOT_DIR/dist/windows"

# 1. Download third-party binaries if missing
if [ ! -f "$WINDOWS_DIR/bin/yt-dlp.exe" ]; then
    echo "Downloading yt-dlp.exe..."
    curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -o "$WINDOWS_DIR/bin/yt-dlp.exe"
fi

if [ ! -f "$WINDOWS_DIR/bin/aria2c.exe" ]; then
    echo "Downloading aria2c.exe..."
    curl -fsSL "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip" -o "$WINDOWS_DIR/bin/aria2.zip"
    unzip -q -o "$WINDOWS_DIR/bin/aria2.zip" -d "$WINDOWS_DIR/bin/aria2_tmp"
    find "$WINDOWS_DIR/bin/aria2_tmp" -name "aria2c.exe" -exec cp {} "$WINDOWS_DIR/bin/" \;
    rm -rf "$WINDOWS_DIR/bin/aria2_tmp" "$WINDOWS_DIR/bin/aria2.zip"
fi

# 2. PyInstaller Build
echo "Building standalone executable using PyInstaller..."
PY_CMD="pyinstaller"
if command -v uv >/dev/null 2>&1; then
    PY_CMD="uv run pyinstaller"
fi

$PY_CMD --noconfirm \
    --distpath "$ROOT_DIR/dist" \
    --workpath "$ROOT_DIR/.pyinstaller-build" \
    "$WINDOWS_DIR/config/bengal-download-manager.spec"

# 3. Inno Setup Compiler if running on Windows
if command -v iscc.exe >/dev/null 2>&1; then
    echo "Compiling Inno Setup installer..."
    iscc.exe "/DAppVersion=$VERSION" "$WINDOWS_DIR/config/installer.iss"
elif [ -f "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" ]; then
    "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" "/DAppVersion=$VERSION" "$WINDOWS_DIR/config/installer.iss"
fi

echo "========================================================"
echo "✓ Windows build finished!"
echo "========================================================"
