#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

APP_ID="io.github.tazihad.bengal-download-manager"
BUILD_DIR="flatpak_app_dir"

DO_RUN=0
DO_BUNDLE=1
EXTRA_APP_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --run)
            DO_RUN=1
            ;;
        --no-bundle)
            DO_BUNDLE=0
            ;;
        --bundle)
            DO_BUNDLE=1
            ;;
        --help|-h)
            echo "Usage: $0 [--run] [--no-bundle] [--bundle] [app_arguments...]"
            echo ""
            echo "Options:"
            echo "  --run        Launch the built application after assembly"
            echo "  --no-bundle  Skip creating the .flatpak single-file bundle"
            echo "  --bundle     Create .flatpak single-file bundle in dist/ (default)"
            echo "  --help, -h   Show this help message"
            exit 0
            ;;
        *)
            EXTRA_APP_ARGS+=("$arg")
            ;;
    esac
done

ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    ARCH_NAME="x86_64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    ARCH_NAME="aarch64"
else
    ARCH_NAME="x86_64"
fi

PY_BIN="python3"
PYINSTALLER_BIN="pyinstaller"
if command -v uv >/dev/null 2>&1; then
    PY_BIN="uv run python"
    PYINSTALLER_BIN="uv run pyinstaller"
elif [ -f ".venv/bin/pyinstaller" ]; then
    PY_BIN=".venv/bin/python"
    PYINSTALLER_BIN=".venv/bin/pyinstaller"
elif [ -f "venv/bin/pyinstaller" ]; then
    PY_BIN="venv/bin/python"
    PYINSTALLER_BIN="venv/bin/pyinstaller"
fi

VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || cat VERSION 2>/dev/null || echo "0.1.20")
VERSION="${VERSION#v}"

echo "========================================================"
echo " Building Bengal Download Manager Flatpak (v$VERSION - $ARCH_NAME)"
echo "========================================================"

echo "=== 1. Building PyInstaller Standalone Application ==="
WORK_DIR=".pyinstaller-build"
rm -rf "$WORK_DIR" dist
RUNTIME_ASSETS_DIR="$WORK_DIR/runtime_assets"
bash "$SCRIPT_DIR/prepare_runtime_assets.sh" "$RUNTIME_ASSETS_DIR" "$ARCH_NAME"

PYTHONPATH=src $PYINSTALLER_BIN \
    --name "bengal-download-manager" \
    --onedir \
    --clean \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --collect-all python_socks \
    --add-data "$RUNTIME_ASSETS_DIR:assets" \
    --distpath "dist" \
    --workpath "$WORK_DIR" \
    --noconfirm src/main.py

echo "=== 2. Assembling Flatpak Package Structure ($BUILD_DIR) ==="
rm -rf "$BUILD_DIR" repo
mkdir -p "$BUILD_DIR/files/bin" \
        "$BUILD_DIR/files/lib/bengal-download-manager" \
        "$BUILD_DIR/files/share/applications" \
        "$BUILD_DIR/files/share/icons/hicolor/256x256/apps" \
        "$BUILD_DIR/files/share/metainfo" \
        "$BUILD_DIR/files/share/appdata" \
        "$BUILD_DIR/files/share/app-info/xmls" \
        "$BUILD_DIR/files/share/app-info/icons/flatpak"

cp -a dist/bengal-download-manager/. "$BUILD_DIR/files/lib/bengal-download-manager/"
chmod +x "$BUILD_DIR/files/lib/bengal-download-manager/bengal-download-manager"
ln -sf /app/lib/bengal-download-manager/bengal-download-manager "$BUILD_DIR/files/bin/bengal-download-manager"

if [ -f "assets/bin/linux/$ARCH_NAME/aria2c" ]; then
    cp "assets/bin/linux/$ARCH_NAME/aria2c" "$BUILD_DIR/files/bin/aria2c"
    chmod +x "$BUILD_DIR/files/bin/aria2c"
elif [ -f "assets/bin/$ARCH_NAME/aria2c" ]; then
    cp "assets/bin/$ARCH_NAME/aria2c" "$BUILD_DIR/files/bin/aria2c"
    chmod +x "$BUILD_DIR/files/bin/aria2c"
fi

for s in 16 32 64 128 256 512; do
    mkdir -p "$BUILD_DIR/files/share/icons/hicolor/${s}x${s}/apps"
    cp "assets/icons/${s}x${s}.png" "$BUILD_DIR/files/share/icons/hicolor/${s}x${s}/apps/$APP_ID.png" 2>/dev/null || true
done
mkdir -p "$BUILD_DIR/files/share/icons/hicolor/scalable/apps"
cp assets/logo.svg "$BUILD_DIR/files/share/icons/hicolor/scalable/apps/$APP_ID.svg" 2>/dev/null || true
cp flatpak/$APP_ID.desktop "$BUILD_DIR/files/share/applications/$APP_ID.desktop"
cp flatpak/$APP_ID.metainfo.xml "$BUILD_DIR/files/share/metainfo/$APP_ID.metainfo.xml"

# Dynamically inject the exact version into AppStream metainfo XML
TODAY=$(date +'%Y-%m-%d')
$PY_BIN -c '
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

# Compose AppStream catalog metadata if appstreamcli is present
if command -v appstreamcli >/dev/null 2>&1; then
    appstreamcli compose \
      --origin="$APP_ID" \
      --prefix=/ \
      --result-root="$BUILD_DIR/files" \
      --data-dir="$BUILD_DIR/files/share/app-info/xmls" \
      --icons-dir="$BUILD_DIR/files/share/app-info/icons/flatpak" \
      "$BUILD_DIR/files" 2>/dev/null || true
fi

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
org.freedesktop.FileManager1=talk
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

if [ "$DO_BUNDLE" -eq 1 ]; then
    if command -v flatpak >/dev/null 2>&1; then
        echo "=== 3. Exporting Flatpak Repository & Bundle ==="
        mkdir -p dist
        flatpak build-finish "$BUILD_DIR" --command=bengal-download-manager
        flatpak build-export --update-appstream repo "$BUILD_DIR"
        flatpak build-update-repo --generate-static-deltas repo
        flatpak build-bundle repo "dist/bengal-download-manager.flatpak" "$APP_ID"
        cp "dist/bengal-download-manager.flatpak" "dist/bengal-download-manager-${VERSION}-${ARCH_NAME}.flatpak" 2>/dev/null || true
        echo "✓ Bundle created: dist/bengal-download-manager.flatpak"
    else
        echo "WARNING: 'flatpak' binary not installed. Flatpak app directory prepared in '$BUILD_DIR', but bundle export skipped."
    fi
fi

if [ "$DO_RUN" -eq 1 ]; then
    echo "=== 4. Launching Application from Flatpak App Structure ==="
    "$BUILD_DIR/files/lib/bengal-download-manager/bengal-download-manager" "${EXTRA_APP_ARGS[@]}"
fi

