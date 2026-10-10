#!/usr/bin/env bash
# Bengal Download Manager - Update Flatpak Python Dependencies
# Uses flatpak-pip-generator (https://github.com/flatpak/flatpak-builder-tools/tree/master/pip)
# to generate offline, hash-pinned modules for both internal and Flathub manifests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

DEFAULT_PACKAGES=(
    "pyinstaller"
    "python-socks[asyncio]>=3.1.0"
    "bgutil-ytdlp-pot-provider>=1.0.0"
)

PACKAGES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: $0 [packages...]"
            echo ""
            echo "Updates Flatpak offline Python dependencies (python3-requirements.yaml)"
            echo "for both internal (flatpak/) and Flathub (flatpak/flathub/) manifests."
            echo ""
            echo "Default packages: ${DEFAULT_PACKAGES[*]}"
            exit 0
            ;;
        *)
            PACKAGES+=("$1")
            shift
            ;;
    esac
done

if [ ${#PACKAGES[@]} -eq 0 ]; then
    PACKAGES=("${DEFAULT_PACKAGES[@]}")
fi

echo "========================================================"
echo " Updating Flatpak Python Dependencies"
echo " Packages: ${PACKAGES[*]}"
echo "========================================================"

GENERATOR_URL="https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator.py"
GENERATOR_BIN="/tmp/flatpak-pip-generator.py"

if [ ! -f "$GENERATOR_BIN" ]; then
    echo "Fetching flatpak-pip-generator from $GENERATOR_URL..."
    curl -fsSL "$GENERATOR_URL" -o "$GENERATOR_BIN"
fi

TEMP_DIR="$(mktemp -d /tmp/bdm-pip-gen-XXXXXX)"
trap 'rm -rf "$TEMP_DIR"' EXIT

if ! command -v pip3 >/dev/null 2>&1 && ! command -v pip >/dev/null 2>&1; then
    mkdir -p "$TEMP_DIR/bin"
    cat << 'EOF' > "$TEMP_DIR/bin/pip3"
#!/usr/bin/env bash
exec python3 -m pip "$@"
EOF
    chmod +x "$TEMP_DIR/bin/pip3"
    ln -sf "$TEMP_DIR/bin/pip3" "$TEMP_DIR/bin/pip"
    export PATH="$TEMP_DIR/bin:$PATH"
fi

RAW_OUTPUT="$TEMP_DIR/python3-requirements-raw.yaml"
CLEAN_OUTPUT="$TEMP_DIR/python3-requirements.yaml"

echo "Running flatpak-pip-generator..."
uv run --with pyyaml --with requirements-parser --with pip \
    python "$GENERATOR_BIN" \
    "${PACKAGES[@]}" \
    --yaml \
    -o "$TEMP_DIR/python3-requirements"

if [ -f "$TEMP_DIR/python3-requirements.yaml" ]; then
    mv "$TEMP_DIR/python3-requirements.yaml" "$RAW_OUTPUT"
elif [ -f "$TEMP_DIR/python3-requirements" ]; then
    mv "$TEMP_DIR/python3-requirements" "$RAW_OUTPUT"
else
    echo "Error: Generator did not produce expected output file."
    exit 1
fi

grep -v '^[[:space:]]*#' "$RAW_OUTPUT" > "$CLEAN_OUTPUT"

uv run python -c "
import yaml
with open('$CLEAN_OUTPUT') as f:
    data = yaml.safe_load(f)
assert data.get('name') == 'python3-requirements', 'Invalid module name'
assert 'modules' in data, 'Missing modules in generated file'
print(f'✓ Validated YAML with {len(data[\"modules\"])} submodules')
"

INTERNAL_DEST="flatpak/python3-requirements.yaml"
FLATHUB_DEST="flatpak/flathub/python3-requirements.yaml"

mkdir -p "flatpak" "flatpak/flathub"
cp "$CLEAN_OUTPUT" "$INTERNAL_DEST"
cp "$CLEAN_OUTPUT" "$FLATHUB_DEST"

echo "✓ Successfully updated:"
echo "  - $INTERNAL_DEST"
echo "  - $FLATHUB_DEST"
