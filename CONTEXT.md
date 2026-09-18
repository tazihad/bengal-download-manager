# CONTEXT.md — Bengal Download Manager Domain Model Glossary

This document establishes the canonical domain language and design vocabulary for Bengal Download Manager.
Architectural refactors and deepening opportunities must use these terms consistently.

---

## Domain Glossary

### Download
A persisted or active transfer request identified by a unique key.
- **URL**: The source network location for the transfer.
- **Target Path**: The absolute local filesystem location where the payload is assembled.
- **Status**: The operational state (`Queued`, `Connecting`, `Downloading`, `Paused`, `Complete`, `Error`, `Cancelled`).
- **Transfer Metrics**: Numeric indicators including byte size, transfer rate, progress percentage, and time remaining (rendered with tabular figures `tnum`).

### Queue
A managed execution group governing concurrency and order for a collection of Downloads.
- **Main Download Queue**: The default FIFO queue for standard transfers.
- **Synchronization Queue**: A specialized queue for recurring or mirrored content synchronization.
- **Custom Queue**: User-defined transfer queues with independent scheduling rules and concurrency caps.
- **Queue Schedule**: Temporal constraints defining when a queue may automatically activate, pause, or retry (e.g., daily time windows, day-of-week filters).

### Download Engine (Worker)
An execution adapter fulfilling the transfer interface at the download seam.
- **Python Segment Worker**: Multi-threaded HTTP/HTTPS chunk downloader utilizing byte-range requests.
- **Aria2 Worker**: Daemon adapter orchestrating high-throughput multi-connection downloads via JSON-RPC.
- **Media Worker**: Stream extraction and retrieval engine powered by yt-dlp.

### Category
Classification of downloads based on payload file extensions (e.g., Compressed, Documents, Music, Programs, Video) used for folder routing and view filtering.

### Bridge
The presentation seam connecting the core application model to alternative frontends (PyQt6 QWidget table and KDE Kirigami QML cards).

### Desktop Integration
The platform seam managing system interactions: XDG Desktop Portals, D-Bus file manager discovery, system tray status, and autostart launchers.
