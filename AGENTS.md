# AGENTS.md — Agent & Architectural Reference Guide

> **Bengal Download Manager** is a high-performance, multi-threaded open-source download manager built with PyQt6, KDE Kirigami QML, and Aria2.

---

## 1. System Architecture Overview

```
+-------------------------------------------------------------------------+
|                  Bengal Download Manager User Interface                 |
|  +-----------------------------------+-------------------------------+  |
|  |     PyQt6 QWidget Interface       |     KDE Kirigami QML Engine   |  |
|  |  (QTableWidget, Sidebar Tree)     |   (CardsListView, Drawer)     |  |
|  +-----------------------------------+-------------------------------+  |
+-------------------------------------------------------------------------+
                                    |
                    [src/core/bridge.py DownloadBridge]
                                    |
+-------------------------------------------------------------------------+
|                        Core Worker Layer (src/core/)                    |
|  +---------------------------+---------------------------------------+  |
|  |  DownloadWorker (Python)  |    Aria2Worker (Aria2 RPC Engine)    |  |
|  +---------------------------+---------------------------------------+  |
+-------------------------------------------------------------------------+
                                    |
                    [Local TCP Listener Port 56800]
                                    |
+-------------------------------------------------------------------------+
|                  Browser Extension (Chrome MV3 / Firefox)               |
+-------------------------------------------------------------------------+
```

---

## 2. Directory Structure & Key Files

* **`src/main.py`**: Application entry point, `MainWindow` setup, IPC TCP listener thread, and theme manager.
* **`src/core/bridge.py`**: `DownloadBridge` (`QObject`) exposing properties and slots for QML Kirigami views.
* **`src/core/workers/`**:
  * `download.py`: Multi-threaded Python HTTP/HTTPS chunk downloader.
  * `aria2.py`: Aria2 RPC daemon integration and background thread manager.
  * `fetcher.py`: Pre-fetcher worker to query filename and size before starting downloads.
* **`src/ui/qml/`**: KDE Kirigami QML view components:
  * `Main.qml`: Root `Kirigami.ApplicationWindow` with header action bar.
  * `GlobalDrawer.qml`: Category and status filtering sidebar.
  * `DownloadCard.qml`: Responsive card view with tabular metrics (`font.features: { "tnum": 1 }`).
  * `AddUrlDialog.qml` & `OptionsDialog.qml`: Kirigami Dialog overlays.
* **`src/ui/dialogs/`**: PyQt6 QWidget dialog windows (`progress.py`, `complete.py`, `file_info.py`, `options.py`, `properties.py`).
* **`flatpak/`**:
  * `io.github.tazihad.bengal-download-manager.yml`: Flatpak manifest for `org.kde.Platform` 6.11.
  * `io.github.tazihad.bengal-download-manager.desktop`: XDG desktop launcher entry.
  * `io.github.tazihad.bengal-download-manager.metainfo.xml`: AppStream component metadata.
* **`extension/`**: Manifest V3 browser extension for Chrome and Firefox.
* **`tests/`**: Automated test suite (`test_utils.py`, `test_workers.py`, `test_bridge.py`, `test_ui.py`).

---

## 3. Development & Build Workflows

### Run Application in Development Mode
```bash
# Standard PyQt6 QWidget Mode
uv run python src/main.py

# KDE Kirigami QML Mode
uv run python src/main.py --kirigami
```

### Run Automated Unit Test Suite
```bash
PYTHONPATH=src uv run pytest -v tests/
```

### Build Standalone Executable Binary
```bash
PYTHONPATH=src uv run pyinstaller \
    --name "bengal-download-manager" \
    --onefile \
    --paths "src" \
    --collect-all core \
    --collect-all ui \
    --add-data "assets:assets" \
    --distpath "dist" \
    --workpath "build" \
    --noconfirm src/main.py
```

### Build and Run Flatpak Package
```bash
bash scripts/build_and_run_flatpak.sh
```

---

## 4. Agent Guidelines & Best Practices

1. **Obey User Directives**: Maintain Documentation integrity and preserve existing docstrings.
2. **No Speculative Code**: Inspect source files directly before assuming signatures or APIs.
3. **Tabular Figures**: Ensure numeric UI labels (sizes, transfer rates, percentages, timestamps) use OpenType tabular numbers (`tnum`).
4. **Theme Adaptability**: Do not hardcode static dark text colors (`#444`). Allow `QPalette` system colors to adapt cleanly across Light, Dark, and Automatic system themes.
5. **Empirical Verification**: Always verify code changes by running `pytest` or testing binary builds before declaring completion.
6. **Single Source of Truth Versioning**: Always use `scripts/sync_version.py` when changing or checking version numbers across `VERSION`, `snap/snapcraft.yaml`, `flatpak/metainfo.xml`, and `src/core/version.py`. (Note: Browser extension in `extension/manifest.json` is versioned independently). See `docs/VERSIONING.md` for details.
7. **Use `uv` Instead of `venv`**: Always use `uv` for Python environment management, package installation, and execution (e.g. `uv venv`, `uv pip install ...`, and `uv run <command>`). Do not use standard `python3 -m venv` or raw `venv/bin/python`.
