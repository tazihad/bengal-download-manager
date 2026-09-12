# Bengal Download Manager — Browser Extension Architecture & Integration Guide

This document provides a comprehensive technical guide to the **Bengal Download Manager Browser Extension** (Google Chrome Manifest V3 & Mozilla Firefox WebExtension MV3), explaining network interception, IPC communication, landing page resolution, cookie forwarding, and extension options.

---

## 1. Architectural Overview

The browser extension integrates Bengal Download Manager seamlessly with modern web browsers, intercepting downloads automatically and forwarding them to the desktop application over a local HTTP REST bridge:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                  BROWSER SANDBOX                                  │
│                                                                                   │
│  ┌───────────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐  │
│  |      Content Script       |  |  Action Popup & UI   |  |   Options Page     |  │
│  │       (content.js)        │  │  (popup.html/js/css) │  │ (options.html/js)  │  │
│  └─────────────┬─────────────┘  └──────────┬───────────┘  └─────────┬──────────┘  │
│                │                           │                        │             │
│                └───────────────────────────┼────────────────────────┘             │
│                                            │                                      │
│                                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                   Service Worker Background Engine (background.js)          │  │
│  │  - chrome.webRequest.onHeadersReceived Listener                             │  │
│  │  - chrome.downloads.onCreated Interceptor                                   │  │
│  │  - Target Resolver (Intermediate Landing Page & Mirror Follower)            │  │
│  │  - Sliding 10-Second Deduplication Map (recentDownloads)                   │  │
│  │  - Cookie Extractor & Total Cookie Protection (dFPI) Formatter              │  │
│  └──────────────────────────────────────┬──────────────────────────────────────┘  │
└─────────────────────────────────────────┼─────────────────────────────────────────┘
                                          │
                                          ▼ Local HTTP REST API
                                 `http://127.0.0.1:56900/`
                                          │
┌─────────────────────────────────────────┼─────────────────────────────────────────┐
│                                         ▼                                         │
│                      BENGAL DOWNLOAD MANAGER APPLICATION                          │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                    IPC Server Thread (src/core/services/ipc_service.py)     │  │
│  │  - OPTIONS Handler: CORS headers (Access-Control-Allow-Origin: *)           │  │
│  │  - GET /: Health verification & Aria2 RPC credentials handshake             │  │
│  │  - POST /: Payload ingestion & SignalEmitter.new_download_signal dispatch   │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Manifest V3 & Cross-Browser Specification

The extension is declared in [`extension/manifest.json`](file:///mnt/data/dev/bengal-download-manager/extension/manifest.json) using standard Manifest V3 specifications:

- **Manifest Version**: `3`
- **Background Context**: Ephemeral Service Worker (`background.js`).
- **Content Scripts**: Injected across `<all_urls>` at `document_start` to detect click interactions and dynamic JavaScript triggers.
- **Declared Permissions**:
  - `downloads`: Monitors, pauses, and cancels native browser downloads.
  - `storage`: Persists configuration settings in `chrome.storage.sync` / `chrome.storage.local`.
  - `contextMenus`: Adds right-click browser menu shortcuts (*Download with Bengal DM*).
  - `webRequest`: Monitors HTTP response headers (`Content-Disposition`, `Content-Type`) in real-time.
  - `cookies`: Extracts session cookies for authenticated requests.
  - `notifications`: Dispatches user notifications when intercepting downloads.
- **Host Permissions**: `<all_urls>`, `http://127.0.0.1/*`, `http://localhost/*`.
- **Firefox Gecko Compatibility**: Declares `browser_specific_settings.gecko.id = "bengal-download-manager@zihad.com.bd"` for Firefox 140.0+ compliance.

---

## 3. Dual Download Interception Engine

To guarantee 100% download interception coverage across direct links, form submissions, and blob transfers, the extension executes two parallel capture strategies:

### Strategy A: Real-Time HTTP Header Inspection (`chrome.webRequest`)
1. **Header Evaluation**: Listens to `chrome.webRequest.onHeadersReceived` for all browser requests.
2. **`Content-Disposition` Matching**: Inspects response headers for `attachment; filename="..."`.
3. **Binary MIME-Type Matching**: Identifies binary content types such as:
   - `application/x-msdownload`, `application/x-msdos-program`
   - `application/zip`, `application/x-7z-compressed`, `application/x-rar-compressed`
   - `application/x-iso9660-image`, `application/octet-stream`
   - `video/mp4`, `video/x-matroska`, `audio/mpeg`, `application/pdf`
4. **Target Extension Filtering**: Checks against a configurable list of file extensions (`.exe`, `.msi`, `.zip`, `.tar.gz`, `.iso`, `.dmg`, `.apk`, `.deb`, `.pdf`, `.mp4`, `.mkv`).
5. **Asset & Telemetry Exclusion**: Excludes static web assets (`.html`, `.js`, `.css`, `.png`, `.jpg`, `.woff2`) and analytics endpoints (`/log/`, `gen_204`, `/collect`).

### Strategy B: Native Download API Interception (`chrome.downloads.onCreated`)
1. **Event Trigger**: When a user clicks a download link or a web application triggers a programmatic download via JavaScript, `chrome.downloads.onCreated` fires.
2. **Instant Pause & Cancel**: If BDM is running and auto-capture is enabled, the extension immediately calls:
   ```javascript
   chrome.downloads.pause(downloadItem.id);
   chrome.downloads.cancel(downloadItem.id);
   ```
3. **Payload Packaging**: Gathers URL, suggested filename, referrer, user agent, and session cookies, then dispatches them to Bengal DM.

---

## 4. Smart Target Resolver & Deduplication Engine

### Target Resolver (`resolveDownloadTarget`)
Many web download buttons point to intermediate HTML landing pages (e.g. SourceForge mirrors, VideoLAN download pages, or Google Drive virus-scan confirmation links) rather than the direct binary payload.

The Target Resolver handles this automatically:
1. **Range Request Probe**: Executes a lightweight `GET` byte-range request (`bytes=0-30720`) with `redirect: 'follow'`.
2. **Meta Refresh Inspection**: Parses HTML headers and `<meta http-equiv="refresh" content="...;url=...">` tags to resolve mirror hops.
3. **Google Drive Confirmation Extraction**: Scrapes the intermediate `uc-download-link` token form and appends required confirmation tokens (`confirm=t&export=download`).

### Deduplication Engine (`isRecentlySent`)
Because both `webRequest` and `downloads.onCreated` can fire for the same user action:
- A 10-second sliding time window is tracked in memory (`recentDownloads` Map).
- Computes canonical download keys combining normalized URL paths and target filenames.
- Subsequent triggers for the same resource within the 10-second window are silently ignored.

---

## 5. Cookie Extraction & Total Cookie Protection (dFPI)

For authenticated downloads (e.g. cloud drives, private intranets, or members-only portals), requests require session credentials.

`getCookiesForUrl(targetUrl, storeId)`:
1. Queries `chrome.cookies.getAll({ url: targetUrl, storeId })`.
2. **Firefox Total Cookie Protection (dFPI) & Partitioned Cookies**: Explicitly queries the host domain (`domain: parsed.hostname`) and parent apex domain (`domain: parentDomain`) to ensure isolated partition cookies are extracted cleanly.
3. Formats cookies into a standard `Cookie: key1=val1; key2=val2` HTTP header string forwarded directly to Bengal DM's Aria2 engine.

---

## 6. IPC Communication Bridge (Port 56900)

The extension communicates with Bengal Download Manager via a local HTTP REST bridge hosted by `src/core/services/ipc_service.py` on port **56900**.

### 1. Health Handshake (`GET /`)
Before attempting download interception, `isBengalDMOnline()` sends an HTTP GET ping:
```http
GET http://127.0.0.1:56900/ HTTP/1.1
Host: 127.0.0.1:56900
```
- **Response 200 OK**:
  ```json
  {
    "status": "Bengal DM is running",
    "version": "0.2.25",
    "aria2": {
      "port": 56800,
      "token": ""
    }
  }
  ```
- **Connection Error / Refused**: BDM is offline; the extension falls back and allows the browser to handle the download natively.

### 2. Download Dispatch (`POST /` or `POST /download`)
When an interception occurs, `sendToBengalDM()` submits a JSON payload:
```http
POST http://127.0.0.1:56900/ HTTP/1.1
Host: 127.0.0.1:56900
Content-Type: application/json

{
  "url": "https://releases.ubuntu.com/24.04/ubuntu-24.04-desktop-amd64.iso",
  "filename": "ubuntu-24.04-desktop-amd64.iso",
  "referrer": "https://ubuntu.com/download/desktop",
  "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...",
  "cookies": "session_id=xyz789; auth=token123"
}
```

---

## 7. Extension UI & Configuration Pages

### Action Popup (`popup.html` / `popup.js`)
- **Connection Status Badge**: Displays live green *Connected* or grey *Offline* indicator.
- **Automatic Interception Toggle**: Instant switch to enable or disable download capture.
- **Open Settings Link**: Shortcut to open Bengal DM options.

### Options Page (`options.html` / `options.js`)
- **Aria2 Daemon Port**: Configure custom RPC port (default: `56800`).
- **File Extension Filter List**: Add or remove file extensions that trigger automatic download capture.
- **Site Exclusions (Bypass List)**: Add domain names or patterns where browser downloads should never be intercepted.
