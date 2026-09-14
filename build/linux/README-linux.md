# Bengal Download Manager — Linux Build System

This directory houses the build scripts, packaging configurations, toolchains, and distribution metadata for **Linux** platforms.

---

## 1. Supported Packaging Targets

* **Standalone Binary**: One-file or directory executable produced via PyInstaller (`scripts/build_binary.sh`).
* **AppImage**: Universal, portable Linux binary bundle (`scripts/build_appimage.sh`).
* **Flatpak**: Sandboxed package targeting `org.kde.Platform` runtime 6.11 (`scripts/build_flatpak.sh` and `flatpak/`).
* **Snap**: Confined package for Ubuntu and snapd-enabled distributions (`scripts/build_snap.sh` and `snap/`).

---

## 2. Directory Layout

```
build/linux/
├── patches/            # Linux-specific distro/upstream compatibility patches
├── fixes/              # Dynamic fixes (e.g. font substitution, portal workarounds)
├── cmake/
│   ├── toolchain-gcc.cmake
│   ├── toolchain-clang.cmake
│   └── options.cmake   # Linux build options and custom CMake targets
├── distro/             # Distribution-specific metadata and launcher assets
├── build-scripts/      # Automated execution scripts
├── config/             # Environment overrides and spec files
└── README-linux.md     # This document
```

---

## 3. Quick Start

### Build Standalone Executable
```bash
bash scripts/build_binary.sh
```

### Build AppImage
```bash
bash scripts/build_appimage.sh
```

### Build Flatpak Package
```bash
bash scripts/build_flatpak.sh
```
