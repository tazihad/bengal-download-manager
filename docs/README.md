# Bengal Download Manager — Documentation Hub

Welcome to the official technical documentation for **Bengal Download Manager (BDM)**, an advanced, high-performance, open-source download accelerator and media acquisition suite built with Python, PyQt6, KDE Kirigami QML, and Aria2.

This documentation suite is organized following standard Free and Open Source Software (FOSS) best practices, providing exhaustive engineering specifications, complete user-interface control references, architectural deep-dives, and package maintenance guides.

---

## 📚 Documentation Index

| Document | Description | Target Audience |
| :--- | :--- | :--- |
| **[System Architecture](ARCHITECTURE.md)** | High-level engineering architecture, dual-engine design (Aria2 RPC + native Python worker), threading and concurrency model, IPC REST bridge, memory guard, and QML integration. | Developers, Contributors, Architects |
| **[Feature Catalog](FEATURES.md)** | Exhaustive technical inventory of all capabilities: multi-segment acceleration, broken link recovery, speed throttling, media stream capture, queue scheduling, and auto-sorting. | Developers, Power Users |
| **[UI & Controls Reference](UI_AND_CONTROLS.md)** | Granular, button-by-button, menu-by-menu, and dialog-by-dialog guide explaining every control, context menu, shortcut, and metric in the application. | End Users, Testers, Documentarians |
| **[Database & Storage Architecture](DATABASE_AND_STORAGE.md)** | SQLite persistence engine, WAL mode, foreign keys, schema definitions, FTS5 full-text indexing, dirty write buffering, and data safety. | Database Engineers, Contributors |
| **[Browser Extension & Interception](BROWSER_EXTENSION.md)** | Architecture of the Manifest V3 browser extension (Chrome & Firefox), network header inspection, download capture, target resolution, and IPC protocol. | Web Developers, Integrators |
| **[Media Downloader Engine](MEDIA_DOWNLOADER.md)** | Technical breakdown of the media capture subsystem: yt-dlp supervisor, ffmpeg/ffprobe stream multiplexing, dependency management, and playlist parsing. | Media Engineers, Contributors |
| **[Cookie Authentication Guide](COOKIES_GUIDE.md)** | Step-by-step instructions for exporting Netscape `cookies.txt` files and leveraging browser session cookies for authenticated downloads. | End Users, Power Users |
| **[Theming & Design System](THEMING.md)** | Visual design language, adaptive OS light/dark tracking, 20+ color themes, 14 accents, resolution-independent vector icons, and OpenType tabular figures (`tnum`). | UI/UX Designers, Frontend Engineers |
| **[Build & Packaging Guide](BUILD_AND_PACKAGING.md)** | Compilation, packaging, and distribution instructions for Linux: Flatpak, Canonical Snap, AppImage, CMake standalone binary, and browser extensions. | Packagers, System Maintainers, CI/CD |
| **[Version Management (SSOT)](VERSIONING.md)** | Single Source of Truth versioning architecture across `VERSION`, Snapcraft, Flatpak AppStream, and runtime metadata using `sync_version.py`. | Maintainers, Release Managers |

---

## 🏛️ High-Level System Overview

Bengal Download Manager connects your web browser, native desktop user interface, and multi-connection network engine through a decoupled, fault-tolerant architecture:

```
+---------------------------------------------------------------------------------------+
|                                    Desktop Shell                                      |
|  +--------------------------------------------+  +---------------------------------+  |
|  |           PyQt6 QWidget Desktop            |  |      KDE Kirigami QML View      |  |
|  |   (Table View, Category Tree, Dialogs)     |  |   (Cards View, Global Drawer)   |  |
|  +--------------------------------------------+  +---------------------------------+  |
+---------------------------------------------------------------------------------------+
                                        │
                                        ▼
+---------------------------------------------------------------------------------------+
|                                Core Application Layer                                 |
|  - DownloadBridge: QObject signals and slots for QML / C++ integration               |
|  - MemoryGuard: glibc malloc_trim(0) heap compaction and weakref tracking             |
|  - SQLite Engine: WAL journal mode, FTS5 full-text search, thread-safe persistence    |
|  - IPC Server: Local REST API on port 56900 handling browser extension dispatches    |
|  - Single-Instance Guard: QLocalServer preventing duplicate daemon processes          |
+---------------------------------------------------------------------------------------+
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
+---------------------------------------+   +---------------------------------------+
|        Primary Download Engine        |   |       Fallback Download Engine        |
|             (Aria2 RPC)               |   |        (Native Python Worker)         |
|  - Multi-connection segmenting (1-32) |   |  - Chunk-based byte-range HTTP/HTTPS  |
|  - JSON-RPC 2.0 daemon on port 56800  |   |  - posix_fallocate contiguous disk I/O|
|  - BitTorrent & Metalink capable      |   |  - Zero external binary dependency    |
+---------------------------------------+   +---------------------------------------+
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
+---------------------------------------------------------------------------------------+
|                               Media Acquisition Subsystem                             |
|  - yt-dlp background execution with automatic binary acquisition from GitHub releases |
|  - ffmpeg & ffprobe stream merging (high-definition video + high-bitrate audio)       |
|  - AtomicParsley metadata embedding and deno runtime deciphering engine               |
+---------------------------------------------------------------------------------------+
```

---

## 🚀 Quick Reference for Developers

### Running in Development Mode
BDM requires Python 3.10+ and uses [`uv`](https://github.com/astral-sh/uv) for fast, reproducible dependency management:

```bash
# Clone the repository
git clone https://github.com/tazihad/bengal-download-manager.git
cd bengal-download-manager

# Run standard PyQt6 desktop interface
uv run python src/main.py

# Run KDE Kirigami QML interface
uv run python src/main.py --kirigami
```

### Running Test Suite
```bash
PYTHONPATH=src uv run pytest -v tests/
```

### Checking Package Manifest Versions
```bash
python3 scripts/sync_version.py --check
```

---

## 📄 License and Community

Bengal Download Manager is free software licensed under the terms of the **MIT License**. All source code, documentation, and extension manifests are publicly maintained on GitHub at [https://github.com/tazihad/bengal-download-manager](https://github.com/tazihad/bengal-download-manager). Contributions, bug reports, and pull requests are welcomed following standard open-source collaboration practices.
