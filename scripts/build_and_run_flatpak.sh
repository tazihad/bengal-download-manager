#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

APP_ID="io.github.tazihad.bengal-download-manager"
BUILD_DIR="flatpak_app_dir"

echo "=== 1. Building Standalone PyInstaller Executable ==="
PYTHONPATH=src venv/bin/pyinstaller \
    --name "bengal-download-manager" \
    --onefile \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --add-data "assets:assets" \
    --distpath "dist" \
    --workpath "build" \
    --noconfirm src/main.py

echo "=== 2. Creating Flatpak App Structure ($BUILD_DIR) ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/files/bin"
mkdir -p "$BUILD_DIR/files/share/applications"
mkdir -p "$BUILD_DIR/files/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/files/share/metainfo"

cp dist/bengal-download-manager "$BUILD_DIR/files/bin/bengal-download-manager"
chmod +x "$BUILD_DIR/files/bin/bengal-download-manager"

ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    ARCH_NAME="x86_64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    ARCH_NAME="aarch64"
else
    ARCH_NAME="x86_64"
fi

if [ -f "assets/bin/$ARCH_NAME/aria2c" ]; then
    cp "assets/bin/$ARCH_NAME/aria2c" "$BUILD_DIR/files/bin/aria2c"
    chmod +x "$BUILD_DIR/files/bin/aria2c"
fi

mkdir -p "$BUILD_DIR/files/share/appdata"
mkdir -p "$BUILD_DIR/files/share/appstream"

cp assets/io.github.tazihad.bengal-download-manager.png "$BUILD_DIR/files/share/icons/hicolor/256x256/apps/$APP_ID.png" 2>/dev/null || cp assets/logo.png "$BUILD_DIR/files/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp flatpak/io.github.tazihad.bengal-download-manager.desktop "$BUILD_DIR/files/share/applications/$APP_ID.desktop"
cp flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml"
cp flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml "$BUILD_DIR/files/share/appdata/$APP_ID.appdata.xml"

# Compose AppStream catalog metadata if tools available
appstreamcli compose --origin=flatpak --prefix=/ "$BUILD_DIR/files" 2>/dev/null || appstream-util compose --origin=flatpak "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml" "$BUILD_DIR/files/share/appstream" 2>/dev/null || true

cat << EOF > "$BUILD_DIR/metadata"
[Application]
name=$APP_ID
runtime=org.kde.Platform/x86_64/6.11
sdk=org.kde.Sdk/x86_64/6.11
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

echo "=== 3. Flatpak Package Build Successfully Prepared in '$BUILD_DIR' ==="
echo "=== 4. Launching Flatpak Build Application ==="
"$BUILD_DIR/files/bin/bengal-download-manager"
