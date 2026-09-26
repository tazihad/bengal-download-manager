"""
Video Thumbnail Generation & Management
=======================================
Provides asynchronous, resource-efficient video thumbnail extraction using ffmpeg.
Discovers ffmpeg in bundled paths, XDG data bin, XDG user bin, or system PATH.
Caches thumbnails in XDG cache directory with SHA256 keying and handles cleanup.
"""

import os
import sys
import shutil
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional, Set

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap, QPixmapCache

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


def get_thumbnail_cache_path(filepath: str) -> Optional[str]:
    """
    Computes a deterministic cache file path based on video filepath, size, and mtime.
    Returns path even if it does not yet exist on disk.
    """
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        stat = os.stat(filepath)
        raw_key = f"{os.path.abspath(filepath)}:{stat.st_size}:{stat.st_mtime_ns}"
    except Exception:
        raw_key = os.path.abspath(filepath)

    key_hash = hashlib.sha256(raw_key.encode("utf-8", errors="ignore")).hexdigest()[:24]
    thumb_path = get_thumbnail_dir() / f"thumb_{key_hash}.jpg"
    return str(thumb_path)


def delete_thumbnail(filepath: str):
    """Deletes any cached thumbnail associated with a given filepath."""
    if not filepath:
        return
    try:
        abs_path = os.path.abspath(filepath)
        # Search thumbnails dir for matching files or prefix
        thumb_dir = get_thumbnail_dir()
        if not thumb_dir.exists():
            return

        # Direct check if file still exists
        direct = get_thumbnail_cache_path(filepath)
        if direct and os.path.exists(direct):
            try:
                os.remove(direct)
                QPixmapCache.remove(direct)
            except Exception:
                pass

        # Also purge any older hashes for this absolute path if file was modified or deleted
        path_prefix_hash = hashlib.sha256(abs_path.encode("utf-8", errors="ignore")).hexdigest()[:12]
        for item in thumb_dir.glob("thumb_*.jpg"):
            # If the name contains the prefix or matches
            try:
                if item.name.startswith(f"thumb_{path_prefix_hash}"):
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
            abs_p = os.path.abspath(fp)
            active_hashes.add(hashlib.sha256(abs_p.encode("utf-8", errors="ignore")).hexdigest()[:12])
            cached = get_thumbnail_cache_path(fp)
            if cached:
                active_hashes.add(Path(cached).name)

        for item in thumb_dir.glob("thumb_*.jpg"):
            try:
                if item.name in active_hashes:
                    continue
                # Check prefix
                is_active = any(item.name.startswith(f"thumb_{p_hash}") for p_hash in active_hashes)
                if not is_active:
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
    """Background runnable worker for extracting video thumbnail."""

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


class VideoThumbnailManager(QObject):
    """
    Central manager for requesting, caching, and serving video thumbnails.
    Emits thumbnail_ready(filepath, thumb_path) when extraction succeeds.
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

    def get_cached_pixmap(self, filepath: str, max_w: int = 44, max_h: int = 30) -> Optional[QPixmap]:
        """
        Retrieves a cached QPixmap thumbnail if available, or queues extraction and returns None.
        Checks QPixmapCache memory cache first, then disk cache.
        """
        if not filepath or not os.path.exists(filepath):
            return None

        # Check if the file is a video
        if not is_video_file(filepath):
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
                from PyQt6.QtCore import Qt
                scaled = raw_pix.scaled(
                    max_w, max_h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                QPixmapCache.insert(cache_key, scaled)
                return scaled

        # Not yet on disk: queue background generation if ffmpeg is available
        self.request_thumbnail(filepath)
        return None

    def request_thumbnail(self, filepath: str):
        """Asynchronously requests thumbnail extraction for a given video file."""
        if not filepath or filepath in self._pending_tasks:
            return
        if not os.path.exists(filepath):
            return
        if not is_video_file(filepath):
            return

        ffmpeg = self._ffmpeg_bin or get_ffmpeg_path()
        if not ffmpeg:
            return

        thumb_path = get_thumbnail_cache_path(filepath)
        if not thumb_path:
            return

        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return

        self._pending_tasks.add(filepath)
        worker = _ThumbnailWorker(filepath, thumb_path, ffmpeg, self._signals)
        self._thread_pool.start(worker)

    @pyqtSlot(str, str)
    def _on_worker_finished(self, filepath: str, thumb_path: str):
        self._pending_tasks.discard(filepath)
        self.thumbnail_ready.emit(filepath, thumb_path)
