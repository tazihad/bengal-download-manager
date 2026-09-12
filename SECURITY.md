# Security Policy

The Bengal Download Manager (BDM) team takes the security and privacy of our users and their data seriously. This document outlines our vulnerability disclosure process, security architecture considerations, and supported versions.

---

## 1. Supported Versions

Security updates and critical bug fixes are applied to the latest release series:

| Version Series | Supported | Notes |
| :--- | :--- | :--- |
| **0.2.x** (Latest) | ✅ Yes | Active development and security maintenance |
| **0.1.x** | ❌ No | Please upgrade to the latest release |

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability or privacy flaw in Bengal Download Manager, please report it privately rather than opening a public GitHub issue.

### How to Report
- **GitHub Security Advisories**: Submit a private advisory via [GitHub Security Advisories](https://github.com/tazihad/bengal-download-manager/security/advisories/new).
- **Direct Maintainer Contact**: You may reach out directly to the maintainer via GitHub profile contact: [@tazihad](https://github.com/tazihad).

### What to Include in Your Report
Please provide:
1. **Description**: A clear summary of the vulnerability.
2. **Steps to Reproduce**: Detailed steps or a minimal proof of concept (PoC).
3. **Affected Component**: Specify the component (e.g. IPC REST server, Aria2 RPC connector, media extractor, browser extension, or file path resolver).
4. **Impact**: An assessment of what an attacker could achieve (e.g. arbitrary file overwrite, unauthorized local IPC triggers, credential leakage).
5. **Proposed Remediation**: Any recommended patches or mitigations (optional).

### Response Timeline
- **Initial Acknowledgment**: Within 48 hours of receiving your report.
- **Assessment & Triage**: Within 5 business days, confirming whether the report is accepted.
- **Patch & Advisory**: A fix will be developed in a private security fork, verified, and released alongside a public CVE / GitHub Security Advisory crediting the finder.

---

## 3. Security Architecture & Threat Model

Bengal Download Manager is designed with local-first, privacy-respecting security principles:

### A. Inter-Process Communication (IPC)
- The extension REST bridge (`src/core/services/ipc_service.py`) is strictly bound to `127.0.0.1` on port `56900` and does not accept remote network traffic.
- Requests are validated and sanitized before any download task is registered.
- The single-instance guard uses local Unix domain sockets scoped to the active user profile.

### B. Cookie Vault & Credential Hygiene
- Authentication cookies (whether loaded from `cookies.txt` or extracted from browser profiles) are **never transmitted externally**.
- Cookies are consumed strictly by local processes (`yt-dlp` and `aria2c`) to fulfill authenticated requests.
- Cookie paths are stored in local user configuration directories with standard OS file permissions.

### C. Download Path & Directory Traversal Protection
- All filenames received from remote HTTP `Content-Disposition` headers are sanitized through `resolve_filename()` to strip path separators (`/`, `\`), null bytes, and traversal tokens (`../`).
- Files are saved strictly within authorized user destinations or sandbox-confined portal boundaries.

### D. Sandboxed Packaging
- Flatpak packages are strictly isolated using FreeDesktop permissions (`xdg-download`, `ipc`, `network`).
- File picking in Flatpak is mediated through the **XDG Desktop Portal** to ensure explicit user consent when selecting storage locations outside default folders.
