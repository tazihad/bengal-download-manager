#!/bin/bash
# Bengal Download Manager — Snapcraft build script
# Extracted from snap/snapcraft.yml override-build for readability and independent testing.

set -eu
craftctl default

# Version and grade come from the VERSION file
VERSION="$(tr -d '[:space:]' < "$CRAFT_PROJECT_DIR/VERSION")"
craftctl set version="$VERSION"
case "$VERSION" in
  *alpha*|*beta*|*rc*|*dev*) craftctl set grade=devel ;;
  *)                         craftctl set grade=stable ;;
esac

ARCH="${CRAFT_ARCH_BUILD_FOR:-$(uname -m)}"
APP=bengal-download-manager
APP_ID=bd.com.zihad.BengalDownloadManager

# 1. Install pyinstaller in uv environment
uv pip install pyinstaller

# 2. Prepare runtime assets once (aria2 binary lives here; ffmpeg/ffprobe downloaded at runtime)
WORK_DIR=".pyinstaller-build"
RUNTIME_ASSETS_DIR="$CRAFT_PART_BUILD/runtime_assets"
rm -rf "$WORK_DIR" dist "$RUNTIME_ASSETS_DIR"
bash "$CRAFT_PROJECT_DIR/scripts/prepare_runtime_assets.sh" "$RUNTIME_ASSETS_DIR" "$ARCH"

# 3. Build PyInstaller onedir bundle
PYTHONPATH=src uv run pyinstaller \
    --name "$APP" \
    --onedir \
    --clean \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --collect-all python_socks \
    --add-data "$RUNTIME_ASSETS_DIR:assets" \
    --add-data "$CRAFT_PROJECT_DIR/VERSION:." \
    --distpath "dist" \
    --workpath "$WORK_DIR" \
    --specpath "$WORK_DIR" \
    --noconfirm src/main.py

# 4. Install onedir bundle
install -d "$CRAFT_PART_INSTALL/usr/lib/$APP"
cp -a "dist/$APP/." "$CRAFT_PART_INSTALL/usr/lib/$APP/"
chmod +x "$CRAFT_PART_INSTALL/usr/lib/$APP/$APP"

# Drop uv venv — PyInstaller already bundles PyQt6 and all dependencies
# into the onedir bundle. Removing it avoids shipping Qt (and everything
# else) a second time in the snap.
rm -rf "$CRAFT_PART_INSTALL/bin" "$CRAFT_PART_INSTALL/lib" "$CRAFT_PART_INSTALL/lib64" "$CRAFT_PART_INSTALL/include" "$CRAFT_PART_INSTALL/pyvenv.cfg"

# 5. Install app sources (only version.py needed for build-marker in build_info.py)
install -d "$CRAFT_PART_INSTALL/share/$APP/src/core"
cp src/core/version.py "$CRAFT_PART_INSTALL/share/$APP/src/core/version.py"

# 7. Install desktop entry & AppStream metadata
install -D -m 644 "$CRAFT_PROJECT_DIR/snap/gui/$APP.desktop" \
  "$CRAFT_PART_INSTALL/usr/share/applications/$APP.desktop"
install -D -m 644 "$CRAFT_PROJECT_DIR/flatpak/$APP_ID.metainfo.xml" \
  "$CRAFT_PART_INSTALL/usr/share/metainfo/$APP_ID.metainfo.xml"

# 8. Install hicolor icons under both names
for s in 16 32 64 128 256 512; do
  src="$CRAFT_PROJECT_DIR/assets/icons/${s}x${s}.png"
  [ -f "$src" ] || continue
  for name in "$APP" "$APP_ID"; do
    install -D -m 644 "$src" \
      "$CRAFT_PART_INSTALL/usr/share/icons/hicolor/${s}x${s}/apps/$name.png"
  done
done
if [ -f "$CRAFT_PROJECT_DIR/assets/logo.svg" ]; then
  for name in "$APP" "$APP_ID"; do
    install -D -m 644 "$CRAFT_PROJECT_DIR/assets/logo.svg" \
      "$CRAFT_PART_INSTALL/usr/share/icons/hicolor/scalable/apps/$name.svg"
  done
fi

# 9. Install launcher wrapper and portal-aware xdg-open wrapper
install -D -m 755 "$CRAFT_PROJECT_DIR/snap/local/bengal-wrapper.sh" "$CRAFT_PART_INSTALL/bin/bengal-wrapper"
install -D -m 755 "$CRAFT_PROJECT_DIR/snap/local/xdg-open" "$CRAFT_PART_INSTALL/bin/xdg-open"
