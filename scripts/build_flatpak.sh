#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

APP_ID="io.github.tazihad.bengal-download-manager"
BUILD_DIR="flatpak_app_dir"

ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    ARCH_NAME="x86_64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    ARCH_NAME="aarch64"
else
    ARCH_NAME="x86_64"
fi

VERSION=$(python3 -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || echo "0.1.20")

echo "=== 1. Building PyInstaller Standalone Executable ==="
rm -rf build dist
PYTHONPATH=src venv/bin/pyinstaller \
    --name "bengal-download-manager" \
    --onefile \
    --clean \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --add-data "assets:assets" \
    --distpath "dist" \
    --workpath "build" \
    --noconfirm src/main.py

echo "=== 2. Assembling Flatpak Package Structure ($BUILD_DIR) ==="
rm -rf "$BUILD_DIR" repo
mkdir -p "$BUILD_DIR/files/bin" \
        "$BUILD_DIR/files/share/applications" \
        "$BUILD_DIR/files/share/icons/hicolor/256x256/apps" \
        "$BUILD_DIR/files/share/metainfo" \
        "$BUILD_DIR/files/share/appdata" \
        "$BUILD_DIR/files/share/app-info/xmls" \
        "$BUILD_DIR/files/share/app-info/icons/flatpak"

cp dist/bengal-download-manager "$BUILD_DIR/files/bin/bengal-download-manager"
chmod +x "$BUILD_DIR/files/bin/bengal-download-manager"

if [ -f "assets/bin/$ARCH_NAME/aria2c" ]; then
    cp "assets/bin/$ARCH_NAME/aria2c" "$BUILD_DIR/files/bin/aria2c"
    chmod +x "$BUILD_DIR/files/bin/aria2c"
fi

cp assets/io.github.tazihad.bengal-download-manager.png "$BUILD_DIR/files/share/icons/hicolor/256x256/apps/$APP_ID.png" 2>/dev/null || cp assets/logo.png "$BUILD_DIR/files/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp flatpak/$APP_ID.desktop "$BUILD_DIR/files/share/applications/$APP_ID.desktop"
cp flatpak/$APP_ID.metainfo.xml "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml"

# Dynamically inject the exact version into AppStream metainfo XML
TODAY=$(date +'%Y-%m-%d')
python3 -c '
import sys, re
ver = sys.argv[1]
today = sys.argv[2]
path = sys.argv[3]
with open(path, "r") as f:
    content = f.read()
new_release = f"<releases>\n    <release version=\"{ver}\" date=\"{today}\"/>\n  </releases>"
content = re.sub(r"<releases>.*?</releases>", new_release, content, flags=re.DOTALL)
with open(path, "w") as f:
    f.write(content)
' "$VERSION" "$TODAY" "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml"

cp "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml" "$BUILD_DIR/files/share/appdata/$APP_ID.appdata.xml"

# Compose AppStream catalog metadata
appstreamcli compose \
  --origin="$APP_ID" \
  --prefix=/ \
  --result-root="$BUILD_DIR/files" \
  --data-dir="$BUILD_DIR/files/share/app-info/xmls" \
  --icons-dir="$BUILD_DIR/files/share/app-info/icons/flatpak" \
  "$BUILD_DIR/files" 2>/dev/null || true

cat << EOF > "$BUILD_DIR/metadata"
[Application]
name=$APP_ID
runtime=org.kde.Platform/${ARCH_NAME}/6.11
sdk=org.kde.Sdk/${ARCH_NAME}/6.11
command=bengal-download-manager

[Context]
shared=network;ipc;
sockets=x11;fallback-x11;wayland;pulseaudio;
filesystems=host;xdg-download;xdg-config/kdeglobals:ro;xdg-config/gtk-3.0:ro;xdg-config/gtk-4.0:ro;xdg-data/icons:ro;~/.icons:ro;~/.local/share/icons:ro;
devices=dri;

[Session Bus Policy]
org.freedesktop.portal.Desktop=talk
org.freedesktop.portal.Settings=talk
org.freedesktop.Notifications=talk
org.kde.StatusNotifierWatcher=talk
org.freedesktop.StatusNotifierWatcher=talk
org.kde.StatusNotifierItem.*=own
org.freedesktop.StatusNotifierItem.*=own

[Environment]
QT_QPA_PLATFORMTHEME=xdgdesktopportal
EOF

echo "=== 3. Exporting Flatpak Repository & Bundle ==="
mkdir -p dist
flatpak build-finish "$BUILD_DIR" --command=bengal-download-manager
flatpak build-export --update-appstream repo "$BUILD_DIR"
flatpak build-update-repo --generate-static-deltas repo
flatpak build-bundle repo "dist/bengal-download-manager.flatpak" "$APP_ID"
cp "dist/bengal-download-manager.flatpak" "dist/bengal-download-manager-${VERSION}-${ARCH_NAME}.flatpak" 2>/dev/null || true
echo "✓ Bundle created: dist/bengal-download-manager.flatpak"
