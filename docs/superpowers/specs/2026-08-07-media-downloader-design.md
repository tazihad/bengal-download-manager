# Media Downloader Feature Specification

**Date:** 2026-08-07  
**Status:** Approved  
**Target Branch:** `feat/media-downloader`

---

## 1. System Overview & Architecture

The **Media Downloader** feature integrates YouTube and multi-site video/audio extraction capabilities into Bengal Download Manager using `yt-dlp` backend engine, inspired by Free Download Manager's *Elephant* add-on architecture.

### Architectural Diagram
```
+-----------------------------------------------------------------------+
|                         Main Toolbar (PyQt6)                          |
|  [Add URL] [Resume] [Pause] ... [Options] [Media Downloader]          |
+-----------------------------------------------------------------------+
                                  |
               Triggers MediaDownloaderDialog (QDialog)
              (Qt.WindowType.Window | parent=None for panel wmclass)
                                  |
                                  v
+-----------------------------------------------------------------------+
|                        MediaDownloaderDialog                          |
|  +-----------------------------------------------------------------+  |
|  | Header: "Enter URL"                                             |  |
|  | QLineEdit URL + [Paste] + [Analyze Link]                        |  |
|  +-----------------------------------------------------------------+  |
|  | [Single Video Mode]               | [Playlist / Batch Mode]     |  |
|  | - Title, Thumbnail, Duration      | - Playlist Title & Count    |  |
|  | - Quality Presets Dropdown        | - Batch Table w/ Checkboxes |  |
|  |   (1080p, 720p, 480p, Audio Only)  | - Select All / Deselect All |  |
|  | - Stream Format Detail Picker     | - Global Quality Selector   |  |
|  +-----------------------------------------------------------------+  |
|  | [Download] / [Download Selected]                              |  |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|                    Core Backend (src/core/)                           |
|  +------------------------------+----------------------------------+  |
|  |  YtDlpManager                |  MediaExtractorWorker            |  |
|  |  - Auto-downloads yt-dlp bin |  - Background subprocess QThread |  |
|  |  - Manages PATH / app-data   |  - Executes `yt-dlp -J ...`      |  |
|  +------------------------------+----------------------------------+  |
+-----------------------------------------------------------------------+
                                  |
                                  v
                     Bengal DM Main Queue (Aria2 Engine)
```

---

## 2. Component Details

### 2.1 UI Window (`src/ui/dialogs/media_downloader.py`)
* **Window Configuration**:
  * Extends `QDialog`.
  * Initialized with `super().__init__(None)` and flags `Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint`.
  * Window Title: `"Media Downloader"`.
  * Preserves application `WM_CLASS` (`bengal-download-manager`) while rendering as an independent taskbar item.
* **Layout Structure**:
  * **Title Header**: `"Enter URL"`.
  * **Input Bar**: `QLineEdit` with paste shortcut and `"Analyze Link"` trigger button.
  * **Status & Loading Area**: Progress spinner / status text during `yt-dlp` download or URL extraction.
  * **View Stack (`QStackedWidget`)**:
    * **Page 0 (Single Video View)**:
      * Video title, author/channel, duration, and thumbnail preview.
      * **Quality Chooser**:
        * Presets: Best (1080p+), 1080p, 720p, 480p, 360p, Audio Only (MP3/M4A).
        * Stream Table: Format ID, Resolution, Extension, Codec, Bitrate, Size estimate.
    * **Page 1 (Playlist / Batch View)**:
      * Playlist Title & total item count.
      * Checkbox list of videos (Index, Title, Duration).
      * "Select All" / "Deselect All" buttons & selection count banner.
      * Global quality chooser applied to selected videos.
  * **Footer Buttons**: `"Download"` (or `"Download Selected (N items)"`) and `"Close"`.

### 2.2 Main Window Toolbar Integration (`src/main.py`)
* New action `self.action_media_downloader` created with `media_downloader` icon.
* Placed in `MainToolbar` immediately to the right of `self.action_options`.
* Placed in `&Downloads` menu bar.

### 2.3 Core Engine (`src/core/media_downloader.py`)
* **`YtDlpManager`**:
  * Target path: `~/.local/share/bengal-download-manager/bin/yt-dlp`.
  * Checks system `PATH` and app-data directory.
  * If missing, fetches binary asynchronously from GitHub Releases (`https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp`), sets `chmod +x`, and emits download progress signals.
* **`MediaExtractorWorker(QThread)`**:
  * Executes `yt-dlp -J --flat-playlist --no-warnings <URL>` using `subprocess.Popen`.
  * Emits `single_video_analyzed(data)` or `playlist_analyzed(data)` upon completion.
  * Handles errors and emits `analysis_failed(error_msg)`.

---

## 3. Data Flow

1. **User Interaction**: User clicks "Media Downloader" on toolbar -> `MediaDownloaderDialog` opens.
2. **URL Entry**: User pastes media link and clicks "Analyze Link".
3. **Engine Readiness Check**: `YtDlpManager` ensures `yt-dlp` binary is available (downloads if missing).
4. **Link Parsing**: `MediaExtractorWorker` runs `yt-dlp -J` in background thread.
5. **UI Update**:
   - Single video: UI displays thumbnail, title, quality presets & detailed stream formats.
   - Playlist: UI displays batch list with select checkboxes and global quality picker.
6. **Task Dispatch**: User selects quality and clicks "Download" -> URLs/streams are added to main window queue.

---

## 4. Empirical Verification & Safety

* Unit test suite for `YtDlpManager` binary path detection and JSON extraction parsing.
* Non-blocking UI execution: `yt-dlp` background thread ensures zero UI freeze.
* Theme-adaptive UI using standard Qt system palette tokens.
