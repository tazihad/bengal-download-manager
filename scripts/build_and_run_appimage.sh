#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

ARCH="$(uname -m)"
REPO_OWNER="tazihad"
REPO_NAME="bengal-download-manager"

echo "=== 1. Checking / Building PyInstaller Executable ==="
if [ ! -f "dist/bengal-download-manager" ]; then
    PYTHONPATH=src venv/bin/pyinstaller --noconfirm bengal-download-manager.spec
fi

echo "=== 2. Preparing Desktop Icon ==="
venv/bin/python -c "from PyQt6.QtGui import QImage; from PyQt6.QtCore import Qt; img = QImage('assets/logo.png'); img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save('assets/bengal-download-manager.png')"

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
# AppImageUpdate zsync information format for GitHub releases
ZSYNC_INFO="zsync|gh-releases-direct|${REPO_OWNER}|${REPO_NAME}|latest|bengal-download-manager-*-${ARCH}.AppImage.zsync"
export UPDATE_INFORMATION="${ZSYNC_INFO}"
export LDAI_UPDATE_INFORMATION="${ZSYNC_INFO}"

rm -rf AppDir
./linuxdeploy.AppImage \
    --appdir AppDir \
    --executable dist/bengal-download-manager \
    --desktop-file assets/bengal-download-manager.desktop \
    --icon-file assets/bengal-download-manager.png \
    --output appimage

# Move generated AppImage and .zsync files to dist/
APPIMAGE_FILE=$(ls Bengal_Download_Manager-*.AppImage 2>/dev/null | head -n 1)
ZSYNC_FILE=$(ls Bengal_Download_Manager-*.AppImage.zsync 2>/dev/null | head -n 1)

if [ -n "$APPIMAGE_FILE" ]; then
    FINAL_APPIMAGE="dist/bengal-download-manager-${ARCH}.AppImage"
    FINAL_ZSYNC="dist/bengal-download-manager-${ARCH}.AppImage.zsync"
    mv "$APPIMAGE_FILE" "$FINAL_APPIMAGE"
    if [ -n "$ZSYNC_FILE" ]; then
        mv "$ZSYNC_FILE" "$FINAL_ZSYNC"
    fi
    echo "AppImage successfully created: $FINAL_APPIMAGE"
    echo "Zsync file successfully created: $FINAL_ZSYNC"
fi

if [ "$1" == "--run" ]; then
    echo "=== 5. Launching AppImage ==="
    ./dist/bengal-download-manager-${ARCH}.AppImage "${@:2}"
fi
