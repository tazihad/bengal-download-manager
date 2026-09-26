"""
Video Thumbnail Generation & Management
=======================================
Provides asynchronous, resource-efficient video thumbnail extraction using ffmpeg
or direct remote thumbnail acquisition (e.g. YouTube thumbnails).
Discovers ffmpeg in bundled paths, XDG data bin, XDG user bin, or system PATH.
Caches thumbnails in XDG cache directory with SHA256 keying and handles cleanup.
"""

import os
import re
import sys
import shutil
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional, Set

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap, QPixmapCache, QImage

from core.utils import get_cache_dir, get_data_dir

logger = logging.getLogger("bengal.core.video_thumbnail")

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v",
    ".ts", ".mts", ".m2ts", ".vob", ".ogv", ".3gp", ".3g2", ".f4v"
}


def is_video_file(path_or_name: str) -> bool:
    """Returns True if the given file path or name has a recognized video extension."""
    if not path_or_name:
        return False
    ext = os.path.splitext(str(path_or_name).lower())[1]
    return ext in VIDEO_EXTENSIONS


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extracts the 11-character video ID from any valid YouTube URL."""
    if not url:
        return None
    patterns = [
        r"(?:v=|vi=)([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/(?:shorts|embed|v|live)/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?.*v=([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_youtube_thumbnail_url(url: str) -> Optional[str]:
    """Returns the standard high-quality YouTube thumbnail image URL for a YouTube video URL."""
    vid = extract_youtube_video_id(url)
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None


_THUMBNAIL_DIR = Path(get_cache_dir()) / "thumbnails"


def get_thumbnail_dir() -> Path:
    """Ensures and returns the thumbnails cache directory."""
    _THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    return _THUMBNAIL_DIR


def get_ffmpeg_path() -> Optional[str]:
    """
    Finds the ffmpeg executable across:
    1. PyInstaller / Flatpak bundled paths
    2. Local app data bin: ~/.local/share/bengal-download-manager/bin/ffmpeg
    3. User XDG bin: ~/.local/bin/ffmpeg (or XDG_BIN_HOME)
    4. System PATH via shutil.which('ffmpeg')
    """
    candidates = []

    # 1. Bundled / Application path
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "bin" / "ffmpeg")
    app_dir = Path(sys.executable).parent
    candidates.append(app_dir / "bin" / "ffmpeg")
    candidates.append(app_dir / "ffmpeg")

    # Flatpak sandbox binary path
    candidates.append(Path("/app/bin/ffmpeg"))

    # 2. XDG data dir for bengal-download-manager
    data_bin = Path(get_data_dir()) / "bin" / "ffmpeg"
    candidates.append(data_bin)

    # 3. User XDG bin (~/.local/bin or XDG_BIN_HOME)
    xdg_bin_env = os.environ.get("XDG_BIN_HOME")
    if xdg_bin_env:
        candidates.append(Path(xdg_bin_env) / "ffmpeg")
    candidates.append(Path.home() / ".local" / "bin" / "ffmpeg")

    for p in candidates:
        try:
            if p.is_file() and os.access(p, os.X_OK):
                return str(p.resolve())
        except Exception:
            continue

    # 4. System PATH
    sys_path = shutil.which("ffmpeg")
    if sys_path and os.access(sys_path, os.X_OK):
        return sys_path

    return None


_FILEPATH_TO_THUMB_MAP: dict[str, str] = {}


def register_thumbnail_file(filepath: str, thumb_file_path: str):
    """Associates a pre-existing thumbnail image file (e.g. downloaded YouTube thumbnail) with a video filepath."""
    if not filepath or not thumb_file_path or not os.path.exists(thumb_file_path):
        return
    abs_fp = os.path.abspath(os.path.normpath(filepath))
    _FILEPATH_TO_THUMB_MAP[abs_fp] = thumb_file_path
    _FILEPATH_TO_THUMB_MAP[filepath] = thumb_file_path
    # Also copy to standard thumbnail cache path so it persists
    try:
        cache_dest = get_thumbnail_cache_path(filepath)
        if cache_dest and cache_dest != thumb_file_path:
            shutil.copyfile(thumb_file_path, cache_dest)
            _FILEPATH_TO_THUMB_MAP[abs_fp] = cache_dest
    except Exception:
        pass


def get_thumbnail_cache_path(filepath: str) -> Optional[str]:
    """
    Computes a deterministic cache file path based on normalized absolute filepath.
    Returns path even if it does not yet exist on disk.
    """
    if not filepath:
        return None

    abs_fp = os.path.abspath(os.path.normpath(filepath))
    mapped = _FILEPATH_TO_THUMB_MAP.get(abs_fp) or _FILEPATH_TO_THUMB_MAP.get(filepath)
    if mapped and os.path.exists(mapped) and os.path.getsize(mapped) > 0:
        return mapped

    key_hash = hashlib.sha256(abs_fp.encode("utf-8", errors="ignore")).hexdigest()[:24]
    thumb_path = get_thumbnail_dir() / f"thumb_{key_hash}.jpg"
    return str(thumb_path)


def download_remote_thumbnail_sync(thumb_url: str, output_path: str) -> bool:
    """Synchronously downloads a remote image (e.g. YouTube thumbnail) into output_path."""
    if not thumb_url or not output_path:
        return False
    import urllib.request
    import ssl
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    urls_to_try = [thumb_url]
    # If high-quality fails, fallback to medium quality
    if "hqdefault.jpg" in thumb_url:
        urls_to_try.append(thumb_url.replace("hqdefault.jpg", "mqdefault.jpg"))

    for u in urls_to_try:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0)"})
            data = None
            try:
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = resp.read()
            except Exception:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                    data = resp.read()

            if data and len(data) > 0:
                with open(output_path, "wb") as f:
                    f.write(data)
                # Verify that it is a valid decodable image
                img = QImage(output_path)
                if not img.isNull():
                    return True
                else:
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("[video_thumbnail] Failed download attempt for %s: %s", u, e)

    return False


def delete_thumbnail(filepath: str):
    """Deletes any cached thumbnail associated with a given filepath."""
    if not filepath:
        return
    try:
        abs_path = os.path.abspath(os.path.normpath(filepath))
        _FILEPATH_TO_THUMB_MAP.pop(abs_path, None)
        _FILEPATH_TO_THUMB_MAP.pop(filepath, None)

        thumb_dir = get_thumbnail_dir()
        if not thumb_dir.exists():
            return

        direct = get_thumbnail_cache_path(filepath)
        if direct and os.path.exists(direct):
            try:
                os.remove(direct)
                QPixmapCache.remove(direct)
            except Exception:
                pass

        path_hash = hashlib.sha256(abs_path.encode("utf-8", errors="ignore")).hexdigest()[:24]
        for item in thumb_dir.glob(f"thumb_{path_hash}*"):
            try:
                item.unlink(missing_ok=True)
                QPixmapCache.remove(str(item))
            except Exception:
                pass
    except Exception as e:
        logger.debug("[video_thumbnail] delete_thumbnail error for %s: %s", filepath, e)


def cleanup_orphaned_thumbnails(active_filepaths: Set[str]):
    """Removes cached thumbnails that no longer correspond to any active download in the list."""
    try:
        thumb_dir = get_thumbnail_dir()
        if not thumb_dir.exists():
            return

        active_hashes = set()
        for fp in active_filepaths:
            if not fp:
                continue
            abs_p = os.path.abspath(os.path.normpath(fp))
            active_hashes.add(f"thumb_{hashlib.sha256(abs_p.encode('utf-8', errors='ignore')).hexdigest()[:24]}.jpg")
            cached = get_thumbnail_cache_path(fp)
            if cached:
                active_hashes.add(Path(cached).name)

        for item in thumb_dir.glob("thumb_*.jpg"):
            try:
                if item.name not in active_hashes:
                    item.unlink(missing_ok=True)
                    QPixmapCache.remove(str(item))
            except Exception:
                pass
    except Exception as e:
        logger.debug("[video_thumbnail] cleanup_orphaned_thumbnails error: %s", e)


def generate_video_thumbnail_sync(video_path: str, output_path: str, ffmpeg_bin: Optional[str] = None) -> bool:
    """
    Low-resource, fast ffmpeg thumbnail extraction.
    - Fast input seek (-ss 00:00:02 before -i)
    - Single thread (-threads 1)
    - Scale width to 160px keeping aspect ratio with fast bilinear filter
    - Single frame (-vframes 1)
    - Disables audio/subtitles/data streams (-an -sn -dn)
    """
    if not os.path.exists(video_path):
        return False

    ffmpeg = ffmpeg_bin or get_ffmpeg_path()
    if not ffmpeg:
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Fast seek at 2.0s, fallback to 0.0s if extraction fails
    for seek_time in ["00:00:02", "00:00:00"]:
        cmd = [
            ffmpeg,
            "-y",
            "-ss", seek_time,
            "-i", video_path,
            "-vframes", "1",
            "-an", "-sn", "-dn",
            "-vf", "scale=160:-1:flags=fast_bilinear",
            "-threads", "1",
            "-q:v", "3",
            output_path
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False
            )
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception as e:
            logger.debug("[video_thumbnail] ffmpeg run failed for %s (seek=%s): %s", video_path, seek_time, e)

    return False


class _ThumbnailWorkerSignals(QObject):
    finished = pyqtSignal(str, str)  # filepath, thumbnail_path


class _ThumbnailWorker(QRunnable):
    """Background runnable worker for extracting video thumbnail with ffmpeg."""

    def __init__(self, filepath: str, output_path: str, ffmpeg_bin: str, signals: _ThumbnailWorkerSignals):
        super().__init__()
        self.filepath = filepath
        self.output_path = output_path
        self.ffmpeg_bin = ffmpeg_bin
        self.signals = signals

    @pyqtSlot()
    def run(self):
        try:
            success = generate_video_thumbnail_sync(self.filepath, self.output_path, self.ffmpeg_bin)
            if success:
                self.signals.finished.emit(self.filepath, self.output_path)
        except Exception as e:
            logger.debug("[video_thumbnail] Worker error on %s: %s", self.filepath, e)


class _RemoteThumbnailWorker(QRunnable):
    """Background runnable worker for fetching remote/YouTube thumbnail."""

    def __init__(self, filepath: str, thumb_url: str, output_path: str, signals: _ThumbnailWorkerSignals):
        super().__init__()
        self.filepath = filepath
        self.thumb_url = thumb_url
        self.output_path = output_path
        self.signals = signals

    @pyqtSlot()
    def run(self):
        try:
            success = download_remote_thumbnail_sync(self.thumb_url, self.output_path)
            if success:
                register_thumbnail_file(self.filepath, self.output_path)
                self.signals.finished.emit(self.filepath, self.output_path)
        except Exception as e:
            logger.debug("[video_thumbnail] Remote worker error on %s: %s", self.filepath, e)


class VideoThumbnailManager(QObject):
    """
    Central manager for requesting, caching, and serving video thumbnails.
    Emits thumbnail_ready(filepath, thumb_path) when extraction or download succeeds.
    """

    thumbnail_ready = pyqtSignal(str, str)

    _instance: Optional["VideoThumbnailManager"] = None

    @classmethod
    def instance(cls) -> "VideoThumbnailManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._pending_tasks: Set[str] = set()
        self._signals = _ThumbnailWorkerSignals()
        self._signals.finished.connect(self._on_worker_finished)
        self._ffmpeg_bin: Optional[str] = get_ffmpeg_path()
        self._checked_ffmpeg = True

    def refresh_ffmpeg(self) -> Optional[str]:
        self._ffmpeg_bin = get_ffmpeg_path()
        return self._ffmpeg_bin

    def is_ffmpeg_available(self) -> bool:
        if not self._ffmpeg_bin:
            self._ffmpeg_bin = get_ffmpeg_path()
        return bool(self._ffmpeg_bin)

    def get_cached_pixmap(
        self,
        filepath: str,
        max_w: int = 44,
        max_h: int = 30,
        url: Optional[str] = None,
        thumb_url: Optional[str] = None
    ) -> Optional[QPixmap]:
        """
        Retrieves a cached QPixmap thumbnail if available, or queues background acquisition and returns None.
        Checks QPixmapCache memory cache first, then disk cache.
        Supports both local video files and YouTube / remote video URLs.
        """
        if not filepath:
            return None

        # Check if video by extension or url
        is_vid = is_video_file(filepath) or (url and bool(extract_youtube_video_id(url)))
        if not is_vid:
            return None

        thumb_path = get_thumbnail_cache_path(filepath)
        if not thumb_path:
            return None

        cache_key = f"{thumb_path}_{max_w}_{max_h}"
        pix = QPixmapCache.find(cache_key)
        if pix:
            return pix

        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            raw_pix = QPixmap(thumb_path)
            if not raw_pix.isNull():
                scaled = raw_pix.scaled(
                    max_w, max_h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                QPixmapCache.insert(cache_key, scaled)
                return scaled

        # Not yet on disk: queue background generation / download
        self.request_thumbnail(filepath, url=url, thumb_url=thumb_url)
        return None

    def request_remote_thumbnail(self, filepath: str, thumb_url: str):
        """Asynchronously downloads and caches a remote thumbnail (e.g. YouTube)."""
        if not filepath or not thumb_url:
            return
        abs_fp = os.path.abspath(os.path.normpath(filepath))
        if abs_fp in self._pending_tasks or filepath in self._pending_tasks:
            return

        thumb_path = get_thumbnail_cache_path(filepath)
        if not thumb_path:
            return

        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return

        self._pending_tasks.add(abs_fp)
        self._pending_tasks.add(filepath)
        worker = _RemoteThumbnailWorker(filepath, thumb_url, thumb_path, self._signals)
        self._thread_pool.start(worker)

    def request_thumbnail(self, filepath: str, url: Optional[str] = None, thumb_url: Optional[str] = None):
        """
        Asynchronously requests thumbnail acquisition:
        - If remote thumb_url or YouTube URL is present, fetches remote thumbnail.
        - Otherwise, extracts thumbnail from local video file using ffmpeg.
        """
        if not filepath:
            return

        abs_fp = os.path.abspath(os.path.normpath(filepath))
        if abs_fp in self._pending_tasks or filepath in self._pending_tasks:
            return

        # 1. Prefer remote thumbnail / YouTube thumbnail
        target_remote = thumb_url
        if not target_remote and url:
            target_remote = get_youtube_thumbnail_url(url)

        thumb_path = get_thumbnail_cache_path(filepath)
        if not thumb_path:
            return

        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return

        if target_remote:
            self.request_remote_thumbnail(filepath, target_remote)
            return

        # 2. Local video thumbnail via ffmpeg
        if not os.path.exists(filepath) or not is_video_file(filepath):
            return

        ffmpeg = self._ffmpeg_bin or get_ffmpeg_path()
        if not ffmpeg:
            return

        self._pending_tasks.add(abs_fp)
        self._pending_tasks.add(filepath)
        worker = _ThumbnailWorker(filepath, thumb_path, ffmpeg, self._signals)
        self._thread_pool.start(worker)

    @pyqtSlot(str, str)
    def _on_worker_finished(self, filepath: str, thumb_path: str):
        abs_fp = os.path.abspath(os.path.normpath(filepath))
        self._pending_tasks.discard(abs_fp)
        self._pending_tasks.discard(filepath)
        self.thumbnail_ready.emit(filepath, thumb_path)
