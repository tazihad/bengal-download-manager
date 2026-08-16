# Modern UI Table & Table Style Switching Specification

## 1. Overview
Introduce dual table presentation modes (**Classic** and **Modern**) for the Bengal Download Manager desktop interface, toggled via **View → Table style**.
- **Classic**: The exact, unmodified 7-column table layout with standard single-line cells.
- **Modern**: The card-like, 2-line title layout modeled after the reference UI (`/home/zihad/Pictures/Screenshots/Screenshot_20260816_093943.png`) featuring embedded progress bars, category subtitles, modern header styling, and tabular metrics.

---

## 2. Core Architectural Constraints
- **Zero Mutation to Existing Core APIs**: The underlying `download_table` data structure, item `UserRole` data attachments (URLs, file paths, worker handles), signals, sorting functions, and worker callbacks remain identical.
- **Pure Layout & Presentation Layer**: Table style changes affect only column configurations, row delegates, row heights, and stylesheet presentation.
- **Persistence**: The active table style selection (`"classic"` or `"modern"`) is saved in user preferences / settings and restored on startup.

---

## 3. UI Specifications

### 3.1 View Menu Options
Under the `View` menu in `MainWindow`:
- Submenu: `Table style`
  - Action 1: `Classic` (Checkable, grouped in `QActionGroup`)
  - Action 2: `Modern` (Checkable, grouped in `QActionGroup`)

### 3.2 Classic Style Layout
- **Columns**: `["File Name", "Size", "Status", "Time left", "Transfer rate", "Last Try Date", "Description"]`
- **Row Height**: Default compact height (~26px).
- **Styling**: Standard Qt grid / header styling.

### 3.3 Modern Style Layout
- **Columns**: `["Name", "Size", "Status", "Speed", "Time Left", "Date Added"]`
- **Header**: Rounded dark container bar with subtle vertical column dividers (`|`) and sort indicators (`⬍`).
- **Row Height**: Ergonomic height (~50px) for multi-line layout.
- **Cell Renderers / Delegates**:
  - **Column 0 (Name)**: File type icon + Primary filename (bold, 13px) + Category subtitle (muted, 11px) on second line.
  - **Column 1 (Size)**: OpenType tabular figures formatted size (`42.50 MB`).
  - **Column 2 (Status)**:
    - Downloading: Status text (`32% Downloading`) + embedded slim horizontal progress bar underneath.
    - Finished: `Finished` text in accent green (`#2ec27e`).
    - Paused: `Paused (<percent>)` text with warning colored progress bar.
  - **Column 3 (Speed)**: Formatted transfer rate (`1.55 MB/s`) with tabular numbers.
  - **Column 4 (Time Left)**: Formatted remaining time (`18 sec left`) with tabular numbers.
  - **Column 5 (Date Added)**: Friendly relative date (`5 minutes ago`, `3 days ago`).

---

## 4. Implementation Strategy

1. **`src/ui/delegates/`**:
   - `ModernTableDelegate` (`QStyledItemDelegate`): Paints the 2-line Name cell, custom status with embedded progress bar, and formatted tabular metric cells.
2. **`MainWindow.set_table_style(style_name: str)`**:
   - Switches between `Classic` and `Modern` delegates, column counts/headers, row heights, and stylesheets seamlessly.
   - Refreshes all rows in `download_table` without interrupting ongoing downloads.
3. **Settings Persistence**:
   - Reads/writes `table_style` key in `config.json` / `QSettings`.

---

## 5. Testing & Verification
- Unit tests verifying menu actions, switching between `Classic` and `Modern` styles dynamically.
- Verifying row selection, context menu invocation, progress updates, and data persistence under both table modes.
