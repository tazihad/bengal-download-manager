#!/usr/bin/env bash
# Bengal Download Manager - Native DEB / RPM Build Script
#
# Builds the PyInstaller --onedir bundle and packages it as .deb and .rpm
# using nfpm. The bundle is installed under /usr/lib/bengal-download-manager
# and exposed through a small /usr/bin launcher.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

SKIP_BUILD=0
for arg in "$@"; do
    case "$arg" in
        --skip-build)
            SKIP_BUILD=1
            ;;
        --help|-h)
            echo "Usage: $0 [--skip-build]"
            echo ""
            echo "Options:"
            echo "  --skip-build  Reuse an existing onedir bundle in dist/"
            echo "  --help, -h    Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

PY_BIN="python3"
if command -v uv >/dev/null 2>&1; then
    PY_BIN="uv run python"
elif [ -f ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PY_BIN="venv/bin/python"
fi

VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || cat VERSION 2>/dev/null || echo "0.1.20")
VERSION="${VERSION#v}"
ARCH="$(uname -m)"

echo "========================================================"
echo " Building Native Packages: Bengal Download Manager"
echo " Version: $VERSION | Arch: $ARCH"
echo "========================================================"

if [ "$SKIP_BUILD" -eq 0 ]; then
    bash "$SCRIPT_DIR/build_binary.sh" --onedir
fi

ONEDIR_DIR="dist/bengal-download-manager"
if [ ! -x "$ONEDIR_DIR/bengal-download-manager" ]; then
    echo "Error: onedir bundle not found at $ONEDIR_DIR" >&2
    echo "Run without --skip-build or build it first with scripts/build_binary.sh" >&2
    exit 1
fi

# Map host architecture to package architecture names
case "$ARCH" in
    x86_64|amd64)
        NFPM_ARCH="amd64"
        RPM_ARCH="x86_64"
        ;;
    aarch64|arm64)
        NFPM_ARCH="arm64"
        RPM_ARCH="aarch64"
        ;;
    *)
        NFPM_ARCH="$ARCH"
        RPM_ARCH="$ARCH"
        ;;
esac

WORK_DIR=".pyinstaller-build"
PKG_DIR="$WORK_DIR/package_${ARCH}"
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/usr/bin" "$PKG_DIR/usr/lib/bengal-download-manager"

echo "=== 1. Staging onedir bundle under /usr/lib ==="
cp -a "$ONEDIR_DIR/." "$PKG_DIR/usr/lib/bengal-download-manager/"
printf '#!/bin/sh\nexec /usr/lib/bengal-download-manager/bengal-download-manager "$@"\n' \
    > "$PKG_DIR/usr/bin/bengal-download-manager"
chmod 755 "$PKG_DIR/usr/bin/bengal-download-manager"

echo "=== 2. Staging runtime assets and desktop metadata ==="
mkdir -p "$PKG_DIR/usr/share/bengal-download-manager/assets"
bash "$SCRIPT_DIR/prepare_runtime_assets.sh" "$PKG_DIR/usr/share/bengal-download-manager/assets" "$ARCH"

mkdir -p "$PKG_DIR/usr/share/applications" "$PKG_DIR/usr/share/metainfo"
install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.desktop \
    "$PKG_DIR/usr/share/applications/bd.com.zihad.BengalDownloadManager.desktop"
install -Dm644 flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml \
    "$PKG_DIR/usr/share/metainfo/bd.com.zihad.BengalDownloadManager.metainfo.xml"

for s in 16 32 64 128 256 512; do
    if [ -f "assets/icons/${s}x${s}.png" ]; then
        install -Dm644 "assets/icons/${s}x${s}.png" \
            "$PKG_DIR/usr/share/icons/hicolor/${s}x${s}/apps/bd.com.zihad.BengalDownloadManager.png"
        install -Dm644 "assets/icons/${s}x${s}.png" \
            "$PKG_DIR/usr/share/icons/hicolor/${s}x${s}/apps/bengal-download-manager.png"
    fi
done
if [ -f assets/logo.svg ]; then
    install -Dm644 assets/logo.svg \
        "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg"
    install -Dm644 assets/logo.svg \
        "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/bengal-download-manager.svg"
fi

echo "=== 3. Locating nfpm ==="
NFPM_BIN="$(command -v nfpm || true)"
if [ -z "$NFPM_BIN" ]; then
    case "$ARCH" in
        aarch64|arm64) NFPM_HOST_ARCH="arm64" ;;
        *) NFPM_HOST_ARCH="x86_64" ;;
    esac
    NFPM_VER="2.48.0"
    NFPM_DIR="$WORK_DIR/nfpm"
    NFPM_BIN="$NFPM_DIR/nfpm"
    if [ ! -x "$NFPM_BIN" ]; then
        mkdir -p "$NFPM_DIR"
        echo "Downloading nfpm v${NFPM_VER} for host ${NFPM_HOST_ARCH}..."
        curl -sSL "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VER}/nfpm_${NFPM_VER}_Linux_${NFPM_HOST_ARCH}.tar.gz" \
            | tar -xz -C "$NFPM_DIR"
    fi
fi
"$NFPM_BIN" -v >/dev/null

echo "=== 4. Generating nfpm configuration ==="
{
    echo "name: \"bengal-download-manager\""
    echo "arch: \"${NFPM_ARCH}\""
    echo "platform: \"linux\""
    echo "version: \"${VERSION}\""
    echo "section: \"net\""
    echo "priority: \"optional\""
    echo "maintainer: \"Zihad <tazihad@gmail.com>\""
    echo "description: |"
    echo "  Bengal Download Manager is a high-performance, multi-threaded open-source download manager powered by Aria2 and PyQt6."
    echo "homepage: \"https://github.com/tazihad/bengal-download-manager\""
    echo "license: \"MIT\""
    echo ""
    echo "contents:"
    echo "  - src: \"${PKG_DIR}/usr/bin/bengal-download-manager\""
    echo "    dst: \"/usr/bin/bengal-download-manager\""
    echo "    file_info:"
    echo "      mode: 0755"
    echo "  - src: \"${PKG_DIR}/usr/lib/bengal-download-manager/\""
    echo "    dst: \"/usr/lib/bengal-download-manager\""
    echo "    type: tree"
    find "$PKG_DIR/usr/share" -type f | sort | while IFS= read -r f; do
        rel="${f#"$PKG_DIR"/}"
        echo "  - src: \"${PKG_DIR}/${rel}\""
        echo "    dst: \"/${rel}\""
        echo "    file_info:"
        echo "      mode: 0644"
    done
} > "$PKG_DIR/nfpm.yaml"

echo "=== 5. Building DEB and RPM packages ==="
mkdir -p dist
"$NFPM_BIN" package --config "$PKG_DIR/nfpm.yaml" --packager deb \
    --target "dist/bengal-download-manager-${VERSION}-${ARCH}.deb"
"$NFPM_BIN" package --config "$PKG_DIR/nfpm.yaml" --packager rpm \
    --target "dist/bengal-download-manager-${VERSION}-${RPM_ARCH}.rpm"

echo ""
echo "========================================================"
echo "✓ Native packages built successfully!"
ls -lh "dist/bengal-download-manager-${VERSION}-${ARCH}.deb" \
       "dist/bengal-download-manager-${VERSION}-${RPM_ARCH}.rpm"
echo "========================================================"
