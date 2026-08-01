# Chrome Web Store Listing & Metadata

> **Extension Name**: Bengal DM Integration Module  
> **Extension ID**: (Assigned upon publishing to Chrome Web Store)  
> **Manifest Version**: 3  
> **Last Updated**: 2026-08-01  

---

## 1. Store Listing Copy

### Detailed Description
Bengal DM Integration Module connects your Chrome browser directly to Bengal Download Manager, providing multi-threaded acceleration, automatic download interception, and seamless management for your downloads.

#### Key Features:
- **Automatic Interception**: Automatically catches browser download requests and routes them to Bengal Download Manager.
- **Context Menu Integration**: Right-click any link, image, video, or audio file and select "Download with Bengal DM".
- **Cookie & Session Preservation**: Transfers session cookies and user-agent strings to ensure authenticated downloads succeed.
- **Customizable Filters**: Skip web pages and common web media assets automatically.
- **Light & Dark Theme Support**: Matches your system theme preferences seamlessly.

---

## 2. Permissions Justification

Every permission declared in `manifest.json` serves a specific purpose:

| Permission | Purpose & Justification |
|------------|-------------------------|
| `downloads` | Required to intercept Chrome browser downloads (`chrome.downloads.onCreated`), cancel native browser downloads, and route them to Bengal Download Manager. |
| `storage` | Required to persist user configuration options such as aria2 RPC port, token, interception toggles, and theme preferences. |
| `contextMenus` | Required to add the "Download with Bengal DM" item to right-click menus on links, media, and text selections. |
| `webRequest` | Used to observe incoming headers for content disposition and download URL detection. |
| `cookies` | Required to read session cookies for download URLs (`chrome.cookies.getAll`), ensuring authenticated downloads work in Bengal DM. |
| `notifications` | Required to display desktop notifications confirming when a download is sent to Bengal Download Manager. |

### Host Permissions

| Host Permission | Purpose |
|-----------------|---------|
| `http://127.0.0.1/*` | Required to communicate with the local Bengal Download Manager HTTP server (port 9000). |
| `http://localhost/*` | Fallback host permission for local Bengal Download Manager communication. |
| `<all_urls>` | Required to extract session cookies and handle download links across web domains. |

---

## 3. Privacy & Data Disclosures

- **Data Collected**: None. No personal data, browsing history, or user credentials are collected or sent to external servers.
- **Data Transmission**: Download URLs and session cookies are transmitted **only** to the local Bengal Download Manager application running on your own computer (`http://127.0.0.1:9000`).
- **Analytics**: Zero third-party tracking or analytics scripts are included.

---

## 4. Version History

### v1.1 (2026-08-01)
- Upgraded extension architecture fully to **Manifest V3**.
- Replaced background page with a non-blocking Manifest V3 Service Worker (`background.js`).
- Implemented `chrome.downloads.onCreated` interceptor for native MV3 download management.
- Added desktop feedback notifications via `chrome.notifications`.
- Updated permissions and host permissions for MV3 web store guidelines.
