"""
Media Downloader Dependencies Management
========================================
Supervises discovery, download, installation, and update verification of
third-party media binaries (yt-dlp, ffmpeg, ffprobe, deno, AtomicParsley).
"""

import os
import re
import sys
import time
import json
import shutil
import logging
import tarfile
import zipfile
import platform
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils import get_cache_dir, get_data_dir, get_clean_env

logger = logging.getLogger("bengal.media.dependencies")

APP_DATA_DIR = Path(get_data_dir())
BIN_DIR = APP_DATA_DIR / "bin"
YT_DLP_BIN = BIN_DIR / "yt-dlp"

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
        "type": "direct",
        "role": "Core Video & Audio Extractor",
        "icon": "📥",
        "desc": "Parses video streams, playlists, audio tracks, and formats across 1000+ media sites."
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
        "extract_files": ["ffmpeg", "ffprobe"],
        "role": "Stream Multiplexer & Transcoder",
        "icon": "🎬",
        "desc": "Merges separate high-res video and audio tracks, extracts MP3/M4A, and converts codecs."
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
        "extract_files": ["ffmpeg", "ffprobe"],
        "role": "Stream Analyzer & Inspector",
        "icon": "🔍",
        "desc": "Inspects media container metadata, bitrates, audio channels, and stream packet structures."
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
        "extract_files": ["deno"],
        "role": "Modern JS Runtime (YouTube Cipher)",
        "icon": "🦕",
        "desc": "Executes client-side YouTube signature cipher solver and n-token evaluation algorithms."
    },
    "AtomicParsley": {
        "binary_name": "AtomicParsley",
        "version_cmd": ["-v"],
        "url": "https://github.com/wez/atomicparsley/releases/download/20240608.083822.1ed9031/AtomicParsleyLinux.zip",
        "type": "zip",
        "extract_files": ["AtomicParsley"],
        "role": "Metadata & Artwork Tagger",
        "icon": "🏷️",
        "desc": "Embeds MP4/M4A thumbnail album art, ID3 tags, and chapters into finished media files."
    }
}


def get_local_tool_path(tool_name: str) -> str:
    """Returns local executable path in XDG data BIN_DIR if it exists and is executable, else empty string."""
    if tool_name not in DEPENDENCY_TOOLS:
        return ""
    if tool_name == "yt-dlp":
        import sys
        md = sys.modules.get("core.media_downloader")
        yt_bin = Path(getattr(md, "YT_DLP_BIN", YT_DLP_BIN)) if md else YT_DLP_BIN
        if yt_bin.exists() and os.access(yt_bin, os.X_OK):
            return str(yt_bin)
        return ""
    binary_name = DEPENDENCY_TOOLS[tool_name]["binary_name"]
    local_bin = BIN_DIR / binary_name
    if local_bin.exists() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    return ""


def get_tool_path(tool_name: str, allow_system: bool = False) -> str:
    """Returns executable path for tool strictly from XDG data BIN_DIR."""
    return get_local_tool_path(tool_name)


_TOOL_VERSION_CACHE: dict[str, tuple[float, str]] = {}


def get_tool_version(tool_name: str, local_only: bool = True) -> str:
    """Queries tool version strictly from XDG data BIN_DIR. Returns empty string if not installed.
    Caches parsed versions using file mtime and persistent .versions.json to prevent UI freeze."""
    path = get_tool_path(tool_name)
    if not path or not os.path.exists(path) or not os.access(path, os.X_OK):
        _TOOL_VERSION_CACHE.pop(tool_name, None)
        return ""

    try:
        mtime = os.path.getmtime(path)
        cached = _TOOL_VERSION_CACHE.get(tool_name)
        if cached and cached[0] == mtime and cached[1]:
            return cached[1]
    except Exception:
        mtime = 0.0

    # Fast persistent metadata lookup
    v_file = BIN_DIR / ".versions.json"
    if v_file.exists():
        try:
            v_data = json.loads(v_file.read_text(encoding="utf-8"))
            saved_ver = v_data.get(f"{tool_name}_version", "")
            saved_mtime = v_data.get(f"{tool_name}_mtime", 0.0)
            if saved_ver and (not mtime or abs(saved_mtime - mtime) < 1e-3):
                _TOOL_VERSION_CACHE[tool_name] = (mtime, saved_ver)
                return saved_ver
        except Exception:
            pass

    import sys
    md = sys.modules.get("core.media_downloader")
    subp = getattr(md, "subprocess", subprocess) if md else subprocess
    try:
        cmd = [path] + DEPENDENCY_TOOLS[tool_name]["version_cmd"]
        clean_env = get_clean_env(str(BIN_DIR))
        res = subp.run(cmd, capture_output=True, text=True, timeout=5, env=clean_env)
        out = (res.stdout + res.stderr).strip()
        if not out:
            ver = "Installed"
        else:
            first_line = out.splitlines()[0]
            m = re.search(r"v?(\d+[\d.a-zA-Z_\-]+)", first_line)
            ver = f"v{m.group(1)}" if m else first_line[:15]
    except Exception:
        ver = "Installed"

    if ver:
        _TOOL_VERSION_CACHE[tool_name] = (mtime, ver)
        try:
            v_data = {}
            if v_file.exists():
                try:
                    v_data = json.loads(v_file.read_text(encoding="utf-8"))
                except Exception:
                    v_data = {}
            v_data[f"{tool_name}_version"] = ver
            v_data[f"{tool_name}_mtime"] = mtime
            v_file.write_text(json.dumps(v_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return ver


class DependencyManagerWorker(QThread):
    """
    Worker thread to check, download, extract, and update external dependencies:
    yt-dlp, ffmpeg, ffprobe, deno, and AtomicParsley.
    Emits tool_status_signal(tool_name, display_text, color_type) where color_type is 'green', 'yellow', or 'gray'.
    """

    tool_status_signal = pyqtSignal(str, str, str)
    all_finished_signal = pyqtSignal()

    def __init__(self, force_download: bool = False, target_tool: str = ""):
        super().__init__()
        self.force_download = force_download
        self.target_tool = target_tool

    def run(self):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_names = [self.target_tool] if self.target_tool and self.target_tool in DEPENDENCY_TOOLS else ["yt-dlp", "ffmpeg", "ffprobe", "deno", "AtomicParsley"]
        downloaded_extract_urls = set()

        for tool in tool_names:
            if self.isInterruptionRequested():
                break

            binary_name = DEPENDENCY_TOOLS[tool]["binary_name"]
            local_bin = BIN_DIR / binary_name
            is_local_installed = local_bin.exists() and os.access(local_bin, os.X_OK)

            if self.force_download:
                self.tool_status_signal.emit(tool, f"{tool} (Checking...)", "yellow")
                self.msleep(40)

            # Skip redundant archive download if previously extracted by companion tool (e.g., ffprobe from ffmpeg)
            tool_url = DEPENDENCY_TOOLS[tool]["url"]
            if self.force_download and tool_url in downloaded_extract_urls and is_local_installed:
                ver = get_tool_version(tool, local_only=True) or "vLatest"
                self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")
                continue

            if not is_local_installed:
                success = self._download_and_install_tool(tool)
                if success:
                    downloaded_extract_urls.add(tool_url)
            elif self.force_download:
                needs_update, latest_ver = self._is_update_available(tool)
                if needs_update:
                    success = self._download_and_install_tool(tool)
                    if success:
                        downloaded_extract_urls.add(tool_url)
                else:
                    ver = latest_ver or get_tool_version(tool, local_only=True) or "Installed"
                    self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")
            else:
                ver = get_tool_version(tool, local_only=True) or "Installed"
                self.tool_status_signal.emit(tool, f"{tool} ({ver})", "green")
                # Perform light background update check for version-tagged tools
                if tool in ("yt-dlp", "deno"):
                    try:
                        needs_update, latest_ver = self._is_update_available(tool)
                        if needs_update and latest_ver and latest_ver.lstrip("v") != ver.lstrip("v"):
                            self.tool_status_signal.emit(tool, f"{tool} (Update Available: {latest_ver})", "yellow")
                    except Exception:
                        pass

        self.all_finished_signal.emit()

    def _save_tool_metadata(self, key: str, value: str):
        v_file = BIN_DIR / ".versions.json"
        data = {}
        if v_file.exists():
            try:
                data = json.loads(v_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[key] = value
        try:
            v_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _is_update_available(self, tool_name: str) -> tuple[bool, str]:
        """
        Checks whether remote version is newer than installed version.
        Returns (needs_update, current_or_latest_version_string).
        """
        import sys
        md = sys.modules.get("core.media_downloader")
        ver_fn = getattr(md, "get_tool_version", get_tool_version) if md else get_tool_version
        local_ver = ver_fn(tool_name, local_only=True)
        if not local_ver:
            return True, ""

        if tool_name == "AtomicParsley":
            # Fixed release URL pinned in configuration
            return False, local_ver

        url = DEPENDENCY_TOOLS[tool_name]["url"]

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
        )

        loc = ""
        try:
            resp = opener.open(req, timeout=8)
            loc = resp.headers.get("Location", "")
            resp.close()
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location", "")
        except Exception:
            return False, local_ver

        if tool_name in ("yt-dlp", "deno"):
            m = re.search(r"/releases/download/([^/]+)/", loc)
            if m:
                remote_tag = m.group(1).lstrip("v")
                local_clean = local_ver.lstrip("v")
                if remote_tag == local_clean:
                    return False, local_ver
                return True, f"v{remote_tag}"
        elif tool_name in ("ffmpeg", "ffprobe"):
            head_req = urllib.request.Request(
                loc,
                method="HEAD",
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
            )
            try:
                with urllib.request.urlopen(head_req, timeout=8) as head_resp:
                    remote_etag = head_resp.headers.get("etag", "").strip('"')
                    v_file = BIN_DIR / ".versions.json"
                    saved_etag = ""
                    if v_file.exists():
                        try:
                            saved_etag = json.loads(v_file.read_text(encoding="utf-8")).get("ffmpeg_etag", "")
                        except Exception:
                            pass
                    if saved_etag and saved_etag == remote_etag:
                        return False, local_ver
                    elif not saved_etag and remote_etag:
                        self._save_tool_metadata("ffmpeg_etag", remote_etag)
                        return False, local_ver
            except Exception:
                return False, local_ver

        return True, "vLatest"

    def _download_and_install_tool(self, tool_name: str) -> bool:
        import ssl
        tool_info = DEPENDENCY_TOOLS[tool_name]
        url = tool_info["url"]
        tool_type = tool_info["type"]
        binary_name = tool_info["binary_name"]

        self.tool_status_signal.emit(tool_name, f"{tool_name} (Downloading...)", "yellow")

        cache_dir = get_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)
        tmp_download_path = Path(os.path.join(cache_dir, f"{tool_name}_download.tmp"))

        last_emit_time = 0.0

        def _reporthook(blocknum, blocksize, totalsize):
            nonlocal last_emit_time
            if self.isInterruptionRequested():
                raise InterruptedError("Download interrupted")
            now = time.monotonic()
            dl_bytes = blocknum * blocksize
            is_done = totalsize > 0 and dl_bytes >= totalsize
            if not is_done and now - last_emit_time < 0.1:
                return
            last_emit_time = now
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

            if tool_name in ("ffmpeg", "ffprobe") and resp:
                remote_etag = resp.headers.get("etag", "").strip('"')
                if remote_etag:
                    self._save_tool_metadata("ffmpeg_etag", remote_etag)

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

        last_cb_time = 0.0

        def _reporthook(blocknum, blocksize, totalsize):
            nonlocal last_cb_time
            if totalsize > 0 and progress_callback:
                now = time.monotonic()
                dl_bytes = blocknum * blocksize
                is_done = dl_bytes >= totalsize
                if not is_done and now - last_cb_time < 0.1:
                    return
                last_cb_time = now
                percent = int((dl_bytes / totalsize) * 100)
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
