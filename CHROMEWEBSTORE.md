# Chrome Web Store Listing & Metadata

> **Extension Name**: Bengal DM Connector  
> **Extension ID**: (Assigned upon publishing to Chrome Web Store)  
> **Manifest Version**: 3  
> **Last Updated**: 2026-11-12  
> 
> ---

## 1. Store Listing Copy

### Detailed Description
Bengal DM Connector integrates your Chrome browser directly with Bengal Download Manager, providing multi-threaded acceleration, automatic download interception, and seamless management for your downloads.

#### Key Features:
- **Automatic Interception**: Automatically catches browser download requests and routes them to Bengal Download Manager.
- **Context Menu Integration**: Right-click any link, image, video, or audio file and select "Download with Bengal DM".
- **Cookie & Session Preservation**: Transfers session cookies and user-agent strings to ensure authenticated downloads succeed.
- **Customizable Filters**: Skip web pages and common web media assets automatically.
- **Light & Dark Theme Support**: Matches your system theme preferences seamlessly.
- **Cross-Platform Compatibility**: Works with Facebook, YouTube, and other major video platforms.

---

## 2. Permissions Justification

Every permission declared in `manifest.json` serves a specific purpose:

| Permission | Purpose & Justification |
|------------|-------------------------|
| `downloads` | Required to intercept Chrome browser downloads (`chrome.downloads.onCreated`), cancel native browser downloads, and route them to Bengal Download Manager. |
| `downloads.ui` | Required to access the downloads UI for managing and monitoring active downloads. |
| `storage` | Required to persist user configuration options such as aria2 RPC port, token, interception toggles, and theme preferences. |
| `contextMenus` | Required to add the "Download with Bengal DM" item to right-click menus on links, media, and text selections. |
| `webRequest` | Used to observe incoming headers for content disposition and download URL detection. |
| `cookies` | Required to read session cookies for download URLs (`chrome.cookies.getAll`), ensuring authenticated downloads work in Bengal DM. |
| `tabs` | Required to access tab information for URL manipulation and download triggering. |
| `alarms` | Required to schedule periodic checks for download status and updates. |

### Host Permissions

| Host Permission | Purpose |
|-----------------|---------|
| `http://127.0.0.1/*` | Required to communicate with the local Bengal Download Manager HTTP server (port 56900). |
| `http://localhost/*` | Fallback host permission for local Bengal Download Manager communication. |
| `http://*/*` | Required to extract session cookies and handle download links across web domains. |
| `https://*/*` | Required to extract session cookies and handle secure download links across web domains. |

---

## 3. Privacy & Data Disclosures

- **Data Collected**: None. No personal data, browsing history, or user credentials are collected or sent to external servers.
- **Data Transmission**: Download URLs and session cookies are transmitted **only** to the local Bengal Download Manager application running on your own computer (`http://127.0.0.1:56900`).
- **Analytics**: Zero third-party tracking or analytics scripts are included.

---

## 4. Version History

### v2.0 (2026-11-12)
- Updated extension name from "Bengal DM Integration Module" to "Bengal DM Connector"
- Updated manifest version from 0.13 to 0.13 (current stable release)
- Refreshed description and key features to match current extension capabilities
- Updated host permissions to include `https://*/*` for secure communication
- Revised web accessible resources to include only `assets/*` (no script files)
- Updated content scripts to focus on Facebook and generic URL matches (YouTube support removed from Chrome build)
- Updated permissions table to include `downloads.ui` and `tabs`
- Added version history entry with release date
- Updated last updated date to 2026-11-12

---