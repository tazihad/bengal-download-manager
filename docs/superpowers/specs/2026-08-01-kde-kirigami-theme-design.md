# Design Spec: KDE Kirigami Architecture & Theme Rewrite

- **Date**: 2026-08-01
- **Status**: Approved
- **Target Application**: Bengal Download Manager (`bengal-download-manager`)

---

## 1. Overview & Objectives

Rewrite the frontend UI architecture of Bengal Download Manager using **KDE Kirigami** (`org.kde.kirigami`), Qt Quick, and QML. This replaces the static PyQt6 `QTableWidget` interface with a responsive, convergent KDE Plasma-native user interface featuring Kirigami Cards, Global Drawer navigation, Kirigami Overlay Sheets, and Breeze visual styling.

---

## 2. Architecture & Components

```
+----------------------------------------------------------------+
|                    Kirigami.ApplicationWindow                   |
|  +-----------------------+----------------------------------+  |
|  | Kirigami.GlobalDrawer |     Kirigami.CardsListView       |  |
|  |  - All Downloads      |  +----------------------------+  |  |
|  |  - Downloading        |  | Kirigami.Card (Download 1) |  |  |
|  |  - Completed          |  +----------------------------+  |  |
|  |  - Paused             |  | Kirigami.Card (Download 2) |  |  |
|  |  - Categories         |  +----------------------------+  |  |
|  +-----------------------+----------------------------------+  |
|  | Overlays/Sheets: Add URL, Progress Sheet, Properties, Options|  |
+----------------------------------------------------------------+
                               |
                   [PyQt6 QObject DownloadBridge]
                               |
         [Core Download Manager / Aria2 / Workers Backend]
```

### 2.1 Backend Bridge (`src/core/bridge.py` / `DownloadBridge`)
A `QObject` subclass registered in QML context exposing backend state and actions:
* **Properties**:
  * `downloadList`: List of active download items (dictionaries/QObjects)
  * `activeCount`, `completedCount`, `pausedCount`
  * `globalSpeed`: Combined transfer rate string
* **Slots (`@pyqtSlot`)**:
  * `addDownload(url, category, savePath)`
  * `pauseDownload(id)` / `resumeDownload(id)` / `cancelDownload(id)`
  * `openFile(path)` / `openFolder(path)`
  * `showProperties(id)` / `showOptions()`

### 2.2 QML View Layer (`src/ui/qml/`)
* **`Main.qml`**: Root `Kirigami.ApplicationWindow` containing the main layout, header actions, and global drawer.
* **`GlobalDrawer.qml`**: Category filtering sidebar (`Kirigami.GlobalDrawer`).
* **`DownloadCard.qml`**: `Kirigami.Card` item representing individual downloads with filename, size, status badge, progress bar, speed, time left, and contextual inline buttons.
* **`AddUrlDialog.qml`**: `Kirigami.Dialog` overlay for inserting download URLs and setting category/save directory.
* **`ProgressOverlay.qml`**: `Kirigami.OverlaySheet` displaying multi-threaded segment progress bars and real-time chunk statistics.
* **`PropertiesDialog.qml`**: `Kirigami.Dialog` displaying metadata for a selected download.
* **`OptionsDialog.qml`**: Kirigami FormCard layout (`org.kde.kirigamiaddons.formcard` / `Kirigami.FormLayout`) for app configuration.

---

## 3. Kirigami Design System & Typography

* **Theme Tokens**: Uses native `Kirigami.Theme` palette (`Kirigami.Theme.backgroundColor`, `Kirigami.Theme.highlightColor`, `Kirigami.Theme.textColor`, `Kirigami.Theme.activeTextColor`).
* **Tabular Numbers**: Numeric indicators (speed, file sizes, percentage indicators, timestamps) enforce OpenType tabular numbers (`font.features: { "tnum": 1 }`) for clean vertical alignment across card metrics.
* **Responsive Layout**: Support for desktop wide view and adaptive narrow window resizing.

---

## 4. Fallback & Environment Compatibility

* Ensure system Qt6 QML module paths (`/usr/lib/x86_64-linux-gnu/qt6/qml`) are configured in Python (`QQmlApplicationEngine.addImportPath`).
* Maintain existing backend download logic (`download.py`, `aria2.py`, `fetcher.py`, `config.py`) untouched, connecting strictly via the QObject bridge.

---

## 5. Verification & Testing

1. Launch application via Python (`python src/main.py`) and verify Kirigami window initialization.
2. Verify adding, pausing, resuming, and deleting downloads updating Kirigami cards in real time.
3. Validate tab switching in Kirigami Global Drawer (Filtering by status & category).
4. Run PyInstaller binary build (`python scripts/pack_extension.py` / PyInstaller build) to confirm package compatibility.
