#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

VERSION="1.0.0"
ARCH="$(uname -m)"

echo "=== 1. Setting up AppDir Structure ==="
rm -rf AppDir
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

cp dist/bengal-download-manager AppDir/usr/bin/bengal-download-manager
chmod +x AppDir/usr/bin/bengal-download-manager
cp assets/bengal-download-manager.desktop AppDir/
echo "X-AppImage-Version=${VERSION}" >> AppDir/bengal-download-manager.desktop
cp assets/logo.png AppDir/bengal-download-manager.png
cp assets/logo.png AppDir/usr/share/icons/hicolor/256x256/apps/bengal-download-manager.png

cat > AppDir/AppRun <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/bin/bengal-download-manager" "\$@"
EOF
chmod +x AppDir/AppRun

echo "=== 2. Building AppImage ==="
if [ ! -f appimagetool.AppImage ]; then
    wget -q "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage" -O appimagetool.AppImage || \
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-${ARCH}.AppImage" -O appimagetool.AppImage
    chmod +x appimagetool.AppImage
fi

ARCH=${ARCH} ./appimagetool.AppImage --appimage-extract-and-run AppDir "dist/bengal-download-manager-${VERSION}-${ARCH}.AppImage"
chmod +x "dist/bengal-download-manager-${VERSION}-${ARCH}.AppImage"

echo "=== 3. Launching AppImage ==="
./dist/bengal-download-manager-${VERSION}-${ARCH}.AppImage "$@"
