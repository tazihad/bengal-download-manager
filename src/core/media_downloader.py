"""
Media Downloader Core Engine for Bengal Download Manager.
Manages yt-dlp binary acquisition, metadata extraction, and multi-format audio+video merging download worker.
"""

import os
import sys
import re
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


def parse_size_str_to_bytes(size_str: str) -> float:
    """Helper to convert sizes like '12.50MiB' or '500KiB' to bytes."""
    size_str = size_str.strip().upper()
    units = {
        "KIB": 1024, "KB": 1000,
        "MIB": 1024**2, "MB": 1000**2,
        "GIB": 1024**3, "GB": 1000**3,
        "B": 1
    }
    for u, factor in units.items():
        if size_str.endswith(u):
            try:
                num = float(size_str[:-len(u)].strip())
                return num * factor
            except ValueError:
                pass
    try:
        return float(re.sub(r"[^\d.]", "", size_str))
    except ValueError:
        return 0.0


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


class YtDlpDownloadWorker(QThread):
    """
    Worker thread that executes yt-dlp to download and merge both video and audio streams into a single output file.
    Emits real-time main_progress_signal for Bengal Download Manager's table interface.
    """

    main_progress_signal = pyqtSignal(int, tuple)  # (row_index, (downloaded, total, speed, time_left, status))
    finished_signal = pyqtSignal(int, str)         # (row_index, final_file_path)
    log_signal = pyqtSignal(str)

    def __init__(self, url: str, row_index: int, save_dir: str, filename: str = None, format_spec: str = "bestvideo+bestaudio/best", is_audio_only: bool = False):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.filename = filename or "media_download"
        self.format_spec = format_spec
        self.is_audio_only = is_audio_only
        self.is_running = True
        self.is_paused = False
        self.process = None
        self.final_file_path = None

    def run(self):
        try:
            bin_path = YtDlpManager.ensure_binary()

            os.makedirs(self.save_dir, exist_ok=True)
            clean_base = re.sub(r'[\\/*?:"<>|]', "_", os.path.splitext(self.filename)[0])
            output_tmpl = os.path.join(self.save_dir, f"{clean_base}.%(ext)s")

            cmd = [
                bin_path,
                "--newline",
                "--no-warnings",
                "--format", self.format_spec,
                "-o", output_tmpl
            ]

            if self.is_audio_only:
                cmd.extend(["-x", "--audio-format", "mp3"])
            else:
                cmd.extend(["--merge-output-format", "mp4"])

            cmd.append(self.url)

            self.log_signal.emit(f"Executing command: {' '.join(cmd)}")
            self.main_progress_signal.emit(self.row_index, (0, 0, 0, "--", "Connecting..."))

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1
            )

            pct = 0.0
            total_bytes = 0.0
            downloaded_bytes = 0.0
            speed_bps = 0.0
            eta_str = "--"
            status_str = "Downloading..."

            for line in self.process.stdout:
                if not self.is_running:
                    self.process.terminate()
                    break

                line_str = line.strip()
                if not line_str:
                    continue

                self.log_signal.emit(line_str)

                # Parse yt-dlp stdout lines like:
                # [download]  45.2% of  120.50MiB at  4.52MiB/s ETA 00:15
                # [download] 100% of  120.50MiB in 00:30
                # [Merger] Merging formats into "/path/to/file.mp4"
                if "[download]" in line_str:
                    match_pct = re.search(r'(\d+(?:\.\d+)?)%', line_str)
                    if match_pct:
                        pct = float(match_pct.group(1))

                    match_size = re.search(r'of\s+~?(\d+(?:\.\d+)?[KMGBi]+)', line_str, re.IGNORECASE)
                    if match_size:
                        total_bytes = parse_size_str_to_bytes(match_size.group(1))
                        downloaded_bytes = (pct / 100.0) * total_bytes

                    match_speed = re.search(r'at\s+(\d+(?:\.\d+)?[KMGBi]+/s)', line_str, re.IGNORECASE)
                    if match_speed:
                        speed_str = match_speed.group(1).replace("/s", "")
                        speed_bps = parse_size_str_to_bytes(speed_str)

                    match_eta = re.search(r'ETA\s+([\d:]+)', line_str, re.IGNORECASE)
                    if match_eta:
                        eta_str = match_eta.group(1)

                    status_str = "Downloading..."

                elif "[Merger]" in line_str or "Merging" in line_str:
                    status_str = "Merging Video + Audio..."
                    match_dest = re.search(r'into "([^"]+)"', line_str)
                    if match_dest:
                        self.final_file_path = match_dest.group(1)

                elif "Destination:" in line_str:
                    dest = line_str.split("Destination:", 1)[1].strip()
                    if not self.final_file_path or dest.endswith(".mp4") or dest.endswith(".mp3"):
                        self.final_file_path = dest

                self.main_progress_signal.emit(
                    self.row_index,
                    (int(downloaded_bytes), int(total_bytes), speed_bps, eta_str, status_str)
                )

            self.process.wait()

            if self.process.returncode == 0:
                # Find final created file if not captured
                if not self.final_file_path or not os.path.exists(self.final_file_path):
                    target_ext = ".mp3" if self.is_audio_only else ".mp4"
                    expected_path = os.path.join(self.save_dir, f"{clean_base}{target_ext}")
                    if os.path.exists(expected_path):
                        self.final_file_path = expected_path
                    else:
                        for f in os.listdir(self.save_dir):
                            if f.startswith(clean_base):
                                self.final_file_path = os.path.join(self.save_dir, f)
                                break

                final_path = self.final_file_path or os.path.join(self.save_dir, self.filename)
                self.main_progress_signal.emit(
                    self.row_index,
                    (int(total_bytes or 1), int(total_bytes or 1), 0, "", "Complete")
                )
                self.finished_signal.emit(self.row_index, final_path)
            else:
                self.main_progress_signal.emit(
                    self.row_index,
                    (int(downloaded_bytes), int(total_bytes), 0, "--", "Error")
                )
                self.finished_signal.emit(self.row_index, "")

        except Exception as e:
            self.main_progress_signal.emit(
                self.row_index,
                (0, 0, 0, "--", f"Error: {e}")
            )
            self.finished_signal.emit(self.row_index, "")

    def stop(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
