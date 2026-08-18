# Clean Architecture Modularization Plan (Bengal Download Manager)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modularize the monolithic `src/main.py` (~5,080 lines) into a decoupled Clean Architecture structure following Python Clean Architecture principles (Sam Keen / Robert C. Martin), separating Domain Entities, Application Services, UI Components, and Infrastructure while preserving 100% of existing behaviors, tests, and CLI flags.

**Architecture:** 
- **Domain & Use Cases (`src/core/`):** Pure Python business logic, download lifecycle orchestration, IPC server, and scheduler services.
- **Interface Adapters (`src/ui/`):** Dedicated UI components for Category Sidebar, Download Table & Delegates, System Tray, Status Bar, and Toolbar.
- **Application Core (`src/ui/main_window.py`):** Lean `MainWindow` integrating decoupled UI controllers and use-case services.
- **Entry Point (`src/main.py`):** Lightweight (~100 lines) bootstrap entry point.

**Tech Stack:** Python 3.13, PyQt6, Qt QML/Kirigami, Aria2 RPC.

## Global Constraints
- Preserve exact exported public API names, Qt signal/slot signatures, and test compatibility.
- Ensure all 123 automated pytest tests in `tests/` continue passing at every step.
- Preserve PyInstaller bundle and Flatpak packaging targets.
- All code changes strictly on branch `optimization` (unpushed).

---

## File Structure & Proposed Decomposition

```
src/
├── main.py                               # Lightweight bootstrap entry point (~100 lines)
├── core/
│   ├── models/
│   │   └── download_item.py              # Download entity data class & status enums
│   ├── services/
│   │   ├── download_service.py           # Download worker orchestration & queue coordinator
│   │   ├── ipc_service.py                # Single instance server & extension IPC listener
│   │   └── theme_service.py              # Palette generator, QColor roles, dynamic stylesheets
│   ├── bridge.py                         # QML Kirigami DownloadBridge
│   ├── memory_guard.py                   # Heap compaction & leak protection
│   └── utils.py                          # Formatting, icons, disk & string utilities
└── ui/
    ├── main_window.py                    # Root MainWindow UI coordinator
    ├── components/
    │   ├── table_view.py                 # Download table widget & column logic
    │   ├── table_delegate.py             # Custom cell painting, tabular figures, progress delegates
    │   ├── category_sidebar.py           # Category tree sidebar & queue management
    │   ├── status_bar_manager.py         # Real-time speed & disk metrics status bar
    │   └── tray_controller.py            # System tray icon, hibernation & speed tooltip
    ├── dialogs/                          # Dialog windows (Progress, Options, Scheduler, etc.)
    └── icons.py                          # Vector icons & monochrome stroke builders
```

---

## Bite-Sized Implementation Tasks

### Task 1: Extract IPC & Single-Instance Services (`src/core/services/ipc_service.py`)
- Move `SingleInstanceServer`, `IPCEmitter`, and `IPCListenerThread` from `src/main.py` to `src/core/services/ipc_service.py`.
- Re-export in `src/core/services/__init__.py`.
- Verify IPC tests in `tests/test_ui.py` pass.

### Task 2: Extract Theme & Dynamic Stylesheet Engine (`src/core/services/theme_service.py`)
- Extract `apply_app_theme`, `generate_dynamic_stylesheet`, `normalize_theme_name`, `get_themed_icon`, and `get_themed_tray_icon` from `src/main.py` to `src/core/services/theme_service.py`.
- Wire theme hooks in `src/ui/icons.py` and `src/main.py`.
- Verify theming tests pass.

### Task 3: Extract Table Component & Delegates (`src/ui/components/table_view.py` & `table_delegate.py`)
- Move `DownloadTableDelegate`, `SidebarItemDelegate`, `SelectableHeaderView`, and `TableCornerButton` into dedicated modules in `src/ui/components/`.
- Decouple column rendering, progress bar painting, and sorting helpers.
- Run table delegate tests (`tests/test_table_delegate.py`, `tests/test_table_styles.py`).

### Task 4: Extract System Tray & Status Bar Controllers (`src/ui/components/tray_controller.py` & `status_bar_manager.py`)
- Move tray icon initialization, hibernation hooks, and real-time tooltip speed tracking into `TrayController`.
- Move status bar labels, disk space queries, and speed formatting into `StatusBarManager`.
- Verify tray hibernation tests pass.

### Task 5: Extract Category Sidebar & Queue Management (`src/ui/components/category_sidebar.py`)
- Move category tree building, item counts, queue context menus, and drag-and-drop filtering to `CategorySidebar`.
- Run sidebar and queue tests (`tests/test_scheduler_queues.py`).

### Task 6: Extract Core Download Coordinator (`src/core/services/download_service.py`)
- Move download worker lifecycle, start/stop/pause/resume routing, speed tracking dictionary, and cache file cleanup to `DownloadService`.
- Wire `DownloadService` signals to `MainWindow` and `DownloadBridge`.
- Verify `tests/test_workers.py` and `tests/test_bridge.py`.

### Task 7: Refactor `MainWindow` & Slim Down `src/main.py`
- Refactor `src/ui/main_window.py` to assemble the decoupled components (`CategorySidebar`, `TableView`, `TrayController`, `StatusBarManager`, `DownloadService`).
- Reduce `src/main.py` to a clean bootstrap script (<120 lines).
- Execute full test suite: `PYTHONPATH=src venv/bin/pytest -v tests/`.
- Verify PyInstaller standalone binary build.
