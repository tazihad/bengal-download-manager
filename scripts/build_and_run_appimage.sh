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
venv/bin/python -c "from PyQt6.QtGui import QImage; from PyQt6.QtCore import Qt; img = QImage('assets/logo.png'); img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save('assets/bengal-download-manager.png')"

rm -rf AppDir

install -Dm755 dist/bengal-download-manager AppDir/usr/bin/bengal-download-manager
install -Dm644 assets/bengal-download-manager.png AppDir/usr/share/icons/hicolor/256x256/apps/bengal-download-manager.png
install -Dm644 assets/bengal-download-manager.desktop AppDir/usr/share/applications/bengal-download-manager.desktop
if [ -f flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml ]; then
    install -Dm644 flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml AppDir/usr/share/metainfo/io.github.tazihad.bengal-download-manager.metainfo.xml
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
    --desktop-file assets/bengal-download-manager.desktop \
    --icon-file assets/bengal-download-manager.png \
    --output appimage

# If appimagetool output files into current directory, move to dist/
GENERATED_APPIMAGE=$(ls Bengal_Download_Manager-*.AppImage 2>/dev/null | head -n 1)
GENERATED_ZSYNC=$(ls Bengal_Download_Manager-*.AppImage.zsync 2>/dev/null | head -n 1)

if [ -n "$GENERATED_APPIMAGE" ]; then
    mv "$GENERATED_APPIMAGE" "$OUTPUT_APPIMAGE"
fi
if [ -n "$GENERATED_ZSYNC" ]; then
    mv "$GENERATED_ZSYNC" "${OUTPUT_APPIMAGE}.zsync"
fi

echo "AppImage created: ${OUTPUT_APPIMAGE}"
echo "Zsync file created: ${OUTPUT_APPIMAGE}.zsync"

if [ "$1" == "--run" ]; then
    echo "=== 5. Launching AppImage ==="
    "./${OUTPUT_APPIMAGE}" "${@:2}"
fi
