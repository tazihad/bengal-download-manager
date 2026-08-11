# Media Downloader Documentation

The **Media Downloader** feature in Bengal Download Manager allows users to extract and download high-definition video, audio streams, and entire playlists from YouTube and hundreds of media sites using an integrated `yt-dlp` backend engine.

---

## 1. Overview & Key Capabilities

- **Toolbar Integration**: Placed directly to the right of **Options** on the main application toolbar (and in the **Downloads** menu).
- **Independent Taskbar Windowing**: `MediaDownloaderDialog` opens as a standalone top-level window (`Qt.WindowType.Window | parent=None`) so Linux desktop environments (KDE Plasma, GNOME, XFCE) display it with a separate taskbar panel button while keeping the shared application `WM_CLASS` (`bengal-download-manager`).
- **Automated Engine Management**: `YtDlpManager` automatically checks for `yt-dlp` on system `PATH` or in local app storage (`~/.local/share/bengal-download-manager/bin/yt-dlp`). If missing, it downloads the latest standalone binary directly from GitHub releases with non-blocking progress updates.
- **Single Video Mode**:
  - Displays Title, Uploader, Duration, and available format streams.
  - **Quality Selection Chooser**: Preset selector (`Best Quality (1080p+)`, `1080p`, `720p`, `480p`, `360p`, `Audio Only`) + Detailed Stream Table (`Format ID`, `Resolution`, `Extension`, `Codec`, `Bitrate`, `Estimated Size`).
- **Playlist / Batch Mode**:
  - Triggered automatically when analyzing playlist URLs.
  - Interactive batch item table with checkboxes for each video item.
  - **Select All** & **Deselect All** buttons with live item counter.
  - Global quality preset applied across selected batch items.

---

## 2. Technical Architecture & File Map

### Core Modules
* **[`src/core/media_downloader.py`](file:///mnt/data/dev/bengal-download-manager/src/core/media_downloader.py)**:
  * `YtDlpManager`: Detects, acquires, and manages `yt-dlp` binary execution.
  * `MediaExtractorWorker`: Background `QThread` executing `yt-dlp -J --flat-playlist --no-warnings <URL>` and parsing JSON metadata into structured single video and playlist payloads.
* **[`src/ui/dialogs/media_downloader.py`](file:///mnt/data/dev/bengal-download-manager/src/ui/dialogs/media_downloader.py)**:
  * `MediaDownloaderDialog`: PyQt6 user interface with URL input bar, status indicators, `QStackedWidget` (empty, single video, playlist views), format selection controls, and enqueue handlers.
* **[`src/ui/icons.py`](file:///mnt/data/dev/bengal-download-manager/src/ui/icons.py)**:
  * Resolution-independent vector stroke icon for `media_downloader` (display monitor + play triangle).
* **[`src/main.py`](file:///mnt/data/dev/bengal-download-manager/src/main.py)**:
  * Action definition `self.action_media_downloader`, toolbar placement after `action_options`, menu entry under `&Downloads`, and launcher slot `open_media_downloader()`.

### Test Suite
* **[`tests/test_media_downloader.py`](file:///mnt/data/dev/bengal-download-manager/tests/test_media_downloader.py)**: Core engine & format parser unit tests.
* **[`tests/test_media_downloader_ui.py`](file:///mnt/data/dev/bengal-download-manager/tests/test_media_downloader_ui.py)**: PyQt dialog window initialization, single video format selection, and playlist batch selection unit tests.

---

## 3. Usage Instructions

1. Launch Bengal Download Manager (`python src/main.py`).
2. Click the **Media Downloader** button on the main toolbar (right of **Options**).
3. Enter or paste a video link (e.g., YouTube video or playlist) into the URL bar and click **Analyze Link**.
4. **Single Video**: Select desired quality preset or stream format, then click **Download Media**.
5. **Playlist**: Check/uncheck desired playlist videos, select global target quality, then click **Download Selected (N items)**.
6. Downloads are immediately enqueued into Bengal Download Manager's core multi-threaded Aria2 download engine.
