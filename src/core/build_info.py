"""
Build information and packaging metadata for Bengal Download Manager.
Handles package environment detection (Flatpak, Snap, AppImage, Tar Build, Dev Build)
and verifies application source authenticity against official Snapcraft and GitHub sources.
"""

import os
import subprocess
import sys

OFFICIAL_GITHUB_REPO = "https://github.com/tazihad/bengal-download-manager"
OFFICIAL_SNAP_URL = "https://snapcraft.io/bengal-download-manager"


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


def get_verified_source_info() -> tuple[bool, str]:
    """
    Verify whether the application source originates from:
      - https://snapcraft.io/bengal-download-manager (Snap)
      - https://github.com/tazihad/bengal-download-manager (Dev, Tar, AppImage, Flatpak)

    Returns:
        (is_verified: bool, source_url: str)
    """
    pkg = get_package_type()

    if pkg == "Snap":
        snap_name = os.environ.get("SNAP_NAME")
        if not snap_name:
            snap_dir = os.environ.get("SNAP", "")
            meta_path = os.path.join(snap_dir, "meta", "snap.yaml")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        if "name: bengal-download-manager" in f.read():
                            snap_name = "bengal-download-manager"
                except Exception:
                    pass
        if snap_name == "bengal-download-manager":
            return True, OFFICIAL_SNAP_URL
        return False, ""

    if pkg == "Dev Build":
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                remote_url = res.stdout.strip()
                if "tazihad/bengal-download-manager" in remote_url:
                    return True, OFFICIAL_GITHUB_REPO
        except Exception:
            pass
        return False, ""

    if pkg == "Flatpak":
        flatpak_id = os.environ.get("FLATPAK_ID")
        if flatpak_id == "bd.com.zihad.BengalDownloadManager" or os.path.exists("/.flatpak-info"):
            return True, OFFICIAL_GITHUB_REPO

    if pkg in ("Tar Build", "AppImage"):
        # Built from official repository release pipeline
        build_source = os.environ.get("BDM_BUILD_SOURCE", OFFICIAL_GITHUB_REPO)
        if "tazihad/bengal-download-manager" in build_source:
            return True, OFFICIAL_GITHUB_REPO

    return False, ""
