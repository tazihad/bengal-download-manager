# Media Downloader Feature Implementation Plan

**Date:** 2026-08-07  
**Spec Document:** `docs/superpowers/specs/2026-08-07-media-downloader-design.md`  
**Target Branch:** `feat/media-downloader`

---

## Proposed Tasks

### Task 1: Core Engine Implementation (`src/core/media_downloader.py`)
- [ ] Create `src/core/media_downloader.py` containing `YtDlpManager` and `MediaExtractorWorker(QThread)`.
- [ ] Implement local `yt-dlp` binary detection and auto-downloading from GitHub releases if missing.
- [ ] Implement `yt-dlp -J` JSON parser for single video and playlist formats.
- [ ] Write unit tests in `tests/test_media_downloader.py` verifying binary detection, format parsing, and extraction handling.

### Task 2: UI Window Implementation (`src/ui/dialogs/media_downloader.py`)
- [ ] Create `MediaDownloaderDialog` using `super().__init__(None)` and `Qt.WindowType.Window` flags.
- [ ] Implement "Enter URL" header, URL input field, Paste button, and Analyze Link action.
- [ ] Build Single Video View with thumbnail preview, title, quality chooser presets (1080p, 720p, 480p, Audio Only), and stream table.
- [ ] Build Playlist View with item checkboxes, Select/Deselect All, count banner, and global quality selector.
- [ ] Register `MediaDownloaderDialog` in `src/ui/dialogs/__init__.py`.

### Task 3: Main Toolbar & Action Integration (`src/main.py` & `src/ui/icons.py`)
- [ ] Add `media_downloader` SVG icon generator/fallback in `src/ui/icons.py`.
- [ ] Add `action_media_downloader` in `src/main.py`.
- [ ] Position `action_media_downloader` in `MainToolbar` directly to the right of `action_options`.
- [ ] Add action to Downloads menu bar.
- [ ] Implement `open_media_downloader()` slot in `MainWindow`.

### Task 4: Automated Verification & Documentation
- [ ] Run full test suite: `PYTHONPATH=src venv/bin/pytest -v tests/`.
- [ ] Verify window flag behavior, `WM_CLASS` sharing, and taskbar separation.

---

## Plan Self-Review
1. **Spec Alignment:** Matches design doc `docs/superpowers/specs/2026-08-07-media-downloader-design.md`.
2. **Tabular Figures & Palette:** Follows project rules for open-type tabular numbers (`tnum`) and theme palette adaptation.
