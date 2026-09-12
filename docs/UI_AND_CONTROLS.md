# Bengal Download Manager — User Interface & Controls Reference

This document provides an exhaustive, button-by-button, menu-by-menu, and dialog-by-dialog technical reference for all interactive controls in **Bengal Download Manager (BDM)**.

---

## Table of Contents
1. [Main Application Window](#1-main-application-window)
   - [Menu Bar Actions](#menu-bar-actions)
   - [Toolbar Buttons](#toolbar-buttons)
   - [Category & Queue Sidebar Tree](#category--queue-sidebar-tree)
   - [Downloads Table View](#downloads-table-view)
   - [Table Row Context Menu](#table-row-context-menu)
   - [Table Header Context Menu](#table-header-context-menu)
   - [Bottom Status Bar](#bottom-status-bar)
   - [System Tray Icon & Menu](#system-tray-icon--menu)
2. [Add URL Dialog](#2-add-url-dialog)
3. [Download File Info Dialog](#3-download-file-info-dialog)
4. [Download Progress Dialog](#4-download-progress-dialog)
5. [Download Complete Dialog](#5-download-complete-dialog)
6. [Options & Preferences Dialog](#6-options--preferences-dialog)
7. [Media Downloader Dialog](#7-media-downloader-dialog)
8. [Scheduler & Queues Dialog](#8-scheduler--queues-dialog)
9. [Properties Dialog](#9-properties-dialog)
10. [Duplicate Download Dialog](#10-duplicate-download-dialog)
11. [Refresh Download Address Dialog](#11-refresh-download-address-dialog)
12. [Rename Dialog](#12-rename-dialog)
13. [Column Configuration Dialog](#13-column-configuration-dialog)
14. [Delete Confirmation Dialog](#14-delete-confirmation-dialog)
15. [KDE Kirigami QML Interface Controls](#15-kde-kirigami-qml-interface-controls)

---

## 1. Main Application Window

The main window provides the primary command center for monitoring, initiating, organizing, and controlling downloads.

### Menu Bar Actions

#### `&Tasks` Menu
- **Add URL (`Ctrl+N`)**: Opens the [Add URL Dialog](#2-add-url-dialog) with an empty or clipboard-populated address bar.
- **Paste URL (`Ctrl+V`)**: Directly opens the [Add URL Dialog](#2-add-url-dialog) with the clipboard text automatically pasted into the input field.
- **Exit**: Gracefully pauses active downloads, flushes database caches, terminates child worker threads and Aria2 daemons, and exits the application.

#### `&File` Menu
- **Stop/Pause**: Pauses the currently selected download task(s).
- **Delete (`Delete`)**: Prompts to delete the selected download item(s) from the list, with an optional disk file removal checkbox.
- **Download Now**: Starts downloading the selected paused, stopped, or queued download immediately.
- **Redownload**: Clears existing downloaded chunks and restarts the selected file transfer from byte 0.
- **Open Downloads Folder**: Launches the desktop's default file manager (Dolphin, Nautilus, Thunar) opened directly to the user's primary download folder (`~/Downloads`).

#### `&Downloads` Menu
- **Resume**: Resumes downloading the selected paused or stopped items.
- **Stop**: Pauses the selected active download(s).
- **Stop All**: Pauses all currently active downloads across all queues simultaneously.
- **Delete**: Removes selected item(s) from the download list.
- **Clear Completed**: Removes all finished/completed downloads from the list view (leaves files safely on disk).
- **Options**: Opens the [Options & Preferences Dialog](#6-options--preferences-dialog).
- **Media Downloader**: Opens the standalone [Media Downloader Dialog](#7-media-downloader-dialog).

#### `&View` Menu
- **Table style**:
  - **Classic** *(radio button)*: Dense table layout matching classic download managers.
  - **Modern** *(radio button)*: Elevated row height, rounded selection indicators, and modern visual spacing.
- **Sort by**:
  - **File Name**: Sorts rows alphabetically by target filename.
  - **Size**: Sorts rows numerically by total file size.
  - **Status**: Sorts rows by status string / completion percentage.
  - **Time Left**: Sorts rows by estimated remaining transfer duration.
  - **Transfer Rate**: Sorts rows by current download speed.
  - **Last Try**: Sorts rows by timestamp of the most recent connection attempt.
  - **Date Added**: Sorts rows chronologically by the timestamp when the task was created.
- **Hide categories** *(checkable)*: Toggles the visibility of the left-hand Category/Queue sidebar to maximize horizontal table space.
- **Toolbar** *(checkable)*: Toggles the top action toolbar visible or hidden.
- **Status Bar** *(checkable)*: Toggles the bottom status bar visible or hidden.

#### `&Help` Menu
- **BDM Homepage**: Opens the official Bengal Download Manager GitHub repository in your default web browser.
- **File bug report**: Opens the GitHub issues submission page in your default browser.
- **About Bengal DM**: Displays the application information modal showing the current version number, author credits, license details, and system environment info.

---

### Toolbar Buttons

The top toolbar displays high-contrast vector icons with hover glow effects and descriptive labels underneath:

| Button | Label | Shortcut | Tooltip | What It Does |
| :--- | :--- | :--- | :--- | :--- |
| ![Add URL](assets/icons/add_url.png) | **Add URL** | `Ctrl+N` | *Add a new download URL address (Ctrl+N)* | Displays the address entry dialog to begin a new download. |
| ![Resume](assets/icons/resume.png) | **Resume** | — | *Resume downloading selected file(s)* | Resumes network transfer for all highlighted paused or queued items. |
| ![Stop](assets/icons/stop.png) | **Stop/Pause** | — | *Pause or stop selected download(s)* | Halts active TCP socket transfer for highlighted downloading items. |
| ![Stop All](assets/icons/stop_all.png) | **Stop All** | — | *Pause or stop all currently active downloads* | Instantly stops all running download workers across all queues. |
| ![Delete](assets/icons/delete.png) | **Delete** | `Delete` | *Delete selected download(s) from the list (Delete key)* | Opens the deletion confirmation dialog for highlighted rows. |
| ![Clear Completed](assets/icons/clear_completed.png) | **Clear Completed** | — | *Remove completed downloads from the list* | Purges all finished rows from the UI table. Files on disk are kept. |
| ![Scheduler](assets/icons/scheduler.png) | **Scheduler** | — | *Manage download queues and scheduling* | Opens the queue scheduler window to define execution times and batch queues. |
| ![Options](assets/icons/options.png) | **Options** | — | *Configure download manager options, connection limits, and engine settings* | Launches the central settings window. |
| ![Media Downloader](assets/icons/media_downloader.png) | **Media Downloader** | `Ctrl+M` | *Parse and download video or audio streams and playlists from media sites* | Opens the standalone yt-dlp media downloader window. |

---

### Category & Queue Sidebar Tree

The left-side tree view allows quick filtering and queue control:

- **All Downloads**: Clears all category filters and displays the complete list of downloads.
- **Statuses**:
  - **Complete**: Filters the table to show only 100% finished downloads.
  - **Unfinished**: Filters the table to show only active, paused, queued, or errored tasks.
- **Categories**:
  - **General**: Files not categorized elsewhere.
  - **Compressed**: Archive formats (`.zip`, `.tar.gz`, `.7z`, `.rar`, etc.).
  - **Documents**: Document files (`.pdf`, `.docx`, `.odt`, `.txt`, etc.).
  - **Music**: Audio tracks and albums (`.mp3`, `.flac`, `.wav`, etc.).
  - **Programs**: Executables and installers (`.deb`, `.rpm`, `.AppImage`, `.exe`, etc.).
  - **Video**: Movie and video clips (`.mp4`, `.mkv`, `.webm`, etc.).
  - **Disk Images**: OS images and disc media (`.iso`, `.img`).
  - **Images**: Raster and vector pictures (`.png`, `.jpg`, `.svg`, etc.).
- **Queues**:
  - **Main download queue**: The primary built-in queue for scheduled sequential downloads.
  - **Synchronization queue**: The built-in recurring periodic queue.
  - **Custom Queues**: User-created download batches.

#### Sidebar Queue Right-Click Context Menu
Right-clicking any queue node in the sidebar opens:
- **Start now**: Immediately initiates processing for all pending items in this queue.
- **Stop**: Pauses all active downloads belonging to this queue.
- **Edit queue**: Opens the [Scheduler Dialog](#8-scheduler--queues-dialog) focused on this queue's *Files in the queue* tab.
- **Schedule**: Opens the [Scheduler Dialog](#8-scheduler--queues-dialog) focused on this queue's *Schedule* settings.
- **Delete**: Deletes the custom queue (disabled for built-in default queues).
- **Create new queue**: Prompts for a queue name and registers a new queue in the system.

---

### Downloads Table View

The central panel renders all download tasks with sortable headers:

1. **File Name** (Column 0): Shows the target filename with a file-type specific icon.
2. **Size** (Column 1): Formatted file size (e.g. `124.50 MB`, `1.85 GB`). Uses tabular numbers (`tnum`).
3. **Status** (Column 2): Displays the visual progress bar, percentage completion (`45.20%`), or textual state (`Complete`, `Paused`, `Queued`, `Error`).
4. **Time Left** (Column 3): Estimated remaining transfer time based on rolling throughput (e.g. `02m 14s`).
5. **Transfer Rate** (Column 4): Real-time network throughput (e.g. `14.20 MB/s`).
6. **Last Try** (Column 5): Relative timestamp of the last connection attempt (e.g. `Just now`, `5 mins ago`, or formatted date).
7. **Date Added** (Column 6): Timestamp when the download task was created.

#### Row Interaction & Shortcuts
- **Single Click**: Highlights the target download row.
- **Ctrl + Click**: Multi-selects non-adjacent rows.
- **Shift + Click**: Selects a contiguous range of rows.
- **Click & Drag (Rubber Band)**: Draws a rectangular selection box across multiple rows.
- **Double-Click**:
  - *If active/downloading*: Opens the [Download Progress Dialog](#4-download-progress-dialog).
  - *If completed*: Launches the downloaded file in the system default viewer/player.
  - *If paused/stopped*: Resumes downloading immediately.
- **`Delete` Key**: Prompts to remove selected item(s).
- **`Spacebar`**: Toggles pause/resume on selected item(s).

---

### Table Row Context Menu

Right-clicking any row in the download table opens the context menu:

- **Open**: Opens the completed file using the operating system default application.
- **Open with...**: Displays the system application chooser dialog to select a specific program.
- **Open folder**: Opens the containing folder in the desktop file manager and highlights the file.
- **Move...**: Displays a folder browser to move the downloaded file to another location on disk and updates the database record.
- **Rename...**: Opens the [Rename Dialog](#12-rename-dialog) to change the target filename.
- **Stop/Pause Download**: Stops active network transfer for this task.
- **Resume download**: Starts or resumes network transfer.
- **Show progress window**: Restores the floating [Download Progress Dialog](#4-download-progress-dialog) to the foreground.
- **Redownload**: Re-initiates download from byte 0, discarding partial bytes.
- **Refresh download address**: Opens the [Refresh Address Dialog](#11-refresh-download-address-dialog) to replace an expired URL.
- **Delete**: Opens the [Delete Confirmation Dialog](#14-delete-confirmation-dialog).
- **Move to queue** *(submenu)*:
  - Lists all existing queues with checkmarks next to the current queue. Selecting a queue moves the item.
  - **Create new queue...**: Prompts to create a new queue and immediately transfers this item into it.
- **Delete from queue**: Removes the download from its assigned queue without deleting it from the main download list.
- **Properties**: Opens the [Properties Dialog](#9-properties-dialog) showing headers, size, URL, and metadata.

---

### Table Header Context Menu

Right-clicking anywhere on the table header row opens:
- Checkbox toggle for each column: **File Name**, **Size**, **Status**, **Time Left**, **Transfer Rate**, **Last Try**, **Date Added**. Unchecking hides that column from view.
- **Columns...**: Opens the [Column Configuration Dialog](#13-column-configuration-dialog) to reorder columns and configure pixel widths.

---

### Bottom Status Bar

Located at the bottom of the main window:
- **Left Panel (Items Counter)**: Displays selection metrics (e.g. `Selected: 3 of 12 items — Total size: 450.20 MB`).
- **Speed Indicator**: Live aggregate transfer throughput across all active connections (e.g. `Speed: 18.50 MB/s`).
- **Aria2 Engine Indicator**:
  - `● Aria2: Connected` *(Green)*: Displays active RPC port and process PID in tooltip.
  - `● Aria2: Stopped` *(Red)*: Indicates fallback Python engine is active.
- **Memory Monitor**: Real-time Resident Set Size (RSS) memory consumption of the application process (e.g. `Memory: 42.15 MB`).

---

### System Tray Icon & Menu

When minimized or running in the background, BDM resides in the desktop system tray:
- **Left-Click / Double-Click**: Toggles main window visibility (Hide to tray / Restore to foreground).
- **Hover Tooltip**: Displays aggregate throughput and active download count (e.g. `Bengal Download Manager\n12.4 MB/s — 3 active downloads`).
- **Right-Click Tray Menu**:
  - **Show / Hide**: Toggles window state.
  - **Add URL**: Opens Add URL dialog directly.
  - **Media Downloader**: Opens Media Downloader window.
  - **Options**: Opens settings window.
  - **Exit**: Terminates the application.

---

## 2. Add URL Dialog

Launched via **Tasks → Add URL**, **Toolbar → Add URL**, or pressing `Ctrl+N`.

### Controls and Buttons
- **Address input field**: Enter the target download URL (`http://`, `https://`, `ftp://`, or `magnet:`). Automatically populated from the system clipboard if a valid URL is detected upon opening.
- **Paste button**: Pastes the current clipboard text into the address field and repositions the cursor at the beginning.
- **Download Media button**: Appears automatically when the entered link is recognized as a streaming video/audio URL (e.g. YouTube, Vimeo, Twitch). Clicking opens the link directly in the [Media Downloader Dialog](#7-media-downloader-dialog).
- **Media URL detected status label**: Green notification text indicating the link has been detected as a streamable media URL.
- **OK button**: Validates the URL, triggers `FetcherWorker` to inspect remote headers and determine file attributes, and opens the [Download File Info Dialog](#3-download-file-info-dialog).
- **Cancel button**: Closes the dialog without taking action.

---

## 3. Download File Info Dialog

Presented when an incoming download link is captured or added manually.

### Controls and Buttons
- **URL field** *(read-only)*: Displays the source URL address.
- **Category dropdown**: Selects the target category (**General**, **Compressed**, **Documents**, **Music**, **Programs**, **Video**). Automatically pre-selected based on file extension matching. Changing the category automatically updates the destination folder.
- **Save As input field**: Displays the target directory path and filename. Allows direct editing of the target filename.
- **Browse button (`...`)**: Opens the system folder picker (or XDG Desktop Portal picker) to choose an alternative save location.
- **File Size & Type label**: Displays the detected remote content length and MIME file type (e.g. `128.45 MB, File type: Compressed Archive (ZIP)`).
- **Don't show this dialog again checkbox**: When checked, future downloads bypass this confirmation dialog and start automatically (can be re-enabled in Options → Downloads).
- **Start Download button** *(Default)*: Enqueues the file and immediately begins multi-segment downloading.
- **Download Later button**: Adds the file to the download list in a **Queued** / **Paused** state without initiating network transfer.
- **Cancel button**: Discards the download request and closes the window.

---

## 4. Download Progress Dialog

Provides real-time visualization of network transfer, speed limits, and multi-threaded connection segments.

### Status Tab
- **URL label**: Elided display of the active download URL with mouse selection and full tooltip.
- **Status**: Live transfer state (e.g. `Connecting...`, `Downloading`, `Paused`, `Merging segments...`).
- **File size**: Total remote content length formatted with tabular numbers.
- **Downloaded**: Exact count of transferred bytes so far.
- **Transfer rate**: Instantaneous throughput (e.g. `12.80 MB/s`).
- **Time left**: Dynamic rolling estimate of remaining duration.
- **Resume capability**: Reports `Yes` or `No` indicating whether the remote server supports HTTP range resumption.

### Speed Limiter Tab
- **Use Speed Limiter checkbox**: Enables active bandwidth throttling for this download.
- **Max speed spinbox**: Numerical input to set the speed ceiling in **KB/sec** (from 1 to 100,000 KB/s). Changing the value applies the restriction immediately.

### Action Buttons & Expander
- **Progress Bar**: Styled bar reflecting overall completion percentage.
- **Details >> button** *(Checkable toggle)*: Expands the dialog downward to reveal the multi-connection segment breakdown.
- **Hide button**: Hides the floating progress dialog while letting the download continue silently in the background. (Double-clicking the table row brings it back).
- **Pause / Resume button**: Toggles the active worker between paused and downloading states.
- **Cancel / Close button**: Cancels an active download or closes the dialog once finished.

### Segment Details Frame (Revealed via `Details >>`)
- **Segment Chunks Bar**: Visual bar partitioned into distinct slices representing each parallel split connection.
- **Connection Segments Table**:
  - **N.** (Column 0): Connection thread index (`1`, `2`, `3`...).
  - **Downloaded** (Column 1): Bytes retrieved by this individual connection thread.
  - **Rate** (Column 2): Current throughput of this specific connection.
  - **Status** (Column 3): Segment lifecycle state (`Connecting`, `Receiving data...`, `Complete`).

---

## 5. Download Complete Dialog

Appears when a download reaches 100% completion (unless disabled or running in silent mode).

### Controls and Buttons
- **Address field**: Source URL of the downloaded file.
- **The file saved as field**: Absolute filesystem path where the finished file is stored.
- **Size label**: Final verified file size on disk.
- **Don't show this dialog again checkbox**: Suppresses this popup window for future completions.
- **Open button**: Launches the file using the desktop's default associated application.
- **Open with... button**: Opens the system application selector to choose a program.
- **Open Folder button**: Opens the directory containing the file in the system file manager and selects it.
- **Close button**: Closes the dialog.

---

## 6. Options & Preferences Dialog

Configures global application behavior through a structured, two-row tab bar.

### Row 1: Advanced Engine & Integration Tabs

#### `Proxy / Socks` Tab
- **No proxy / Get from system** *(radio)*: Uses direct connection or host environment proxy settings.
- **Manual proxy configuration** *(radio)*: Enables custom proxy routing.
- **Type**: Choose **HTTP** or **HTTPS** protocol.
- **Proxy host**: IP address or hostname of the proxy server.
- **Port**: Proxy port number (1-65535).
- **Authentication required checkbox**: Toggles username and password credential fields.
- **Username & Password**: Authentication credentials for the proxy server.

#### `Extensions` Tab
- **Aria2 RPC Settings**:
  - **Protocol**: Select `http`, `https`, `websocket` (`ws`), or secure websocket (`wss`).
  - **Port spinbox**: Local daemon port (default: `56800`).
  - **Secret Token**: Optional secret token for Aria2 RPC authentication.
  - **Show Token checkbox**: Toggles password masking on the token field.
- **Get Browser Extension Buttons**:
  - **GitHub button**: Opens GitHub releases to download offline `.xpi` or `.zip` extensions.
  - **Firefox Store button**: Opens Mozilla Add-ons Store page for one-click installation.
  - **Chrome button**: Links to Chrome Web Store package.

#### `Media` Tab
- **Browser Integration & Auto-Start**:
  - **Auto-start media downloads when sent from browser checkbox**: Automatically initiates stream extraction and download without extra prompts.
  - **Preselected Quality Target dropdown**: Default resolution preset (`Best Quality`, `4K`, `2K`, `1080p`, `720p`, `480p`, `360p`, `Audio Only`).
- **Authentication & Cookie Vault Defaults**:
  - **Cookie Strategy dropdown**: Choose **Netscape File (cookies.txt)**, **Browser Auto-Extraction**, or **None**.
  - **Browser dropdown**: Select browser profile to extract session cookies from (**Chrome**, **Firefox**, **Brave**, **Edge**, **Chromium**, **Vivaldi**, **Opera**).
  - **Netscape cookies.txt Path**: File path to exported cookies file with **Browse...** and **Clear** buttons.

#### `Startup` Tab
- **Launch Bengal DM on system startup checkbox**: Creates an XDG autostart `.desktop` entry to launch BDM upon user login.
- **Start minimized in system tray on system startup checkbox**: Launches BDM directly into the system tray without showing the main window.

---

### Row 2: Core Behavior & Appearance Tabs

#### `General` Tab
- **Theme and Appearance**:
  - **Theme dropdown**: Select visual color scheme (**System**, **BDM Auto**, **BDM Dark**, **BDM Light**, **Breeze Dark**, **Breeze Light**, **Catppuccin**, **Dracula**, **IDM Classic**, **Kirigami Dark/Light**, **Material You**, **Nord**, **Obsidian Flow**, **One Dark**, **Solarized**, **Twilight**, **Ubuntu**).
  - **Accent dropdown**: Choose highlight color (**System**, **BDM Default**, **Amethyst Violet**, **Breeze Blue**, **Crimson Red**, **Dracula Purple**, **Emerald Green**, **Material Cobalt**, **Nord Frost**, **Ubuntu Orange**, etc.).
  - **Icons dropdown**: Select icon pack (**BDM Auto**, **BDM Dark**, **BDM Light**, **Adwaita**, **Breeze**, **Breeze Dark**, **Modern Color**, **Yaru**).
  - **Tray Icon dropdown**: Select tray icon variant (**App Icon**, **Automatic**, **Monochrome Dark**, **Monochrome Light**).

#### `Save To` Tab
- **Category dropdown**: Select category to edit rules for.
- **Automatically put in above category file types**: Space-separated list of extensions assigned to this category (e.g. `zip rar 7z tar gz`).
- **Default download directory**: Path where files in this category are saved, with **Browse** button.
- **Change folder for selected category on last selected checkbox**: Automatically updates the default folder to match the directory chosen in the last save prompt.
- **Temporary / Cache directory**: Path where partial chunks and video stream segments are cached before final assembly, with **Browse** button.

#### `Downloads` Tab
- **Download Dialogs**:
  - **Silent download mode checkbox**: Disables all popup dialogs (Start, Progress, Complete); downloads operate completely in the background.
  - **Show start download dialog checkbox**: Toggles the pre-download file info dialog.
  - **Show download progress dialog checkbox**: Toggles the floating progress window.
  - **Show download complete dialog checkbox**: Toggles the completion popup.
  - **Show download complete dialog for downloads in queues checkbox**: Toggles completion popups for queue items (disabled by default to prevent spam).
- **Notifications**:
  - **Show system notification when download completes checkbox**: Disables/enables desktop XDG notifications.
- **Engine and Connection Settings**:
  - **Active Engine status label**: Shows current RPC connection status and binary path.
  - **Max Split Connections (threads) spinbox**: Default number of parallel connections per download (1 to 32).

#### Bottom Action Buttons
- **OK button**: Saves all configuration changes to disk, reapplies themes/palettes, restarts engines if necessary, and closes the dialog.
- **Cancel button**: Discards unapplied changes and closes the window.

---

## 7. Media Downloader Dialog

Accessible via toolbar button or `Ctrl+M`.

### 0. Engine Status Bar (Top Panel)
Displays connection badges for the 5 media tools:
- **`yt-dlp`**, **`ffmpeg`**, **`ffprobe`**, **`deno`**, **`AtomicParsley`**: Each box indicates green (ready), yellow (checking), or red (missing).
- **`ⓘ` Info buttons**: Clicking displays the installed binary path and version tooltip.
- **Update button**: Downloads or updates all 5 tools to their latest releases directly from GitHub.

### 1. Link Input Bar
- **URL input field**: Paste media link or playlist URL. Pressing `Enter` triggers analysis.
- **Paste button (`Ctrl+V`)**: Pastes clipboard content.
- **Analyze button**: Spawns `MediaExtractorWorker` to parse remote streams without downloading.
- **🍪 Cookies ▾ button** *(Toggle)*: Expands or collapses the authentication vault panel.

### 2. Cookies & Authentication Vault Panel
- **Auth Source dropdown**: Choose **Netscape cookies.txt File**, **Auto-Extract from Browser**, or **None**.
- **File Mode**: Text field with **Browse...** and **Clear** buttons.
- **Browser Mode**: Dropdown to select installed browser profile.

### 3. Single Video View (Displayed for individual media URLs)
- **Hero Card**:
  - Rounded thumbnail preview.
  - Video title with mouse selection capability.
  - Metadata badges: Uploader / channel name and duration in seconds/minutes.
- **Filter Row**:
  - **Preset dropdown**: Select target quality (e.g. *Best Quality*, *1080p Full HD*, *Audio Only*).
  - **FPS dropdown**: Filter available streams by framerate (*Any FPS*, *60 FPS*, *30 FPS*).
  - **Video format dropdown**: Filter by codec (*Any*, *MP4 / H.264*, *WebM / VP9*, *AV1*).
  - **Audio format dropdown**: Filter audio codec (*Any*, *M4A / AAC*, *Opus*, *MP3*).
- **Toggles**:
  - **Enable Manual Stream Selection checkbox**: Unlocks the detailed stream table to manually pick an exact video or audio stream ID.
  - **Auto-start from extension checkbox**: Automatically begins download when invoked by the browser extension.
  - **Remember Preset checkbox**: Persists the selected quality options as default for future links.
- **Available Formats Table**:
  - Columns: **ID**, **Ext**, **Resolution / FPS**, **Video Codec**, **Audio Codec**, **Bitrate**, **File Size**.

### 4. Playlist View (Displayed for playlist URLs)
- **Batch Table**:
  - Checkbox per video item.
  - Columns: **#**, **Title**, **Uploader**, **Duration**, **Status**.
- **Select All button**: Checks all items in the playlist.
- **Deselect All button**: Unchecks all items.
- **Selection Badge**: Live counter showing selected items (e.g. `Selected: 15 / 25 items`).

### 5. Bottom Action Buttons
- **Download button**: Dispatches the selected media stream(s) into BDM's core download engine.
- **Close button**: Closes the dialog.

---

## 8. Scheduler & Queues Dialog

Opened via **Toolbar → Scheduler** or sidebar context menu.

### Left Panel: Queue Navigation
- **Queues List**: Lists all defined queues (**Main download queue**, **Synchronization queue**, plus custom queues).
- **New queue button**: Creates a new custom queue.
- **Delete button**: Deletes the selected custom queue (disabled for default queues).

### Right Panel: Schedule Tab
- **Mode Selection**:
  - **One-time downloading** *(radio)*: Downloads the files once and stops.
  - **Periodic synchronization** *(radio)*: Continuously checks and re-synchronizes files at fixed intervals.
- **Start on startup checkbox**: Initiates queue processing as soon as Bengal DM launches.
- **Start download at checkbox & time edit**: Schedules automatic start at a specific time of day (`hh:mm:ss AP`).
- **Once at radio & date picker**: Executes on a specific date.
- **Daily radio & Day checkboxes**: Runs every week on checked days (**Sunday** through **Saturday**).
- **Start again every checkbox & spinboxes**: For synchronization queues, specifies repeat frequency in hours and minutes.
- **Stop download at checkbox & time edit**: Pauses all active downloads in the queue at a designated cut-off time.
- **Number of retries checkbox & spinbox**: Sets maximum retry attempts for failed downloads in the queue.

### Right Panel: Files in the Queue Tab
- **Download N files at the same time spinbox**: Controls concurrency (1 to 20 concurrent downloads).
- **Files Table**: Lists all files assigned to this queue with columns: **File Name**, **Size**, **Status**, **Time left**.

### Bottom Action Buttons
- **Start now button**: Immediately starts downloading all eligible items in the active queue.
- **Stop button**: Pauses the active queue.
- **Apply button**: Persists all schedule and queue changes to the SQLite database.
- **Close button**: Closes the dialog.

---

## 9. Properties Dialog

Opened by right-clicking a download item and selecting **Properties**.

### Controls and Buttons
- **File Information Grid**:
  - **File Name**: Name of the target file.
  - **Type**: File extension type description.
  - **Status**: Progress state or completion percentage.
  - **Size**: Total content length.
  - **Saved To**: Absolute directory path where the file is stored.
  - **Address**: Original download URL.
  - **Referer**: HTTP referrer address used during request headers.
  - **Date Added**: Exact timestamp when the item was enqueued.
  - **Last Try**: Timestamp of the most recent connection attempt.
- **Open button**: Launches the downloaded file in the system default application.
- **Close button**: Closes the properties modal.

---

## 10. Duplicate Download Dialog

Triggered when adding a download URL or file that already exists in the database.

### Controls and Buttons
- **Header Notice**: Indicates whether the file was already completed or is currently unfinished.
- **File Metadata**: Displays filename with icon, URL, total size, and existing storage path.
- **Open File button**: Immediately opens the existing completed file.
- **Open Folder button**: Reveals the existing file in your desktop file manager.
- **Redownload button**: Overwrites the existing file and restarts the download from byte 0.
- **Resume button**: Resumes the unfinished existing item.
- **Restart button**: Clears progress on the unfinished item and starts fresh.
- **Download Copy button**: Creates a new independent download task with an automatically incremented filename (e.g. `package (1).zip`).
- **Cancel button**: Dismisses the dialog without modifying the existing item.

---

## 11. Refresh Download Address Dialog

Opened by right-clicking an interrupted download and choosing **Refresh download address**.

### Controls and Buttons
- **Address input field**: Enter the new, refreshed URL containing updated authentication tokens or session parameters.
- **Paste button**: Pastes clipboard contents into the field.
- **OK button**: Updates the database record with the new URL and resumes downloading from the exact previous byte offset.
- **Cancel button**: Closes the dialog without changing the address.

---

## 12. Rename Dialog

Opened by right-clicking a row and choosing **Rename...**.

### Controls and Buttons
- **Enter new file name input field**: Text field pre-populated with the current filename.
- **OK button**: Renames the physical file on disk (if already downloaded) and updates the database record.
- **Cancel button**: Cancels renaming.

---

## 13. Column Configuration Dialog

Opened via **Header Right-Click → Columns...**.

### Controls and Buttons
- **Column List**: Reorderable list displaying all columns with checkable visibility boxes.
- **Move Up button**: Shifts the selected column one position to the left in the visual table order.
- **Move Down button**: Shifts the selected column one position to the right.
- **Select All button**: Checks all columns, making them visible.
- **Deselect All button**: Unchecks non-essential columns.
- **Column width (pixels) spinbox**: Adjusts the exact width in pixels for the highlighted column.
- **OK button**: Applies the new column order, visibilities, and widths to the table.
- **Cancel button**: Discards changes.

---

## 14. Delete Confirmation Dialog

Prompted when pressing the `Delete` key or clicking the **Delete** toolbar button.

### Controls and Buttons
- **Warning Label**: Confirms the count of selected download(s) to be removed.
- **Also delete files from disk (permanently) checkbox**:
  - *Unchecked (Default)*: Removes records from the download manager table and database; leaves downloaded files untouched on disk.
  - *Checked*: Permanently deletes the associated files and partial chunks from disk storage.
- **Yes button**: Executes deletion according to the checkbox setting.
- **No button**: Cancels the deletion action.

---

## 15. KDE Kirigami QML Interface Controls

Invoked via `uv run python src/main.py --kirigami`:

- **Header Action Bar**: Contains Kirigami action icons for **Add URL**, **Resume**, **Stop**, and **Options**.
- **Global Drawer**: Slide-out drawer on the left side allowing category filtering (**All**, **Documents**, **Videos**, etc.) and status filtering.
- **CardsListView**: Touch-optimized download card items rendering:
  - File icon and filename.
  - Status chip badge (`Complete`, `Downloading`, `Paused`).
  - Progress bar with smooth Kirigami animations.
  - Tabular transfer speed, downloaded size, and remaining time labels.
  - Action buttons on card: **Pause/Resume**, **Open File**, **Open Folder**, and **Delete**.
- **Kirigami Dialog Overlays**: Native Kirigami modal sheets for URL entry and queue management.
