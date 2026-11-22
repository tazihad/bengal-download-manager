#!/usr/bin/env bash
# Bengal Download Manager - Portable Tarball Build Script
#
# Builds the PyInstaller --onedir bundle and packages it as a portable
# .tar.xz archive with a top-level launcher script.
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
DIR_NAME="bengal-download-manager-${VERSION}-${ARCH}"

echo "========================================================"
echo " Building Portable Tarball: Bengal Download Manager"
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

STAGE_DIR="$ROOT_DIR/.pyinstaller-build/tarball/${DIR_NAME}"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/lib"

echo "=== 1. Staging onedir bundle ==="
cp -a "$ONEDIR_DIR" "$STAGE_DIR/lib/bengal-download-manager"
printf '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/lib/bengal-download-manager/bengal-download-manager" "$@"\n' \
    > "$STAGE_DIR/bengal-download-manager"
chmod 755 "$STAGE_DIR/bengal-download-manager"

for doc in README.md LICENSE; do
    if [ -f "$doc" ]; then
        cp "$doc" "$STAGE_DIR/"
    fi
done

echo "=== 2. Creating archive ==="
mkdir -p dist
tar -cJf "dist/${DIR_NAME}.tar.xz" -C "$(dirname "$STAGE_DIR")" "$DIR_NAME"

echo ""
echo "========================================================"
echo "✓ Portable tarball built successfully!"
ls -lh "dist/${DIR_NAME}.tar.xz"
echo "========================================================"
