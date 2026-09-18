# 0007 Modularize Media Downloader Subsystem

Status: accepted

## Context
The media downloader subsystem previously resided in a single 1,732-line monolithic file (`src/core/media_downloader.py`). This file conflated multiple distinct architectural responsibilities:
1. Binary dependency acquisition (`yt-dlp`, `ffmpeg`, `ffprobe`, `deno`, `AtomicParsley` downloading, decompression, and updates).
2. Remote stream probing and metadata extraction (`MediaExtractorWorker`).
3. Multi-connection media downloading and adaptive audio/video stream multiplexing (`YtDlpDownloadWorker`).
4. Duplicated size parsing logic (`parse_size_str_to_bytes`).

This lack of locality made navigating, maintaining, and testing media downloading difficult, as changes to binary packaging carried risks of regressing download execution.

## Decision
We decompose the media downloader subsystem into a cohesive `core.media` package:
- `src/core/media/dependencies.py`: Owns external binary specifications, download routines, and version verification (`DependencyManagerWorker`, `YtDlpManager`).
- `src/core/media/extractor.py`: Owns media metadata JSON extraction and playlist/video parsing (`MediaExtractorWorker`).
- `src/core/media/worker.py`: Owns download execution, segment progress signaling, and stream muxing (`YtDlpDownloadWorker`).
- `src/core/media/__init__.py`: Package entry point consolidating exports.
- `src/core/media_downloader.py`: Retained as a thin adapter facade re-exporting all components to maintain 100% backwards compatibility with existing UI dialogs and test fixtures.

## Consequences
- Single-responsibility modules with high locality and clear interfaces.
- AI navigability and human maintainability significantly enhanced (no file exceeds ~900 lines).
- Seamless backwards compatibility with zero changes required in calling code.
