#!/usr/bin/env bash
# Bengal Download Manager - Snap Build Automation Script (core26, PyInstaller onedir)
# Uses the tracked snap/snapcraft.yml (adopt-info + craftctl set version)
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
            echo ""
            echo "Builds the snap using the tracked snap/snapcraft.yml (adopt-info)."
            echo "Version and grade are set from VERSION file via craftctl."
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

# Use uv if available for version display
PY_BIN="python3"
if command -v uv >/dev/null 2>&1; then
    PY_BIN="uv run python"
elif [ -f ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PY_BIN="venv/bin/python"
fi

VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || cat VERSION 2>/dev/null || echo "0.3.23")
VERSION="${VERSION#v}"

echo "Target snap version: $VERSION"

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

# Use --target-arch if specified
if [ -n "$TARGET_ARCH" ]; then
    EXTRA_ARGS+=("--target-arch=$TARGET_ARCH")
fi

snapcraft pack "${EXTRA_ARGS[@]}"

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