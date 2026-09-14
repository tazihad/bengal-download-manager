#!/usr/bin/env bash
# Bengal Download Manager - Standalone Executable Build Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

MODE="--onefile"
DO_CLEAN=1
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --onefile)
            MODE="--onefile"
            ;;
        --onedir)
            MODE="--onedir"
            ;;
        --no-clean)
            DO_CLEAN=0
            ;;
        --help|-h)
            echo "Usage: $0 [--onefile|--onedir] [--no-clean]"
            echo ""
            echo "Options:"
            echo "  --onefile   Build single self-contained executable binary (default)"
            echo "  --onedir    Build directory containing executable and shared libraries"
            echo "  --no-clean  Do not delete existing build/ and dist/ folders before building"
            echo "  --help, -h  Show this help message"
            exit 0
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

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
ARCH="$(uname -m)"

echo "========================================================"
echo " Building Standalone Binary: Bengal Download Manager"
echo " Version: $VERSION | Arch: $ARCH | Mode: $MODE"
echo "========================================================"

PYINSTALLER_WORKPATH=".pyinstaller-build"

if [ "$DO_CLEAN" -eq 1 ]; then
    echo "Cleaning previous build and dist directories..."
    rm -rf "$PYINSTALLER_WORKPATH" dist
fi

mkdir -p dist "$PYINSTALLER_WORKPATH"

PYTHONPATH=src $PYINSTALLER_BIN \
    --name "bengal-download-manager" \
    "$MODE" \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --add-data "assets:assets" \
    --distpath "dist" \
    --workpath "$PYINSTALLER_WORKPATH" \
    --noconfirm \
    "${EXTRA_ARGS[@]}" \
    src/main.py

echo ""
echo "========================================================"
echo "✓ Standalone binary build completed successfully!"
if [ "$MODE" = "--onefile" ]; then
    ls -lh dist/bengal-download-manager
    echo "Executable location: dist/bengal-download-manager"
else
    ls -lh dist/bengal-download-manager/bengal-download-manager
    echo "Executable directory: dist/bengal-download-manager/"
fi
echo "========================================================"
