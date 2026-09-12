# Bengal Download Manager — System Architecture & Engineering Deep-Dive

This document provides a comprehensive technical breakdown of Bengal Download Manager's engineering architecture, concurrency design, worker lifecycle, persistence layer, and system integration.

---

## 1. Architectural Topology

Bengal Download Manager is designed around a decoupled, asynchronous, and reactive architecture. The user interface remains 100% responsive at 60 FPS while network operations, disk I/O, format extraction, and inter-process communication execute concurrently on dedicated background worker threads.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                     PRESENTATION LAYER                                  │
│                                                                                         │
│   ┌──────────────────────────────────────────────┐  ┌────────────────────────────────┐  │
│   │         PyQt6 QWidget Application            │  │     KDE Kirigami QML Engine    │  │
│   │  - MainWindow, QSplitter, Category Sidebar   │  │  - Main.qml, CardsListView     │  │
│   │  - DownloadTableWidget & Custom Delegates    │  │  - GlobalDrawer, Dialogs       │  │
│   │  - Specialized Modal Dialogs (Add, Progress) │  │  - OpenType Tabular Numerics   │  │
│   └──────────────────────┬───────────────────────┘  └───────────────┬────────────────┘  │
│                          │                                          │                   │
│                          └────────────────────┬─────────────────────┘                   │
│                                               │                                         │
│                                               ▼                                         │
│                                  ┌───────────────────────────┐                          │
│                                  │   DownloadBridge QObject  │                          │
│                                  │  (Signals, Slots, Props)  │                          │
│                                  └────────────┬──────────────┘                          │
└───────────────────────────────────────────────┼─────────────────────────────────────────┘
                                                │
┌───────────────────────────────────────────────┼─────────────────────────────────────────┐
│                                   APPLICATION CONTROLLER                                │
│                                               │                                         │
│   ┌───────────────────────────────────────────┴──────────────────────────────────────┐  │
│   │                       MainWindow State Coordinator & Dispatcher                  │  │
│   │  - Active download registry (self.active_downloads, self.active_speeds)          │  │
│   │  - Dynamic system theme listener (QStyleHints, QEvent.Type.ApplicationPaletteChange)│
│   │  - System tray controller (QSystemTrayIcon, dynamic speed tooltips)             │  │
│   │  - Auto-start scheduler ticker (QTimer: _check_scheduled_queues)                 │  │
│   └───────────────┬───────────────────────────┬──────────────────────────┬───────────┘  │
└───────────────────┼───────────────────────────┼──────────────────────────┼──────────────┘
                    │                           │                          │
                    ▼                           ▼                          ▼
┌───────────────────────────────┐ ┌───────────────────────────┐ ┌─────────────────────────┐
│     IPC & SINGLE INSTANCE     │ │   PERSISTENCE & STORAGE   │ │      MEMORY GUARD       │
│  - TCP Server (Port 56900)    │ │  - SQLite 3 WAL Database  │ │  - glibc malloc_trim(0) │
│  - REST API for Extensions    │ │  - FTS5 Virtual Table     │ │  - Cyclic GC Collector  │
│  - QLocalServer Daemon Guard  │ │  - In-memory dirty cache  │ │  - Weakref Dialog Map   │
│  - CLI Argument Pass-through  │ │  - Auto-migration JSON/DB │ │  - Safe QWidget Cleanup │
└───────────────────────────────┘ └───────────────────────────┘ └─────────────────────────┘
                    │                           │                          │
                    └───────────────────────────┼──────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CORE WORKER SUBSYSTEM                                 │
│                                                                                         │
│   ┌──────────────────────────────┐  ┌─────────────────────────┐  ┌───────────────────┐  │
│   │      FetcherWorker           │  │   Aria2Worker (Primary) │  │ DownloadWorker    │  │
│   │  - Probes HEAD / Range       │  │  - JSON-RPC 2.0 Client  │  │ (Native Fallback) │  │
│   │  - Parses RFC 6266 Filenames │  │  - Managed Daemon Proc  │  │ - Multi-segment   │  │
│   │  - Detects Binary MIME types │  │  - Dynamic Split (1-32) │  │ - Direct pwrite   │  │
│   │  - Resolves Direct Mirrors   │  │  - Port 56800 Listener  │  │ - Range chunking  │  │
│   └──────────────────────────────┘  └─────────────────────────┘  └───────────────────┘  │
│                                                   │                                     │
│                                                   ▼                                     │
│                                     ┌───────────────────────────┐                       │
│                                     │   Media Downloader Engine │                       │
│                                     │  - yt-dlp Process Wrapper │                       │
│                                     │  - ffmpeg/ffprobe Multiplex│                      │
│                                     │  - AtomicParsley Tagger   │                       │
│                                     │  - Cookie Vault Decryptor │                       │
│                                     └───────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Concurrency & Threading Model

Bengal Download Manager strictly follows the **Single GUI Thread Rule** enforced by Qt6 while offloading heavy networking and disk I/O to background threads:

### 2.1 The Main Thread (Event Loop)
The main thread executes the Qt application event loop (`QApplication.exec()`). It is exclusively responsible for:
- Constructing and rendering UI widgets (`QMainWindow`, `QTableWidget`, `QDialog`).
- Dispatching repaint events and CSS styling updates.
- Processing keyboard shortcuts and mouse input.
- Animating progress bars and updating status labels at 100ms throttle intervals.
- Handling OS-level signals (e.g. desktop palette changes, window minimize/restore).

No blocking calls (such as synchronous network requests, disk pre-allocation, or subprocess execution) are ever allowed on this thread.

### 2.2 Background Workers (`QThread`)
All network interactions and process monitors subclass `QThread`. Communication between workers and the UI layer occurs exclusively via **thread-safe Qt Signals and Slots** (`pyqtSignal`), ensuring zero GUI lockup:

```python
class Aria2Worker(QThread):
    main_progress_signal = pyqtSignal(int, tuple)       # (row_index, (downloaded, total, speed, time_left, status))
    main_bar_signal = pyqtSignal(object, object)        # (downloaded_bytes, total_bytes)
    finished_signal = pyqtSignal(int, str)              # (row_index, final_status)
    log_signal = pyqtSignal(str)                        # Raw log text
    segment_update_signal = pyqtSignal(int, object, object, float, str) # Thread segment stats
    init_segments_signal = pyqtSignal(int)              # Number of active connections
```

---

## 3. Dual-Engine Download Execution Strategy

To ensure absolute reliability across all environments (including restricted enterprise setups, sandboxed Flatpaks, and systems without external utilities), BDM implements a dual-engine architecture:

### 3.1 Primary Engine: Aria2 RPC Integration (`Aria2Worker`)
When `aria2c` is available on the host system or inside the sandbox package, BDM launches an isolated background daemon using JSON-RPC 2.0:
- **Daemon Lifecycle**: Automatically started on a configurable local port (default: `56800`), bound exclusively to `127.0.0.1`.
- **Authentication**: Secured using a generated or user-specified secret RPC token.
- **Connection Allocation**: Divides downloads into up to 32 parallel split connections (`--split=N`, `--max-connection-per-server=N`).
- **Resumption**: Fully tracks `.aria2` metadata files, allowing uninterrupted pause and resume across application restarts.
- **Real-Time RPC Polling**: A dedicated polling loop executes `aria2.tellStatus` every 300ms, extracting byte counters, transfer speed, and connection health before emitting Qt signals.

### 3.2 Native Fallback Engine: Python Multi-Segment Downloader (`DownloadWorker`)
If `aria2c` is not installed, BDM immediately falls back to its built-in, pure Python multi-threaded chunk downloader:
- **Byte-Range Partitioning**: Probes the server with an `Accept-Ranges: bytes` request. If supported, calculates equal byte offsets:
  $$\text{Offset}_i = \left[ i \cdot \frac{\text{TotalBytes}}{N}, (i+1) \cdot \frac{\text{TotalBytes}}{N} - 1 \right]$$
- **Worker Segments (`SegmentWorker`)**: Spawns $N$ concurrent `SegmentWorker` threads, each maintaining an independent HTTP keep-alive connection with custom `User-Agent`, `Cookie`, and `Referer` headers.
- **Direct Slicing I/O**: Each thread seeks directly to its assigned byte position inside the target file using `r+b` mode, writing chunks into the pre-allocated disk space without thread contention.
- **Dynamic Speed Limiting**: Implements a high-precision token bucket sleep algorithm inside the chunk read loop to enforce per-download transfer rate limits.

---

## 4. Pre-Fetcher & Link Resolution (`FetcherWorker`)

Before any download begins, BDM invokes `FetcherWorker` to inspect the target URL without downloading the file body:

1. **HTTP Probe**: Issues a lightweight byte-range `GET` (`bytes=0-0`) or `HEAD` request.
2. **RFC 6266 Filename Resolution**: Parses the `Content-Disposition` header, resolving UTF-8 and legacy encoded filenames (`filename*=UTF-8''...` or `filename="..."`).
3. **MIME-Type & Content-Length Evaluation**: Extracts `Content-Length` for total file size and `Content-Type` for automated category routing.
4. **Intermediate Mirror & Redirect Resolution**: Transparently follows HTTP 301/302/307/308 redirects and parses intermediate HTML meta-refresh landing pages (e.g. SourceForge, VideoLAN mirrors, Google Drive confirmation tokens).
5. **Portal Save Path Resolution**: On Linux Flatpak environments, routes file destination dialogues through `XDG Desktop Portal` to obtain access to the host filesystem.

---

## 5. Inter-Process Communication (IPC) & Single Instance

### 5.1 Extension REST Bridge (Port 56900)
BDM hosts an embedded HTTP server (`TcpListenerThread`) on `http://127.0.0.1:56900` using `http.server.BaseHTTPRequestHandler`:
- **CORS Handling**: Fully implements `OPTIONS` preflight requests with `Access-Control-Allow-Origin: *` to accept dispatches from Chrome and Firefox extension service workers.
- **Health Verification (`GET /`)**: Returns application status, version string, and active Aria2 RPC configuration.
- **Download Ingestion (`POST /` or `POST /download`)**: Accepts JSON payloads containing:
  ```json
  {
    "url": "https://example.com/archive.tar.gz",
    "filename": "archive.tar.gz",
    "referrer": "https://example.com/",
    "userAgent": "Mozilla/5.0 ...",
    "cookies": "session=xyz123"
  }
  ```
- **Thread Safety**: Decodes the payload in the listener thread and dispatches it to the GUI thread via `SignalEmitter.new_download_signal`.

### 5.2 Single-Instance Guard (`QLocalServer` / `QLocalSocket`)
To prevent port collisions and redundant background processes:
- BDM acquires a user-scoped Unix local socket: `bengal_dm_single_instance_{getpass.getuser()}`.
- If an instance is already running, the secondary launch command forwards any CLI arguments (URLs) over the local socket to the primary instance and terminates immediately.
- The primary instance receives the arguments via `SingleInstanceServer.message_received`, restores its main window from the system tray, and presents the download prompt.

---

## 6. Memory Guard & Leak Protection Subsystem

Long-running download managers often suffer from Python memory fragmentation and C++ Qt widget accumulation. BDM incorporates a dedicated subsystem in [`src/core/memory_guard.py`](file:///mnt/data/dev/bengal-download-manager/src/core/memory_guard.py):

1. **OS Heap Trimming (`malloc_trim`)**: Under Linux glibc, free heap pages inside the allocator often remain unreleased to the kernel. `MemoryGuard.trim_heap()` calls `ctypes.CDLL('libc.so.6').malloc_trim(0)`, forcibly relinquishing unmapped memory back to the operating system.
2. **Cyclic Garbage Collection Tuning**: Triggers full Generation-2 garbage collection (`gc.collect()`) upon dialog closure, download completion, and queue state changes.
3. **Weakref Tracking**: Tracks transient dialogs (`DownloadProgressDialog`, `PropertiesDialog`) using `weakref.WeakSet`. When a dialog is closed, it explicitly disconnects all Qt signals and calls `deleteLater()`.
4. **C++ Instance Liveness Verification**: `MemoryGuard.is_widget_alive()` checks both Python reference validity and underlying C++ wrapper integrity via `sip.isdeleted()`, preventing `RuntimeError: wrapped C/C++ object has been deleted`.

---

## 7. KDE Kirigami QML Hybrid Architecture

BDM includes an alternative, touch-friendly UI mode built on KDE's Kirigami framework (`src/ui/qml/`):
- **Entry Point**: Triggered via `uv run python src/main.py --kirigami`.
- **C++ / Python Bridge (`DownloadBridge`)**: A `QObject` subclass registered into the QML context as `DownloadBridge`. Exposes reactive Qt properties (`downloads`, `statusMessage`, `totalSpeed`, `memoryUsage`, `aria2Running`) and invokable slots (`addDownload`, `pauseDownload`, `resumeDownload`, `deleteDownload`, `openFile`, `openFolder`).
- **QML Components**:
  - `Main.qml`: Root Kirigami application window featuring responsive action bars.
  - `GlobalDrawer.qml`: Collapsible category and queue filter drawer.
  - `DownloadCard.qml`: Fluid cards list view displaying download status badges, speed counters, and OpenType tabular figures (`font.features: { "tnum": 1 }`).

---

## 8. Operating System & Desktop Environment Integration

- **Theme Detection**: Listens to `QGuiApplication.styleHints().colorSchemeChanged` and Qt event types `ApplicationPaletteChange`, `PaletteChange`, `ThemeChange`, and `StyleChange` to switch themes dynamically between Dark and Light mode.
- **Icon Resolution**: Probes standard FreeDesktop icon paths (`/usr/share/icons`, `~/.local/share/icons`, `/app/share/icons`). If monochrome mode is active, generates vector stroke icons with dynamic luminance matching the active palette.
- **Desktop Notifications**: Dispatches standard FreeDesktop notifications via `notify-send` or XDG desktop portals upon download completion.
- **File Manager Integration**: Uses `QDesktopServices`, `xdg-open`, or D-Bus `org.freedesktop.FileManager1.ShowItems` to open files and highlight downloaded items inside Nautilus, Dolphin, Thunar, or PCManFM.
