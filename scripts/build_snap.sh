#!/usr/bin/env bash
# Bengal Download Manager - Snap Build Automation Script
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
echo " Building Bengal Download Manager Snap (core24)"
echo "========================================================"

if ! command -v snapcraft &>/dev/null; then
    echo "ERROR: snapcraft is not installed."
    echo "Install snapcraft via: sudo snap install snapcraft --classic"
    exit 1
fi

echo "--- 1. Validating Snapcraft Recipe Syntax ---"
PY_BIN="python3"
if [ -f "venv/bin/python" ]; then
    PY_BIN="venv/bin/python"
fi

$PY_BIN -c "
try:
    import yaml
    d = yaml.safe_load(open('snap/snapcraft.yaml'))
    print(f'Validated snap: {d[\"name\"]} (base: {d[\"base\"]})')
except ImportError:
    print('PyYAML not in environment, skipping pre-lint.')
"

echo "--- 2. Executing Snapcraft Build ---"
if [ -z "${APP_VERSION:-}" ]; then
    APP_VERSION=$($PY_BIN -c "import sys; sys.path.insert(0, 'src'); from core.version import VERSION; print(VERSION)" 2>/dev/null || echo "0.2.20")
    export APP_VERSION
fi
echo "Target snap version: $APP_VERSION"
$PY_BIN -c "
import re
path = 'snap/snapcraft.yaml'
with open(path, 'r') as f:
    content = f.read()
content = re.sub(r'version:\s*[\x27\"][^\x27\"]+[\x27\"]', f'version: \x27$APP_VERSION\x27', content)
with open(path, 'w') as f:
    f.write(content)
"
snapcraft pack "${EXTRA_ARGS[@]}"

echo "--- 3. Verifying Generated Snap Artifact ---"
SNAP_FILE=$(find . -maxdepth 1 -name "bengal-download-manager_*.snap" -print -quit)
if [ -n "$SNAP_FILE" ] && [ -f "$SNAP_FILE" ]; then
    echo "SUCCESS: Snap package built successfully -> ${SNAP_FILE}"
    ls -lh "$SNAP_FILE"
else
    echo "WARNING: Snap package build completed, check current directory for output .snap files."
fi
