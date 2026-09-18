# 0006 Deepen Download Controller

Status: accepted

## Context
`MainWindow` previously managed active worker threads, progress dialog instances, and bandwidth metrics directly in its internal dictionaries (`self.active_downloads = {}`, `self.active_speeds = {}`). It was responsible for iterating active worker entries, inspecting whether entries were `QDialog` or `QThread` instances, managing pause/resume operations, and calculating overall transfer rates. This coupled active download execution lifecycles to GUI table presentation and forced QML `DownloadBridge` to inspect GUI window dictionaries.

## Decision
We introduce `DownloadController` in `src/core/download_controller.py` as a deep module that:
- Coordinates active download workers and associated dialogs behind clean registration methods (`register`, `unregister`, `get_worker`, `get_dialog`, `is_active`).
- Maintains thread-safe dictionary protocol compatibility (`__getitem__`, `__setitem__`, `__contains__`, `pop`, `get`, `items`) to preserve complete backwards compatibility with existing UI routines and tests.
- Encapsulates speed tracking and bandwidth aggregation (`update_speed`, `get_total_speed`, `get_active_count`, signal `aggregate_speed_changed`).
- Centralizes graceful bulk pausing and termination (`stop_all`, `pause`).

## Consequences
- Presentation views (`MainWindow`, `DownloadBridge`) access active download state and speed metrics through a unified domain controller.
- Concurrency tracking and speed calculations can be tested headlessly without GUI tables.
- Eliminates brittle duck-typing checks across GUI layers for worker vs. dialog objects.
