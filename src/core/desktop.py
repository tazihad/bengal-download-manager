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
    - Flatpak: uses FLATPAK_ID (io.github.tazihad.bengal-download-manager).
    - Host/Unpackaged: discovers installed desktop entries in XDG_DATA_DIRS
      or defaults to 'io.github.tazihad.bengal-download-manager'.
    """
    if os.environ.get("SNAP"):
        snap_instance = os.environ.get("SNAP_INSTANCE_NAME") or os.environ.get("SNAP_NAME", "bengal-download-manager")
        snap_app = os.environ.get("SNAP_APP_NAME", "bengal-download-manager")
        return f"{snap_instance}_{snap_app}"

    if os.environ.get("FLATPAK_ID"):
        return os.environ.get("FLATPAK_ID")

    # If running unpackaged on host, check if an existing desktop entry is installed
    candidate_ids = [
        "io.github.tazihad.bengal-download-manager",
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

    return "io.github.tazihad.bengal-download-manager"


def ensure_desktop_integration() -> None:
    """
    On Linux (outside Snap and Flatpak), ensures a valid .desktop file and hicolor icon
    are installed in ~/.local/share/applications/ and ~/.local/share/icons/hicolor/.
    This ensures GNOME Shell (Ubuntu Wayland), KDE, and other Wayland compositors
    can immediately resolve the application name and high-res icon in panels/docks.
    """
    import sys
    if sys.platform != "linux":
        return
    # In Snap or Flatpak, the packaging container manages desktop entries
    if os.environ.get("SNAP") or os.environ.get("FLATPAK_ID"):
        return
    # Skip during automated testing
    if "pytest" in sys.modules or os.environ.get("BDM_TESTING") == "1" or os.environ.get("BDM_SKIP_DESKTOP_INTEGRATION") == "1":
        return

    try:
        import shutil
        home = os.path.expanduser("~")
        apps_dir = os.path.join(home, ".local", "share", "applications")
        desktop_file = os.path.join(apps_dir, "io.github.tazihad.bengal-download-manager.desktop")

        _meipass = getattr(sys, "_MEIPASS", None)
        _argv0_src = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else None
        _argv0_root = os.path.dirname(_argv0_src) if _argv0_src else None
        _module_dir = os.path.dirname(os.path.abspath(__file__)) if __file__ else None
        _module_root = os.path.dirname(os.path.dirname(_module_dir)) if _module_dir else None

        assets_candidates = [
            os.path.join(_meipass, "assets") if _meipass else None,
            os.path.join(_argv0_root, "assets") if _argv0_root else None,
            os.path.join(_module_root, "assets") if _module_root else None,
            "/usr/share/bengal-download-manager/assets",
            "/usr/local/share/bengal-download-manager/assets",
        ]
        assets_dir = next((d for d in assets_candidates if d and os.path.isdir(d)), None)
        if not assets_dir:
            return

        # 1. Install hicolor application icons if not present
        icons_base = os.path.join(home, ".local", "share", "icons", "hicolor")
        for size in [16, 32, 48, 64, 128, 256, 512]:
            src_png = os.path.join(assets_dir, "icons", f"{size}x{size}.png")
            dst_dir = os.path.join(icons_base, f"{size}x{size}", "apps")
            dst_png = os.path.join(dst_dir, "io.github.tazihad.bengal-download-manager.png")
            if os.path.exists(src_png) and not os.path.exists(dst_png):
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src_png, dst_png)

        src_svg = os.path.join(assets_dir, "logo.svg")
        dst_svg_dir = os.path.join(icons_base, "scalable", "apps")
        dst_svg = os.path.join(dst_svg_dir, "io.github.tazihad.bengal-download-manager.svg")
        if os.path.exists(src_svg) and not os.path.exists(dst_svg):
            os.makedirs(dst_svg_dir, exist_ok=True)
            shutil.copy2(src_svg, dst_svg)

        # 2. Install desktop entry if not present or needs update
        if getattr(sys, "frozen", False):
            exec_cmd = f'"{sys.executable}" %u'
        else:
            script_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
            if script_path and os.path.isfile(script_path):
                exec_cmd = f'"{sys.executable}" "{script_path}" %u'
            else:
                exec_cmd = f'"{sys.executable}" -m bengal_download_manager %u'

        need_write = not os.path.exists(desktop_file)
        if not need_write:
            try:
                with open(desktop_file, "r", encoding="utf-8") as f:
                    content_existing = f.read()
                if (
                    "StartupWMClass=io.github.tazihad.bengal-download-manager" not in content_existing
                    or "Icon=io.github.tazihad.bengal-download-manager" not in content_existing
                    or f"Exec={exec_cmd}" not in content_existing
                ):
                    need_write = True
            except Exception:
                need_write = True

        if need_write:
            os.makedirs(apps_dir, exist_ok=True)
            content = f"""[Desktop Entry]
Name=Bengal Download Manager
GenericName=Download Manager
Comment=Fast multi-threaded download manager powered by Aria2 and PyQt6
Exec={exec_cmd}
Icon=io.github.tazihad.bengal-download-manager
Terminal=false
Type=Application
Categories=Network;FileTransfer;
MimeType=x-scheme-handler/http;x-scheme-handler/https;
Keywords=download;manager;aria2;multithread;
StartupWMClass=io.github.tazihad.bengal-download-manager
"""
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            try:
                import subprocess
                subprocess.run(["update-desktop-database", apps_dir], capture_output=True, timeout=2)
            except Exception:
                pass
    except Exception:
        pass
