#!/usr/bin/env bash
# Bengal Download Manager - AppImage Build Automation Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

ARCH="$(uname -m)"
REPO_OWNER="tazihad"
REPO_NAME="bengal-download-manager"

PYINSTALLER_BIN="pyinstaller"
PY_BIN="python3"
if command -v uv >/dev/null 2>&1; then
    PYINSTALLER_BIN="uv run pyinstaller"
    PY_BIN="uv run python"
elif [ -f ".venv/bin/pyinstaller" ]; then
    PYINSTALLER_BIN=".venv/bin/pyinstaller"
    PY_BIN=".venv/bin/python"
elif [ -f "venv/bin/pyinstaller" ]; then
    PYINSTALLER_BIN="venv/bin/pyinstaller"
    PY_BIN="venv/bin/python"
fi

VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || cat VERSION 2>/dev/null || echo "0.1.20")
VERSION="${VERSION#v}"

echo "=== 1. Checking / Building PyInstaller Executable (v$VERSION - $ARCH) ==="

if [ ! -f "dist/bengal-download-manager" ]; then
    PYTHONPATH=src $PYINSTALLER_BIN --noconfirm bengal-download-manager.spec
fi

echo "=== 2. Preparing Icon & AppDir Structure ==="
$PY_BIN -c "from PyQt6.QtGui import QImage; from PyQt6.QtCore import Qt; img = QImage('assets/logo.png'); img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save('assets/bd.com.zihad.BengalDownloadManager.png')"
cp assets/bd.com.zihad.BengalDownloadManager.png assets/bengal-download-manager.png

rm -rf AppDir

install -Dm755 dist/bengal-download-manager AppDir/usr/bin/bengal-download-manager
for s in 16 32 64 128 256 512; do
    if [ -f "assets/icons/${s}x${s}.png" ]; then
        install -Dm644 "assets/icons/${s}x${s}.png" "AppDir/usr/share/icons/hicolor/${s}x${s}/apps/bd.com.zihad.BengalDownloadManager.png"
        install -Dm644 "assets/icons/${s}x${s}.png" "AppDir/usr/share/icons/hicolor/${s}x${s}/apps/bengal-download-manager.png"
    fi
done
if [ -f assets/logo.svg ]; then
    install -Dm644 assets/logo.svg AppDir/usr/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg
    install -Dm644 assets/logo.svg AppDir/usr/share/icons/hicolor/scalable/apps/bengal-download-manager.svg
fi
install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.desktop AppDir/usr/share/applications/bd.com.zihad.BengalDownloadManager.desktop
install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.desktop AppDir/usr/share/applications/bengal-download-manager.desktop
if [ -f flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml ]; then
    install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml AppDir/usr/share/metainfo/bd.com.zihad.BengalDownloadManager.metainfo.xml
    install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml AppDir/usr/share/appdata/bd.com.zihad.BengalDownloadManager.appdata.xml
fi

echo "=== 3. Fetching linuxdeploy and appimage plugin ==="
if [ ! -f linuxdeploy.AppImage ]; then
    wget -q "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${ARCH}.AppImage" -O linuxdeploy.AppImage
    chmod +x linuxdeploy.AppImage
fi

if [ ! -f linuxdeploy-plugin-appimage.AppImage ]; then
    wget -q "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-${ARCH}.AppImage" -O linuxdeploy-plugin-appimage.AppImage
    chmod +x linuxdeploy-plugin-appimage.AppImage
fi

export PATH="$PWD:$PATH"

echo "=== 4. Packaging AppImage with linuxdeploy & zsync ==="
UPDATE_INFO="gh-releases-zsync|${REPO_OWNER}|${REPO_NAME}|latest|bengal-download-manager-*-${ARCH}.AppImage.zsync"
OUTPUT_APPIMAGE="dist/bengal-download-manager-${ARCH}.AppImage"

SIGN_ENV=()
if [ "${SIGN:-0}" = "1" ] || [ "${SIGN:-0}" = "true" ]; then
    SIGN_ENV+=(SIGN=1 LDAI_SIGN=1)
    if [ -n "${GPG_KEY:-}" ]; then
        SIGN_ENV+=(GPG_KEY="${GPG_KEY}" LDAI_GPG_KEY="${GPG_KEY}")
    fi
fi

env "${SIGN_ENV[@]}" \
VERSION="${VERSION}" \
LINUXDEPLOY_OUTPUT_VERSION="${VERSION}" \
UPDATE_INFORMATION="${UPDATE_INFO}" \
LDAI_UPDATE_INFORMATION="${UPDATE_INFO}" \
OUTPUT="${OUTPUT_APPIMAGE}" \
LDAI_OUTPUT="${OUTPUT_APPIMAGE}" \
./linuxdeploy.AppImage \
    --appdir AppDir \
    --desktop-file flatpak/bd.com.zihad.BengalDownloadManager.desktop \
    --icon-file assets/bd.com.zihad.BengalDownloadManager.png \
    --output appimage

# Ensure target files exist or move fallback generated files safely without failing set -e
if [ ! -f "$OUTPUT_APPIMAGE" ]; then
    FALLBACK_APPIMAGE=$(find . -maxdepth 1 -iname "*bengal*download*manager*.AppImage" ! -name "$OUTPUT_APPIMAGE" -print -quit)
    if [ -n "$FALLBACK_APPIMAGE" ]; then
        mv "$FALLBACK_APPIMAGE" "$OUTPUT_APPIMAGE"
    fi
fi

if [ ! -f "${OUTPUT_APPIMAGE}.zsync" ]; then
    FALLBACK_ZSYNC=$(find . -maxdepth 1 -iname "*bengal*download*manager*.AppImage.zsync" ! -name "${OUTPUT_APPIMAGE}.zsync" -print -quit)
    if [ -n "$FALLBACK_ZSYNC" ]; then
        mv "$FALLBACK_ZSYNC" "${OUTPUT_APPIMAGE}.zsync"
    elif command -v zsyncmake &>/dev/null; then
        zsyncmake -u "$(basename "$OUTPUT_APPIMAGE")" -o "${OUTPUT_APPIMAGE}.zsync" "$OUTPUT_APPIMAGE"
    fi
fi

echo "AppImage created: ${OUTPUT_APPIMAGE}"
echo "Zsync file created: ${OUTPUT_APPIMAGE}.zsync"

if [ "${1:-}" = "--run" ]; then
    echo "=== 5. Launching AppImage ==="
    "./${OUTPUT_APPIMAGE}" "${@:2}"
fi
