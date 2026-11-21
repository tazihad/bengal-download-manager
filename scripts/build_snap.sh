#!/usr/bin/env bash
# Bengal Download Manager - Snap Build Automation Script (PyInstaller onedir mode using uv plugin)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

TARGET_ARCH=""
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --target-arch=*)
            TARGET_ARCH="${arg#*=}"
            EXTRA_ARGS+=("$arg")
            ;;
        --destructive-mode)
            EXTRA_ARGS+=("--destructive-mode")
            ;;
        --use-lxd)
            EXTRA_ARGS+=("--use-lxd")
            ;;
        --help|-h)
            echo "Usage: $0 [--target-arch=amd64|arm64] [--destructive-mode] [--use-lxd]"
            exit 0
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

echo "========================================================"
echo " Building Bengal Download Manager Snap (core26, onedir via uv plugin)"
echo "========================================================"

if ! command -v snapcraft &>/dev/null; then
    echo "ERROR: snapcraft is not installed."
    echo "Install snapcraft via: sudo snap install snapcraft --classic"
    exit 1
fi

# Use uv if available
PY_BIN="python3"
if command -v uv >/dev/null 2>&1; then
    PY_BIN="uv run python"
elif [ -f ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PY_BIN="venv/bin/python"
fi

VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || cat VERSION 2>/dev/null || echo "0.3.23-alpha.1")
VERSION="${VERSION#v}"

echo "Target snap version: $VERSION"

# Backup original snapcraft.yaml
cp snap/snapcraft.yaml snap/snapcraft.yaml.backup

# Create onedir variant of snapcraft.yaml (based on main branch but with onedir build)
cat > snap/snapcraft.yaml << EOF
name: bengal-download-manager
base: core26
version: '$VERSION'
summary: High-speed multi-threaded download manager powered by Aria2
description: |
  Bengal Download Manager is a high-performance, open-source download accelerator
  featuring multi-threaded segment downloads, Aria2 engine acceleration, modern UI,
  browser extension integration, scheduled download queues, and media capture.

  Key Features:
  - Multi-threaded segment download acceleration
  - Aria2 engine integration with custom chunk splits
  - Browser extension capture for Chrome, Edge, and Firefox
  - Scheduled queues, proxy manager, and speed limiter
  - Media Downloader

grade: stable
confinement: strict
license: MIT
icon: assets/icons/512x512.png
website: https://github.com/tazihad/bengal-download-manager
source-code: https://github.com/tazihad/bengal-download-manager
issues: https://github.com/tazihad/bengal-download-manager/issues

platforms:
  amd64:
    build-on: [amd64]
    build-for: [amd64]
  arm64:
    build-on: [arm64]
    build-for: [arm64]

apps:
  bengal-download-manager:
    command: bin/bengal-wrapper
    common-id: bd.com.zihad.BengalDownloadManager
    desktop: usr/share/applications/bengal-download-manager.desktop
    autostart: bengal-download-manager.desktop
    extensions: [ gnome ]
    plugs:
      - desktop
      - desktop-legacy
      - wayland
      - x11
      - opengl
      - home
      - network
      - network-bind
      - removable-media
      - audio-playback
      - unity7
    environment:
      PATH: \$SNAP/bin:\$SNAP/usr/bin:\$PATH
      LD_LIBRARY_PATH: \$SNAP/usr/lib/\$TRIPLET:\$SNAP/usr/lib:\$SNAP/lib/\$TRIPLET:\$SNAP/lib:\$LD_LIBRARY_PATH

parts:
  desktop-deps:
    plugin: nil
    stage-packages:
      - aria2
      - ffmpeg
      - libgl1-mesa-dri
      - libgl1
      - libegl1
      - libxkbcommon0
      - libdbus-1-3
      - ca-certificates
      - xdg-utils
    stage:
      - -usr/lib/*/librsvg*
      - -usr/lib/*/gdk-pixbuf-2.0/*/loaders/libpixbufloader_svg.so
      - "*"

  bengal-download-manager:
    after:
      - desktop-deps
    plugin: uv
    source: .
    build-snaps:
      - astral-uv
    build-environment:
      - UV_PYTHON: python3
    stage-packages:
      - python3-venv
      - python3
    override-build: |
      craftctl default

      # 1. Install pyinstaller in uv environment
      uv pip install pyinstaller

      # 2. Build PyInstaller onedir bundle
      WORK_DIR=".pyinstaller-build"
      rm -rf "\$WORK_DIR" dist
      RUNTIME_ASSETS_DIR="\$CRAFT_PART_INSTALL/\$WORK_DIR/runtime_assets"
      bash "\$CRAFT_PROJECT_DIR/scripts/prepare_runtime_assets.sh" "\$RUNTIME_ASSETS_DIR" "\${CRAFT_ARCH_BUILD_FOR:-\$(uname -m)}"

      PYTHONPATH=src uv run pyinstaller \\
          --name "bengal-download-manager" \\
          --onedir \\
          --clean \\
          --paths "src" \\
          --collect-all core \\
          --collect-all ui \\
          --collect-all python_socks \\
          --add-data "\$RUNTIME_ASSETS_DIR:assets" \\
          --add-data "\$CRAFT_PROJECT_DIR/VERSION:." \\
          --distpath "dist" \\
          --workpath "\$WORK_DIR" \\
          --specpath "\$WORK_DIR" \\
          --noconfirm src/main.py

      # 2. Install onedir bundle to \$CRAFT_PART_INSTALL
      install -d "\$CRAFT_PART_INSTALL/usr/lib/bengal-download-manager"
      cp -a dist/bengal-download-manager/. "\$CRAFT_PART_INSTALL/usr/lib/bengal-download-manager/"
      chmod +x "\$CRAFT_PART_INSTALL/usr/lib/bengal-download-manager/bengal-download-manager"

      # 3. Install app sources (for version.py and any runtime Python modules)
      install -d "\$CRAFT_PART_INSTALL/share/bengal-download-manager"
      cp -r src "\$CRAFT_PART_INSTALL/share/bengal-download-manager/"

      # 4. Install runtime assets
      bash "\$CRAFT_PROJECT_DIR/scripts/prepare_runtime_assets.sh" "\$CRAFT_PART_INSTALL/share/bengal-download-manager/assets" "\${CRAFT_ARCH_BUILD_FOR:-\$(uname -m)}"

      # 5. Install desktop entry & AppStream metadata
      install -D -m 644 "\$CRAFT_PROJECT_DIR/snap/gui/bengal-download-manager.desktop" "\$CRAFT_PART_INSTALL/usr/share/applications/bengal-download-manager.desktop"
      install -D -m 644 "\$CRAFT_PROJECT_DIR/flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml" "\$CRAFT_PART_INSTALL/usr/share/metainfo/bd.com.zihad.BengalDownloadManager.metainfo.xml"

      # 6. Install hicolor icons
      for s in 16 32 64 128 256 512; do
        if [ -f "\$CRAFT_PROJECT_DIR/assets/icons/\${s}x\${s}.png" ]; then
          install -D -m 644 "\$CRAFT_PROJECT_DIR/assets/icons/\${s}x\${s}.png" "\$CRAFT_PART_INSTALL/usr/share/icons/hicolor/\${s}x\${s}/apps/bengal-download-manager.png"
          install -D -m 644 "\$CRAFT_PROJECT_DIR/assets/icons/\${s}x\${s}.png" "\$CRAFT_PART_INSTALL/usr/share/icons/hicolor/\${s}x\${s}/apps/bd.com.zihad.BengalDownloadManager.png"
        fi
      done
      if [ -f "\$CRAFT_PROJECT_DIR/assets/logo.svg" ]; then
        install -D -m 644 "\$CRAFT_PROJECT_DIR/assets/logo.svg" "\$CRAFT_PART_INSTALL/usr/share/icons/hicolor/scalable/apps/bengal-download-manager.svg"
        install -D -m 644 "\$CRAFT_PROJECT_DIR/assets/logo.svg" "\$CRAFT_PART_INSTALL/usr/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg"
      fi

      # 7. Install launcher wrapper (modified for onedir binary)
      if [ -f "\$CRAFT_PROJECT_DIR/snap/local/bengal-wrapper-ondir.sh" ]; then
        install -D -m 755 "\$CRAFT_PROJECT_DIR/snap/local/bengal-wrapper-ondir.sh" "\$CRAFT_PART_INSTALL/bin/bengal-wrapper"
      elif [ -f snap/local/bengal-wrapper-ondir.sh ]; then
        install -D -m 755 snap/local/bengal-wrapper-ondir.sh "\$CRAFT_PART_INSTALL/bin/bengal-wrapper"
      fi

      # 8. Install portal-aware xdg-open wrapper
      if [ -f "\$CRAFT_PROJECT_DIR/snap/local/xdg-open" ]; then
        install -D -m 755 "\$CRAFT_PROJECT_DIR/snap/local/xdg-open" "\$CRAFT_PART_INSTALL/bin/xdg-open"
      elif [ -f snap/local/xdg-open ]; then
        install -D -m 755 snap/local/xdg-open "\$CRAFT_PART_INSTALL/bin/xdg-open"
      fi
    stage:
      - -usr/lib/*/librsvg*
      - -usr/lib/*/gdk-pixbuf-2.0/*/loaders/libpixbufloader_svg.so
      - "*"
    prime:
      # Remove external symlinks created by uv plugin (point to build env Python)
      - -bin/python
      - -bin/python3
      - -bin/python3.*
      - "*"

EOF

# Create the onedir-specific wrapper script
cat > snap/local/bengal-wrapper-ondir.sh << 'WRAPPER_EOF'
#!/bin/bash
# Bengal Download Manager - Snap Execution Wrapper (PyInstaller onedir mode)

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)
        TRIPLET="x86_64-linux-gnu"
        ;;
    aarch64|arm64)
        TRIPLET="aarch64-linux-gnu"
        ;;
    *)
        TRIPLET="${ARCH}-linux-gnu"
        ;;
esac

# 1. Environment & Library paths
export SNAP_APP_ROOT="$SNAP/usr/lib/bengal-download-manager"
if [ -n "$SNAP_VERSION" ] && [ -z "$APP_VERSION" ]; then
    export APP_VERSION="$SNAP_VERSION"
fi

# Find Python site-packages from gnome extension / staged python
SITE_PACKAGES=""
QT_PLUGINS=""
QML_IMPORTS=""
for py_site in "$SNAP"/lib/python3.*/site-packages; do
    if [ -d "$py_site" ]; then
        SITE_PACKAGES="${SITE_PACKAGES:+${SITE_PACKAGES}:}$py_site"
        if [ -d "$py_site/PyQt6/Qt6/plugins" ]; then
            QT_PLUGINS="${QT_PLUGINS:+${QT_PLUGINS}:}$py_site/PyQt6/Qt6/plugins"
        fi
        if [ -d "$py_site/PyQt6/Qt6/qml" ]; then
            QML_IMPORTS="${QML_IMPORTS:+${QML_IMPORTS}:}$py_site/PyQt6/Qt6/qml"
        fi
    fi
done

export PATH="$SNAP/bin:$SNAP/usr/bin:$SNAP_APP_ROOT/assets/bin/linux/$ARCH:$SNAP_APP_ROOT/assets/bin/$ARCH:$SNAP_APP_ROOT/assets/bin:$PATH"
export LD_LIBRARY_PATH="$SNAP/usr/lib/$TRIPLET:$SNAP/usr/lib:$SNAP/lib/$TRIPLET:$SNAP/lib:$SNAP_APP_ROOT:$SNAP_APP_ROOT/_internal:$LD_LIBRARY_PATH"

# 2. Qt6 / Wayland / Rendering configuration
if [ "$QT_QPA_PLATFORM" = "wayland-egl" ] || [ -z "$QT_QPA_PLATFORM" ]; then
    export QT_QPA_PLATFORM="wayland;xcb"
fi
export QT_PLUGIN_PATH="$SNAP/usr/lib/$TRIPLET/qt6/plugins${QT_PLUGINS:+:${QT_PLUGINS}}${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
export QML2_IMPORT_PATH="$SNAP/usr/lib/$TRIPLET/qt6/qml${QML_IMPORTS:+:${QML_IMPORTS}}${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
export XDG_DATA_DIRS="$SNAP/usr/share:$SNAP_APP_ROOT/assets:$XDG_DATA_DIRS"

# 3. GDK Pixbuf — do NOT override GDK_PIXBUF_MODULE_FILE or GDK_PIXBUF_MODULEDIR.

# 4. Aria2 bundled fallback detection
if [ -f "$SNAP_APP_ROOT/assets/bin/linux/$ARCH/aria2c" ]; then
    chmod +x "$SNAP_APP_ROOT/assets/bin/linux/$ARCH/aria2c" 2>/dev/null || true
elif [ -f "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" ]; then
    chmod +x "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" 2>/dev/null || true
fi

# 5. Execute onedir binary with branded process identity
cd "$SNAP_APP_ROOT"
exec -a "bengal-download-manager" "$SNAP_APP_ROOT/bengal-download-manager" "$@"
WRAPPER_EOF
chmod +x snap/local/bengal-wrapper-ondir.sh

echo "=== 3. Executing Snapcraft Build (ondir) ==="

# Default to destructive-mode if no LXD/multipass and user didn't specify
USE_DESTRUCTIVE=0
if [[ ! " ${EXTRA_ARGS[@]} " =~ " --destructive-mode " ]] && [[ ! " ${EXTRA_ARGS[@]} " =~ " --use-lxd " ]]; then
    if ! command -v lxc &>/dev/null || ! lxc list &>/dev/null 2>&1; then
        echo "WARNING: LXD not available/configured. Using --destructive-mode (builds on host)."
        echo "         For isolated builds, run: sudo usermod -aG lxd \$USER && newgrp lxd && lxd init --auto"
        EXTRA_ARGS+=("--destructive-mode")
        USE_DESTRUCTIVE=1
    fi
fi

snapcraft pack "${EXTRA_ARGS[@]}"

# Restore original snapcraft.yaml
mv snap/snapcraft.yaml.backup snap/snapcraft.yaml

echo "=== 4. Verifying Generated Snap Artifact ==="
SNAP_FILE=$(find . -maxdepth 1 -name "bengal-download-manager_*.snap" -print -quit)
if [ -n "$SNAP_FILE" ] && [ -f "$SNAP_FILE" ]; then
    echo "SUCCESS: Snap package built successfully -> ${SNAP_FILE}"
    ls -lh "$SNAP_FILE"
    
    # Move to dist/
    mkdir -p dist
    DEST="dist/$(basename "$SNAP_FILE")"
    mv "$SNAP_FILE" "$DEST"
    echo "Moved to: $DEST"
    ls -lh "$DEST"
else
    echo "WARNING: Snap package build completed, check current directory for output .snap files."
fi