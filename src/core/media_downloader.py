"""
Media Downloader Core Engine for Bengal Download Manager.
Manages yt-dlp binary acquisition, update, and URL/playlist metadata extraction.
"""

import os
import sys
import json
import shutil
import urllib.request
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, QObject

APP_DATA_DIR = Path.home() / ".local" / "share" / "bengal-download-manager"
BIN_DIR = APP_DATA_DIR / "bin"
YT_DLP_BIN = BIN_DIR / "yt-dlp"
YT_DLP_DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"


class YtDlpManager:
    """Manages detection, downloading, and updating of the yt-dlp binary."""

    @staticmethod
    def get_binary_path() -> str:
        """Returns path to executable yt-dlp binary, checking app bin dir first, then system PATH."""
        if YT_DLP_BIN.exists() and os.access(YT_DLP_BIN, os.X_OK):
            return str(YT_DLP_BIN)
        
        system_path = shutil.which("yt-dlp")
        if system_path:
            return system_path
        
        return str(YT_DLP_BIN)

    @staticmethod
    def is_binary_available() -> bool:
        """Checks if yt-dlp executable exists either in app bin dir or system PATH."""
        if YT_DLP_BIN.exists() and os.access(YT_DLP_BIN, os.X_OK):
            return True
        return shutil.which("yt-dlp") is not None

    @classmethod
    def ensure_binary(cls, progress_callback=None) -> str:
        """Ensures yt-dlp executable exists. Downloads it if missing."""
        if cls.is_binary_available():
            return cls.get_binary_path()

        BIN_DIR.mkdir(parents=True, exist_ok=True)
        
        if progress_callback:
            progress_callback("Downloading yt-dlp engine...")

        def _reporthook(blocknum, blocksize, totalsize):
            if totalsize > 0 and progress_callback:
                percent = int((blocknum * blocksize / totalsize) * 100)
                progress_callback(f"Downloading yt-dlp engine ({min(100, percent)}%)...")

        tmp_path = YT_DLP_BIN.with_suffix(".tmp")
        try:
            urllib.request.urlretrieve(YT_DLP_DOWNLOAD_URL, tmp_path, reporthook=_reporthook)
            tmp_path.rename(YT_DLP_BIN)
            YT_DLP_BIN.chmod(0o755)
            if progress_callback:
                progress_callback("yt-dlp engine ready.")
            return str(YT_DLP_BIN)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download yt-dlp binary: {e}") from e


class MediaExtractorWorker(QThread):
    """Background worker thread to fetch and parse video/playlist metadata using yt-dlp."""

    status_signal = pyqtSignal(str)
    single_video_analyzed = pyqtSignal(dict)
    playlist_analyzed = pyqtSignal(dict)
    analysis_failed = pyqtSignal(str)

    def __init__(self, url: str, parent: QObject = None):
        super().__init__(parent)
        self.url = url.strip()

    def run(self):
        try:
            self.status_signal.emit("Checking yt-dlp engine...")
            bin_path = YtDlpManager.ensure_binary(
                progress_callback=lambda msg: self.status_signal.emit(msg)
            )

            self.status_signal.emit("Analyzing media URL...")
            cmd = [
                bin_path,
                "-J",
                "--flat-playlist",
                "--no-warnings",
                "--compat-options", "no-youtube-unavailable-videos",
                self.url
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                err_msg = stderr.strip() or stdout.strip() or f"yt-dlp process failed with code {process.returncode}"
                self.analysis_failed.emit(err_msg)
                return

            try:
                data = json.loads(stdout)
            except json.JSONDecodeError as json_err:
                self.analysis_failed.emit(f"Failed to parse yt-dlp metadata JSON: {json_err}")
                return

            # Check if JSON payload represents a playlist or single video
            if data.get("_type") == "playlist" or (isinstance(data.get("entries"), list) and len(data.get("entries")) > 0 and not data.get("formats")):
                parsed_playlist = self._parse_playlist_data(data)
                self.playlist_analyzed.emit(parsed_playlist)
            else:
                parsed_video = self._parse_single_video_data(data)
                self.single_video_analyzed.emit(parsed_video)

        except Exception as e:
            self.analysis_failed.emit(str(e))

    def _parse_single_video_data(self, raw_data: dict) -> dict:
        """Parses raw yt-dlp video JSON output into a structured dictionary."""
        formats = []
        raw_formats = raw_data.get("formats", [])

        for fmt in raw_formats:
            fmt_id = fmt.get("format_id", "")
            ext = fmt.get("ext", "")
            vcodec = fmt.get("vcodec", "none")
            acodec = fmt.get("acodec", "none")
            height = fmt.get("height")
            width = fmt.get("width")
            filesize = fmt.get("filesize") or fmt.get("filesize_approx")
            fps = fmt.get("fps")
            tbr = fmt.get("tbr")
            format_note = fmt.get("format_note", "")
            url = fmt.get("url", "")

            # Resolution label
            if height:
                res_label = f"{height}p"
            elif width:
                res_label = f"{width}w"
            elif vcodec != "none":
                res_label = "Video"
            else:
                res_label = "Audio Only"

            is_video = vcodec != "none"
            is_audio = acodec != "none"

            formats.append({
                "format_id": fmt_id,
                "ext": ext,
                "vcodec": vcodec,
                "acodec": acodec,
                "height": height or 0,
                "width": width or 0,
                "fps": fps or 0,
                "filesize": filesize or 0,
                "tbr": tbr or 0,
                "res_label": res_label,
                "format_note": format_note,
                "is_video": is_video,
                "is_audio": is_audio,
                "url": url,
                "manifest_url": fmt.get("manifest_url", "")
            })

        return {
            "title": raw_data.get("title") or "Untitled Media",
            "id": raw_data.get("id", ""),
            "uploader": raw_data.get("uploader") or raw_data.get("channel") or "Unknown",
            "duration": raw_data.get("duration") or 0,
            "thumbnail": raw_data.get("thumbnail") or "",
            "webpage_url": raw_data.get("webpage_url") or self.url,
            "formats": formats,
            "raw": raw_data
        }

    def _parse_playlist_data(self, raw_data: dict) -> dict:
        """Parses raw yt-dlp playlist JSON output into structured dictionary."""
        entries = []
        raw_entries = raw_data.get("entries", [])

        for idx, entry in enumerate(raw_entries, start=1):
            if not isinstance(entry, dict):
                continue
            item_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
            entries.append({
                "index": idx,
                "id": entry.get("id", ""),
                "title": entry.get("title") or f"Item {idx}",
                "duration": entry.get("duration") or 0,
                "url": item_url,
                "uploader": entry.get("uploader") or raw_data.get("uploader") or "Unknown"
            })

        return {
            "title": raw_data.get("title") or "Playlist",
            "id": raw_data.get("id", ""),
            "uploader": raw_data.get("uploader") or "Unknown",
            "total_items": len(entries),
            "entries": entries,
            "raw": raw_data
        }
