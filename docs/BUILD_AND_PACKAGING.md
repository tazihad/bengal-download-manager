# Bengal Download Manager — Build, Packaging & Distribution Guide

This document provides complete instructions for setting up development environments, running automated test suites, and building production distribution packages across Linux targets (Flatpak, Snap, AppImage, Standalone CMake Binary, and Browser Extensions).

---

## 1. Development Environment Setup

Bengal Download Manager requires **Python 3.10+** and uses [`uv`](https://github.com/astral-sh/uv) for fast, deterministic dependency resolution.

### Install Dependencies via `uv`
```bash
# Clone repository
git clone https://github.com/tazihad/bengal-download-manager.git
cd bengal-download-manager

# Install project dependencies
uv pip install -r requirements.txt
```

### Running in Development Mode
```bash
# Launch standard PyQt6 desktop interface
uv run python src/main.py

# Launch KDE Kirigami QML interface
uv run python src/main.py --kirigami
```

---

## 2. Automated Test Suite

Bengal Download Manager maintains an automated unit and integration test suite in `tests/`:

```bash
# Run all test suites with verbose output
PYTHONPATH=src uv run pytest -v tests/

# Run individual test files
PYTHONPATH=src uv run pytest -v tests/test_database.py
PYTHONPATH=src uv run pytest -v tests/test_workers.py
PYTHONPATH=src uv run pytest -v tests/test_media_downloader.py
```

---

## 3. Standalone Binary Build (CMake & PyInstaller)

BDM includes a CMake build definition (`CMakeLists.txt`) that compiles a single-file, self-contained executable bundling all Python code, Qt6 libraries, and application assets:

```bash
# 1. Configure the CMake build directory
cmake -B build -S .

# 2. Compile standalone binary
cmake --build build
```

The compiled standalone binary executable will be located at:
```bash
./build/dist/bengal-download-manager
```

To run directly:
```bash
./build/dist/bengal-download-manager
```

---

## 4. Flatpak Packaging (Flathub / KDE Platform 6.11)

The Flatpak manifest is maintained in [`flatpak/io.github.tazihad.bengal-download-manager.yml`](file:///mnt/data/dev/bengal-download-manager/flatpak/io.github.tazihad.bengal-download-manager.yml) using the `org.kde.Platform` 6.11 runtime.

### Local Flatpak Build & Run Script
Run the automated packaging helper:
```bash
bash scripts/build_and_run_flatpak.sh
```

### Manual Flatpak Build Commands
```bash
# 1. Install Flatpak SDK and runtime
flatpak install flathub org.kde.Platform//6.11 org.kde.Sdk//6.11

# 2. Build and export Flatpak bundle
flatpak-builder --user --install --force-clean build-flatpak flatpak/io.github.tazihad.bengal-download-manager.yml

# 3. Launch installed Flatpak package
flatpak run io.github.tazihad.bengal-download-manager
```

---

## 5. Canonical Snap Packaging (Snapcraft)

The Snapcraft manifest is maintained in [`snap/snapcraft.yaml`](file:///mnt/data/dev/bengal-download-manager/snap/snapcraft.yaml).

### Build with Snapcraft
```bash
# Build locally using LXD or Multipass container
snapcraft --use-lxd

# Install locally for testing
sudo snap install bengal-download-manager_*.snap --dangerous
```

---

## 6. AppImage Packaging

BDM builds portable `x86_64` and `aarch64` AppImages packaged with AppImageKit:

```bash
# Make AppImage executable and run
chmod +x bengal-download-manager-*-x86_64.AppImage
./bengal-download-manager-*-x86_64.AppImage
```

---

## 7. Browser Extension Packaging

The browser extension located in `extension/` is packaged into signed zip bundles for the Mozilla Add-ons Store (AMO) and Google Chrome Web Store:

```bash
# Package extension zip
python3 scripts/pack_extension.py
```

The script outputs `extension-firefox.zip` and `extension-chrome.zip` containing validated Manifest V3 declarations.

---

## 8. Single Source of Truth Version Verification

Before committing release tags or building distribution packages, ensure all package manifests match the root `VERSION` file:

```bash
# Verify consistency across all manifests
python3 scripts/sync_version.py --check

# To bump version atomically across VERSION, snapcraft.yaml, metainfo.xml, and runtime:
python3 scripts/sync_version.py --set 0.2.25
```
