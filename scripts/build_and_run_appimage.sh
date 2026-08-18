#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

VERSION="1.0.0"
ARCH="$(uname -m)"
REPO_OWNER="tazihad"
REPO_NAME="bengal-download-manager"

echo "=== 1. Checking / Building PyInstaller Executable ==="
if [ ! -f "dist/bengal-download-manager" ]; then
    PYTHONPATH=src venv/bin/pyinstaller --noconfirm bengal-download-manager.spec
fi

echo "=== 2. Preparing Icon & AppDir Structure ==="
venv/bin/python -c "from PyQt6.QtGui import QImage; from PyQt6.QtCore import Qt; img = QImage('assets/logo.png'); img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save('assets/io.github.tazihad.bengal-download-manager.png')"
cp assets/io.github.tazihad.bengal-download-manager.png assets/bengal-download-manager.png

rm -rf AppDir

install -Dm755 dist/bengal-download-manager AppDir/usr/bin/bengal-download-manager
for s in 16 32 64 128 256 512 1024; do
    if [ -f "assets/icons/${s}x${s}.png" ]; then
        install -Dm644 "assets/icons/${s}x${s}.png" "AppDir/usr/share/icons/hicolor/${s}x${s}/apps/io.github.tazihad.bengal-download-manager.png"
        install -Dm644 "assets/icons/${s}x${s}.png" "AppDir/usr/share/icons/hicolor/${s}x${s}/apps/bengal-download-manager.png"
    fi
done
if [ -f assets/logo.svg ]; then
    install -Dm644 assets/logo.svg AppDir/usr/share/icons/hicolor/scalable/apps/io.github.tazihad.bengal-download-manager.svg
    install -Dm644 assets/logo.svg AppDir/usr/share/icons/hicolor/scalable/apps/bengal-download-manager.svg
fi
install -Dm644 flatpak/io.github.tazihad.bengal-download-manager.desktop AppDir/usr/share/applications/io.github.tazihad.bengal-download-manager.desktop
install -Dm644 flatpak/io.github.tazihad.bengal-download-manager.desktop AppDir/usr/share/applications/bengal-download-manager.desktop
if [ -f flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml ]; then
    install -Dm644 flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml AppDir/usr/share/metainfo/io.github.tazihad.bengal-download-manager.metainfo.xml
    install -Dm644 flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml AppDir/usr/share/appdata/io.github.tazihad.bengal-download-manager.appdata.xml
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

VERSION="${VERSION}" \
LINUXDEPLOY_OUTPUT_VERSION="${VERSION}" \
UPDATE_INFORMATION="${UPDATE_INFO}" \
LDAI_UPDATE_INFORMATION="${UPDATE_INFO}" \
OUTPUT="${OUTPUT_APPIMAGE}" \
LDAI_OUTPUT="${OUTPUT_APPIMAGE}" \
./linuxdeploy.AppImage \
    --appdir AppDir \
    --desktop-file flatpak/io.github.tazihad.bengal-download-manager.desktop \
    --icon-file assets/io.github.tazihad.bengal-download-manager.png \
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

if [ "$1" == "--run" ]; then
    echo "=== 5. Launching AppImage ==="
    "./${OUTPUT_APPIMAGE}" "${@:2}"
fi
