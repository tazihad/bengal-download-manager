#!/usr/bin/env bash
# Bengal Download Manager - Standalone Executable Build Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

MODE="--onefile"
ONEDIR_FLAG="0"
DO_CLEAN=1
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --onefile)
            MODE="--onefile"
            ONEDIR_FLAG="0"
            ;;
        --onedir)
            MODE="--onedir"
            ONEDIR_FLAG="1"
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

RUNTIME_ASSETS_DIR="$PYINSTALLER_WORKPATH/runtime_assets"
if [ -f "$SCRIPT_DIR/i18n.py" ]; then
    echo "Compiling latest translation catalogs..."
    $PY_BIN "$SCRIPT_DIR/i18n.py" compile || true
fi
bash "$SCRIPT_DIR/prepare_runtime_assets.sh" "$RUNTIME_ASSETS_DIR" "$ARCH"

PYTHONPATH=src BDM_ONEDIR="$ONEDIR_FLAG" $PYINSTALLER_BIN \
    --noconfirm \
    --distpath "dist" \
    --workpath "$PYINSTALLER_WORKPATH" \
    "${EXTRA_ARGS[@]}" \
    bengal-download-manager.spec

# The spec already filters the PyInstaller TOCs (required for --onefile).  Run
# the standalone cleaner as a second, idempotent pass for --onedir output so
# anything added by COLLECT is caught as well.
if [ "$MODE" = "--onedir" ]; then
    $PY_BIN "$SCRIPT_DIR/cleanup_application_tree.py" "dist/bengal-download-manager"
fi

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
