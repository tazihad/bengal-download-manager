# Design Spec: IDM-Like UI Scaling & Behavior
Date: 2026-05-11
Status: Draft

## 1. Goal
Ensure Bengal Download Manager scales correctly across all display resolutions (720p to 8K) and mimics the behavior of Internet Download Manager (IDM) by Tonec.

## 2. Architectural Changes

### 2.1 High DPI Support
Enable High DPI scaling in the PyQt6 application to ensure text and icons are sharp on 4K/8K displays.
- **Implementation:** Set `Qt.HighDpiScaleFactorRoundingPolicy` before `QApplication` instantiation in `src/main.py`.
- **Constraint:** Use `PassThrough` policy to respect system-level scaling (125%, 150%, 200%, etc.).

### 2.2 Dynamic & Resizable Layouts
Replace hardcoded pixel sizes with flexible layouts to support both small (720p) and large (4K+) screens.
- **Action:** Remove all instances of `setFixedSize()` in `src/dialogs.py`.
- **Action:** Replace hardcoded `setGeometry()` in `src/main.py` with saved state restoration.
- **Pattern:** Use `setMinimumSize()` to prevent dialogs from becoming unusable while allowing expansion.
- **Layouts:** Use `QGridLayout` and `QVBoxLayout` with appropriate stretch factors for table and list views.

### 2.3 State Persistence
Mimic IDM's behavior by remembering window positions, sizes, and column widths.
- **Storage:** Use `QSettings` to persist data in a platform-independent way.
- **Data Points:**
    - Main window geometry and state (splitters, toolbars).
    - Table column widths for the download list.
    - Category list width.

## 3. UI Components Affected
- **MainWindow:** Restore previous size/position; enable High DPI.
- **AddUrlDialog:** Remove fixed 600x100 size; use layout constraints.
- **OptionsDialog:** Remove fixed 600x550 size; ensure tabs are scrollable if screen is too small.
- **DownloadProgressDialog:** Remove fixed width; allow horizontal expansion for long filenames.
- **PropertiesDialog:** Remove fixed size.

## 4. Verification Plan
- **Mocked Scaling:** Use `QT_SCALE_FACTOR` environment variable to simulate 2x (4K) scaling on 1080p hardware.
- **Small Screen Test:** Manually resize window to 1024x768 (approximating 720p) to ensure no UI elements are truncated.
- **Persistence Check:** Close and reopen the app after resizing columns and windows; verify state is preserved.
