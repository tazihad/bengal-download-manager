<div align="center">

<img src="assets/logo.png" alt="Bengal Download Manager Logo" width="128" />

# Bengal Download Manager

### Downloads, Supercharged.

*Bengal Download Manager is a powerful and efficient download management tool designed to simplify and accelerate your downloading experience.*

[![Latest Release](https://img.shields.io/github/v/release/tazihad/bengal-download-manager?style=flat-square&color=06b6d4&label=release)](https://github.com/tazihad/bengal-download-manager/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/tazihad/bengal-download-manager/total?style=flat-square&color=22c55e)](https://github.com/tazihad/bengal-download-manager/releases)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Flatpak%20%7C%20AppImage-8b5cf6?style=flat-square)](#build-instructions)

</div>

<br />

<p align="center">
  <img width="100%" alt="Bengal Download Manager Poster" src="assets/poster.jpg" />
</p>

Bengal Download Manager is a high-performance download management tool built with PyQt6, KDE Kirigami QML, and Aria2 to accelerate and simplify your download workflow.

## Screenshots

<p align="center">
  <img width="80%" alt="Bengal Download Manager Interface Screenshot" src="assets/Screenshot_20260805_125846.png" />
</p>

## Features

- **Multi-threaded Downloads using Aria2:** Download files in multiple parts simultaneously, significantly increasing transfer rates.
- **Pause and Resume:** Conveniently pause and resume downloads at any time.
- **Bandwidth Limiting:** Control your download and upload speeds to prevent network congestion.
- **Categorization:** Organize your downloads into different categories for easy management.
- **Browser Integration:** Seamlessly integrate with Chrome, Firefox, Edge, and Brave via Manifest V3 integration module.
- **Error Recovery:** Automatically retry failed downloads due to network interruptions.
- **User-friendly Interface:** Modern PyQt6 and KDE Kirigami interface supporting light and dark themes.

## Build Instructions

### Linux

Build from source (see [DEPENDENCIES.md](DEPENDENCIES.md) for requirements):

```bash
git clone https://github.com/tazihad/bengal-download-manager.git
cd bengal-download-manager
```

```sh
pip install -r requirements.txt
python3 src/main.py
```
