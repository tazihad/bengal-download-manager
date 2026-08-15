# How to Export cookies.txt for Bengal Download Manager

This guide explains how to export a Netscape-formatted `cookies.txt` file from your web browser using the open-source **Get cookies.txt LOCALLY** browser extension, and import it into **Bengal Download Manager's Media Downloader**.

---

## 1. Why Are Cookies Needed?

Video streaming platforms like YouTube use bot detection algorithms, login gates, and throttling mechanisms. Providing an authenticated `cookies.txt` file helps:

- **Bypass "Sign in to confirm you're not a bot" errors**: Download age-restricted, subscriber-only, or rate-limited content.
- **Access High Quality Streams**: Unlock premium or restricted stream formats (such as 4K/1080p Premium bitrates).
- **Download Private or Unlisted Playlists**: Access your personal saved playlists and member content.

> **Security Note:**
> Bengal Download Manager processes `cookies.txt` **100% locally** on your machine via `yt-dlp`. Cookies are never transmitted to external servers or third parties. Keep your `cookies.txt` secure and never share it publicly.

---

## 2. Install the "Get cookies.txt LOCALLY" Extension

**Get cookies.txt LOCALLY** is a secure, open-source browser extension that exports cookies in standard Netscape format without sending data to any cloud service.

* **GitHub Repository:** [kairi003/Get-cookies.txt-Locally](https://github.com/kairi003/Get-cookies.txt-Locally)
* **Chrome Web Store:** [Get cookies.txt LOCALLY (Chrome/Chromium/Brave/Edge)](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
* **Firefox Add-ons:** [Get cookies.txt LOCALLY (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)

Install the extension for your preferred browser using the links above.

---

## 3. Export cookies.txt from Your Browser

1. Open your browser and navigate to the target website (e.g., [YouTube](https://www.youtube.com)).
2. Make sure you are logged in to your account.
3. Click the **Extensions** icon (puzzle piece) in your browser toolbar, then click **Get cookies.txt LOCALLY**.
4. In the popup window:
   - Select **Export Current Tab** (or **Export All Cookies**).
   - Click the **Export** button.
5. Save the generated `cookies.txt` (e.g. `youtube.com_cookies.txt`) in a convenient local directory (e.g., `~/Downloads` or `~/.config/bengal-download-manager/`).

---

## 4. Import cookies.txt into Bengal Download Manager

1. Open **Bengal Download Manager**.
2. Launch the **Media Downloader** (`Ctrl+M` or click the **Media Downloader** button on the toolbar).
3. Click the **Gear / Settings** icon (`⚙`) next to the *Analyze Link* button to expand the **Cookies Authentication** panel.
4. Click **Browse...** next to **cookies.txt Path** and select your exported `.txt` file.
5. The path is saved persistently across app restarts.
6. Paste your media or playlist URL and click **Analyze Link** — `yt-dlp` will now authenticate seamlessly using your exported cookies.

---

## 5. Tips & Troubleshooting

- **Expired Sessions:** Cookies naturally expire after days or weeks depending on the service. If you encounter authentication errors, re-export fresh cookies from your browser.
- **Multiple Accounts/Domains:** You can export separate cookie files for different domains (e.g. `youtube.com`, `bilibili.com`, `vimeo.com`) and switch them in the Media Downloader settings as needed.
- **Clear Cookies:** To reset authentication, open the Media Downloader cookies panel and click the **Clear** button.
