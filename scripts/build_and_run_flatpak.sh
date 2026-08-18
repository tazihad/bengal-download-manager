#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

APP_ID="io.github.tazihad.bengal-download-manager"
BUILD_DIR="flatpak_app_dir"

echo "=== 1. Building PyInstaller Application ==="
rm -rf build dist
PYTHONPATH=src venv/bin/pyinstaller \
    --name "bengal-download-manager" \
    --onedir \
    --clean \
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
mkdir -p "$BUILD_DIR/files/lib/bengal-download-manager"
mkdir -p "$BUILD_DIR/files/share/applications"
mkdir -p "$BUILD_DIR/files/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/files/share/metainfo"

cp -a dist/bengal-download-manager/. "$BUILD_DIR/files/lib/bengal-download-manager/"
chmod +x "$BUILD_DIR/files/lib/bengal-download-manager/bengal-download-manager"
ln -sf /app/lib/bengal-download-manager/bengal-download-manager "$BUILD_DIR/files/bin/bengal-download-manager"

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
mkdir -p "$BUILD_DIR/files/share/app-info/xmls"
mkdir -p "$BUILD_DIR/files/share/app-info/icons/flatpak"

VERSION=$(python3 -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || echo "0.1.20")
VERSION="${VERSION#v}"

for s in 16 32 64 128 256 512; do
    mkdir -p "$BUILD_DIR/files/share/icons/hicolor/${s}x${s}/apps"
    cp "assets/icons/${s}x${s}.png" "$BUILD_DIR/files/share/icons/hicolor/${s}x${s}/apps/$APP_ID.png" 2>/dev/null || true
done
mkdir -p "$BUILD_DIR/files/share/icons/hicolor/scalable/apps"
cp assets/logo.svg "$BUILD_DIR/files/share/icons/hicolor/scalable/apps/$APP_ID.svg" 2>/dev/null || true
cp flatpak/io.github.tazihad.bengal-download-manager.desktop "$BUILD_DIR/files/share/applications/$APP_ID.desktop"
cp flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml"

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

# Compose AppStream catalog metadata if tools available
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
