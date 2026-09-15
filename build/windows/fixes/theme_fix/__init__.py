"""
Windows native theming integration package for Bengal Download Manager.
"""

from .windows_theme_fix import (
    apply_windows_theme_patches,
    apply_windows_dark_title_bar,
    apply_dark_title_bar_to_all_windows,
    is_windows_os_dark_mode,
    get_windows_modern_accent_color,
    enforce_windows_style,
    sanitize_stylesheet,
)

__all__ = [
    "apply_windows_theme_patches",
    "apply_windows_dark_title_bar",
    "apply_dark_title_bar_to_all_windows",
    "is_windows_os_dark_mode",
    "get_windows_modern_accent_color",
    "enforce_windows_style",
    "sanitize_stylesheet",
]
