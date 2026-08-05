# Bengal DM Integration Module — Extension Source & Build Guide

This document contains full source build instructions for the **Bengal DM Integration Module** browser extension for Firefox (Gecko) and Chrome (Chromium).

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
├── manifest.json       # Manifest V3 extension configuration
├── background.js       # Service worker / background script (interception & Native RPC listener)
├── content.js          # Content script (web page download link detection & context triggers)
├── popup.html          # Browser action popup UI markup
├── popup.js            # Popup UI logic and connection status monitor
├── popup.css           # Popup styling
├── options.html        # Extension settings page markup
├── options.js          # Extension settings & IPC configuration logic
├── options.css         # Extension settings page styling
├── README.md           # Extension build guide for store reviewers
└── assets/             # Extension icons (16x16, 32x32, 48x48, 128x128)
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

## 5. Technical Details of Build Script (`scripts/pack_extension.py`)

The automated build script `scripts/pack_extension.py` performs the following technical steps:

1. **Target-Specific Manifest Processing**:
   - **Firefox**: Strips Chromium-only `background.service_worker` keys, sets `background.scripts = ["background.js"]` for Gecko compatibility, and verifies `data_collection_permissions = { "required": ["none"] }` under `browser_specific_settings.gecko`.
   - **Chrome**: Preserves `background.service_worker = "background.js"` required for Chrome Manifest V3 service workers.
2. **Compression**: Uses `zipfile` (ZIP_DEFLATED) to compress the extension source files cleanly without metadata clutter or OS garbage files (`.DS_Store`, `__MACOSX`).
3. **CRX3 Signing**: Generates a 2048-bit RSA key via OpenSSL, calculates the extension ID hash, and constructs the CRX3 binary header according to Chromium specifications.

---

## 6. Reviewer Notes for Mozilla AMO Submission

- **Data Collection**: This add-on collects **zero** personal data, browsing history, or telemetry.
- **Local Host Communication**: The extension communicates exclusively with the local Bengal Download Manager application running on the user's local machine via localhost (`http://127.0.0.1:56800` / native messaging).
- **Source Code Verification**: Running `python3 scripts/pack_extension.py` directly compiles and outputs byte-for-byte verifiable `.xpi` archives matching the submitted add-on binary.
