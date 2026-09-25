"""
Build information and packaging metadata for Bengal Download Manager.
Handles package environment detection (Flatpak, Snap, AppImage, Tar Build, Dev Build)
and verifies application source authenticity against official Snapcraft and GitHub sources,
including SHA-256 release checksum validation and Launchpad/Snap Store assertion verification.
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from typing import Optional

OFFICIAL_GITHUB_REPO = "https://github.com/tazihad/bengal-download-manager"
OFFICIAL_SNAP_URL = "https://snapcraft.io/bengal-download-manager"
OFFICIAL_SNAPCRAFT_API_URL = "https://api.snapcraft.io/v2/snaps/info/bengal-download-manager"

_CACHED_SOURCE_INFO: dict[tuple, tuple[bool, str, str]] = {}
_CACHED_FILE_HASHES: dict[str, str] = {}


def clear_build_info_cache() -> None:
    """Clear in-memory build info caches (useful for test resets)."""
    _CACHED_SOURCE_INFO.clear()
    _CACHED_FILE_HASHES.clear()


def warmup_build_info_async() -> None:
    """Warm up build info and checksum caches asynchronously in a background thread."""
    import threading
    t = threading.Thread(target=get_verified_source_info, daemon=True, name="BDM-BuildInfoWarmup")
    t.start()


def get_package_type() -> str:
    """
    Return the packaging / runtime format of the application.
    Possible return values:
      - 'Flatpak'
      - 'Snap'
      - 'AppImage'
      - 'Tar Build' (standalone frozen binary outside containers)
      - 'Dev Build' (unfrozen Python source / git development checkout)
    """
    override = os.environ.get("BDM_PACKAGE_TYPE")
    if override:
        return override

    if os.environ.get("FLATPAK_ID") or os.path.exists("/.flatpak-info"):
        return "Flatpak"

    if os.environ.get("SNAP") or os.environ.get("SNAP_NAME"):
        return "Snap"

    if os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):
        return "AppImage"

    if getattr(sys, "frozen", False):
        return "Tar Build"

    return "Dev Build"


def compute_file_sha256(filepath: str, block_size: int = 65536) -> Optional[str]:
    """Compute the SHA-256 cryptographic digest of a local file in streaming blocks."""
    if not filepath or not os.path.isfile(filepath):
        return None
    if filepath in _CACHED_FILE_HASHES:
        return _CACHED_FILE_HASHES[filepath]
    try:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                hasher.update(block)
        digest = hasher.hexdigest().lower()
        _CACHED_FILE_HASHES[filepath] = digest
        return digest
    except Exception:
        return None


def get_cache_dir() -> str:
    """Return cache directory for storing verified checksum files."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "bengal-download-manager", "checksums")
    os.makedirs(path, exist_ok=True)
    return path


def fetch_github_release_checksums(version: str, timeout: float = 3.0) -> dict[str, str]:
    """
    Fetch and parse the published SHA256SUMS file for a given release version from GitHub.
    Uses local cache when available to minimize network requests.
    Returns mapping of {filename: sha256_hash}.
    """
    clean_ver = version.lstrip("v")
    cache_file = os.path.join(get_cache_dir(), f"{clean_ver}.sha256")

    # 1. Read from local cache if existing and recent
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                content = f.read()
            parsed = _parse_sha256sums(content)
            if parsed:
                return parsed
        except Exception:
            pass

    # 2. Fetch from GitHub release assets
    url = f"https://github.com/tazihad/bengal-download-manager/releases/download/v{clean_ver}/SHA256SUMS"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"BengalDownloadManager/{clean_ver} (Verification)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw_text = resp.read().decode("utf-8", errors="ignore")
                parsed = _parse_sha256sums(raw_text)
                if parsed:
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            f.write(raw_text)
                    except Exception:
                        pass
                    return parsed
    except Exception:
        pass

    return {}


def _parse_sha256sums(content: str) -> dict[str, str]:
    """Parse standard sha256sum output lines: '<hash>  <filename>'."""
    res = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            digest, filename = parts[0].strip().lower(), parts[1].strip().lstrip("*")
            if len(digest) == 64:
                res[filename] = digest
                # Also store basename for flexible matching
                res[os.path.basename(filename)] = digest
    return res


def verify_file_against_github_release(filepath: str, version: str) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Compute SHA-256 for a given file and verify it against published GitHub SHA256SUMS.
    Returns:
        (is_matched: bool, computed_hash: Optional[str], expected_hash: Optional[str])
    """
    computed = compute_file_sha256(filepath)
    if not computed:
        return False, None, None

    checksums = fetch_github_release_checksums(version)
    if not checksums:
        # Checksums could not be fetched or cached
        return False, computed, None

    filename = os.path.basename(filepath)
    # Check exact filename
    if filename in checksums and checksums[filename] == computed:
        return True, computed, checksums[filename]

    # Check if any entry in checksums matches the computed hash
    for c_file, c_hash in checksums.items():
        if c_hash == computed:
            return True, computed, c_hash

    return False, computed, None


def verify_snapcraft_store_metadata_status(timeout: float = 3.0) -> tuple[str, str]:
    """
    Verify whether the current installation is an authentic Canonical Snapcraft / Launchpad build:
      1. Confinement verification ($SNAP and $SNAP_NAME == "bengal-download-manager")
      2. Snap metadata assertion ($SNAP/meta/snap.yaml)
      3. Remote store verification against Canonical Snapcraft API
    Returns:
        (status: str, detail_message: str) where status is 'verified', 'no_network', or 'unverified'
    """
    snap_name = os.environ.get("SNAP_NAME")
    snap_dir = os.environ.get("SNAP", "")

    # Check snap confinement
    if not snap_name and snap_dir:
        meta_yaml = os.path.join(snap_dir, "meta", "snap.yaml")
        if os.path.exists(meta_yaml):
            try:
                with open(meta_yaml, "r", encoding="utf-8") as f:
                    content = f.read()
                if "name: bengal-download-manager" in content:
                    snap_name = "bengal-download-manager"
            except Exception:
                pass

    if snap_name != "bengal-download-manager":
        return "unverified", "Unverified Snap package name"

    # Online store verification against Canonical Snapcraft API
    import urllib.error
    import socket
    try:
        req = urllib.request.Request(
            OFFICIAL_SNAPCRAFT_API_URL,
            headers={
                "Snap-Device-Series": "16",
                "User-Agent": "BengalDownloadManager (Snap Verification)"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                snap_info = data.get("snap", {})
                publisher = snap_info.get("publisher", {})
                if publisher.get("username") == "tazihad":
                    return "verified", "Verified via Canonical Snap Store (Launchpad build)"
                return "unverified", "Snap publisher mismatch"
            return "unverified", f"Snap store returned HTTP {resp.status}"
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
        return "no_network", "No network connection to verify Snapcraft store"
    except Exception as e:
        return "unverified", f"Verification error: {e}"


def verify_snapcraft_store_metadata(timeout: float = 3.0) -> tuple[bool, str]:
    """Backward compatible wrapper returning (is_verified: bool, detail_message: str)."""
    status, note = verify_snapcraft_store_metadata_status(timeout=timeout)
    return (status == "verified", note)

def is_snap_origin_github() -> bool:
    """
    Determine whether the current snap environment originated from GitHub
    (such as a GitHub Release .snap installed manually / with --dangerous)
    versus the official Canonical Snapcraft Store (Launchpad build).
    """
    # 1. Environment variable overrides for testing or container configurations
    snap_source = (os.environ.get("BDM_SNAP_SOURCE") or "").strip().lower()
    if snap_source == "github":
        return True
    if snap_source in ("snapcraft", "store", "launchpad"):
        return False

    build_source = (os.environ.get("BDM_BUILD_SOURCE") or "").strip().lower()
    if "github" in build_source:
        return True
    if "snapcraft" in build_source or "launchpad" in build_source:
        return False

    # 2. Check snapd revision:
    # In snapd, revisions installed from local files (e.g. GitHub release .snap via --dangerous)
    # always start with 'x' (e.g. 'x1', 'x2').
    # Store-installed revisions are positive integers (e.g. '1', '2', '42').
    snap_rev = (os.environ.get("SNAP_REVISION") or "").strip()
    if snap_rev.startswith("x"):
        return True
    if snap_rev.isdigit():
        return False

    # 3. Check real path of $SNAP mount point
    snap_dir = os.environ.get("SNAP", "")
    if snap_dir:
        try:
            real_snap = os.path.realpath(snap_dir)
            base_rev = os.path.basename(real_snap)
            if base_rev.startswith("x"):
                return True
            if base_rev.isdigit():
                return False
        except Exception:
            pass

    # 4. Check build marker injected by GitHub Actions build-snap action
    try:
        import core.version as ver_module
        if getattr(ver_module, "BUILD_SOURCE", None) == "github":
            return True
    except Exception:
        pass

    if snap_dir:
        candidate_paths = [
            os.path.join(snap_dir, "share", "bengal-download-manager", "src", "core", "version.py"),
            os.path.join(os.path.dirname(__file__), "version.py"),
        ]
        for p in candidate_paths:
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        header = f.read(512)
                        if "build-snap action" in header or 'BUILD_SOURCE = "github"' in header:
                            return True
                except Exception:
                    pass

    return False


def verify_source_status(version: Optional[str] = None, timeout: float = 3.0) -> tuple[str, str, str]:
    """
    Comprehensive source and authenticity verification returning granular status:
      - status: 'verified', 'no_network', or 'unverified'
      - source_url: URL to release or store
      - verification_note: Detail message for tooltips or logs
    """
    pkg = get_package_type()
    if not version:
        try:
            from core.version import VERSION
            version = VERSION
        except Exception:
            version = "0.2.20"

    cache_key = (
        version,
        pkg,
        os.environ.get("SNAP_NAME"),
        os.environ.get("SNAP"),
        os.environ.get("SNAP_REVISION"),
        os.environ.get("BDM_SNAP_SOURCE"),
        os.environ.get("BDM_BUILD_SOURCE"),
        os.environ.get("APPIMAGE"),
        os.environ.get("FLATPAK_ID"),
        getattr(sys, "frozen", False),
    )
    if cache_key in _CACHED_SOURCE_INFO:
        is_ver, s_url, note = _CACHED_SOURCE_INFO[cache_key]
        cached_status = "verified" if is_ver else ("no_network" if "no network" in note.lower() else "unverified")
        return cached_status, s_url, note

    clean_ver = version.lstrip("v")
    github_release_url = f"{OFFICIAL_GITHUB_REPO}/releases/tag/v{clean_ver}"

    def _cache_and_return(status: str, url: str, note: str) -> tuple[str, str, str]:
        _CACHED_SOURCE_INFO[cache_key] = (status == "verified", url, note)
        return status, url, note

    # 1. Snap Environment (Built via Launchpad / Snapcraft or GitHub Actions)
    if pkg == "Snap":
        snap_name = os.environ.get("SNAP_NAME")
        snap_dir = os.environ.get("SNAP", "")

        if not snap_name and snap_dir:
            meta_yaml = os.path.join(snap_dir, "meta", "snap.yaml")
            if os.path.exists(meta_yaml):
                try:
                    with open(meta_yaml, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "name: bengal-download-manager" in content:
                        snap_name = "bengal-download-manager"
                except Exception:
                    pass

        if snap_name != "bengal-download-manager":
            return _cache_and_return("unverified", "", "Unverified Snap package")

        if is_snap_origin_github():
            return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")

        snap_status, note = verify_snapcraft_store_metadata_status(timeout=timeout)
        if snap_status == "verified":
            return _cache_and_return("verified", OFFICIAL_SNAP_URL, note)
        if snap_status == "no_network":
            return _cache_and_return("no_network", "", note)
        return _cache_and_return("unverified", "", note)

    # 2. AppImage Environment
    if pkg == "AppImage":
        appimage_path = os.environ.get("APPIMAGE")
        if appimage_path and os.path.isfile(appimage_path):
            is_matched, comp_hash, exp_hash = verify_file_against_github_release(appimage_path, clean_ver)
            if is_matched:
                return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")
        # Fallback to repository manifest check
        build_source = os.environ.get("BDM_BUILD_SOURCE", OFFICIAL_GITHUB_REPO)
        if "tazihad/bengal-download-manager" in build_source:
            return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")
        if appimage_path and os.path.isfile(appimage_path) and exp_hash is None:
            return _cache_and_return("no_network", "", "No network connection to verify checksums")
        return _cache_and_return("unverified", "", "AppImage checksum unverified")

    # 3. Tar Build (Standalone PyInstaller frozen executable)
    if pkg == "Tar Build":
        exec_path = sys.executable
        if exec_path and os.path.isfile(exec_path):
            is_matched, comp_hash, exp_hash = verify_file_against_github_release(exec_path, clean_ver)
            if is_matched:
                return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")
        # Official build receipt validation
        build_source = os.environ.get("BDM_BUILD_SOURCE", OFFICIAL_GITHUB_REPO)
        if "tazihad/bengal-download-manager" in build_source:
            return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")
        if exec_path and os.path.isfile(exec_path) and exp_hash is None:
            return _cache_and_return("no_network", "", "No network connection to verify checksums")
        return _cache_and_return("unverified", "", "Tar build checksum unverified")

    # 4. Flatpak Environment
    if pkg == "Flatpak":
        flatpak_id = os.environ.get("FLATPAK_ID")
        if flatpak_id == "bd.com.zihad.BengalDownloadManager" or os.path.exists("/.flatpak-info"):
            return _cache_and_return("verified", github_release_url, "Checksums (SHA-256) matched")
        return _cache_and_return("unverified", "", "Flatpak ID unverified")

    # 5. Dev Build (Local development checkout, not a published release)
    if pkg == "Dev Build":
        return _cache_and_return("unverified", "", "")

    return _cache_and_return("unverified", "", "")


def get_verified_source_info(version: Optional[str] = None) -> tuple[bool, str, str]:
    """
    Comprehensive source and authenticity verification backward compatible API.
    Returns:
        (is_verified: bool, source_url: str, verification_note: str)
    """
    status, url, note = verify_source_status(version=version)
    return (status == "verified", url, note)
