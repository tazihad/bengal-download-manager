"""
Media Downloader Core Engine for Bengal Download Manager.
Manages yt-dlp binary acquisition, metadata extraction, dependency management (yt-dlp, ffmpeg, ffprobe, deno, AtomicParsley),
subtitles & thumbnails embedding, and multi-format audio+video merging download worker.
"""

import os
import sys
import re
import json
import shutil
import tarfile
import zipfile
import urllib.request
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, QObject

APP_DATA_DIR = Path.home() / ".local" / "share" / "bengal-download-manager"
BIN_DIR = APP_DATA_DIR / "bin"
YT_DLP_BIN = BIN_DIR / "yt-dlp"

DEPENDENCY_TOOLS = {
    "yt-dlp": {
        "binary_name": "yt-dlp",
        "version_cmd": ["--version"],
        "url": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
        "type": "direct"
    },
    "ffmpeg": {
        "binary_name": "ffmpeg",
        "version_cmd": ["-version"],
        "url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "type": "tar.xz",
        "extract_files": ["ffmpeg", "ffprobe"]
    },
    "ffprobe": {
        "binary_name": "ffprobe",
        "version_cmd": ["-version"],
        "url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "type": "tar.xz",
        "extract_files": ["ffmpeg", "ffprobe"]
    },
    "deno": {
        "binary_name": "deno",
        "version_cmd": ["--version"],
        "url": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip",
        "type": "zip",
        "extract_files": ["deno"]
    },
    "AtomicParsley": {
        "binary_name": "AtomicParsley",
        "version_cmd": ["-v"],
        "url": "https://github.com/atomicparsley/atomicparsley/releases/latest/download/AtomicParsley-Linux.zip",
        "type": "zip",
        "extract_files": ["AtomicParsley"]
    }
}


def get_tool_path(tool_name: str) -> str:
    """Returns executable path for tool, checking BIN_DIR first, then system PATH."""
    if tool_name not in DEPENDENCY_TOOLS:
        return ""
    if tool_name == "yt-dlp":
        if YT_DLP_BIN.exists() and os.access(YT_DLP_BIN, os.X_OK):
            return str(YT_DLP_BIN)
        system_path = shutil.which("yt-dlp")
        if system_path:
            return system_path
        return str(YT_DLP_BIN)

    binary_name = DEPENDENCY_TOOLS[tool_name]["binary_name"]
    local_bin = BIN_DIR / binary_name
    if local_bin.exists() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    system_path = shutil.which(binary_name)
    if system_path:
        return system_path
    return str(local_bin)


def get_tool_version(tool_name: str) -> str:
    """Queries tool version via subprocess. Returns version string or empty string if not installed."""
    path = get_tool_path(tool_name)
    if not os.path.exists(path) or not os.access(path, os.X_OK):
        return ""
    try:
        cmd = [path] + DEPENDENCY_TOOLS[tool_name]["version_cmd"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        out = (res.stdout + res.stderr).strip()
        if not out:
            return "Installed"
        first_line = out.splitlines()[0]
        m = re.search(r"v?(\d+[\d.a-zA-Z_\-]+)", first_line)
        if m:
            return f"v{m.group(1)}"
        return first_line[:15]
    except Exception:
        return "Installed"


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


class DependencyManagerWorker(QThread):
    """
    Worker thread to check, download, extract, and update external dependencies:
    yt-dlp, ffmpeg, ffprobe, deno, and AtomicParsley.
    Emits tool_status_signal(tool_name, display_text, color_type) where color_type is 'green', 'yellow', or 'gray'.
    """

    tool_status_signal = pyqtSignal(str, str, str)
    all_finished_signal = pyqtSignal()

    def __init__(self, force_download: bool = False):
        super().__init__()
        self.force_download = force_download

    def run(self):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_names = ["yt-dlp", "ffmpeg", "ffprobe", "deno", "AtomicParsley"]

        for tool in tool_names:
            ver = get_tool_version(tool)

            if ver:
                # If tool is already installed and valid, display installed version and skip download
                self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")
                continue

            # Only download if tool is missing / not installed
            self._download_and_install_tool(tool)

        self.all_finished_signal.emit()

    def _download_and_install_tool(self, tool_name: str):
        tool_info = DEPENDENCY_TOOLS[tool_name]
        url = tool_info["url"]
        tool_type = tool_info["type"]
        binary_name = tool_info["binary_name"]

        self.tool_status_signal.emit(tool_name, f"{tool_name} (Downloading...)", "yellow")

        tmp_download_path = BIN_DIR / f"{tool_name}_download.tmp"

        def _reporthook(blocknum, blocksize, totalsize):
            dl_bytes = blocknum * blocksize
            if totalsize > 0:
                dl_mb = dl_bytes / (1024 * 1024)
                tot_mb = totalsize / (1024 * 1024)
                display_str = f"{tool_name} ({dl_mb:.1f} MB / {tot_mb:.1f} MB)"
            else:
                dl_mb = dl_bytes / (1024 * 1024)
                display_str = f"{tool_name} ({dl_mb:.1f} MB)"
            self.tool_status_signal.emit(tool_name, display_str, "yellow")

        try:
            urllib.request.urlretrieve(url, tmp_download_path, reporthook=_reporthook)

            if tool_type == "direct":
                dest = BIN_DIR / binary_name
                if dest.exists():
                    dest.unlink()
                tmp_download_path.rename(dest)
                dest.chmod(0o755)

            elif tool_type == "zip":
                extract_files = tool_info.get("extract_files", [binary_name])
                with zipfile.ZipFile(tmp_download_path, "r") as zf:
                    for member in zf.namelist():
                        base = os.path.basename(member)
                        if base in extract_files:
                            dest = BIN_DIR / base
                            with zf.open(member) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            dest.chmod(0o755)
                tmp_download_path.unlink(missing_ok=True)

            elif tool_type == "tar.xz":
                extract_files = tool_info.get("extract_files", [binary_name])
                with tarfile.open(tmp_download_path, "r:*") as tar:
                    for member in tar.getmembers():
                        base = os.path.basename(member.name)
                        if base in extract_files:
                            f = tar.extractfile(member)
                            if f:
                                dest = BIN_DIR / base
                                with open(dest, "wb") as dst:
                                    shutil.copyfileobj(f, dst)
                                dest.chmod(0o755)
                tmp_download_path.unlink(missing_ok=True)

            ver = get_tool_version(tool_name) or "vLatest"
            self.tool_status_signal.emit(tool_name, f"{tool_name} ({ver})", "green")

        except Exception as e:
            if tmp_download_path.exists():
                tmp_download_path.unlink(missing_ok=True)
            current_ver = get_tool_version(tool_name)
            if current_ver:
                self.tool_status_signal.emit(tool_name, f"{tool_name} ({current_ver})", "green")
            else:
                self.tool_status_signal.emit(tool_name, f"{tool_name} (Failed)", "gray")


class YtDlpManager:
    """Manages detection, downloading, and updating of the yt-dlp binary."""

    @staticmethod
    def get_binary_path() -> str:
        """Returns path to executable yt-dlp binary, checking app bin dir first, then system PATH."""
        return get_tool_path("yt-dlp")

    @staticmethod
    def is_binary_available() -> bool:
        """Checks if yt-dlp executable exists either in app bin dir or system PATH."""
        path = get_tool_path("yt-dlp")
        return bool(path and os.path.exists(path) and os.access(path, os.X_OK))

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
            urllib.request.urlretrieve(DEPENDENCY_TOOLS["yt-dlp"]["url"], tmp_path, reporthook=_reporthook)
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

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.status_signal.emit("Checking yt-dlp engine...")
            yt_dlp_bin = YtDlpManager.ensure_binary(progress_callback=lambda msg: self.status_signal.emit(msg))

            self.status_signal.emit("Analyzing media URL metadata...")
            
            bin_dir = str(BIN_DIR)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

            cmd = [
                yt_dlp_bin,
                "-J",
                "--flat-playlist",
                "--no-warnings",
                "--ffmpeg-location", bin_dir,
                self.url
            ]

            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )

            stdout, stderr = process.communicate(timeout=60)

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
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec", "none") or "none"
            acodec = fmt.get("acodec", "none") or "none"

            if ext in ("mhtml", "html", "htm") or (vcodec == "none" and acodec == "none"):
                continue

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

        def format_sort_key(fmt):
            is_video = fmt.get("is_video", False)
            height = fmt.get("height", 0) or 0
            tbr = fmt.get("tbr", 0) or 0
            if is_video:
                return (0, -height, -tbr)
            else:
                return (1, 0, -tbr)

        formats.sort(key=format_sort_key)

        return {
            "title": raw_data.get("title") or "Untitled Media",
            "id": raw_data.get("id", ""),
            "uploader": raw_data.get("uploader") or raw_data.get("channel") or "Unknown",
            "duration": raw_data.get("duration", 0),
            "thumbnail": raw_data.get("thumbnail", ""),
            "webpage_url": raw_data.get("webpage_url") or self.url,
            "formats": formats
        }

    def _parse_playlist_data(self, raw_data: dict) -> dict:
        """Parses playlist yt-dlp JSON output into list of items."""
        entries = []
        raw_entries = raw_data.get("entries", [])

        for idx, entry in enumerate(raw_entries, start=1):
            if not isinstance(entry, dict):
                continue
            item_url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
            entries.append({
                "index": idx,
                "id": entry.get("id", ""),
                "title": entry.get("title") or f"Item {idx}",
                "duration": entry.get("duration", 0),
                "url": item_url
            })

        return {
            "title": raw_data.get("title") or "Playlist",
            "total_items": len(entries),
            "entries": entries
        }


class YtDlpDownloadWorker(QThread):
    """
    Download worker thread executing yt-dlp to download media, embed thumbnail & subtitles,
    and merge adaptive streams via ffmpeg.
    Emits main_progress_signal for main download table.
    """

    main_progress_signal = pyqtSignal(int, tuple)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, str)

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

    def format_bytes_str(self, size: float) -> str:
        if not isinstance(size, (int, float)) or size <= 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        idx = 0
        s = float(size)
        while s >= 1024.0 and idx < len(units) - 1:
            s /= 1024.0
            idx += 1
        return f"{s:.2f} {units[idx]}"

    def run(self):
        try:
            bin_path = YtDlpManager.ensure_binary()
            bin_dir = str(BIN_DIR)

            os.makedirs(self.save_dir, exist_ok=True)
            clean_base = re.sub(r'[\\/*?:"<>|]', "_", os.path.splitext(self.filename)[0])
            output_tmpl = os.path.join(self.save_dir, f"{clean_base}.%(ext)s")

            cmd = [
                bin_path,
                "--newline",
                "--no-warnings",
                "--ffmpeg-location", bin_dir,
                "--embed-thumbnail",
                "--write-thumbnail",
                "--embed-subs",
                "--write-subs",
                "--sub-langs", "all",
                "--format", self.format_spec,
                "-o", output_tmpl
            ]

            if self.is_audio_only:
                cmd.extend(["-x", "--audio-format", "mp3"])
            else:
                cmd.extend(["--merge-output-format", "mp4"])

            cmd.append(self.url)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

            self.log_signal.emit(f"Executing command: {' '.join(cmd)}")
            self.main_progress_signal.emit(self.row_index, (self.filename, "Unknown", "Connecting...", "--", "--", 0, 0))

            self.process = subprocess.Popen(
                cmd,
                env=env,
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

                # Parse yt-dlp stdout
                if "[download]" in line_str and "of" in line_str:
                    pct_match = re.search(r"(\d+\.?\d*)%", line_str)
                    if pct_match:
                        pct = float(pct_match.group(1))

                    size_match = re.search(r"of\s+~?\s*(\d+\.?\d*\s*[KMGTP]?i?B)", line_str, re.IGNORECASE)
                    if size_match:
                        total_bytes = parse_size_str_to_bytes(size_match.group(1))
                        downloaded_bytes = (pct / 100.0) * total_bytes

                    speed_match = re.search(r"at\s+(\d+\.?\d*\s*[KMGTP]?i?B/s)", line_str, re.IGNORECASE)
                    if speed_match:
                        speed_str = speed_match.group(1)
                        speed_bps = parse_size_str_to_bytes(speed_str.replace("/s", ""))

                    eta_match = re.search(r"ETA\s+(\d+:\d+(?::\d+)?)", line_str)
                    if eta_match:
                        eta_str = eta_match.group(1)

                    speed_fmt = f"{self.format_bytes_str(speed_bps)}/s" if speed_bps > 0 else "--"
                    size_fmt = self.format_bytes_str(total_bytes) if total_bytes > 0 else "Unknown"

                    data_tuple = (
                        self.filename,
                        size_fmt,
                        f"Downloading ({pct:.1f}%)",
                        eta_str,
                        speed_fmt,
                        int(downloaded_bytes),
                        int(total_bytes)
                    )
                    self.main_progress_signal.emit(self.row_index, data_tuple)

                elif "[Merger]" in line_str or "Merging formats" in line_str:
                    status_str = "Merging Video + Audio..."
                    self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes_str(total_bytes), status_str, "--", "--", int(total_bytes), int(total_bytes)))
                    m_file = re.search(r'"([^"]+)"', line_str)
                    if m_file:
                        self.final_file_path = m_file.group(1)

                elif "[EmbedSubtitle]" in line_str or "[EmbedThumbnail]" in line_str:
                    status_str = "Embedding Media Assets..."
                    self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes_str(total_bytes), status_str, "--", "--", int(total_bytes), int(total_bytes)))

            self.process.wait()
            rc = self.process.returncode

            if rc == 0:
                final_ext = ".mp3" if self.is_audio_only else ".mp4"
                final_path = self.final_file_path or os.path.join(self.save_dir, f"{clean_base}{final_ext}")
                final_size = os.path.getsize(final_path) if os.path.exists(final_path) else total_bytes

                data_tuple = (
                    self.filename,
                    self.format_bytes_str(final_size),
                    "Complete",
                    "--",
                    "--",
                    int(final_size),
                    int(final_size)
                )
                self.main_progress_signal.emit(self.row_index, data_tuple)
                self.finished_signal.emit(self.row_index, final_path)
            else:
                data_tuple = (self.filename, "Unknown", "Error", "--", "--", 0, 0)
                self.main_progress_signal.emit(self.row_index, data_tuple)
                self.finished_signal.emit(self.row_index, "")

        except Exception as e:
            self.log_signal.emit(f"Download Worker Exception: {e}")
            data_tuple = (self.filename, "Unknown", "Error", "--", "--", 0, 0)
            self.main_progress_signal.emit(self.row_index, data_tuple)
            self.finished_signal.emit(self.row_index, "")

    def stop(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
