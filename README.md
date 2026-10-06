<div align="center">

<img src="assets/logo.png" alt="Bengal Download Manager Logo" width="128" />

# Bengal Download Manager

### Downloads, Supercharged.

*Bengal Download Manager is a powerful and efficient download management tool designed to simplify and accelerate your downloading experience.*

<div align="center">

[![Latest Release](https://img.shields.io/github/v/release/tazihad/bengal-download-manager?style=flat-square&color=06b6d4&label=release)](https://github.com/tazihad/bengal-download-manager/releases/latest)
[![bengal-download-manager](https://snapcraft.io/bengal-download-manager/badge.svg)](https://snapcraft.io/bengal-download-manager)
[![Downloads](https://img.shields.io/github/downloads/tazihad/bengal-download-manager/total?style=flat-square&color=22c55e)](https://github.com/tazihad/bengal-download-manager/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Snap%20%7C%20Flatpak%20%7C%20AppImage-8b5cf6?style=flat-square)](#build-instructions)

</div>

### Get App

[![Get it from the Snap Store](https://snapcraft.io/en/dark/install.svg)](https://snapcraft.io/bengal-download-manager)
[![Download AppImage](assets/badges/badge_appimage.svg)](https://github.com/tazihad/bengal-download-manager/releases/latest)
[![Install via Flatpak](assets/badges/badge_flatpak.svg)](https://zihad.com.bd/bengal-download-manager/bengal-download-manager.flatpakref)

### Get Addon

[![Get the Firefox Add-on](https://img.shields.io/badge/Firefox-Get_the_Add--on-ff7139?style=for-the-badge&logo=firefox-browser&logoColor=white)](https://addons.mozilla.org/en-US/firefox/addon/bengal-dm-integration-module)
[![Chrome Web Store](https://img.shields.io/badge/Chrome_Store-Upcoming-4285F4?style=for-the-badge&logo=google-chrome&logoColor=white)](#browser-extensions)
[![GitHub Extension Package](https://img.shields.io/badge/GitHub-Extension_Package-24292e?style=for-the-badge&logo=github&logoColor=white)](https://github.com/tazihad/bengal-download-manager/releases/latest)

</div>

<br />

<p align="center">
  <img width="100%" alt="Bengal Download Manager Poster 1 - Multi-Threaded Downloader" src="assets/posters/poster_classic_hero.jpg" />
</p>

<p align="center">
  <img width="100%" alt="Bengal Download Manager Poster 2 - Adaptive Light & Dark Themes" src="assets/posters/poster_duo.jpg" />
</p>

Bengal Download Manager is a high-performance download management tool built with PyQt6, KDE Kirigami QML, and Aria2 to accelerate and simplify your download workflow.

## Screenshots & Product Posters

### Main Application (Dark & Light Mode)

<p align="center">
  <img width="49%" alt="Bengal Download Manager Dark Mode" src="assets/screenshots/screenshot_dark_mode.png" />
  <img width="49%" alt="Bengal Download Manager Light Mode" src="assets/screenshots/screenshot_light_mode.png" />
</p>

### One-Click Browser Integration & Settings

<p align="center">
  <img width="49%" alt="Download Interception File Info Dialog" src="assets/screenshots/screenshot_download_dialog.png" />
  <img width="49%" alt="Browser Extension Popup Settings" src="assets/screenshots/screenshot_extension_popup.png" />
</p>

### Feature Branding Posters

<p align="center">
  <img width="100%" alt="Seamless Browser Integration Poster" src="assets/posters/poster_browser_integration.jpg" />
</p>

<p align="center">
  <img width="100%" alt="Complete Download Ecosystem Poster" src="assets/posters/poster_master_suite.jpg" />
</p>

## Key Features

- ⚡ **Supercharged Speed:** Downloads files in multiple split parts simultaneously to get the absolute maximum speed from your internet connection.
- ⏯️ **Pause & Resume Anytime:** Pause downloads whenever you need, and pick up right where you left off without ever losing progress.
- 🌐 **One-Click Browser Integration:** Automatically catches download links from Firefox, Chrome, Brave, and Edge as soon as you click them.
- 🗂️ **Smart File Organization:** Keeps your downloads tidy by automatically sorting them into clear categories like *Documents*, *Videos*, *Music*, *Compressed*, and *Programs*.
- 🛡️ **Automatic Connection Recovery:** Automatically retries and resumes downloads if your Wi-Fi or internet connection temporarily drops.
- 🎛️ **Bandwidth Speed Controls:** Easily limit download speeds so your video streaming and web browsing stay smooth while downloading in the background.
- 🎨 **Clean Light & Dark Themes:** Enjoy a modern, distraction-free interface that automatically adapts to your preferred light or dark desktop mode.

## Installation

Download pre-built packages from the [Latest Release](https://github.com/tazihad/bengal-download-manager/releases/latest).

### Supported Architectures
- **`x86_64`** (64-bit Intel / AMD)
- **`aarch64` / `arm64`** (64-bit ARM)

### Available Packages

| Format | Supported Architectures | Quick Command / Link |
| :--- | :--- | :--- |
| **Snap Store** | `x86_64`, `arm64` | `sudo snap install bengal-download-manager` / [Snapcraft](https://snapcraft.io/bengal-download-manager) |
| **Flatpak (Repository)** | `x86_64`, `aarch64` | `flatpak install https://zihad.com.bd/bengal-download-manager/bengal-download-manager.flatpakref` |
| **AppImage** | `x86_64`, `aarch64` | [Download AppImage](https://github.com/tazihad/bengal-download-manager/releases/latest) |
| **Standalone Binary** | `x86_64`, `aarch64` | [Download Binary Executable](https://github.com/tazihad/bengal-download-manager/releases/latest) |

#### Flatpak Quick Start (Online Repository & Auto-Updates)
```bash
# 1-Click / One-Command Install via Flatpakref
flatpak install --user https://zihad.com.bd/bengal-download-manager/bengal-download-manager.flatpakref

# Or Add Flathub-Standard Remote Repository
flatpak remote-add --user --if-not-exists tazihad https://zihad.com.bd/bengal-download-manager/tazihad.flatpakrepo
flatpak install --user tazihad bd.com.zihad.BengalDownloadManager
```

#### AppImage Quick Start
```bash
chmod +x bengal-download-manager-*-x86_64.AppImage
./bengal-download-manager-*-x86_64.AppImage
```

---

## Browser Extensions

Integrate Bengal Download Manager with your browser for automatic download interception:

- **Firefox Add-ons Store:**  
  [![Get the Firefox Add-on](https://img.shields.io/badge/Firefox-Get_the_Add--on-ff7139?style=for-the-badge&logo=firefox-browser&logoColor=white)](https://addons.mozilla.org/en-US/firefox/addon/bengal-dm-integration-module)

- **GitHub Release (Offline Zip):**  
  [![GitHub Extension Package](https://img.shields.io/badge/GitHub-Extension_Package-24292e?style=for-the-badge&logo=github&logoColor=white)](https://github.com/tazihad/bengal-download-manager/releases/latest)

- **Google Chrome:**  
  [![Chrome Web Store](https://img.shields.io/badge/Chrome_Store-Upcoming-4285F4?style=for-the-badge&logo=google-chrome&logoColor=white)](#browser-extensions) *(Chrome Web Store release coming soon)*

---

## Build Instructions

### 1. Python Development Mode

Run directly from source (see [DEPENDENCIES.md](DEPENDENCIES.md) for requirements):

```bash
git clone https://github.com/tazihad/bengal-download-manager.git
cd bengal-download-manager
pip install -e .
python3 src/main.py
```

#### Command-Line Options & Debug Flags

| Option / Flag | Environment Variable | Description |
| :--- | :--- | :--- |
| *(default)* | *(none)* | Standard mode with clean `INFO`-level logging. |
| `--debug` | `DEBUG=1` or `BENGAL_DEBUG=1` | Enables detailed `DEBUG` logging with timestamps, source file/line context, and clean throttled IPC heartbeat summaries. |
| `--verbose` | `VERBOSE=1` or `BENGAL_VERBOSE=1` | Enables full, unrestricted diagnostic logging including every raw IPC extension ping and HTTP request/response line. |
| `--debug --verbose` | `DEBUG=1 VERBOSE=1` | Complete unrestricted verbose debug output for comprehensive troubleshooting. |
| `--kirigami` | *(none)* | Launches the KDE Kirigami QML responsive user interface instead of the classic PyQt6 QWidget table view. |


### 2. Standalone Binary Build (CMake)

Build a self-contained, single-file binary executable using **CMake** and **PyInstaller**:

```bash
# Ensure dependencies and PyInstaller are installed
pip install -e ".[dev]"

# Configure CMake build tree
cmake -B build -S .

# Compile standalone executable
cmake --build build
```

The resulting binary will be generated at:
```bash
./build/dist/bengal-download-manager
```

### 3. Flatpak Package Build

Build and test the Flatpak package locally using the Flatpak manifest:

```bash
bash scripts/build_flatpak.sh
```

### 4. Browser Extension Packaging

Package the Manifest V3 browser extension zip for Firefox Add-ons (AMO) or Chrome Web Store:

```bash
python3 scripts/pack_extension.py
```

See [extension/README.md](extension/README.md) for step-by-step build instructions, environment requirements, and reviewer documentation.
