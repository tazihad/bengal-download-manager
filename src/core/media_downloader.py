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
import logging
import tarfile
import zipfile
import urllib.request
import subprocess
from pathlib import Path
from .utils import get_cache_dir, get_data_dir, get_clean_env
from .config import load_category_config
from PyQt6.QtCore import QThread, pyqtSignal, QObject

logger = logging.getLogger("bengal.media_downloader")

APP_DATA_DIR = Path(get_data_dir())
BIN_DIR = APP_DATA_DIR / "bin"
YT_DLP_BIN = BIN_DIR / "yt-dlp"

import platform

_ARCH = platform.machine().lower()
IS_ARM = _ARCH in ("aarch64", "arm64")

DEPENDENCY_TOOLS = {
    "yt-dlp": {
        "binary_name": "yt-dlp",
        "version_cmd": ["--version"],
        "url": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64"
            if IS_ARM else
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"
        ),
        "type": "direct"
    },
    "ffmpeg": {
        "binary_name": "ffmpeg",
        "version_cmd": ["-version"],
        "url": (
            "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
            if IS_ARM else
            "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
        ),
        "type": "tar.xz",
        "extract_files": ["ffmpeg", "ffprobe"]
    },
    "ffprobe": {
        "binary_name": "ffprobe",
        "version_cmd": ["-version"],
        "url": (
            "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
            if IS_ARM else
            "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
        ),
        "type": "tar.xz",
        "extract_files": ["ffmpeg", "ffprobe"]
    },
    "deno": {
        "binary_name": "deno",
        "version_cmd": ["--version"],
        "url": (
            "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-unknown-linux-gnu.zip"
            if IS_ARM else
            "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"
        ),
        "type": "zip",
        "extract_files": ["deno"]
    },
    "AtomicParsley": {
        "binary_name": "AtomicParsley",
        "version_cmd": ["-v"],
        "url": "https://github.com/wez/atomicparsley/releases/download/20240608.083822.1ed9031/AtomicParsleyLinux.zip",
        "type": "zip",
        "extract_files": ["AtomicParsley"]
    }
}


def get_local_tool_path(tool_name: str) -> str:
    """Returns local executable path in XDG data BIN_DIR if it exists and is executable, else empty string."""
    if tool_name not in DEPENDENCY_TOOLS:
        return ""
    if tool_name == "yt-dlp":
        if YT_DLP_BIN.exists() and os.access(YT_DLP_BIN, os.X_OK):
            return str(YT_DLP_BIN)
        return ""
    binary_name = DEPENDENCY_TOOLS[tool_name]["binary_name"]
    local_bin = BIN_DIR / binary_name
    if local_bin.exists() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    return ""


def get_tool_path(tool_name: str, allow_system: bool = False) -> str:
    """Returns executable path for tool strictly from XDG data BIN_DIR."""
    return get_local_tool_path(tool_name)


def get_tool_version(tool_name: str, local_only: bool = True) -> str:
    """Queries tool version strictly from XDG data BIN_DIR. Returns empty string if not installed."""
    path = get_tool_path(tool_name)
    if not path or not os.path.exists(path) or not os.access(path, os.X_OK):
        return ""
    try:
        cmd = [path] + DEPENDENCY_TOOLS[tool_name]["version_cmd"]
        clean_env = get_clean_env(str(BIN_DIR))
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3, env=clean_env)
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
        downloaded_extract_urls = set()

        for tool in tool_names:
            if self.isInterruptionRequested():
                break

            binary_name = DEPENDENCY_TOOLS[tool]["binary_name"]
            local_bin = BIN_DIR / binary_name
            is_local_installed = local_bin.exists() and os.access(local_bin, os.X_OK)

            if self.force_download:
                self.tool_status_signal.emit(tool, f"{tool} (Checking...)", "yellow")
                self.msleep(50)

            # Skip redundant archive download if previously extracted by companion tool (e.g., ffprobe from ffmpeg)
            tool_url = DEPENDENCY_TOOLS[tool]["url"]
            if self.force_download and tool_url in downloaded_extract_urls and is_local_installed:
                ver = get_tool_version(tool, local_only=True) or "vLatest"
                self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")
                continue

            if not is_local_installed or self.force_download:
                success = self._download_and_install_tool(tool)
                if success:
                    downloaded_extract_urls.add(tool_url)
            else:
                ver = get_tool_version(tool, local_only=True) or "Installed"
                self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")

        self.all_finished_signal.emit()

    def _download_and_install_tool(self, tool_name: str) -> bool:
        import ssl
        tool_info = DEPENDENCY_TOOLS[tool_name]
        url = tool_info["url"]
        tool_type = tool_info["type"]
        binary_name = tool_info["binary_name"]

        self.tool_status_signal.emit(tool_name, f"{tool_name} (Downloading...)", "yellow")

        # Use XDG cache dir for temporary download to avoid polluting BIN_DIR
        cache_dir = get_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)
        tmp_download_path = Path(os.path.join(cache_dir, f"{tool_name}_download.tmp"))

        def _reporthook(blocknum, blocksize, totalsize):
            if self.isInterruptionRequested():
                raise InterruptedError("Download interrupted")
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
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"})
            resp = None
            for use_unverified in (False, True):
                try:
                    ssl_ctx = ssl._create_unverified_context() if use_unverified else ssl.create_default_context()
                    resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=30)
                    break
                except Exception as net_err:
                    if use_unverified:
                        raise net_err

            with resp, open(tmp_download_path, "wb") as out_f:
                totalsize = int(resp.headers.get("Content-Length", 0))
                blocksize = 16384
                blocknum = 0
                while True:
                    if self.isInterruptionRequested():
                        raise InterruptedError("Download interrupted")
                    chunk = resp.read(blocksize)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    blocknum += 1
                    _reporthook(blocknum, blocksize, totalsize)

            if tool_type == "direct":
                dest = BIN_DIR / binary_name
                if dest.exists():
                    dest.unlink()
                shutil.move(str(tmp_download_path), str(dest))
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

            ver = get_tool_version(tool_name, local_only=True) or "vLatest"
            self.tool_status_signal.emit(tool_name, f"{tool_name} ({ver})", "green")
            return True

        except Exception as e:
            if tmp_download_path.exists():
                tmp_download_path.unlink(missing_ok=True)
            current_ver = get_tool_version(tool_name, local_only=True)
            if current_ver:
                self.tool_status_signal.emit(tool_name, f"{tool_name} ({current_ver})", "green")
                return True
            else:
                self.tool_status_signal.emit(tool_name, f"{tool_name} (Not Installed)", "gray")
                return False


class YtDlpManager:
    """Manages detection, downloading, and updating of the yt-dlp binary."""

    @staticmethod
    def get_binary_path() -> str:
        """Returns path to executable yt-dlp binary strictly from the XDG data bin directory."""
        return get_tool_path("yt-dlp")

    @staticmethod
    def is_binary_available() -> bool:
        """Checks if yt-dlp executable exists in the XDG data bin directory."""
        path = get_tool_path("yt-dlp")
        return bool(path and os.path.exists(path) and os.access(path, os.X_OK))

    @classmethod
    def ensure_binary(cls, progress_callback=None) -> str:
        """Ensures yt-dlp executable exists in XDG data BIN_DIR. Downloads it if missing."""
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
            import ssl
            req = urllib.request.Request(DEPENDENCY_TOOLS["yt-dlp"]["url"], headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"})
            resp = None
            for use_unverified in (False, True):
                try:
                    ssl_ctx = ssl._create_unverified_context() if use_unverified else ssl.create_default_context()
                    resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=30)
                    break
                except Exception as net_err:
                    if use_unverified:
                        raise net_err

            with resp, open(tmp_path, "wb") as out_f:
                totalsize = int(resp.headers.get("Content-Length", 0))
                blocksize = 16384
                blocknum = 0
                while True:
                    chunk = resp.read(blocksize)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    blocknum += 1
                    _reporthook(blocknum, blocksize, totalsize)

            tmp_path.rename(YT_DLP_BIN)
            YT_DLP_BIN.chmod(0o755)
            if progress_callback:
                progress_callback("yt-dlp engine ready.")
            return str(YT_DLP_BIN)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download yt-dlp binary: {e}") from e


_ACTIVE_WORKER_THREADS = set()

def _keep_thread_alive(thread: QThread):
    _ACTIVE_WORKER_THREADS.add(thread)
    thread.finished.connect(lambda: _ACTIVE_WORKER_THREADS.discard(thread))


class MediaExtractorWorker(QThread):
    """Background worker thread to fetch and parse video/playlist metadata using yt-dlp."""

    status_signal = pyqtSignal(str)
    single_video_analyzed = pyqtSignal(dict)
    playlist_analyzed = pyqtSignal(dict)
    analysis_failed = pyqtSignal(str)

    def __init__(self, url: str, cookies_browser: str = None, cookies_file: str = None, referrer: str = None, user_agent: str = None, cookies: str = None):
        super().__init__()
        from core.utils import sanitize_media_url
        self.url = sanitize_media_url(url)
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.referrer = referrer
        self.user_agent = user_agent
        self.cookies = cookies
        self.process = None
        self.is_running = True
        _keep_thread_alive(self)

    def stop(self):
        self.is_running = False
        if hasattr(self, 'process') and self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass

    def run(self):
        try:
            self.status_signal.emit("Checking yt-dlp engine...")
            yt_dlp_bin = YtDlpManager.ensure_binary(progress_callback=lambda msg: self.status_signal.emit(msg))

            self.status_signal.emit("Analyzing media URL metadata...")
            
            bin_dir = str(BIN_DIR)
            clean_env = get_clean_env(bin_dir)
            is_debug = "--debug" in sys.argv or os.environ.get("DEBUG") == "1" or logger.isEnabledFor(logging.DEBUG)

            try:
                cfg = load_category_config()
                media_defaults = cfg.get("media_downloader_defaults", {})
                yt_client = media_defaults.get("youtube_player_client", "default") or "default"
            except Exception:
                yt_client = "default"

            cmd = [
                yt_dlp_bin,
                "-J",
                "--flat-playlist",
                "--playlist-end", "100",
                "--verbose" if is_debug else "--no-warnings",
                "--remote-components", "ejs:github",
                "--extractor-args", f"youtube:player_client={yt_client}",
            ]

            ffmpeg_bin = get_tool_path("ffmpeg") or shutil.which("ffmpeg")
            if ffmpeg_bin:
                cmd.extend(["--ffmpeg-location", ffmpeg_bin])
            elif os.path.exists(bin_dir):
                cmd.extend(["--ffmpeg-location", bin_dir])

            if self.referrer:
                cmd.extend(["--referer", self.referrer])
                try:
                    from urllib.parse import urlparse
                    p_ref = urlparse(self.referrer)
                    if p_ref.scheme and p_ref.netloc:
                        cmd.extend(["--add-header", f"Origin:{p_ref.scheme}://{p_ref.netloc}"])
                except Exception:
                    pass
            if self.user_agent:
                cmd.extend(["--user-agent", self.user_agent])

            # Supply standard browser headers (Accept-Language) to satisfy strict CDNs (e.g. cdn-tnmr, lulustream)
            cmd.extend(["--add-header", "Accept-Language:en-US,en;q=0.9"])

            if self.cookies_browser and self.cookies_browser.lower() not in ("none", ""):
                cmd.extend(["--cookies-from-browser", self.cookies_browser.lower()])
            elif self.cookies_file and os.path.exists(self.cookies_file):
                cmd.extend(["--cookies", self.cookies_file])
            elif getattr(self, "cookies", None):
                cmd.extend(["--add-header", f"Cookie:{self.cookies}"])

            cmd.append(self.url)

            if is_debug:
                logger.debug("[MediaExtractor] Running command: %s", " ".join(cmd))

            self.process = subprocess.Popen(
                cmd,
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )

            stdout, stderr = self.process.communicate(timeout=60)

            if self.process.returncode != 0:
                # RETRY FALLBACK: If extraction failed with cookies, retry clean extraction without cookies
                if (self.cookies_browser and self.cookies_browser.lower() not in ("none", "")) or (self.cookies_file and os.path.exists(str(self.cookies_file))) or getattr(self, "cookies", None):
                    self.status_signal.emit("Cookies invalid or rejected, retrying clean metadata extraction...")
                    clean_cmd = [
                        yt_dlp_bin,
                        "-J",
                        "--flat-playlist",
                        "--playlist-end", "100",
                        "--verbose" if is_debug else "--no-warnings",
                        "--remote-components", "ejs:github",
                        "--extractor-args", f"youtube:player_client={yt_client}",
                        "--add-header", "Accept-Language:en-US,en;q=0.9",
                    ]
                    if ffmpeg_bin:
                        clean_cmd.extend(["--ffmpeg-location", ffmpeg_bin])
                    elif os.path.exists(bin_dir):
                        clean_cmd.extend(["--ffmpeg-location", bin_dir])
                    if self.referrer:
                        clean_cmd.extend(["--referer", self.referrer])
                        try:
                            from urllib.parse import urlparse
                            p_ref = urlparse(self.referrer)
                            if p_ref.scheme and p_ref.netloc:
                                clean_cmd.extend(["--add-header", f"Origin:{p_ref.scheme}://{p_ref.netloc}"])
                        except Exception:
                            pass
                    if self.user_agent:
                        clean_cmd.extend(["--user-agent", self.user_agent])
                    clean_cmd.append(self.url)
                    if is_debug:
                        logger.debug("[MediaExtractor] Retrying clean command: %s", " ".join(clean_cmd))
                    self.process = subprocess.Popen(
                        clean_cmd,
                        env=clean_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8"
                    )
                    stdout, stderr = self.process.communicate(timeout=60)

            if self.process.returncode != 0:
                err_msg = stderr.strip() or stdout.strip() or f"yt-dlp process failed with code {self.process.returncode}"
                logger.error("[MediaExtractor] yt-dlp metadata extraction failed: %s", err_msg)
                if is_debug and stderr:
                    logger.debug("[MediaExtractor] stderr output:\n%s", stderr)
                self.analysis_failed.emit(err_msg)
                return

            try:
                data = json.loads(stdout)
            except json.JSONDecodeError as json_err:
                logger.error("[MediaExtractor] Failed to parse yt-dlp metadata JSON: %s", json_err)
                if is_debug and stdout:
                    logger.debug("[MediaExtractor] Raw stdout:\n%s", stdout[:1000])
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
            duration = raw_data.get("duration") or 0
            filesize = fmt.get("filesize") or fmt.get("filesize_approx")
            fps = fmt.get("fps")
            tbr = fmt.get("tbr")
            if not filesize and duration and tbr:
                try:
                    filesize = int(float(duration) * float(tbr) * 125)
                except Exception:
                    filesize = 0
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

        thumb = raw_data.get("thumbnail") or ""
        if not thumb and isinstance(raw_data.get("thumbnails"), list) and raw_data.get("thumbnails"):
            thumb = raw_data["thumbnails"][-1].get("url", "")

        return {
            "title": raw_data.get("title") or "Untitled Media",
            "id": raw_data.get("id", ""),
            "uploader": raw_data.get("uploader") or raw_data.get("channel") or "Unknown",
            "duration": raw_data.get("duration", 0),
            "thumbnail": thumb,
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
            entry_thumb = entry.get("thumbnail") or ""
            if not entry_thumb and isinstance(entry.get("thumbnails"), list) and entry.get("thumbnails"):
                entry_thumb = entry["thumbnails"][-1].get("url", "")
            entries.append({
                "index": idx,
                "id": entry.get("id", ""),
                "title": entry.get("title") or f"Item {idx}",
                "duration": entry.get("duration", 0),
                "url": item_url,
                "thumbnail": entry_thumb
            })

        pl_thumb = raw_data.get("thumbnail") or ""
        if not pl_thumb and isinstance(raw_data.get("thumbnails"), list) and raw_data.get("thumbnails"):
            pl_thumb = raw_data["thumbnails"][-1].get("url", "")
        if not pl_thumb and entries and entries[0].get("thumbnail"):
            pl_thumb = entries[0]["thumbnail"]

        return {
            "title": raw_data.get("title") or "Playlist",
            "total_items": len(entries),
            "thumbnail": pl_thumb,
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
    main_bar_signal = pyqtSignal(int, int)
    init_segments_signal = pyqtSignal(int)
    segment_update_signal = pyqtSignal(int, int, int, float, str)

    def __init__(self, url: str, row_index: int, save_dir: str, filename: str = None, format_spec: str = "bestvideo+bestaudio/best", is_audio_only: bool = False, cookies_browser: str = None, cookies_file: str = None, referrer: str = None, user_agent: str = None, cookies: str = None, total_bytes: int = 0):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.filename = filename or "media_download"
        self.format_spec = format_spec
        self.is_audio_only = is_audio_only
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.referrer = referrer
        self.user_agent = user_agent
        self.cookies = cookies
        self.is_running = True
        self.is_paused = False
        self.supports_resume = True
        self.process = None
        self.final_file_path = None
        self.total_bytes = int(total_bytes or 0)
        self.current_bytes = 0
        self.target_path = os.path.join(self.save_dir, self.filename)
        self.speed_limit_bytes = 0

        try:
            from core.utils import load_extension_config
            ext_data = load_extension_config()
            conn_val = ext_data.get("max_connections", 8)
            self.max_connections = int(conn_val) if isinstance(conn_val, (int, float, str)) and str(conn_val).isdigit() else 8
        except Exception:
            self.max_connections = 8
        self.max_connections = max(1, min(32, self.max_connections))

        _keep_thread_alive(self)

    def _emit_segment_updates(self, downloaded_bytes: int, total_bytes: int, speed_bps: float, status_text: str = None):
        """Emit per-connection segment progress signals for the UI Details table."""
        num_conn = getattr(self, "max_connections", 8)
        if num_conn <= 0:
            return

        import math
        import time

        if total_bytes > 0:
            part = total_bytes // num_conn
            ratio = min(1.0, max(0.0, downloaded_bytes / total_bytes))
            now = time.time()
            weights = [1.0 + 0.15 * math.sin(i * 1.7 + now * 2.0) for i in range(num_conn)]
            tot_w = sum(weights)

            for i in range(num_conn):
                seg_total = part if i < num_conn - 1 else max(0, total_bytes - part * (num_conn - 1))
                seg_dl = min(seg_total, int(ratio * seg_total))

                if status_text:
                    seg_status = status_text
                    seg_speed = speed_bps * (weights[i] / tot_w) if speed_bps > 0 and status_text not in ("Paused", "Error", "Cancelled", "Complete") else 0.0
                    if status_text == "Complete":
                        seg_dl = seg_total
                elif seg_dl >= seg_total and seg_total > 0:
                    seg_speed = 0.0
                    seg_status = "Complete"
                    seg_dl = seg_total
                elif speed_bps > 0:
                    seg_speed = speed_bps * (weights[i] / tot_w)
                    seg_status = "Receiving data..."
                elif downloaded_bytes > 0:
                    seg_speed = 0.0
                    seg_status = "Receiving data..."
                else:
                    seg_speed = 0.0
                    seg_status = "Connecting..."

                self.segment_update_signal.emit(i, int(seg_dl), int(seg_total), float(seg_speed), seg_status)
        else:
            for i in range(num_conn):
                if status_text:
                    seg_status = status_text
                    seg_speed = speed_bps if i == 0 and status_text not in ("Paused", "Error", "Cancelled", "Complete") else 0.0
                elif i == 0 and speed_bps > 0:
                    seg_status = "Receiving data..."
                    seg_speed = speed_bps
                elif i == 0 and downloaded_bytes > 0:
                    seg_status = "Receiving data..."
                    seg_speed = 0.0
                else:
                    seg_status = "Connecting..." if speed_bps > 0 else "Pending..."
                    seg_speed = 0.0

                dl_val = int(downloaded_bytes) if i == 0 else 0
                self.segment_update_signal.emit(i, dl_val, 0, float(seg_speed), seg_status)

    def pause(self):
        self.is_paused = True
        self.is_running = False
        self._emit_segment_updates(self.current_bytes, self.total_bytes, 0.0, status_text="Paused")
        if hasattr(self, 'process') and self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

    def resume(self):
        self.is_paused = False
        self.is_running = True
        self._emit_segment_updates(self.current_bytes, self.total_bytes, 0.0, status_text="Resuming...")

    def stop(self):
        self.is_running = False
        self._emit_segment_updates(self.current_bytes, self.total_bytes, 0.0, status_text="Cancelled")
        if hasattr(self, 'process') and self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass

    def set_global_speed_limit(self, limit_bytes: int):
        self.speed_limit_bytes = limit_bytes

    def format_bytes(self, size, precision=2, pad=False):
        power = 1024
        n = 0
        power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        try:
            val = float(size)
        except (ValueError, TypeError):
            val = 0.0
        while val >= power and n < 4:
            val /= power
            n += 1
        if pad:
            width = precision + 5
            return f"{val:{width}.{precision}f}  {power_labels.get(n, '')}B"
        else:
            return f"{val:.{precision}f}  {power_labels.get(n, '')}B"

    def format_bytes_str(self, size: float) -> str:
        return self.format_bytes(size, precision=2, pad=False).replace("  ", " ")

    def run(self):
        try:
            bin_path = YtDlpManager.ensure_binary()
            bin_dir = str(BIN_DIR)

            is_debug = "--debug" in sys.argv or os.environ.get("DEBUG") == "1" or logger.isEnabledFor(logging.DEBUG)
            clean_base = os.path.splitext(self.filename)[0] if self.filename else ""
            is_youtube = bool(self.url and ("youtube.com" in self.url.lower() or "youtu.be" in self.url.lower()))
            has_brackets = bool(clean_base and "[" in clean_base and "]" in clean_base)
            is_generic = not clean_base or clean_base.lower() in ("media", "media_download", "master", "index", "video", "videoplayback")

            if is_youtube and not has_brackets:
                if self.is_audio_only:
                    output_tmpl = os.path.join(self.save_dir, "%(title).100B [%(id)s].%(ext)s")
                else:
                    output_tmpl = os.path.join(self.save_dir, "%(title).100B [%(id)s]%(height& [{}p]|)s.%(ext)s")
            elif not is_generic:
                pattern = r'^(.*?)(\s*(?:\[[^\]]+\]|\(\d+\))+(?:\s*(?:\[[^\]]+\]|\(\d+\)))*)$'
                m_suf = re.search(pattern, clean_base)
                if m_suf and m_suf.group(2).strip():
                    main_p, suf_p = m_suf.group(1), m_suf.group(2)
                    eff_limit = max(10, 100 - len(suf_p.encode("utf-8")))
                    while len(main_p.encode("utf-8")) > eff_limit:
                        main_p = main_p.encode("utf-8")[:eff_limit].decode("utf-8", errors="ignore").rstrip("_ ").strip()
                    clean_base = f"{main_p}{suf_p}"
                else:
                    while len(clean_base.encode("utf-8")) > 100:
                        clean_base = clean_base.encode("utf-8")[:100].decode("utf-8", errors="ignore").rstrip("_ ").strip()
                output_tmpl = os.path.join(self.save_dir, f"{clean_base}.%(ext)s")
            else:
                if self.is_audio_only:
                    output_tmpl = os.path.join(self.save_dir, "%(title).100B [%(id)s].%(ext)s")
                else:
                    output_tmpl = os.path.join(self.save_dir, "%(title).100B [%(id)s]%(height& [{}p]|)s.%(ext)s")

            try:
                cfg = load_category_config()
                media_defaults = cfg.get("media_downloader_defaults", {})
                yt_client = media_defaults.get("youtube_player_client", "default") or "default"
            except Exception:
                yt_client = "default"

            cmd = [
                bin_path,
                "--newline",
                "--verbose" if is_debug else "--no-warnings",
                "--progress-delta", "0.1",
                "--remote-components", "ejs:github",
                "--embed-thumbnail",
                "--convert-thumbnails", "png",
                "--restrict-filenames",
                "--extractor-args", f"youtube:player_client={yt_client}",
                "--format", self.format_spec,
                "-o", output_tmpl
            ]

            ffmpeg_bin = get_tool_path("ffmpeg") or shutil.which("ffmpeg")
            if ffmpeg_bin:
                cmd.extend(["--ffmpeg-location", ffmpeg_bin])
            elif os.path.exists(bin_dir):
                cmd.extend(["--ffmpeg-location", bin_dir])

            if self.referrer:
                cmd.extend(["--referer", self.referrer])
                try:
                    from urllib.parse import urlparse
                    p_ref = urlparse(self.referrer)
                    if p_ref.scheme and p_ref.netloc:
                        cmd.extend(["--add-header", f"Origin:{p_ref.scheme}://{p_ref.netloc}"])
                except Exception:
                    pass
            if self.user_agent:
                cmd.extend(["--user-agent", self.user_agent])

            # Supply standard browser headers (Accept-Language) to satisfy strict CDNs (e.g. cdn-tnmr, lulustream)
            cmd.extend(["--add-header", "Accept-Language:en-US,en;q=0.9"])

            if self.cookies_browser and self.cookies_browser.lower() not in ("none", ""):
                cmd.extend(["--cookies-from-browser", self.cookies_browser.lower()])
            elif self.cookies_file and os.path.exists(self.cookies_file):
                cmd.extend(["--cookies", self.cookies_file])
            elif getattr(self, "cookies", None):
                cmd.extend(["--add-header", f"Cookie:{self.cookies}"])

            if self.is_audio_only:
                cmd.extend(["-x", "--audio-format", "opus", "--audio-quality", "0"])
            else:
                cmd.extend(["--merge-output-format", "mkv"])

            if self.max_connections > 1:
                cmd.extend(["--concurrent-fragments", str(self.max_connections)])
            if getattr(self, "speed_limit_bytes", 0) > 0:
                cmd.extend(["--limit-rate", str(self.speed_limit_bytes)])

            cmd.append(self.url)

            clean_env = get_clean_env(bin_dir)

            self.log_signal.emit(f"Executing command: {' '.join(cmd)}")
            if is_debug:
                logger.debug("[YtDlpDownload] Executing command: %s", " ".join(cmd))
            self.main_progress_signal.emit(self.row_index, (self.filename, "Unknown", "Connecting...", "--", "--", 0, 0))
            self.init_segments_signal.emit(self.max_connections)
            self._emit_segment_updates(0, self.total_bytes, 0.0, status_text="Connecting...")

            self.process = subprocess.Popen(
                cmd,
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1
            )

            pct = 0.0
            total_bytes = float(self.total_bytes) if self.total_bytes > 0 else 0.0
            downloaded_bytes = 0.0
            speed_bps = 0.0
            eta_str = "--"
            is_media_stream = True
            last_seg_update = 0.0

            for line in self.process.stdout:
                if not self.is_running:
                    self.process.terminate()
                    break

                line_str = line.strip()
                if not line_str:
                    continue
                if "ERROR:" in line_str or "error:" in line_str.lower():
                    logger.error("[YtDlpDownload] %s", line_str)
                    self.log_signal.emit(line_str)
                elif "WARNING:" in line_str or "warning:" in line_str.lower():
                    logger.warning("[YtDlpDownload] %s", line_str)
                elif is_debug:
                    logger.debug("[YtDlpDownload] %s", line_str)

                # Track destination file type to filter out subtitles/thumbnails
                dest_match = re.search(r"\[(?:download|aria2c)\]\s+Destination:\s+\"?([^\"]+)\"?", line_str, re.IGNORECASE)
                if dest_match:
                    dest_path = dest_match.group(1).strip()
                    dest_ext = os.path.splitext(dest_path)[1].lower()
                    if dest_ext in (".vtt", ".srt", ".ass", ".webp", ".jpg", ".png"):
                        is_media_stream = False
                    elif dest_ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flv", ".avi"):
                        is_media_stream = True
                        self.final_file_path = dest_path

                # Capture output file path from stdout line (only valid video/audio extensions)
                m_dest = re.search(r"\[(?:Merger|ExtractAudio|VideoRemuxer)\]\s+(?:Merging formats into\s+\"|Remuxing video into\s+\")?\"?([^\"]+\.(?:mp4|mkv|webm|mp3|m4a|flv|avi))\"?", line_str, re.IGNORECASE)
                if m_dest:
                    cand_path = m_dest.group(1).strip()
                    cand_ext = os.path.splitext(cand_path)[1].lower()
                    if cand_ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flv", ".avi") and not cand_path.endswith(".part"):
                        self.final_file_path = cand_path
                        is_media_stream = True

                # Parse yt-dlp / aria2c stdout for media streams only
                if ("[download]" in line_str or "[aria2c]" in line_str or "SPD:" in line_str or "CN:" in line_str or "DL:" in line_str or "[#" in line_str) and ("of" in line_str or "SPD:" in line_str or "DL:" in line_str or "%" in line_str):
                    if any(sub_ext in line_str.lower() for sub_ext in [".vtt", ".srt", ".ass", ".webp", ".jpg", ".png"]):
                        is_media_stream = False

                    # Check for explicit dual sizes (downloaded / total or downloaded of total)
                    dual_size_match = re.search(r"(\d+\.?\d*\s*[KMGTP]?i?B)\s*(?:/|of)\s*~?\s*(\d+\.?\d*\s*[KMGTP]?i?B)", line_str, re.IGNORECASE)
                    if dual_size_match:
                        parsed_downloaded = parse_size_str_to_bytes(dual_size_match.group(1))
                        parsed_total = parse_size_str_to_bytes(dual_size_match.group(2))
                        if parsed_total > 500 * 1024:
                            is_media_stream = True
                            if parsed_total > total_bytes:
                                total_bytes = parsed_total
                            if parsed_downloaded > 0:
                                downloaded_bytes = parsed_downloaded
                    else:
                        size_match = re.search(r"(?:of|/)\s*~?\s*(\d+\.?\d*\s*[KMGTP]?i?B)", line_str, re.IGNORECASE)
                        if size_match:
                            parsed_total = parse_size_str_to_bytes(size_match.group(1))
                            if parsed_total > 500 * 1024:
                                is_media_stream = True
                                if parsed_total > total_bytes:
                                    total_bytes = parsed_total
                        elif "SPD:" in line_str or "CN:" in line_str or "DL:" in line_str or "[#" in line_str:
                            is_media_stream = True

                    if is_media_stream:
                        pct_match = re.search(r"(\d+\.?\d*)\s*%", line_str)
                        if pct_match:
                            pct = float(pct_match.group(1))
                            if total_bytes > 500 * 1024 and (not dual_size_match or downloaded_bytes == 0):
                                downloaded_bytes = (pct / 100.0) * total_bytes

                        speed_match = re.search(r"(?:at|SPD:|DL:)\s*(\d+\.?\d*\s*[KMGTP]?i?B(?:/s)?)", line_str, re.IGNORECASE)
                        if not speed_match:
                            speed_match = re.search(r"(\d+\.?\d*\s*[KMGTP]?i?B/s)", line_str, re.IGNORECASE)
                        if speed_match:
                            speed_str = speed_match.group(1).replace("/s", "").strip()
                            speed_bps = parse_size_str_to_bytes(speed_str)

                        eta_match = re.search(r"ETA:?\s*(\d+:\d+(?::\d+)?|\w+)", line_str, re.IGNORECASE)
                        if eta_match:
                            eta_str = eta_match.group(1)

                        speed_fmt = f"{self.format_bytes_str(speed_bps)}/s" if speed_bps > 0 else "--"
                        size_fmt = self.format_bytes_str(total_bytes) if total_bytes > 0 else "Calculating..."

                        # Clamp live downloaded bytes below total_bytes while process is running to avoid premature 100% completion
                        if total_bytes > 0:
                            clamped_downloaded = min(int(downloaded_bytes), int(total_bytes) - 1)
                        else:
                            clamped_downloaded = int(downloaded_bytes)

                        data_tuple = (
                            self.filename,
                            size_fmt,
                            "Downloading",
                            eta_str,
                            speed_fmt,
                            max(0, clamped_downloaded),
                            int(total_bytes)
                        )
                        self.current_bytes = max(0, clamped_downloaded)
                        self.total_bytes = int(total_bytes)
                        self.main_progress_signal.emit(self.row_index, data_tuple)
                        self.main_bar_signal.emit(self.current_bytes, self.total_bytes)
                        import time
                        now_time = time.time()
                        if (now_time - last_seg_update) >= 0.15:
                            last_seg_update = now_time
                            self._emit_segment_updates(self.current_bytes, self.total_bytes, speed_bps)

            self.process.wait()
            rc = self.process.returncode

            if self.is_paused:
                logger.info("[YtDlpDownload] yt-dlp paused by user for %s", self.url)
                return

            if not self.is_running:
                logger.info("[YtDlpDownload] yt-dlp stopped by user for %s", self.url)
                return

            if rc == 0:
                final_path = None
                if self.final_file_path and os.path.exists(self.final_file_path) and os.path.isfile(self.final_file_path):
                    f_ext = os.path.splitext(self.final_file_path)[1].lower()
                    if f_ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flv", ".avi"):
                        final_path = self.final_file_path

                target_expected = os.path.join(self.save_dir, self.filename)
                if os.path.exists(target_expected) and os.path.isfile(target_expected):
                    final_path = target_expected

                if not final_path or not os.path.exists(final_path):
                    candidates = []
                    if os.path.exists(self.save_dir):
                        for fname in os.listdir(self.save_dir):
                            fext = os.path.splitext(fname)[1].lower()
                            if fext not in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flv", ".avi"):
                                continue
                            fpath = os.path.join(self.save_dir, fname)
                            if os.path.isfile(fpath):
                                if clean_base.lower() in fname.lower() or fname.lower().startswith(clean_base[:15].lower()):
                                    candidates.append(fpath)
                    if candidates:
                        final_path = max(candidates, key=lambda p: os.path.getsize(p))

                if final_path:
                    self.target_path = final_path

                final_size = os.path.getsize(final_path) if (final_path and os.path.exists(final_path)) else total_bytes
                self.current_bytes = int(final_size)
                self.total_bytes = int(final_size)

                data_tuple = (
                    self.filename,
                    self.format_bytes_str(final_size),
                    "Complete",
                    "--",
                    "--",
                    int(final_size),
                    int(final_size)
                )
                self._emit_segment_updates(int(final_size), int(final_size), 0.0, status_text="Complete")
                self.main_progress_signal.emit(self.row_index, data_tuple)
                self.main_bar_signal.emit(int(final_size), int(final_size))
                self.finished_signal.emit(self.row_index, final_path or "Complete")
            else:
                logger.error("[YtDlpDownload] yt-dlp process exited with error code %d for %s", rc, self.url)
                self._emit_segment_updates(self.current_bytes, self.total_bytes, 0.0, status_text="Error")
                data_tuple = (self.filename, "Unknown", "Error", "--", "--", 0, 0)
                self.main_progress_signal.emit(self.row_index, data_tuple)
                self.finished_signal.emit(self.row_index, "")

        except Exception as e:
            if getattr(self, "is_paused", False) or not getattr(self, "is_running", True):
                return
            logger.exception("[YtDlpDownload] Download Worker Exception: %s", e)
            self.log_signal.emit(f"Download Worker Exception: {e}")
            self._emit_segment_updates(self.current_bytes, self.total_bytes, 0.0, status_text="Error")
            data_tuple = (self.filename, "Unknown", "Error", "--", "--", 0, 0)
            self.main_progress_signal.emit(self.row_index, data_tuple)
            self.finished_signal.emit(self.row_index, "")
