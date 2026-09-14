"""
Windows Native Theming Integration & Modern Palette Fixes for Bengal Download Manager
Inspired by the Desktop Window Manager (DWM) architecture of Stellar Download Manager.

Features:
  1. Desktop Window Manager (DWM) Immersive Dark Mode for Win32 title bars (attributes 20 & 19).
  2. HWND memoization cache to prevent recursive activation loops (Stellar AppController pattern).
  3. QGuiApplication::focusWindowChanged hook to automatically theme all dialogs and popup windows.
  4. Enforced Qt 'Fusion' style on Windows to bypass broken 'windowsvista' UxTheme light bitmaps.
  5. Windows 10/11 Registry dark mode detection (AppsUseLightTheme) for reliable Auto theme resolution.
  6. Windows modern accent color detection from registry (HKCU\\Software\\Microsoft\\Windows\\DWM\\AccentColor).
  7. Global stylesheet sanitizer ensuring palette(highlighted-text) is used instead of hardcoded #000000.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QObject
from PyQt6.QtGui import QColor, QGuiApplication, QWindow
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger("bdm.windows_theme")

# Cache to prevent recursive DwmSetWindowAttribute calls and focus-loop activation storms.
# Modeled directly after Stellar's static QHash<HWND, BOOL> s_applied in AppController.cpp.
_APPLIED_HWNDS: Dict[int, bool] = {}


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
    Inspired by Stellar's applyDarkCaption in AppController.cpp:
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


def enforce_windows_style(app: Optional[QApplication] = None):
    """
    Enforces Qt's 'Fusion' style on Windows to prevent the broken 'windowsvista'
    UxTheme light bitmap engine from overriding dark QPalette backgrounds.
    """
    if not is_windows():
        return

    if app is None:
        app = QApplication.instance()
    if not app:
        return

    try:
        available_styles = [s.lower() for s in app.style().metaObject().className()]
        # Setting Fusion ensures pure QPalette conformance across all controls
        app.setStyle("Fusion")
        logger.info("Enforced 'Fusion' QStyle for Windows theme consistency.")
    except Exception as e:
        logger.warning("Failed to enforce 'Fusion' style: %s", e)


def apply_windows_theme_patches(app: Optional[QApplication] = None):
    """
    Installs runtime hooks and monkey-patches for Windows:
      1. Enforces Fusion style on Windows.
      2. Wires focusWindowChanged to automatically theme all dialogs and popup windows.
      3. Hooks core.services.theme_service to apply DWM caption styling and registry detection.
    """
    if app is None:
        app = QApplication.instance()

    # Always enforce Fusion style on Windows for widget consistency
    if is_windows() and app:
        enforce_windows_style(app)

    try:
        import core.services.theme_service as ts

        # 1. Override Windows accent detection with modern registry reader
        original_get_windows_accent = getattr(ts, "get_windows_accent_color", None)
        ts.get_windows_accent_color = get_windows_modern_accent_color

        # 2. Wrap apply_app_theme to sanitize stylesheets and update DWM title bars
        original_apply_app_theme = ts.apply_app_theme

        def patched_apply_app_theme(theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None, app_inst=None):
            active_app = app_inst or QApplication.instance()

            # Handle Auto mode on Windows with registry detection
            theme_str = str(theme_name).strip().lower()
            if is_windows() and theme_str in ("bdm auto (default)", "bdm auto", "bdmauto", "automatic", "auto", "system"):
                if is_windows_os_dark_mode():
                    theme_name = "BDM Dark (Default)"
                else:
                    theme_name = "BDM Light"

            # Call original theme applier
            res = original_apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name, active_app)

            # Sanitize global stylesheet
            if active_app:
                current_css = active_app.styleSheet()
                sanitized_css = sanitize_stylesheet(current_css)
                if sanitized_css != current_css:
                    active_app.setStyleSheet(sanitized_css)

                # Determine if active theme is dark and update all title bars
                is_dark = ts.is_dark_theme(active_app)
                apply_dark_title_bar_to_all_windows(is_dark)

            return res

        ts.apply_app_theme = patched_apply_app_theme
        logger.info("Successfully patched theme_service for Windows theming parity.")
    except Exception as e:
        logger.warning("Failed patching theme_service: %s", e)

    # 3. Hook focusWindowChanged for newly created windows / dialogs (Stellar pattern)
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
