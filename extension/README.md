# Bengal DM Integration Module — Extension Source & Build Guide

This directory contains the source code for the **Bengal DM Integration Module** browser extension for Firefox (Gecko) and Chrome (Chromium).

---

## 1. System & Environment Requirements

* **Operating System**: Linux (Ubuntu, Debian, Fedora, Arch, etc.), macOS, or Windows 10/11.
* **Python Runtime**: Python 3.8 or higher (Python 3.10+ recommended).
* **Optional System Utilities**: `openssl` (only required if generating signed `.crx` binaries for Chromium).
* **External Package Managers / Node / npm**: **None required**. The extension is written in standard vanilla modern JavaScript (ES6+ / WebExtensions API / Manifest V3) and uses Python's built-in standard library (`zipfile`, `json`, `hashlib`, `shutil`, `struct`) for packaging.

---

## 2. Program Installation Instructions

### Linux (Ubuntu / Debian)
```bash
sudo apt update
sudo apt install python3 openssl
```

### Linux (Fedora)
```bash
sudo dnf install python3 openssl
```

### Linux (Arch Linux)
```bash
sudo pacman -S python openssl
```

### macOS (Homebrew)
```bash
brew install python openssl
```

### Windows
1. Download Python 3 from [python.org/downloads](https://www.python.org/downloads/).
2. During installation, check the box **"Add python.exe to PATH"**.

---

## 3. Extension Directory Structure

```
extension/
├── manifest.json             # Manifest V3 extension configuration (defaults to Chrome)
├── manifest.chrome.json      # Chromium-specific manifest target
├── manifest.firefox.json     # Firefox Gecko-specific manifest target
├── switch-manifest.sh        # Target switching helper script
├── README.md                 # This build guide for store reviewers and developers
├── assets/                   # Extension icons (16x16, 32x32, 48x48, 128x128)
├── src/
│   ├── background/
│   │   └── background.js     # Background service worker / script (interception & RPC listener)
│   ├── content/
│   │   ├── content.js        # Content script (download detection, floating video widget)
│   │   ├── inject.js         # MAIN-world media bridge
│   │   └── direct-inject.js  # MAIN-world bridge exposing muxed YouTube stream URLs
│   ├── popup/
│   │   ├── popup.html        # Browser action popup UI markup
│   │   ├── popup.js          # Popup UI logic and connection status monitor
│   │   └── popup.css         # Popup styling
│   ├── options/
│   │   ├── options.html      # Extension settings page markup
│   │   ├── options.js        # Extension settings & IPC configuration logic
│   │   └── options.css       # Extension settings page styling
│   └── youtube/
│       ├── youtube-media.js  # YouTube media response parsing and format definitions
│       ├── youtube-direct.js # YouTube stream observation & SABR session capture
│       ├── youtube-page.js   # MAIN-world player response hook
│       └── youtube-relay.js  # Content-script relay bridging player responses to background
└── tests/
    ├── youtube-media.test.cjs   # Media format parsing & selection test suite
    └── youtube-direct.test.cjs  # WebRequest observation & SABR capture test suite
```

---

## 4. Step-by-Step Build Instructions

To build an exact copy of the Firefox Add-on (`.xpi` / `.zip`) and Chrome packages from source:

1. **Clone the Repository** (or extract the source code archive):
   ```bash
   git clone https://github.com/tazihad/bengal-download-manager.git
   cd bengal-download-manager
   ```

2. **Execute the Build Script**:
   Run the project's automated extension packing script:
   ```bash
   python3 scripts/pack_extension.py
   ```
   *(Alternatively, if using virtual environment: `venv/bin/python scripts/pack_extension.py`)*

3. **Verify Build Output**:
   The script builds target-tailored packages in the `dist/` directory:
   * **`dist/bengal-download-manager-firefox.xpi`**: Firefox Add-on package ready for upload to Mozilla AMO.
   * **`dist/bengal-download-manager-firefox.zip`**: Firefox Manifest V3 source archive.
   * **`dist/bengal-download-manager-chrome.zip`**: Chrome Web Store Manifest V3 ZIP package.
   * **`dist/bengal-download-manager-extension.crx`**: Chromium signed CRX3 package.

---

## 5. Standard vs Direct Download Method

The popup exposes a **Download method** choice; **Standard** stays the default.

* **Standard** sends the media page URL to the desktop app and lets yt-dlp plus FFmpeg extract
  and mux the best available streams. It works on virtually every site and supports high
  resolutions, but it needs to probe, download separate tracks, and merge them.
* **Direct** prefers an already-muxed progressive stream URL that the page is currently playing
  and downloads it as-is through the Aria2 engine. There is no extraction or FFmpeg step, so the
  download starts immediately and the file already contains audio. Direct also handles plain
  `.mp4`/`.webm` sniffed streams on regular sites.
* **Direct with resolution selection** lists every progressive (already-muxed) stream the page
  exposes, so you can pick a specific quality or audio-only where available. Each progressive tier
  is downloaded as-is through the Aria2 engine.
* **Adaptive YouTube tiers** (separate video and audio tracks, including SABR-only streams) cannot
  be fetched as one file. When one is chosen from the video chooser, the desktop keeps that exact
  quality, transfers both tracks through Aria2, and muxes them with FFmpeg, so the saved file always
  contains audio. A video-only file is treated as a failure instead of a finished download.

Direct never handles `.m3u8`/`.mpd` playlists or DASH/HLS segments as-is, and the in-page widget
shows "Direct unavailable on this video. Switch to Standard." when the page exposes no progressive
tier rather than silently running the Standard pipeline. Signed stream URLs also expire (typically
within hours), so a paused Direct download may need to be re-added from the browser. If the Aria2
engine cannot be started, Direct cancels with a status-bar notice instead of falling back to the
Python downloader.

---


## 6. Technical Details of Build Script (`scripts/pack_extension.py`)

The automated build script `scripts/pack_extension.py` performs the following technical steps:

1. **Target-Specific Manifest Processing**:
   - **Firefox**: Strips Chromium-only `background.service_worker` keys, sets `background.scripts = ["background.js"]` for Gecko compatibility, and verifies `data_collection_permissions = { "required": ["none"] }` under `browser_specific_settings.gecko`.
   - **Chrome**: Preserves `background.service_worker = "background.js"` required for Chrome Manifest V3 service workers.
2. **Compression**: Uses `zipfile` (ZIP_DEFLATED) to compress the extension source files cleanly without metadata clutter or OS garbage files (`.DS_Store`, `__MACOSX`).
3. **CRX3 Signing**: Generates a 2048-bit RSA key via OpenSSL, calculates the extension ID hash, and constructs the CRX3 binary header according to Chromium specifications.

---

## 7. Reviewer Notes for Mozilla AMO Submission

- **Data Collection**: This add-on collects **zero** personal data, browsing history, or telemetry.
- **Local Host Communication**: The extension communicates exclusively with the local Bengal Download Manager application running on the user's local machine via localhost (`http://127.0.0.1:56800` / native messaging).
- **Source Code Verification**: Running `python3 scripts/pack_extension.py` directly compiles and outputs byte-for-byte verifiable `.xpi` archives matching the submitted add-on binary.
