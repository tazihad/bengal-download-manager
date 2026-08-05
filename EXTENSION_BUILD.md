# Bengal DM Browser Extension — Build Guide & Source Documentation

> **Extension Name**: Bengal DM Integration Module  
> **Firefox Extension ID**: `bengal-download-manager@zihad.com.bd`  
> **Manifest Version**: 3  

This guide provides instructions to build and package the **Bengal DM Integration Module** browser extension for Firefox (AMO) and Chrome (Web Store) from source.

---

## 1. System Requirements & Dependencies

* **Supported Operating Systems**: Linux (Ubuntu, Fedora, Arch, etc.), macOS, Windows 10/11.
* **Python Environment**: Python 3.8+ (Python 3.10+ recommended).
* **Build System Programs**: Python standard library (`zipfile`, `json`, `hashlib`, `shutil`, `struct`, `subprocess`, `tempfile`).
* **OpenSSL** (Optional, used for CRX3 binary signing for Chromium).
* **Node / npm / External Compilers**: **None required**. The extension is written in standard modern JavaScript (ES6+ / WebExtensions API / Manifest V3).

---

## 2. Installing Required Programs

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install python3 openssl
```

### Fedora
```bash
sudo dnf install python3 openssl
```

### Arch Linux
```bash
sudo pacman -S python openssl
```

### macOS (Homebrew)
```bash
brew install python openssl
```

### Windows
Download and install Python 3 from [python.org/downloads](https://www.python.org/downloads/). Ensure **"Add python.exe to PATH"** is selected during installation.

---

## 3. Step-by-Step Build Instructions

1. **Navigate to Project Directory**:
   ```bash
   cd bengal-download-manager
   ```

2. **Run Extension Packager Script**:
   ```bash
   python3 scripts/pack_extension.py
   ```
   *(Or using virtual environment: `venv/bin/python scripts/pack_extension.py`)*

3. **Output Files Generated in `dist/`**:
   * **`dist/bengal-download-manager-firefox.xpi`**: Firefox Add-on package formatted for Mozilla AMO upload.
   * **`dist/bengal-download-manager-firefox.zip`**: Firefox Manifest V3 source zip.
   * **`dist/bengal-download-manager-chrome.zip`**: Chrome Web Store Manifest V3 ZIP package.
   * **`dist/bengal-download-manager-extension.crx`**: Chromium signed CRX3 package.

---

## 4. Manifest & Compatibility Adjustments

The packaging script (`scripts/pack_extension.py`) automatically adapts `manifest.json` for target browser standards:

- **Firefox (AMO)**:
  - Configures `background.scripts = ["background.js"]` (removing Chrome-specific `service_worker`).
  - Sets `data_collection_permissions = { "required": ["none"] }` under `browser_specific_settings.gecko` per Mozilla AMO guidelines.
- **Chrome (Web Store)**:
  - Configures `background.service_worker = "background.js"` for Chrome Manifest V3 compliance.

---

## 5. Reviewer Notes (addons.mozilla.org)

- **Data Privacy**: No user data, telemetry, or browsing statistics are collected or shared.
- **Local IPC Communication**: The extension communicates exclusively with the local Bengal Download Manager daemon on `http://127.0.0.1:56800` or via native messaging.
- **Source Verification**: Building via `python3 scripts/pack_extension.py` produces an exact byte-for-byte verifiable `.xpi` package matching submitted releases.
