#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

echo "=== 1. Building PyInstaller Standalone Executable ==="
PYTHONPATH=src venv/bin/pyinstaller \
    --name "bengal-download-manager" \
    --onefile \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --add-data "assets:assets" \
    --distpath "dist" \
    --workpath "build" \
    --noconfirm src/main.py

echo "=== 2. Verifying Flatpak Files ==="
if [ ! -f "dist/bengal-download-manager" ]; then
    echo "Error: dist/bengal-download-manager binary missing!"
    exit 1
fi

echo "=== 3. Flatpak Manifest Ready ==="
echo "Manifest: io.github.tazihad.bengal-download-manager.yml"
echo "Desktop Entry: io.github.tazihad.bengal-download-manager.desktop"
echo "AppStream Metainfo: io.github.tazihad.bengal-download-manager.metainfo.xml"
