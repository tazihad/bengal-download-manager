"""
Desktop Integration Module for Bengal Download Manager.
Provides an integrated seam for system-level desktop actions:
XDG Desktop Portals, D-Bus file manager discovery, OS file opening, and autostart launchers.
"""

import os
from typing import Optional


def open_file(path: str) -> bool:
    """Opens a file using the OS-default application handler."""
    from core.utils import open_file_generic
    return open_file_generic(path)


def open_with(path: str) -> bool:
    """Displays the OS-native 'Open With' application chooser."""
    from core.utils import open_with as _utils_open_with
    return _utils_open_with(path)


def show_in_folder(path: str) -> None:
    """Highlights a file or opens its parent directory in the OS file manager."""
    from core.utils import show_in_folder as _utils_show_in_folder
    _utils_show_in_folder(path)


def choose_save_path(title: str = "Save File As", filename: str = "file", folder: str = "") -> Optional[str]:
    """Triggers the native XDG Desktop Portal SaveFile dialog."""
    from core.utils import choose_portal_save_path
    return choose_portal_save_path(title=title, filename=filename, folder=folder)


def choose_folder_path(title: str = "Select Directory", folder: str = "") -> Optional[str]:
    """Triggers the native XDG Desktop Portal folder chooser dialog."""
    from core.utils import choose_portal_folder_path
    return choose_portal_folder_path(title=title, folder=folder)


def choose_open_file_path(title: str = "Select File", folder: str = "") -> Optional[str]:
    """Triggers the native XDG Desktop Portal open file chooser dialog."""
    from core.utils import choose_portal_open_file_path
    return choose_portal_open_file_path(title=title, folder=folder)


def is_autostart_enabled() -> bool:
    """Checks whether autostart is enabled in system desktop entries."""
    from core.utils import is_autostart_enabled as _utils_is_autostart
    return _utils_is_autostart()


def set_autostart_enabled(enabled: bool, start_minimized: bool = False) -> bool:
    """Toggles desktop launcher autostart configuration."""
    from core.utils import set_autostart_enabled as _utils_set_autostart
    return _utils_set_autostart(enabled, start_minimized=start_minimized)


def get_autostart_filepath() -> str:
    """Returns the path to the user's autostart .desktop entry."""
    from core.utils import get_autostart_filepath as _utils_get_autostart
    return _utils_get_autostart()


def get_desktop_file_name() -> str:
    """
    Resolves the canonical desktop file name matching the environment.
    - Snap: snapd namespaces desktop entries as ${SNAP_INSTANCE_NAME}_${SNAP_APP_NAME}.desktop.
    - Flatpak: uses FLATPAK_ID (bd.com.zihad.BengalDownloadManager).
    - Host/Unpackaged: discovers installed desktop entries in XDG_DATA_DIRS
      or defaults to 'bd.com.zihad.BengalDownloadManager'.
    """
    if os.environ.get("SNAP"):
        snap_instance = os.environ.get("SNAP_INSTANCE_NAME") or os.environ.get("SNAP_NAME", "bengal-download-manager")
        snap_app = os.environ.get("SNAP_APP_NAME", "bengal-download-manager")
        return f"{snap_instance}_{snap_app}"

    if os.environ.get("FLATPAK_ID"):
        return os.environ.get("FLATPAK_ID")

    # If running unpackaged on host, check if an existing desktop entry is installed
    candidate_ids = [
        "bd.com.zihad.BengalDownloadManager",
        "bengal-download-manager",
        "bengal-download-manager_bengal-download-manager",
    ]
    raw_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    search_dirs = [os.path.expanduser("~/.local/share/applications")] + [
        os.path.join(d, "applications") for d in raw_dirs.split(":") if d
    ]
    for cid in candidate_ids:
        for sdir in search_dirs:
            if os.path.exists(os.path.join(sdir, f"{cid}.desktop")):
                return cid

    return "bd.com.zihad.BengalDownloadManager"

