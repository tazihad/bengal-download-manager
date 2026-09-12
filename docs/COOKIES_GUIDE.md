# How to Export & Use Cookies in Bengal Download Manager

This guide explains how to export a Netscape-formatted `cookies.txt` file or use browser session auto-extraction to authenticate requests in **Bengal Download Manager's Media Downloader**.

---

## 1. Why Are Cookies Needed?

Modern video streaming and file storage services (such as YouTube, Vimeo, Twitch, and cloud storage providers) deploy aggressive bot detection algorithms, login requirements, and bandwidth throttling mechanisms. Providing authenticated session cookies allows BDM to:

- **Bypass "Sign in to confirm you're not a bot" and HTTP 429 Errors**: Download age-restricted, subscriber-only, or rate-limited streams reliably.
- **Unlock High-Quality Bitrates**: Access premium stream tiers (e.g. YouTube 1080p Premium Enhanced Bitrate or 4K/60fps streams).
- **Download Private & Member Playlists**: Access your personal "Watch Later" list, private playlists, or subscription-only channel uploads.

> [!IMPORTANT]
> **Security & Privacy Guarantee**
> Bengal Download Manager processes all cookies **100% locally on your machine**. Cookies are passed strictly to the local `yt-dlp` / Aria2 process and are **never** transmitted to external analytics, telemetries, or third-party servers. Always treat your `cookies.txt` as confidential and never share it publicly.

---

## 2. Option A: Export Netscape cookies.txt (Recommended)

Using the open-source **Get cookies.txt LOCALLY** browser extension is the safest, most reliable method for creating a persistent cookie file.

### Step 1: Install the Extension
Install the extension in your preferred web browser:
- **Firefox Add-ons**: [Get cookies.txt LOCALLY (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
- **Chrome Web Store**: [Get cookies.txt LOCALLY (Chrome/Brave/Edge)](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Source Code**: [GitHub Repository (kairi003/Get-cookies.txt-Locally)](https://github.com/kairi003/Get-cookies.txt-Locally)

### Step 2: Export Cookies from Your Browser
1. Open your browser and navigate to the target website (e.g. `https://www.youtube.com`).
2. Log in to your account.
3. Click the **Extensions icon** (puzzle piece) in your browser toolbar, then select **Get cookies.txt LOCALLY**.
4. In the popup window:
   - Select **Export Current Tab** (or **Export All Cookies**).
   - Click the **Export** button.
5. Save the resulting text file (e.g. `youtube.com_cookies.txt`) in a secure directory on your computer (e.g. `~/.config/bengal-download-manager/cookies/`).

### Step 3: Import into Bengal Download Manager
1. Launch Bengal Download Manager and open the **Media Downloader** (`Ctrl+M` or click the toolbar button).
2. Click the **🍪 Cookies ▾** button to open the authentication panel.
3. Set **Auth Source** to **Netscape cookies.txt File**.
4. Click **Browse...** and select the saved `cookies.txt` file.
5. The path is saved persistently. When you analyze or download links, BDM automatically passes the cookies to `yt-dlp`.

---

## 3. Option B: Native Browser Auto-Extraction

If you prefer not to export files manually, BDM can extract cookies directly from your installed browser profile:

1. In the **Media Downloader**, expand the **🍪 Cookies ▾** panel.
2. Set **Auth Source** to **Auto-Extract from Browser**.
3. In the **Installed Browser** dropdown, choose your browser (**Chrome**, **Firefox**, **Brave**, **Edge**, **Chromium**, **Vivaldi**, **Opera**).
4. `yt-dlp` will automatically read session tokens from your browser's cookie database on your machine.

> [!NOTE]
> On Chromium-based browsers under Linux, close the browser before running auto-extraction if your browser locks its SQLite cookie database while running.

---

## 4. Maintenance & Session Hygiene

- **Session Expiration**: Authentication cookies naturally expire after several weeks or months depending on the website's security policy. If you begin seeing authentication errors, simply re-export a fresh `cookies.txt` file.
- **Multiple Accounts/Domains**: You can maintain separate cookie files for different services (e.g. `youtube_cookies.txt`, `vimeo_cookies.txt`) and switch the active file path as needed.
- **Clearing Cookies**: To return to anonymous public access, open the cookies panel and click the **Clear** button, or switch **Auth Source** to **None (Direct Public Access)**.
