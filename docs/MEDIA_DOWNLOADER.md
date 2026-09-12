# Bengal Download Manager — Media Downloader Engine Deep-Dive

The **Media Downloader** in Bengal Download Manager is an integrated multimedia acquisition and post-processing subsystem. It enables high-speed extraction, stream muxing, and batch downloading of high-definition video, audio streams, and playlists from YouTube and hundreds of media platforms.

---

## 1. System Architecture & Toolchain

The Media Downloader is built upon an orchestration layer combining five key open-source media engines:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 MediaDownloaderDialog                                   │
│  - Independent top-level taskbar window (Qt.WindowType.Window | parent=None)            │
│  - Video Hero Card (thumbnail preview, duration, channel metadata)                      │
│  - Quality Presets & Codec Filters (FPS, H.264, VP9, AV1, AAC, Opus, MP3)               │
│  - Cookies Authentication Vault (Netscape cookies.txt & Browser Profile Extractor)      │
│  - Playlist Batch Table with Multi-Select Checkboxes                                    │
└────────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                MediaExtractorWorker (QThread)                           │
│  - Non-blocking execution of yt-dlp metadata analysis                                   │
│  - JSON parsing: formats, bitrates, audio channels, storyboard thumbnails               │
│  - Flat playlist parsing without downloading payload bodies                             │
└────────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
┌──────────────────────────────────────────────┐ ┌──────────────────────────────────────┐
│          Dependency Engines & Binaries       │ │         Authentication Subsystem     │
│  1. yt-dlp: Stream extractor & format engine │ │  1. Netscape cookies.txt parser      │
│  2. ffmpeg: Multi-stream audio/video muxer   │ │  2. Native browser session extractor │
│  3. ffprobe: Media stream container analyzer │ │  3. 100% local encrypted execution   │
│  4. deno: Modern JavaScript decipher runtime │ └──────────────────────────────────────┘
│  5. AtomicParsley: MP4/M4A metadata tagger   │
└──────────────────────────────────────────────┘
```

---

## 2. Dynamic Dependency Management (`YtDlpManager`)

Unlike traditional download managers that fail when external command-line utilities are missing, BDM features an autonomous **Dependency Management Engine** (`DependencyManagerWorker`):

1. **System & Local Path Resolution**:
   - Searches system `PATH` (`/usr/bin`, `/usr/local/bin`).
   - Searches local user storage: `~/.local/share/bengal-download-manager/bin/`.
2. **Automated Acquisition from GitHub**:
   - If any required utility (`yt-dlp`, `ffmpeg`, `ffprobe`, `deno`, `AtomicParsley`) is missing or outdated, clicking **Update** downloads the latest standalone statically-compiled binary directly from official GitHub releases.
   - Real-time download progress is rendered in the dialog status bar.
   - Automatically sets executable permissions (`chmod +x`) upon extraction.
3. **Engine Status Indicators**:
   - The top status panel displays real-time status chips for each of the 5 utilities.
   - Clicking the `ⓘ` button reveals the active binary location, version string, and architecture (`x86_64` / `aarch64`).

---

## 3. Metadata Extraction & Format Evaluation

When a user pastes a URL and clicks **Analyze**, `MediaExtractorWorker` executes:

```bash
yt-dlp -J --flat-playlist --no-warnings --no-call-home <URL>
```

### Format Sorting & Stream Pairing Algorithm
Video platforms (such as YouTube) serve 1080p, 1440p, 4K, and 8K videos as separate, un-muxed streams: one high-resolution video-only stream (DASH/HLS) and one high-bitrate audio-only stream.

BDM automatically pairs and calculates the best combination:
1. Identifies the video stream matching the user's selected preset (e.g. `1080p Full HD`).
2. Evaluates selected codec filters:
   - Video: `H.264 / AVC` (maximum compatibility), `VP9` (efficient bandwidth), or `AV1` (next-gen efficiency).
   - Audio: `AAC / M4A`, `Opus` (high fidelity), or `MP3`.
3. Identifies the highest-bitrate matching audio stream.
4. Generates an Aria2/ffmpeg pipeline instruction combining both streams into a single container (`.mp4` or `.mkv`).

---

## 4. Single Video vs. Playlist Batch Processing

### Single Video Mode
- Renders the video title, uploader channel, total duration, and smooth-rounded thumbnail preview.
- **Preset Selector**:
  - *Best Quality (Video + Audio merged)*
  - *4K Ultra HD (2160p)*
  - *2K Quad HD (1440p)*
  - *1080p Full HD*
  - *720p HD*
  - *480p SD*
  - *360p Low Quality*
  - *Audio Only (Opus / MP3 / M4A)*
- **Manual Stream Inspection**: Unchecking presets reveals the granular format table displaying Format ID, Container Extension, Resolution, Codecs, Bitrate, and Estimated Size.

### Playlist & Channel Mode
- Analyzing a playlist or channel URL dynamically switches the UI to the **Playlist View**.
- Populates an interactive batch table with individual video checkboxes.
- **Select All** & **Deselect All** buttons with live item counters.
- Applies the selected quality preset uniformly across all checked items.
- Dispatches all selected videos sequentially or concurrently into Bengal DM's core download queues.

---

## 5. Authentication & Cookie Vault

To download age-restricted, subscriber-only, private, or rate-limited content:

1. Click the **🍪 Cookies ▾** button to open the authentication drawer.
2. Select your authentication strategy:
   - **Netscape cookies.txt**: Browse to your exported cookies file (see [COOKIES_GUIDE.md](COOKIES_GUIDE.md)).
   - **Auto-Extract from Browser**: Select your active web browser (**Chrome**, **Firefox**, **Brave**, **Edge**, **Chromium**, **Vivaldi**, **Opera**). BDM invokes `yt-dlp --cookies-from-browser <browser>` to read credentials directly from your browser profile.
   - **None**: Public anonymous access.
3. Path configurations and preferred browser choices are persistently saved in `categories.json` under `media_downloader_defaults`.

---

## 6. Windowing & Desktop Integration

The `MediaDownloaderDialog` is constructed with:
```python
self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
```
- Operates as an **independent top-level window** (`parent=None`), giving it a dedicated taskbar panel icon in KDE Plasma, GNOME Dash, and XFCE window managers.
- Inherits the application-wide `WM_CLASS` (`bengal-download-manager`), allowing window managers and Wayland compositors to group it cleanly under the parent desktop application entry.
- Fully adheres to system light/dark themes, adaptive stroke icons, and OpenType tabular figures.
