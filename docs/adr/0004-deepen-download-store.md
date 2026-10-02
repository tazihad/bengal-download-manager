# 0004 Deepen Download Store and Decouple Presentation Views

Status: accepted

## Context
Previously, `MainWindow.download_table` (`QTableWidget`) served as the application's de facto in-memory data store. Persistence routines (`save_data`) and presentation bridges had to iterate GUI table cells and extract internal Qt `UserRole` integers to access download state, coupling presentation widgets tightly to core domain models.

## Decision
We introduce `DownloadStore` in `src/core/download_store.py` as an autonomous in-memory repository managing `Download` records. It maintains synchronized state with SQLite persistence, emits reactive change signals (`itemAdded`, `itemUpdated`, `itemRemoved`, `downloadsChanged`), and serves as the data provider for table view adapters.

## Consequences
- GUI table widgets are treated strictly as view presentation adapters rather than data stores.
- Download lifecycle, state transitions, and concurrency filtering are testable in headless unit tests.

> **Note:** `DownloadBridge` and the Kirigami QML layer that originally consumed `DownloadStore` signals were removed in PR #144. The store continues to serve the PyQt6 QWidget table view adapter.
