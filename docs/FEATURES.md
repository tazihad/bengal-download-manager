# Bengal Download Manager — Feature Catalog & Capabilities

Bengal Download Manager (BDM) is engineered to provide an uncompromising, high-performance download experience on Linux and Unix desktops. Below is an exhaustive technical catalog of all features and capabilities built into the software.

---

## 1. Core Download Acceleration & Networking

### Multi-Segment Split Downloading (1 to 32 Parallel Connections)
- Divides any remote file supporting HTTP/HTTPS byte-ranges into multiple segments.
- Each segment is fetched simultaneously across independent TCP streams, overcoming server-side per-connection speed caps and maximizing bandwidth saturation.
- User-configurable split limits from 1 to 32 connections per file (default: 8 connections).

### Fault-Tolerant Pause & Resumption
- Pause any active download at any time without discarding already transferred data.
- Persists exact byte positions to disk. Resuming reconnects each split connection directly at its next required byte offset using HTTP `Range: bytes=X-Y`.
- Automatically checks server resume support (`Accept-Ranges` header or HTTP 206 Partial Content response) before enabling segmented allocation.

### Dynamic Bandwidth Speed Limiting
- Per-download and global speed throttling to ensure background transfers do not interfere with video conferencing, gaming, or web browsing.
- Interactive **Speed Limiter** tab in the download progress dialog allows setting exact transfer limits in KB/sec on the fly.
- High-precision token-bucket algorithm eliminates CPU spikes while maintaining a strict speed ceiling.

### Automatic Connection Drop Recovery & Retries
- Robust network error handling detects broken pipes, dropped Wi-Fi connections, and server timeouts.
- Automatically attempts reconnections using an exponential backoff schedule with configurable maximum retry counts per file.

### Expired Link & Broken URL Refreshing
- Handles temporary, time-limited, or tokenized download URLs (such as cloud storage pre-signed links or file hoster sessions).
- Right-click any interrupted download and select **Refresh download address** to supply a fresh URL.
- Resumes the transfer seamlessly from the exact byte where the previous link expired without re-downloading existing chunks.

---

## 2. Smart Organization & Categorization

### Automated Category File Routing
Incoming downloads are automatically inspected and routed into designated target folders based on their file extension:

| Category | Default Destination | Recognized File Extensions |
| :--- | :--- | :--- |
| **Compressed** | `~/Downloads/Compressed` | `.7z`, `.ace`, `.arj`, `.bz2`, `.gz`, `.gzip`, `.lzh`, `.rar`, `.sea`, `.sit`, `.sitx`, `.tar`, `.zip`, `.xz`, `.bz`, `.lzma`, `.war`, `.ear` |
| **Documents** | `~/Downloads/Documents` | `.pdf`, `.pps`, `.ppt`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.rtf`, `.csv`, `.ppsx`, `.dot`, `.txt` |
| **Music** | `~/Downloads/Music` | `.aac`, `.aif`, `.m4a`, `.mp3`, `.mpa`, `.ogg`, `.wav`, `.wma`, `.flac` |
| **Programs** | `~/Downloads/Programs` | `.exe`, `.msi`, `.msu`, `.bin`, `.deb`, `.rpm`, `.appimage`, `.flatpak`, `.snap`, `.apk`, `.sh`, `.bat`, `.cmd`, `.run`, `.dmg`, `.pkg`, `.jar` |
| **Video** | `~/Downloads/Video` | `.3gp`, `.asf`, `.avi`, `.m4v`, `.mkv`, `.mov`, `.mp4`, `.mpe`, `.mpeg`, `.mpg`, `.ogv`, `.rmvb`, `.wmv`, `.webm`, `.flv` |
| **Disk Images**| `~/Downloads/Images` | `.img`, `.iso` |
| **Images** | `~/Downloads/Pictures` | `.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, `.bmp` |
| **General** | `~/Downloads` | All other unclassified file types |

- Fully customizable in **Options → Save To**: modify directory destinations, create custom rules, or adjust extension lists.
- Snap sandbox paths are automatically normalized to user-accessible home directory paths (`SNAP_REAL_HOME`).

### Duplicate File Detection
- Proactively identifies if an incoming URL or filename matches an existing record in the database.
- Displays an intelligent **Duplicate Download** modal with options to:
  - **Open File**: Immediately open the existing file.
  - **Open Folder**: Highlight the file in the file manager.
  - **Resume / Restart**: Re-attempt download or overwrite.
  - **Download Copy**: Automatically append an incremented counter (e.g. `document (1).pdf`) and save as a separate file.

---

## 3. Media Downloader (Video, Audio & Playlists)

### Integrated Media Stream Extraction
- Dedicated **Media Downloader** window accessible via the main toolbar or `Ctrl+M`.
- Built-in engine powered by `yt-dlp`, `ffmpeg`, `ffprobe`, `deno`, and `AtomicParsley`.
- Automatically checks for missing or outdated media binaries and downloads/updates them directly from official GitHub releases with live progress bars.

### Single Video Acquisition
- Fetches and displays media title, channel/uploader, duration, and thumbnail preview.
- **Quality Presets**:
  - *Best Quality (Video + Audio merged)*
  - *4K Ultra HD (2160p)*
  - *2K Quad HD (1440p)*
  - *1080p Full HD*
  - *720p HD*
  - *480p SD*
  - *360p Low Quality*
  - *Audio Only (Opus / MP3 / M4A)*
- **Advanced Codec & Stream Filtering**: Filter by FPS (e.g. 60 FPS), Video Codec (`H.264/AVC`, `VP9`, `AV1`), and Audio Codec (`AAC`, `Opus`, `MP3`).
- **Manual Stream Inspection Table**: Inspect individual raw format streams, bitrates, audio channels, and estimated sizes.

### Playlist & Batch Processing
- Analyzing a playlist URL switches the interface into **Playlist Batch Mode**.
- Renders an interactive table displaying index, video title, uploader, duration, and selection checkboxes.
- **Select All** and **Deselect All** buttons with live selection counters.
- Global quality presets applied across all checked playlist items before batch dispatch to the queue.

### Authentication & Cookie Vault
- Bypass bot detection, login barriers, age restrictions, and private content gates.
- Supports both:
  1. **Netscape cookies.txt**: Import an exported cookie text file.
  2. **Browser Auto-Extraction**: Directly reads authenticated session cookies from Chrome, Firefox, Brave, Edge, Chromium, Vivaldi, or Opera.
- All cookie parsing is executed 100% locally on your machine and never transmitted externally.

---

## 4. Browser Integration (Chrome & Firefox Extensions)

### One-Click Download Interception
- Native browser extensions for Google Chrome (Manifest V3) and Mozilla Firefox (WebExtension MV3).
- Dual interception strategy combining `chrome.webRequest.onHeadersReceived` (monitoring `Content-Disposition: attachment` and binary MIME types) and `chrome.downloads.onCreated`.
- Seamlessly pauses and cancels native browser downloads, passing the payload over local HTTP REST IPC (`port 56900`) to Bengal DM.

### Smart Target Resolver
- Transparently navigates intermediate HTML redirect pages, countdown landing pages, SourceForge mirrors, and Google Drive virus-scan confirmation forms to retrieve direct download links.

### Sliding Deduplication Engine
- 10-second sliding time window prevents accidental double-capture when both header monitoring and download creation fire simultaneously.

### Total Cookie Protection & Partitioned Cookie Passthrough
- Extracts browser session cookies (including Firefox dFPI / Total Cookie Protection isolated partitions) and forwards them in request headers so authenticated downloads succeed seamlessly.

---

## 5. Queue Management & Scheduling

### Queue Modes
- **One-Time Downloading**: Executes queued tasks once sequentially or up to $N$ concurrent downloads.
- **Periodic Synchronization**: Automatically re-runs downloads at scheduled hourly/minute intervals for continuously updating remote archives or data feeds.

### Advanced Scheduling Controls
- **Application Startup**: Trigger queue execution automatically when Bengal DM starts.
- **Specific Time Trigger**: Configure exact start times (`hh:mm:ss AP`).
- **Recurrence Patterns**:
  - *Once*: Runs on a specific calendar date.
  - *Daily*: Executes on selected days of the week (Sunday through Saturday).
- **Scheduled Stop Time**: Automatically pauses active queue downloads at a designated time (e.g. 07:30 AM before work hours).
- **Concurrency Limiter**: Specify how many items in the queue download simultaneously (1 to 20 files).
- **Configurable Retries**: Set maximum retry thresholds for failed queue items before moving to the next item.

---

## 6. User Interface & Desktop Integration

### Adaptive Theme Engine
- Seamlessly conforms to host desktop appearance (GNOME, KDE Plasma, XFCE).
- Listens to OS `QStyleHints` signals for real-time dark/light mode transitions without restarting.
- Includes 20+ built-in color schemes (Breeze Light/Dark, Kirigami, Dracula, Catppuccin, Nord, Obsidian Flow, Material You, One Dark, Solarized) and 14 vibrant accent colors.
- Custom vector monochrome icons dynamically render strokes and luminance to match active background palettes.

### OpenType Tabular Numerics (`tnum: 1`)
- All numerical displays (file sizes, transfer rates, elapsed/remaining times, percentage badges) use OpenType tabular numbers.
- Ensures fixed character widths to eliminate visual jitter and flickering during rapid data updates.

### System Tray & Desktop Shell
- Dockable system tray icon with real-time transfer speed tooltips and active download counters.
- Left-click or double-click to toggle window visibility; right-click context menu for quick actions.
- Optional *Launch minimized in system tray on system startup*.
- Native FreeDesktop notifications on download completion.

### Dual Interface Options: Classic Qt & KDE Kirigami QML
- **Classic Mode**: Dense, informative, and productivity-oriented Qt6 QWidget layout with customizable columns and category tree.
- **Kirigami Mode** (`--kirigami`): Modern, touch-friendly QML card view ideal for KDE Plasma Wayland sessions, convertibles, and Steam Deck devices.
