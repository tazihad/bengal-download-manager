"""
Windows Native Theming Integration & Modern Palette Fixes for Bengal Download Manager.

Features:
  1. Desktop Window Manager (DWM) Immersive Dark Mode for Win32 title bars (attributes 20 & 19).
  2. HWND memoization cache to prevent recursive activation loops and title-bar flicker.
  3. QGuiApplication::focusWindowChanged hook to automatically theme all dialogs and popup windows.
  4. Dynamic style switching:
     - Enforces Qt 'Fusion' style in Dark Mode to bypass broken 'windowsvista' UxTheme light bitmaps
       (which cause stark white headers, white comboboxes, light gray buttons with white text, and dark group titles).
     - Preserves native 'windowsvista' style in Light Mode where UxTheme works correctly.
  5. Windows Dark Mode QSS overrides for QHeaderView, QComboBox, QPushButton, QGroupBox, and QScrollBar.
  6. Windows 10/11 Registry dark mode detection (AppsUseLightTheme) for reliable Auto theme resolution.
  7. Windows modern accent color detection from registry (HKCU\\Software\\Microsoft\\Windows\\DWM\\AccentColor).
  8. Global stylesheet sanitizer ensuring palette(highlighted-text) is used instead of hardcoded #000000.
  9. Windows binary resolution safety for aria2c to prevent WinError 193 from Linux ELF binaries.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette, QWindow
from PyQt6.QtWidgets import QApplication, QStyleFactory

logger = logging.getLogger("bdm.windows_theme")

# Cache to prevent recursive DwmSetWindowAttribute calls and focus-loop activation storms.
_APPLIED_HWNDS: Dict[int, bool] = {}

WINDOWS_DARK_MODE_QSS = """
/* === Bengal Download Manager — Windows Dark Mode Controls === */
QHeaderView::section {
    background-color: #2a2e32;
    color: #eff0f1;
    border: 1px solid #1c1e20;
    padding: 5px 8px;
    font-weight: 500;
}
QHeaderView::section:hover {
    background-color: #353a3e;
}
QHeaderView::section:checked {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
QComboBox {
    background-color: #2a2e32;
    color: #eff0f1;
    border: 1px solid #3c4043;
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid palette(highlight);
}
QComboBox:focus {
    border: 1px solid palette(highlight);
}
QComboBox:disabled {
    background-color: #1e2022;
    color: #888888;
    border: 1px solid #2a2e32;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left-width: 0px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #eff0f1;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #202326;
    color: #eff0f1;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    border: 1px solid #3c4043;
    outline: none;
    padding: 2px;
}
QGroupBox {
    color: #eff0f1;
    border: 1px solid #3c4043;
    border-radius: 5px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: normal;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 5px;
    color: #eff0f1;
    background-color: #202326;
}
QPushButton {
    background-color: #2a2e32;
    color: #eff0f1;
    border: 1px solid #3c4043;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #353a3e;
    border: 1px solid palette(highlight);
}
QPushButton:pressed {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
QPushButton:default {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border: 1px solid palette(highlight);
}
QScrollBar:vertical {
    background-color: #1a1c1e;
    width: 12px;
    margin: 0px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background-color: #3c4043;
    min-height: 24px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background-color: #555a5f;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}
QScrollBar:horizontal {
    background-color: #1a1c1e;
    height: 12px;
    margin: 0px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background-color: #3c4043;
    min-width: 24px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #555a5f;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}
"""


def is_windows() -> bool:
    """Return True if running on a native Windows platform."""
    return platform.system() == "Windows" or sys.platform == "win32"


def is_windows_os_dark_mode() -> bool:
    """
    Detects whether Windows 10/11 is configured in Dark Mode for applications
    by querying the Windows Registry.
    """
    if not is_windows():
        return False
    try:
        import winreg  # type: ignore

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            try:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
            except FileNotFoundError:
                val, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
                return val == 0
    except Exception as e:
        logger.debug("Could not read Windows dark mode from registry: %s", e)
        return False


def get_windows_modern_accent_color() -> Optional[QColor]:
    """
    Retrieves the active Windows 10/11 system accent color from the Windows Registry
    (HKCU\\Software\\Microsoft\\Windows\\DWM\\AccentColor) formatted as ABGR DWORD.
    Falls back to DwmGetColorizationColor if registry access is unavailable.
    """
    if not is_windows():
        return None

    # 1. Query modern AccentColor DWORD (ABGR)
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            r = val & 0xFF
            g = (val >> 8) & 0xFF
            b = (val >> 16) & 0xFF
            return QColor(r, g, b)
    except Exception:
        pass

    # 2. Fallback to DwmGetColorizationColor
    try:
        import ctypes
        from ctypes import wintypes

        dwm = ctypes.WinDLL("dwmapi")
        color = wintypes.DWORD()
        opaque = wintypes.BOOL()
        hr = dwm.DwmGetColorizationColor(ctypes.byref(color), ctypes.byref(opaque))
        if hr == 0:
            c = color.value
            r = (c >> 16) & 0xFF
            g = (c >> 8) & 0xFF
            b = c & 0xFF
            return QColor(r, g, b)
    except Exception:
        pass

    return None


def extract_hwnd(window_or_widget: object) -> Optional[int]:
    """Safely extracts the Win32 HWND integer from a QWidget, QWindow, or QQuickWindow."""
    if not window_or_widget:
        return None

    try:
        if isinstance(window_or_widget, int):
            return window_or_widget

        # QWidget or QWindow
        if hasattr(window_or_widget, "winId"):
            wid = window_or_widget.winId()
            return int(wid) if wid else None

        # QWidget.windowHandle()
        if hasattr(window_or_widget, "windowHandle"):
            wh = window_or_widget.windowHandle()
            if wh and hasattr(wh, "winId"):
                wid = wh.winId()
                return int(wid) if wid else None

        # QWindow handle
        if hasattr(window_or_widget, "handle"):
            h = window_or_widget.handle()
            if h and hasattr(h, "winId"):
                wid = h.winId()
                return int(wid) if wid else None
    except Exception as e:
        logger.debug("Failed extracting HWND: %s", e)

    return None


def apply_windows_dark_title_bar(window_or_widget: object, is_dark: bool) -> bool:
    """
    Applies DWM Immersive Dark Mode to a Win32 window caption bar.
      DwmSetWindowAttribute(hwnd, 20, &value, sizeof(value))
      fallback: DwmSetWindowAttribute(hwnd, 19, &value, sizeof(value))
    """
    if not is_windows():
        return False

    hwnd = extract_hwnd(window_or_widget)
    if not hwnd:
        return False

    # Skip redundant calls to prevent focus change recursion and frame activation flicker
    target_val = bool(is_dark)
    if hwnd in _APPLIED_HWNDS and _APPLIED_HWNDS[hwnd] == target_val:
        return True

    try:
        import ctypes
        from ctypes import wintypes

        dwm = ctypes.WinDLL("dwmapi")

        val = wintypes.BOOL(1 if target_val else 0)
        # Modern attribute 20 (Windows 10 1903+, Windows 11)
        # Legacy attribute 19 (Windows 10 1809)
        k_attr_modern = wintypes.DWORD(20)
        k_attr_legacy = wintypes.DWORD(19)

        hr = dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            k_attr_modern,
            ctypes.byref(val),
            ctypes.sizeof(val),
        )
        if hr != 0:
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                k_attr_legacy,
                ctypes.byref(val),
                ctypes.sizeof(val),
            )

        _APPLIED_HWNDS[hwnd] = target_val
        return True
    except Exception as e:
        logger.debug("DwmSetWindowAttribute failed for HWND %s: %s", hwnd, e)
        return False


def apply_dark_title_bar_to_all_windows(is_dark: bool):
    """Iterates all top-level QWidgets and QWindows and updates their DWM title bar attribute."""
    if not is_windows():
        return

    app = QApplication.instance()
    if not app:
        return

    for top in app.topLevelWidgets():
        apply_windows_dark_title_bar(top, is_dark)

    for win in app.topLevelWindows():
        apply_windows_dark_title_bar(win, is_dark)


def sanitize_stylesheet(css: str) -> str:
    """
    Eliminates hardcoded '#000000' text from selection and hover rules,
    replacing it with 'palette(highlighted-text)' according to AGENTS.md Rule 4.
    """
    if not css:
        return css

    replacements = [
        ("color: #000000;", "color: palette(highlighted-text);"),
        ("selection-color: #000000;", "selection-color: palette(highlighted-text);"),
    ]
    for old, new in replacements:
        css = css.replace(old, new)

    return css


def enforce_windows_style(app: Optional[QApplication] = None, is_dark: bool = True):
    """
    Sets the appropriate Qt Style on Windows:
      - 'Fusion' for Dark themes: ensures QPalette colors govern all controls, bypassing
        UxTheme light bitmap rendering for comboboxes, headers, buttons, and scrollbars.
      - 'windowsvista' for Light themes: preserves 100% native Windows widgets when light mode is used.
    """
    if not is_windows():
        return

    if app is None:
        app = QApplication.instance()
    if not app:
        return

    try:
        available_styles = [s.lower() for s in QStyleFactory.keys()]
        if is_dark:
            if "fusion" in available_styles and app.style().metaObject().className() != "QFusionStyle":
                app.setStyle("Fusion")
                logger.info("Enforced 'Fusion' QStyle on Windows for Dark Mode parity.")
        else:
            if "windowsvista" in available_styles and app.style().metaObject().className() != "QWindowsVistaStyle":
                app.setStyle("windowsvista")
                logger.info("Restored native 'windowsvista' QStyle on Windows for Light Mode.")
            elif "windows" in available_styles and app.style().metaObject().className() != "QWindowsStyle":
                app.setStyle("Windows")
    except Exception as e:
        logger.warning("Failed to adjust Windows Qt style: %s", e)


def safe_find_aria2(orig_fn):
    """
    Safe Windows wrapper for core.utils.find_aria2.
    Avoids returning Linux ELF binaries on Windows, which cause WinError 193.
    """
    def _wrapped():
        if not is_windows():
            return orig_fn()

        # 1. Look for Windows aria2c.exe in local directories
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        search_dirs = [
            os.path.join(repo_root, "build", "windows", "bin"),
            os.path.join(repo_root, "windows", "bin"),
            os.path.join(repo_root, "bin"),
        ]
        if getattr(sys, "frozen", False):
            search_dirs.insert(0, os.path.dirname(sys.executable))

        for d in search_dirs:
            candidate = os.path.join(d, "aria2c.exe")
            if os.path.isfile(candidate):
                return candidate

        # 2. System PATH aria2c.exe
        sys_bin = shutil.which("aria2c.exe") or shutil.which("aria2c")
        if sys_bin and sys_bin.lower().endswith(".exe"):
            return sys_bin

        # 3. Call original, but filter out Linux ELF binaries
        orig_cand = orig_fn()
        if orig_cand and orig_cand.lower().endswith(".exe") and "linux" not in orig_cand.lower():
            return orig_cand

        return None

    return _wrapped


def safe_ensure_aria2(orig_fn):
    """
    Safe Windows wrapper for core.utils.ensure_aria2.
    Ensures that only Windows binaries are checked and downloaded.
    """
    def _wrapped():
        if not is_windows():
            return orig_fn()

        found = safe_find_aria2(lambda: None)()
        if found:
            return found

        # On Windows, try downloading the Windows zip if missing
        try:
            import urllib.request
            import zipfile
            from core.utils import get_data_dir, get_system_arch

            data_dir = get_data_dir()
            bin_dir = os.path.join(data_dir, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            local_aria2 = os.path.join(bin_dir, "aria2c.exe")

            arch = get_system_arch()
            if arch in ("x86_64", "amd64"):
                url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
            else:
                url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-32bit-build1.zip"

            temp_file = os.path.join(data_dir, "aria2_win.zip")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                with open(temp_file, "wb") as out:
                    out.write(resp.read())

            with zipfile.ZipFile(temp_file, "r") as z:
                for name in z.namelist():
                    if name.lower().endswith("aria2c.exe"):
                        with open(local_aria2, "wb") as out:
                            out.write(z.read(name))
                        break
            if os.path.exists(temp_file):
                os.remove(temp_file)

            if os.path.isfile(local_aria2):
                return local_aria2
        except Exception as e:
            logger.debug("Failed Windows ensure_aria2 download: %s", e)

        return None

    return _wrapped


def set_windows_app_user_model_id(app_id: str = "io.github.tazihad.bengal-download-manager") -> bool:
    """Explicitly sets AppUserModelID on Windows so the taskbar displays the application icon instead of Python's."""
    if is_windows():
        try:
            import ctypes
            res = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
            return res == 0
        except Exception as e:
            logger.debug("Could not set AppUserModelID: %s", e)
    return False


def apply_windows_theme_patches(app: Optional[QApplication] = None):
    """
    Installs runtime hooks and monkey-patches for Windows:
      0. Sets AppUserModelID so taskbar displays the application icon instead of Python's.
      1. Wires dynamic style switching (Fusion for dark mode, native for light mode).
      2. Wires focusWindowChanged to automatically theme all dialogs and popup windows.
      3. Injects Windows Dark Mode QSS for headers, comboboxes, buttons, and groupboxes.
      4. Hooks core.services.theme_service to apply DWM caption styling and registry detection.
      5. Wraps core.utils.find_aria2 and ensure_aria2 to eliminate WinError 193 on Windows.
    """
    # 0. Set AppUserModelID for proper taskbar icon grouping
    set_windows_app_user_model_id()

    if app is None:
        app = QApplication.instance()

    # 1. Patch find_aria2 and ensure_aria2 to prevent WinError 193 on Windows
    try:
        import core.utils as utils_mod
        if hasattr(utils_mod, "find_aria2"):
            if not getattr(utils_mod.find_aria2, "_is_win_patched", False):
                orig_find = utils_mod.find_aria2
                wrapped_find = safe_find_aria2(orig_find)
                wrapped_find._is_win_patched = True  # type: ignore
                utils_mod.find_aria2 = wrapped_find

        if hasattr(utils_mod, "ensure_aria2"):
            if not getattr(utils_mod.ensure_aria2, "_is_win_patched", False):
                orig_ensure = utils_mod.ensure_aria2
                wrapped_ensure = safe_ensure_aria2(orig_ensure)
                wrapped_ensure._is_win_patched = True  # type: ignore
                utils_mod.ensure_aria2 = wrapped_ensure
    except Exception as e:
        logger.debug("Could not patch aria2 resolvers: %s", e)

    # 2. Patch theme_service
    try:
        import core.services.theme_service as ts

        # Modern accent detection
        ts.get_windows_accent_color = get_windows_modern_accent_color

        original_apply_app_theme = ts.apply_app_theme

        def patched_apply_app_theme(theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None, app=None, **kwargs):
            active_app = app or kwargs.get("app_inst") or QApplication.instance()

            # Handle Auto mode on Windows with registry detection
            theme_str = str(theme_name).strip().lower()
            if is_windows() and theme_str in ("bdm auto (default)", "bdm auto", "bdmauto", "automatic", "auto", "system"):
                if is_windows_os_dark_mode():
                    theme_name = "BDM Dark (Default)"
                else:
                    theme_name = "BDM Light"

            # Determine whether requested theme is dark
            t_low = str(theme_name).strip().lower()
            is_dark = t_low not in (
                "bdm light", "bdmlight", "light", "ubuntu light", "ubuntulight",
                "idm classic", "idm", "windows classic", "kirigami light", "kirigamilight",
                "material you light", "material light", "solarized light", "solarizedlight",
                "breeze light", "breezelight", "breeze white", "stellar light", "stellarlight"
            )

            # Enforce style BEFORE applying theme so palette maps cleanly
            if active_app and is_windows():
                enforce_windows_style(active_app, is_dark=is_dark)

            # Call original theme applier
            res = original_apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name, active_app)

            # Post-process for Windows theming parity
            if active_app:
                # Fix highlighted text in palette for dark mode
                if is_dark:
                    pal = active_app.palette()
                    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
                    pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
                    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
                    active_app.setPalette(pal)

                # Process stylesheet
                current_css = active_app.styleSheet()
                sanitized_css = sanitize_stylesheet(current_css)

                if is_windows():
                    if is_dark:
                        if "Bengal Download Manager — Windows Dark Mode Controls" not in sanitized_css:
                            sanitized_css = sanitized_css + "\n" + WINDOWS_DARK_MODE_QSS
                    else:
                        # Clean out dark mode controls if switching back to light mode
                        if "Bengal Download Manager — Windows Dark Mode Controls" in sanitized_css:
                            sanitized_css = sanitized_css.split("/* === Bengal Download Manager — Windows Dark Mode Controls === */")[0]

                if sanitized_css != current_css:
                    active_app.setStyleSheet(sanitized_css)

                # Update DWM title bars for all windows
                if is_windows():
                    apply_dark_title_bar_to_all_windows(is_dark)

            return res

        # Patch theme_service module
        ts.apply_app_theme = patched_apply_app_theme

        # Also patch any already-imported references in sys.modules
        for mod_name in ("main", "ui.main_window", "core.services"):
            if mod_name in sys.modules and hasattr(sys.modules[mod_name], "apply_app_theme"):
                setattr(sys.modules[mod_name], "apply_app_theme", patched_apply_app_theme)

        logger.info("Successfully patched theme_service for Windows theming parity.")
    except Exception as e:
        logger.warning("Failed patching theme_service: %s", e)

    # 3. Hook focusWindowChanged for newly created windows / dialogs
    if is_windows() and app:
        def on_focus_window_changed(win: Optional[QWindow]):
            if not win:
                return
            try:
                import core.services.theme_service as ts_mod
                is_dark = ts_mod.is_dark_theme(app)
            except Exception:
                is_dark = is_windows_os_dark_mode()
            apply_windows_dark_title_bar(win, is_dark)

        try:
            app.focusWindowChanged.connect(on_focus_window_changed)
            logger.info("Connected focusWindowChanged to Windows DWM caption manager.")
        except Exception as e:
            logger.debug("Could not connect focusWindowChanged: %s", e)

        # 4. Listen for system colorSchemeChanged (Qt 6.5+) to adapt dynamically
        try:
            sh = app.styleHints()
            if hasattr(sh, "colorSchemeChanged"):
                def on_color_scheme_changed(_scheme):
                    try:
                        import core.services.theme_service as ts_mod
                        cur = getattr(ts_mod, "CURRENT_THEME", "").lower()
                        if "auto" in cur or "system" in cur:
                            ts_mod.apply_app_theme(cur, app=app)
                    except Exception:
                        pass

                sh.colorSchemeChanged.connect(on_color_scheme_changed)
        except Exception as e:
            logger.debug("Could not connect colorSchemeChanged: %s", e)
