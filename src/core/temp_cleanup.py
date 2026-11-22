"""Clean up stale PyInstaller onefile extraction directories.

A PyInstaller ``--onefile`` build unpacks its payload into a temporary
``_MEIxxxxxx`` directory. The parent bootloader removes that directory when it
exits normally, but a forced termination (crash, system shutdown, Flatpak
``kill``) leaves the directory behind. Inside a Flatpak sandbox ``/tmp`` is
backed by RAM, so a handful of leftover bundles can exhaust the user's runtime
directory and prevent other applications from starting.

This module removes only directories that clearly belong to an older Bengal
Download Manager bundle. The current bundle, foreign ``_MEI*`` directories,
recent directories, and directories referenced by a live process are preserved.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

_MEI_DIR_RE = re.compile(r"^_MEI[A-Za-z0-9]{6,}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+")
# ``VERSION`` and ``base_library.zip`` are added by every Linux PyInstaller
# build, while the runtime assets identify the bundle as ours.
_REQUIRED_MARKERS = ("VERSION", "base_library.zip")
_ASSET_MARKERS = (
    "assets/bd.com.zihad.BengalDownloadManager.desktop",
    "assets/bd.com.zihad.BengalDownloadManager.png",
    "assets/logo.svg",
)
_MIN_AGE_SECONDS = 30 * 60

InUseProbe = Callable[[Path], bool]


def _looks_like_bdm_bundle(path: Path) -> bool:
    """Return True only for a PyInstaller bundle containing our application files."""
    try:
        if not all((path / marker).exists() for marker in _REQUIRED_MARKERS):
            return False
        if not any((path / marker).exists() for marker in _ASSET_MARKERS):
            return False
        version = (path / "VERSION").read_text(encoding="utf-8", errors="ignore").strip()
        return bool(_VERSION_RE.match(version))
    except OSError:
        return False


def _is_owned_by_current_user(path: Path) -> bool:
    try:
        return path.stat().st_uid == os.getuid()
    except (AttributeError, OSError):
        return False


def _directory_in_use(path: Path) -> bool:
    """Check whether any running process has files from *path* mapped."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        # Cannot verify: leave the directory alone rather than risk breaking a
        # running application.
        return True

    needles = {str(path)}
    try:
        needles.add(str(path.resolve()))
    except OSError:
        pass

    try:
        pids = [entry for entry in proc_root.iterdir() if entry.name.isdigit()]
    except OSError:
        return True

    for pid in pids:
        try:
            maps = (pid / "maps").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(needle in maps for needle in needles):
            return True
    return False


def _is_recent(path: Path, now: float, min_age_seconds: float) -> bool:
    try:
        return (now - path.stat().st_mtime) < min_age_seconds
    except OSError:
        return True


def cleanup_stale_pyinstaller_dirs(
    temp_root: Optional[os.PathLike] = None,
    *,
    min_age_seconds: float = _MIN_AGE_SECONDS,
    in_use: Optional[InUseProbe] = None,
    now: Optional[float] = None,
) -> List[Path]:
    """Remove stale Bengal Download Manager ``_MEI*`` extraction directories.

    :param temp_root: Directory to scan. Defaults to ``tempfile.gettempdir()``.
    :param min_age_seconds: Skip directories modified more recently than this.
    :param in_use: Optional probe used to detect directories used by a process.
    :param now: Optional timestamp override (used by tests).
    :returns: Paths that were successfully removed.
    """
    if not sys.platform.startswith("linux"):
        return []

    root = Path(temp_root) if temp_root is not None else Path(tempfile.gettempdir())
    timestamp = time.time() if now is None else now
    probe = in_use or _directory_in_use

    current_bundle: Optional[Path] = None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            current_bundle = Path(meipass).resolve()
        except OSError:
            current_bundle = Path(meipass)

    try:
        entries = list(root.iterdir())
    except OSError:
        return []

    removed: List[Path] = []
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
        except OSError:
            continue

        if not _MEI_DIR_RE.match(entry.name):
            continue

        try:
            resolved = entry.resolve()
        except OSError:
            resolved = entry

        if current_bundle is not None and resolved == current_bundle:
            continue

        if not _is_owned_by_current_user(entry):
            continue
        if not _looks_like_bdm_bundle(entry):
            continue
        if _is_recent(entry, timestamp, min_age_seconds):
            continue
        if probe(entry):
            continue

        shutil.rmtree(entry, ignore_errors=True)
        if not entry.exists():
            removed.append(entry)
            logger.debug("Removed stale PyInstaller temp directory: %s", entry)

    return removed
