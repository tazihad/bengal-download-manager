# Bengal Download Manager — Browser Extension Architecture & Integration Guide

This document provides a comprehensive technical guide to the **Bengal Download Manager Browser Extension** (Chrome Manifest V3 & Firefox WebExtension MV3), explaining how network interception, IPC communication, landing page resolution, cookie forwarding, and extension options operate.

---

## 1. Architectural Overview

```
+-----------------------------------------------------------------------------------+
|                                  Browser (Chrome / Firefox)                       |
|  +---------------------------+  +----------------------+  +--------------------+  |
|  |     Content Script        |  |  Action Popup & UI   |  |   Options Page     |  |
|  |       (content.js)        |  |  (popup.html/js/css) |  | (options.html/js)  |  |
|  +---------------------------+  +----------------------+  +--------------------+  |
|                                            |                                      |
|                                    [chrome.runtime]                               |
|                                            v                                      |
|  +-----------------------------------------------------------------------------+  |
|  |                   Service Worker Background Engine (background.js)           |  |
|  |  - webRequest Header Listener    - downloads.onCreated Interceptor            |  |
|  |  - Cookie & dFPI Extractor       - Target Resolver & Deduplication Tracker    |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                            |
                            [Local HTTP REST POST - Port 9000]
                                            v
+-----------------------------------------------------------------------------------+
|                        Bengal Download Manager Core Application                   |
|  +-----------------------------------------------------------------------------+  |
|  |                 IPC TCP Listener (src/main.py - Port 9000)                  |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Manifest V3 & Cross-Browser Compatibility

The extension is declared in [`extension/manifest.json`](file:///mnt/data/dev/bengal-download-manager/extension/manifest.json) as a **Manifest V3** extension, fully compliant with Chrome Web Store and Firefox Add-on Store standards.

### Manifest Configuration Summary
* **Manifest Version:** `3`
* **Background Context:** Ephemeral Service Worker (`background.js`).
* **Content Scripts:** Injected into all URLs (`<all_urls>`) at `document_start`.
* **Declared Permissions:**
  - `downloads`: Intercepts and pauses native browser downloads.
  - `storage`: Persists configuration settings in `chrome.storage.sync` / `chrome.storage.local`.
  - `contextMenus`: Adds right-click context menu options.
  - `webRequest`: Monitors HTTP response headers (`Content-Disposition`, `Content-Type`) in real-time.
  - `cookies`: Extracts session cookies for authentication.
  - `notifications`: Optional user notifications.
* **Host Permissions:** `<all_urls>`, `http://127.0.0.1/*`, `http://localhost/*`.
* **Cross-Browser Gecko Settings:** Declares `browser_specific_settings.gecko` ID (`bengal-download-manager@zihad.com.bd`) for Firefox 140.0+ compliance.

---

## 3. How Network Download Interception Works

The extension captures downloads through **two parallel mechanisms** to ensure IDM-style capture coverage:

### A. Real-Time HTTP Response Header Monitoring (`chrome.webRequest`)
1. **Header Inspection:** `background.js` listens to `chrome.webRequest.onHeadersReceived`.
2. **Content-Disposition Detection:** Detects `Content-Disposition: attachment; filename="..."` headers.
3. **MIME-Type & Extension Matching:** Identifies binary Content-Types (`application/x-msdownload`, `application/zip`, `application/x-7z-compressed`, `application/x-iso9660-image`) and target file extensions (`.exe`, `.msi`, `.zip`, `.7z`, `.rar`, `.tar.gz`, `.iso`, `.dmg`, `.apk`, `.deb`, `.pdf`, `.mp4`, `.mkv`, etc.).
4. **Exclusion Filtering:** Ignores static web assets (`.html`, `.js`, `.css`, `.png`, `.jpg`, `.woff2`) and telemetry/analytics endpoints (`/log/`, `gen_204`, `/collect`).

### B. Browser Download API Interception (`chrome.downloads.onCreated`)
1. **Download Triggering:** When a user initiates a download via a click or script, `chrome.downloads.onCreated` fires.
2. **Pause & Cancel:** If auto-capture is enabled and Bengal DM is online, the extension immediately calls `chrome.downloads.pause(downloadItem.id)` and `chrome.downloads.cancel(downloadItem.id)`.
3. **Payload Packaging:** Extracts the original download URL, suggested filename, referrer, user agent, and cookies, then forwards them to Bengal DM.

---

## 4. Target Resolver & Deduplication Tracker

### Target Resolver (`resolveDownloadTarget`)
Many file download buttons link to intermediate HTML landing pages (e.g. VideoLAN mirrors, Google Drive confirmation pages, SourceForge download buttons) rather than direct binary files.

1. **Range Request Check:** Performs a lightweight `GET` byte-range request (`bytes=0-30720`) with `redirect: 'follow'`.
2. **Meta Refresh Parsing:** Inspects HTML headers and `<meta http-equiv="refresh" content="...;url=...">` tags to resolve redirect mirrors.
3. **Google Drive Confirmation Forms:** Automatically extracts Google Drive `uc-download-link` token forms and appended confirmation parameters (`confirm=t&export=download`).

### Deduplication Engine (`isRecentlySent`)
To prevent duplicate download triggers caused by simultaneous `webRequest` and `downloads.onCreated` events:
- Implements a 10-second sliding deduplication window (`recentDownloads` Map).
- Computes canonical download keys combining URL paths and cleaned filenames.
- Ignores requests already transmitted within the 10-second window.

---

## 5. Cookie Extraction & Total Cookie Protection (dFPI)

For authenticated downloads (e.g. private cloud storage, user portals), downloads require session authentication cookies.

`getCookiesForUrl(targetUrl, storeId)`:
1. Queries `chrome.cookies.getAll({ url: targetUrl, storeId })`.
2. **Firefox Total Cookie Protection (dFPI) & Partitioned Cookies:** Queries host domain (`domain: parsed.hostname`) and parent domain (`domain: parentDomain`) to ensure isolated partition cookies are captured.
3. Formats cookies into a standard `Cookie: name1=val1; name2=val2` HTTP header string forwarded directly to Bengal DM's Aria2 engine.

---

## 6. IPC Communication Bridge (Port 9000)

The extension communicates with the desktop application via a local HTTP REST bridge server hosted by `src/main.py` on port **9000**.

### Health Check Ping (`GET /`)
Before attempting download interception, `isBengalDMOnline()` performs an aborted HTTP GET request:
```http
GET http://127.0.0.1:9000/ HTTP/1.1
```
* **Response 200 OK:** Extension intercepts download and passes payload to Bengal DM.
* **Connection Error / Refused:** Extension bypasses capture and lets the browser handle the download natively.

### Download Dispatch Payload (`POST /`)
When a download is captured, `sendToBengalDM()` sends a JSON POST request:
```json
POST http://127.0.0.1:9000/ HTTP/1.1
Content-Type: application/json

{
  "url": "https://downloads.example.com/software-package.zip",
  "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...",
  "cookies": "session_id=abc123xyz; auth=token_value",
  "filename": "software-package.zip",
  "referrer": "https://example.com/download-page"
}
```

---

## 7. Extension Options & Popup UI

- **Action Popup (`popup.html` / `popup.js`):**
  - Displays real-time connection status badge (Connected / Offline).
  - Quick toggle switch for **Automatic Download Capture**.
  - Direct link to open Bengal DM settings.
- **Options Tab Page (`options.html` / `options.js`):**
  - **Local Port Configuration:** Change IPC port (Default: `9000`).
  - **Custom Extension Filters:** Add or remove file extensions triggering auto-capture.
  - **Site Bypass List:** Add domains excluded from auto-capture.
