"""
Theme & Dynamic Stylesheet Engine
=================================
Manages application palettes, desktop system accent detection (Windows, KDE Plasma, GNOME, Qt),
dynamic stylesheets, icon themes, and font initialization for Bengal Download Manager.
"""

import os
import sys
import re
import time
import glob
import configparser
import platform
from pathlib import Path
from typing import Optional, Tuple, List

from PyQt6.QtWidgets import QApplication, QStyle, QFileIconProvider, QMainWindow, QDialog
from PyQt6.QtGui import QColor, QPalette, QIcon, QFont, QPixmap, QImage, QPainter
from PyQt6.QtCore import Qt, QFileInfo, QMimeDatabase, QLocale, QEvent, QTimer, QByteArray, QObject

from core.utils import get_data_dir

import ctypes

# Optional Windows API for accent extraction
if platform.system() == "Windows":
    from ctypes import wintypes

# Optional GIO/GSettings for GNOME
_HAS_GIO = False
try:
    if getattr(sys, 'frozen', False) or os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):
        os.environ["GIO_MODULE_DIR"] = "/dev/null"
        os.environ.pop("GIO_EXTRA_MODULES", None)
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio
    _HAS_GIO = True
except Exception:
    _HAS_GIO = False


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))


def xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))


def common_system_data_dirs() -> List[Path]:
    dirs = [
        Path("/usr/share"),
        Path("/usr/local/share"),
        Path("/var/lib/flatpak/exports/share"),
        Path("/run/host/usr/share"),
    ]
    return [d for d in dirs if d.exists()]


def _qcolor_from_rgb_tuple(t: Tuple[int, int, int], a: int = 255) -> QColor:
    r, g, b = t
    return QColor(r, g, b, a)


def _qcolor_from_hex(hexstr: str) -> Optional[QColor]:
    if not hexstr:
        return None
    s = hexstr.strip()
    m = re.match(r'^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$', s)
    if m:
        return QColor(s)
    return None


def _parse_color_value_string(s: str) -> Optional[Tuple[int, int, int]]:
    if not s:
        return None
    s = s.strip()
    m = re.match(r'^#?([0-9A-Fa-f]{6})$', s)
    if m:
        hexpart = m.group(1)
        r = int(hexpart[0:2], 16)
        g = int(hexpart[2:4], 16)
        b = int(hexpart[4:6], 16)
        return r, g, b
    m = re.match(r'^\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*$', s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return r, g, b
    m = re.match(r'rgb\s*\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*\)', s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return r, g, b
    return None


def get_windows_accent_color() -> Optional[QColor]:
    if platform.system() != "Windows":
        return None
    try:
        dwm = ctypes.WinDLL("dwmapi")
        color = wintypes.DWORD()
        opaque = wintypes.BOOL()
        hr = dwm.DwmGetColorizationColor(ctypes.byref(color), ctypes.byref(opaque))
        if hr == 0:
            c = color.value
            a = (c >> 24) & 0xFF
            r = (c >> 16) & 0xFF
            g = (c >> 8) & 0xFF
            b = c & 0xFF
            if a == 0:
                a = 255
            return _qcolor_from_rgb_tuple((r, g, b), a)
    except Exception:
        pass
    return None


GNOME_ACCENT_MAP = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#c88800",
    "orange": "#ed6218",
    "red": "#e01b24",
    "pink": "#d44a7d",
    "purple": "#9141ac",
    "slate": "#6f8396",
    "brown": "#986a44",
}


def get_gnome_accent_color() -> Optional[QColor]:
    if not _HAS_GIO:
        return None
    try:
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        keys = settings.list_keys()
        candidates = ("accent-color", "accent-color-rgba", "gtk-color-scheme")
        for candidate in candidates:
            if candidate in keys:
                val = settings.get_value(candidate).unpack() if settings.get_value(candidate) is not None else None
                if isinstance(val, str):
                    if val.lower() in GNOME_ACCENT_MAP:
                        return _qcolor_from_hex(GNOME_ACCENT_MAP[val.lower()])
                    col = _qcolor_from_hex(val)
                    if col:
                        return col
                if isinstance(val, (list, tuple)):
                    try:
                        r, g, b = int(val[0]), int(val[1]), int(val[2])
                        a = int(val[3]) if len(val) > 3 else 255
                        return _qcolor_from_rgb_tuple((r, g, b), a)
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def get_kde_accent_color() -> Optional[QColor]:
    kg = xdg_config_home() / "kdeglobals"
    cfg_paths = [kg] if kg.exists() else []

    cs_dirs = [xdg_data_home() / "color-schemes"]
    for sysd in common_system_data_dirs():
        cs_dirs.append(sysd / "color-schemes")

    color_files = []
    for d in cs_dirs:
        if d.exists() and d.is_dir():
            color_files.extend(sorted(glob.glob(str(d / "*.colors"))))

    keys_of_interest = [
        "accentcolor", "AccentColor", "Accent", "SelectionBackground",
        "SelectionBackgroundNormal", "Highlight", "ButtonBackgroundActive"
    ]

    for p in cfg_paths:
        try:
            cfg = configparser.RawConfigParser()
            cfg.optionxform = str
            cfg.read(p, encoding="utf-8")
            for ki in keys_of_interest:
                for sec in cfg.sections():
                    if cfg.has_option(sec, ki):
                        raw = cfg.get(sec, ki)
                        parsed = _parse_color_value_string(raw)
                        if parsed:
                            return _qcolor_from_rgb_tuple(parsed, 255)
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            cs_match = re.search(r'^\s*ColorScheme\s*=\s*(\S+)\s*$', text, flags=re.MULTILINE)
            if cs_match:
                scheme_name = cs_match.group(1)
                potential = [xdg_data_home() / "color-schemes" / f"{scheme_name}.colors"]
                for sysd in common_system_data_dirs():
                    potential.append(sysd / "color-schemes" / f"{scheme_name}.colors")
                for pot in potential:
                    if pot.exists():
                        color_files.insert(0, str(pot))
        except Exception:
            pass

    seen = set()
    candidate_files = []
    for p in color_files:
        if p and p not in seen and Path(p).exists():
            seen.add(p)
            candidate_files.append(p)

    for path in candidate_files:
        try:
            cfg = configparser.RawConfigParser()
            cfg.optionxform = str
            cfg.read(path, encoding="utf-8")
            for ki in keys_of_interest:
                for sec in cfg.sections():
                    if cfg.has_option(sec, ki):
                        raw = cfg.get(sec, ki)
                        parsed = _parse_color_value_string(raw)
                        if parsed:
                            return _qcolor_from_rgb_tuple(parsed, 255)
        except Exception:
            continue

    return None


def get_qt_accent_color(app=None) -> Optional[QColor]:
    if app is None:
        app = QApplication.instance()
    if app:
        col = app.palette().color(QPalette.ColorRole.Highlight)
        if col.isValid():
            return col
    return None


def detect_accent(method: str = "auto", app=None) -> QColor:
    system = platform.system()
    method = method.lower() if method else "auto"

    if method == "auto":
        if system == "Windows":
            methods = ["windows", "qt"]
        elif system == "Linux":
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            if "KDE" in desktop:
                methods = ["kde", "gnome", "qt"]
            elif "GNOME" in desktop or "UBUNTU" in desktop:
                methods = ["gnome", "kde", "qt"]
            else:
                methods = ["kde", "gnome", "qt"]
        else:
            methods = ["qt"]
    else:
        methods = [method, "qt"]

    for m in methods:
        try:
            if m == "windows" and system == "Windows":
                c = get_windows_accent_color()
                if c and c.isValid():
                    return c
            elif m == "gnome":
                c = get_gnome_accent_color()
                if c and c.isValid():
                    return c
            elif m == "kde":
                c = get_kde_accent_color()
                if c and c.isValid():
                    return c
            elif m == "qt":
                c = get_qt_accent_color(app)
                if c and c.isValid():
                    return c
        except Exception:
            continue

    return QColor("#0078d4")


ACCENT_COLORS = {
    "BDM (Default)": "#3daee9",
    "BDM": "#3daee9",
    "System": None,
    "Twilight": "#8b5cf6",
    "Breeze Blue": "#3daee9",
    "Ubuntu Orange": "#e95420",
    "Windows Blue": "#0078d4",
    "Dracula Purple": "#bd93f9",
    "Nord Frost": "#88c0d0",
    "Emerald Green": "#2ecc71",
    "Crimson Red": "#e74c3c",
    "Amethyst Violet": "#9b59b6",
    "Obsidian Purple": "#dab9ff",
    "Material Cobalt": "#a8c7fa",
    "Material Violet": "#d0bcff",
    "Stellar Blue": "#4488dd",
    "TMOG Cyan": "#00e5ff",
    "Cyber Cyan": "#00e5ff",
}


def _build_palette(bg, text, base, alt, btn, link, hl, hl_text, accent=None):
    if accent and str(accent).lower() == "system":
        sys_acc = detect_accent("auto", app=QApplication.instance())
        if sys_acc and sys_acc.isValid():
            hl = sys_acc
            link = sys_acc
    elif accent and accent in ACCENT_COLORS and ACCENT_COLORS[accent]:
        hl = ACCENT_COLORS[accent]
        link = ACCENT_COLORS[accent]
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(text))
    pal.setColor(QPalette.ColorRole.Base, QColor(base))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(alt))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(alt))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(text))
    pal.setColor(QPalette.ColorRole.Text, QColor(text))
    pal.setColor(QPalette.ColorRole.Button, QColor(btn))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ff5555"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(hl))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
    pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor("#000000"))
    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#000000"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#000000"))

    # ── Structural derived roles ───────────────────────────────────────────────
    # QPalette() constructor copies unset roles from the CURRENT app palette,
    # not from Qt Fusion defaults. On Snap the GNOME extension (gnome-46-2404
    # content snap) injects a GTK3 *light* palette before Python starts:
    #   Midlight ≈ #efefec (near-white) → toolbar hover appears white
    #   PlaceholderText = rgb(0,0,0) α=127 (black) → sidebar headers unreadable
    # Flatpak/AppImage/native don't see this because their pre-existing app
    # palette is already dark.  Fix: set every role we depend on explicitly so
    # no platform palette can bleed through.
    bg_c  = QColor(bg)
    btn_c = QColor(btn)
    is_dark = bg_c.value() < 128

    if is_dark:
        midlight      = bg_c.lighter(120)   # subtly brighter than Window
        mid           = bg_c.darker(115)    # subtly darker than Window
        dark_c        = bg_c.darker(140)
        light_c       = bg_c.lighter(150)
        shadow        = QColor(0, 0, 0, 180)
        placeholder_c = QColor(text)
        placeholder_c.setAlpha(100)         # muted light text on dark bg
    else:
        midlight      = bg_c.lighter(110)
        mid           = bg_c.darker(110)
        dark_c        = bg_c.darker(130)
        light_c       = bg_c.lighter(120)
        shadow        = QColor(0, 0, 0, 80)
        placeholder_c = QColor(text)
        placeholder_c.setAlpha(120)         # muted dark text on light bg

    pal.setColor(QPalette.ColorRole.Midlight,        midlight)
    pal.setColor(QPalette.ColorRole.Mid,             mid)
    pal.setColor(QPalette.ColorRole.Dark,            dark_c)
    pal.setColor(QPalette.ColorRole.Light,           light_c)
    pal.setColor(QPalette.ColorRole.Shadow,          shadow)
    pal.setColor(QPalette.ColorRole.Link,            QColor(link))
    pal.setColor(QPalette.ColorRole.LinkVisited,     QColor(link))
    pal.setColor(QPalette.ColorRole.PlaceholderText, placeholder_c)
    pal.setColor(QPalette.ColorGroup.Active,   QPalette.ColorRole.Button, btn_c)
    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, btn_c)

    dis_text = QColor(text)
    dis_text.setAlpha(90)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText,      dis_text)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,      dis_text)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,            dis_text)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, dis_text)
    return pal


def normalize_theme_name(name, default="BDM Auto (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm auto (default)", "bdm auto", "bdmauto", "automatic", "auto"):
        return "BDM Auto (Default)"
    if s_lower in ("bdm dark (default)", "bdm dark", "bdmdark", "dark"):
        return "BDM Dark"
    if s_lower == "system":
        return "System"
    if s_lower in ("bdm light", "bdmlight", "light"):
        return "BDM Light"
    if s_lower in ("twilight", "twilight dark"):
        return "Twilight"
    if s_lower in ("stellar dark", "stellardark"):
        return "Stellar Dark"
    if s_lower in ("stellar light", "stellarlight"):
        return "Stellar Light"
    if s_lower in ("tmog dark", "tmog", "tmogdark", "cyberpunk tmog", "cyber tmog", "cyber"):
        return "TMOG Dark"
    return s


def normalize_accent_name(name, default="BDM (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm", "bdm (default)", "default"):
        return "BDM (Default)"
    if s_lower == "system":
        return "System"
    if s_lower in ("twilight", "twilight violet"):
        return "Twilight"
    if s_lower in ("stellar", "stellar blue", "stellarblue"):
        return "Stellar Blue"
    if s_lower in ("tmog", "tmog cyan", "tmogcyan", "cyber cyan", "cybercyan", "electric cyan"):
        return "TMOG Cyan"
    return s


def normalize_icon_theme_name(name, default="BDM Auto (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm dark", "bdmdark"):
        return "BDM Dark"
    elif s_lower in ("bdm light", "bdmlight"):
        return "BDM Light"
    elif s_lower in ("modern color", "modern", "prism", "prism color", "vivid", "color", "vibrant"):
        return "Modern Color"
    elif s_lower in ("yaru", "ubuntu yaru"):
        return "Yaru"
    elif s_lower in ("stellar", "stellar icons", "stellaricons"):
        return "Stellar"
    elif s_lower in ("tmog neon", "tmog", "tmogneon", "cyber neon", "cyberneon", "cyber"):
        return "TMOG Neon"
    elif s_lower in ("bdm", "bdm auto (default)", "bdm auto", "bdmauto", "bdm (default)", "default", "automatic"):
        return "BDM Auto (Default)"
    return s


def normalize_tray_icon_name(name, default="App Icon (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("app icon", "app_icon", "app icon (default)", "default", "bdm app icon"):
        return "App Icon (Default)"
    return s


def normalize_titlebar_name(name, default="Automatic"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("auto", "auto (default)", "automatic", "system", "default"):
        return "Automatic"
    if s_lower in ("light", "system light", "system light title bar"):
        return "Light"
    if s_lower in ("dark", "system dark", "system dark title bar"):
        return "Dark"
    return default


CURRENT_THEME = "BDM Auto (Default)"
CURRENT_ICON_THEME = "Automatic"
CURRENT_TRAY_ICON = "App Icon (Default)"
CURRENT_TITLE_BAR_MODE = "Automatic"


def _find_kde_color_scheme(is_dark: bool) -> Tuple[str, str]:
    """
    Returns (scheme_name, scheme_path_or_name)
    """
    if is_dark:
        candidates = [
            "/usr/share/color-schemes/BreezeDark.colors",
            "/usr/local/share/color-schemes/BreezeDark.colors",
            str(xdg_data_home() / "color-schemes" / "BreezeDark.colors"),
            "BreezeDark"
        ]
        default_name = "BreezeDark"
    else:
        candidates = [
            "/usr/share/color-schemes/BreezeLight.colors",
            "/usr/share/color-schemes/BreezeClassic.colors",
            "/usr/local/share/color-schemes/BreezeLight.colors",
            str(xdg_data_home() / "color-schemes" / "BreezeLight.colors"),
            "BreezeLight"
        ]
        default_name = "BreezeLight"

    for c in candidates:
        if c.startswith("/") and os.path.isfile(c):
            return default_name, c
    return default_name, default_name


def _apply_in_process_gtk_theme(is_dark: bool, mode: str = "Auto") -> bool:
    """Sets in-process environment variable for Wayland libdecor GTK plugin without mutating global settings."""
    try:
        if mode in ("Auto", "Automatic"):
            os.environ.pop("GTK_THEME", None)
        elif is_dark:
            os.environ["GTK_THEME"] = "Adwaita:dark"
        else:
            os.environ["GTK_THEME"] = "Adwaita:light"
        return True
    except Exception:
        return False

def is_gnome_desktop() -> bool:
    """
    Detects whether the running desktop environment is GNOME, GTK-based, Ubuntu, or derivative.
    Matches GNOME, Ubuntu, Pop!_OS, Cinnamon, MATE, XFCE, Budgie, Pantheon, Cosmic, Deepin, LXDE.
    """
    if os.environ.get("BDM_FORCE_CSD") == "1":
        return True
    if os.environ.get("BDM_DISABLE_CSD") == "1":
        return False
    desktop = (
        os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" +
        os.environ.get("GDMSESSION", "") + ":" +
        os.environ.get("XDG_SESSION_DESKTOP", "") + ":" +
        os.environ.get("DESKTOP_SESSION", "")
    ).upper()
    gtk_desktops = (
        "GNOME", "UBUNTU", "UNITY", "POPOS", "POP", "PANTHEON",
        "CINNAMON", "X-CINNAMON", "MATE", "XFCE", "X-XFCE",
        "BUDGIE", "COSMIC", "DEEPIN", "DDE", "LXDE"
    )
    return any(d in desktop for d in gtk_desktops)


is_gnome_or_gtk_desktop = is_gnome_desktop


def _apply_gnome_csd_titlebar(mode: str, is_dark: bool, windows: list):
    """
    On GNOME and GTK-based distros, apply custom Libadwaita Client-Side Decorations (CSD).
    Title bar theme options:
      - 'Automatic': Uses default system native title bar (CSD detached)
      - 'Light': Custom Libadwaita light headerbar
      - 'Dark': Custom Libadwaita dark headerbar
    """
    try:
        from ui.components.csd_titlebar import attach_csd, detach_csd
        for w in windows:
            if not w:
                continue
            if mode in ("Light", "Dark"):
                attach_csd(w, is_dark=is_dark, mode=mode)
            else:
                detach_csd(w)
    except Exception:
        pass


def apply_titlebar_theme(title_bar_mode="Automatic", window=None, app=None):
    """
    Applies Title bar theme:
      - 'Automatic': Follows system theme with native system title bar
      - 'Light': System light title bar (or custom CSD on GNOME)
      - 'Dark': System dark title bar (or custom CSD on GNOME)
    """
    global CURRENT_TITLE_BAR_MODE
    mode = normalize_titlebar_name(title_bar_mode)
    CURRENT_TITLE_BAR_MODE = mode

    if app is None:
        app = QApplication.instance()
    if not app:
        return
    init_titlebar_filter(app)

    global _THEME_CHANGE_ACTIVE
    _THEME_CHANGE_ACTIVE = True
    QTimer.singleShot(250, _clear_theme_change_active)

    if mode == "Dark":
        is_dark = True
    elif mode == "Light":
        is_dark = False
    else:  # "Automatic" -> follow system theme
        is_dark = is_system_dark_theme(app)

    # 1. Cross-platform Qt styleHints (Qt 6.5+ sets Wayland / libdecor / macOS / Windows titlebar scheme)
    sh = app.styleHints()
    if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        sh.setColorScheme(Qt.ColorScheme.Dark if is_dark else Qt.ColorScheme.Light)

    all_windows = []
    if window and isinstance(window, (QMainWindow, QDialog)) and window.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog):
        all_windows.append(window)
    for w in app.topLevelWidgets():
        if w and w.isWindow() and isinstance(w, (QMainWindow, QDialog)) and w.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog) and w not in all_windows:
            all_windows.append(w)

    scheme_name, scheme_path = _find_kde_color_scheme(is_dark)

    # Dynamic Qt/KDE application and window properties
    try:
        app.setProperty("KDE_COLOR_SCHEME_PATH", scheme_path)
        app.setProperty("_KDE_NET_WM_COLOR_SCHEME", scheme_name)
    except Exception:
        pass

    for w in all_windows:
        try:
            w.setProperty("KDE_COLOR_SCHEME_PATH", scheme_path)
            w.setProperty("_KDE_NET_WM_COLOR_SCHEME", scheme_name)
            if hasattr(w, "windowHandle") and w.windowHandle():
                w.windowHandle().setProperty("KDE_COLOR_SCHEME_PATH", scheme_path)
                w.windowHandle().setProperty("_KDE_NET_WM_COLOR_SCHEME", scheme_name)
        except Exception:
            pass

    # 2. Windows DWM immersive dark mode
    if sys.platform == "win32":
        try:
            import ctypes
            dwm = ctypes.windll.dwmapi
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
            val = ctypes.c_int(1 if is_dark else 0)

            hwnds = set()
            for w in all_windows:
                if hasattr(w, "winId"):
                    try:
                        hwnds.add(int(w.winId()))
                    except Exception:
                        pass
            for hwnd in hwnds:
                res = dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val))
                if res != 0:
                    dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    # 3. Linux X11 / XWayland _GTK_THEME_VARIANT and _KDE_NET_WM_COLOR_SCHEME
    if sys.platform.startswith("linux"):
        try:
            variant = "dark" if is_dark else "light"
            import shutil, subprocess
            if shutil.which("xprop"):
                hwnds = set()
                for w in all_windows:
                    if hasattr(w, "winId") and w.isVisible():
                        try:
                            hwnds.add(int(w.winId()))
                        except Exception:
                            pass
                for wid in hwnds:
                    try:
                        subprocess.run(
                            ["xprop", "-id", str(wid), "-f", "_GTK_THEME_VARIANT", "8s", "-set", "_GTK_THEME_VARIANT", variant],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5
                        )
                        subprocess.run(
                            ["xprop", "-id", str(wid), "-f", "_KDE_NET_WM_COLOR_SCHEME", "8s", "-set", "_KDE_NET_WM_COLOR_SCHEME", scheme_name],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # 3b. In-process GTK decoration preference (for libdecor-gtk on Wayland, zero system mutation)
    if sys.platform.startswith("linux"):
        _apply_in_process_gtk_theme(is_dark, mode)

    # 5. Linux GNOME / GTK Client-Side Decoration (CSD) - only for custom Light/Dark, Automatic uses system default titlebar
    if sys.platform.startswith("linux") and is_gnome_desktop() and mode in ("Light", "Dark"):
        _apply_gnome_csd_titlebar(mode, is_dark, all_windows)
    else:
        try:
            from ui.components.csd_titlebar import detach_csd
            for w in all_windows:
                if w and getattr(w, "_csd_titlebar", None) is not None:
                    detach_csd(w)
        except Exception:
            pass


def get_current_titlebar_mode() -> str:
    """Returns the current active title bar theme mode ('Automatic', 'Light', or 'Dark')."""
    global CURRENT_TITLE_BAR_MODE
    return CURRENT_TITLE_BAR_MODE


class _TitleBarEventFilter(QObject):
    """
    Application-wide event filter to ensure that any top-level window or dialog
    (e.g., Options, Media Downloader, Add URL, Progress dialogs) automatically receives
    the active title bar theme decoration when shown.
    """
    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Type.Show:
                if hasattr(watched, "isWindow") and watched.isWindow():
                    if isinstance(watched, (QMainWindow, QDialog)) and watched.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog):
                        mode = get_current_titlebar_mode()
                        if mode in ("Light", "Dark"):
                            apply_titlebar_theme(mode, window=watched)
                        else:
                            # Automatic mode: Window inherits app-level styleHints & GTK_THEME automatically.
                            # Ensure no leftover custom CSD is attached.
                            if getattr(watched, "_csd_titlebar", None) is not None:
                                from ui.components.csd_titlebar import detach_csd
                                detach_csd(watched)
        except Exception:
            pass
        return super().eventFilter(watched, event)


_GLOBAL_TITLEBAR_FILTER = None


def init_titlebar_filter(app: Optional[QApplication] = None):
    """
    Installs the global title bar event filter on the QApplication instance once.
    """
    global _GLOBAL_TITLEBAR_FILTER
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    if app is None:
        app = QApplication.instance()
    if not app or _GLOBAL_TITLEBAR_FILTER is not None:
        return
    _GLOBAL_TITLEBAR_FILTER = _TitleBarEventFilter(app)
    app.installEventFilter(_GLOBAL_TITLEBAR_FILTER)


_THEME_CHANGE_ACTIVE = False


def is_theme_change_active() -> bool:
    """Returns True if an internal programmatic theme or title bar change is currently executing."""
    global _THEME_CHANGE_ACTIVE
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    return _THEME_CHANGE_ACTIVE


def _clear_theme_change_active():
    global _THEME_CHANGE_ACTIVE
    _THEME_CHANGE_ACTIVE = False


def is_system_dark_theme(app=None) -> bool:
    """
    Detects whether the underlying desktop environment/system theme is dark.
    First queries the XDG Desktop Portal on Linux via D-Bus for real-time accuracy,
    then falls back to QStyleHints.colorScheme() and standardPalette().
    """
    try:
        from PyQt6 import QtDBus
        bus = QtDBus.QDBusConnection.sessionBus()
        if bus.isConnected():
            msg = QtDBus.QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings",
                "Read"
            )
            msg.setArguments(["org.freedesktop.appearance", "color-scheme"])
            reply = bus.call(msg)
            if reply.type() == QtDBus.QDBusMessage.MessageType.ReplyMessage and reply.arguments():
                val = reply.arguments()[0]
                if isinstance(val, QtDBus.QDBusVariant):
                    val = val.variant()
                # 1 = Prefer Dark, 0 = No preference / Light, 2 = Prefer Light
                return int(val) == 1
    except Exception:
        pass

    if app is None:
        app = QApplication.instance()
    if app:
        sh = app.styleHints()
        if hasattr(sh, "colorScheme"):
            cs = sh.colorScheme()
            if cs == Qt.ColorScheme.Dark:
                return True
            elif cs == Qt.ColorScheme.Light:
                return False
        sys_pal = app.style().standardPalette()
        return sys_pal.color(QPalette.ColorRole.Window).value() < 128 or sys_pal.color(QPalette.ColorRole.WindowText).value() > 128
    return False


def is_dark_theme(app=None) -> bool:
    """Returns True if the current active theme is dark, False if light."""
    global CURRENT_THEME
    t_lower = str(CURRENT_THEME).strip().lower() if 'CURRENT_THEME' in globals() and CURRENT_THEME else ""
    if t_lower in ("bdm dark", "bdm dark (default)", "bdmdark", "dark", "ubuntu dark", "ubuntudark", "kirigami dark", "kirigamidark", "dracula", "nord", "obsidian flow", "obsidian", "material you dark", "one dark", "onedark", "catppuccin", "catppuccin mocha", "solarized dark", "solarizeddark", "twilight", "twilight dark", "breeze dark", "breezedark", "stellar dark", "stellardark", "tmog dark", "tmog", "tmogdark", "cyberpunk tmog", "cyber tmog", "cyber"):
        return True
    if t_lower in ("bdm light", "bdmlight", "light", "ubuntu light", "ubuntulight", "idm classic", "idm", "windows classic", "kirigami light", "kirigamilight", "material you light", "material light", "solarized light", "solarizedlight", "breeze light", "breezelight", "breeze white", "stellar light", "stellarlight"):
        return False
    if t_lower in ("bdm auto (default)", "bdm auto", "bdmauto", "automatic", "auto", "system"):
        return is_system_dark_theme(app)
    if app is None:
        app = QApplication.instance()
    if app:
        pal = app.palette()
        bg_val = pal.color(QPalette.ColorRole.Window).value()
        base_val = pal.color(QPalette.ColorRole.Base).value()
        text_val = pal.color(QPalette.ColorRole.WindowText).value()
        if bg_val < 128 or base_val < 128 or text_val > 128:
            return True
        return False
    return True


def is_monochrome_icon_theme(icon_theme_name=None) -> bool:
    """Returns True if the specified or active icon theme is a BDM monochrome stroke theme."""
    if icon_theme_name is None:
        global CURRENT_ICON_THEME
        icon_theme_name = CURRENT_ICON_THEME if CURRENT_ICON_THEME else "BDM Auto (Default)"
    s_lower = str(icon_theme_name).strip().lower()
    return s_lower in (
        "automatic", "bdm", "bdm auto (default)", "bdm auto", "bdmauto",
        "bdm (default)", "default", "bdm dark", "bdmdark", "bdm dark (default)",
        "bdm light", "bdmlight"
    )


def init_app_font(lang_code: Optional[str] = None) -> QFont:
    """
    Initializes the primary application font.
    Adapts font family and sizing based on active UI language (e.g. Bengali fonts for 'bn').
    Loads the bundled modern Inter font family from assets/fonts if available,
    with robust fallback to system UI fonts.
    Enforces OpenType tabular figures (tnum) for smooth numeric alignment across the entire UI.
    """
    from PyQt6.QtGui import QFontDatabase
    from core.services.language_service import get_current_language_code

    if lang_code is None:
        lang_code = get_current_language_code()
    lang_code = (lang_code or "system").lower()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fonts_dir = os.path.join(base_dir, "assets", "fonts")
    if os.path.isdir(fonts_dir):
        for font_file in sorted(os.listdir(fonts_dir)):
            if font_file.endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(fonts_dir, font_file))

    available = set(QFontDatabase.families())

    font_size = 9
    if lang_code == "bn" or (lang_code == "system" and "bn" in QLocale.system().name().lower()):
        # Cross-platform Bengali system fonts (Linux, Windows, macOS)
        candidates = [
            # Linux system fonts
            "Hind Siliguri", "Kalpurush", "Noto Sans Bengali", "Nikosh",
            "SolaimanLipi", "Mitra", "Mukti", "Akaash", "Bangla",
            # Windows native fonts
            "Nirmala UI", "Vrinda",
            # macOS native fonts
            "Bangla Sangam MN", "Kohinoor Bangla",
            # General UI fallbacks
            "Inter", "Segoe UI", "Noto Sans", "Ubuntu", "DejaVu Sans"
        ]
        font_size = 10  # Bengali text is much more legible at 10pt
    elif lang_code in ("ar", "fa", "ur"):
        candidates = [
            "Noto Sans Arabic", "Segoe UI", "Tahoma", "Geeza Pro",
            "Inter", "Ubuntu", "DejaVu Sans"
        ]
        font_size = 10
    elif lang_code in ("zh_cn", "zh_tw", "ja", "ko"):
        candidates = [
            "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK KR",
            "Microsoft YaHei", "PingFang SC", "Meiryo", "Malgun Gothic",
            "Inter", "Segoe UI", "Noto Sans"
        ]
    else:
        candidates = ["Inter", "Segoe UI", "Noto Sans", "Ubuntu", "Cantarell", "Liberation Sans", "DejaVu Sans"]

    chosen_family = "Inter"
    for candidate in candidates:
        if candidate in available:
            chosen_family = candidate
            break

    app_font = QFont(chosen_family, font_size)
    app_font.setFamilies(candidates)
    app_font.setFeature(QFont.Tag.fromString('tnum'), 1)
    app_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return app_font


def apply_app_theme(theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None, app=None, title_bar_mode=None):
    """
    Applies application theme, custom accent color, custom toolbar icon set, custom system tray icon set, and title bar theme.
    """
    if not isinstance(app, QApplication) and app is not None and title_bar_mode is None:
        title_bar_mode = app
        app = None

    global CURRENT_THEME, CURRENT_TITLE_BAR_MODE
    CURRENT_THEME = str(theme_name).strip()
    if title_bar_mode is not None:
        CURRENT_TITLE_BAR_MODE = normalize_titlebar_name(title_bar_mode)

    if app is None:
        app = QApplication.instance()
    if not app:
        return

    global _THEME_CHANGE_ACTIVE
    _THEME_CHANGE_ACTIVE = True
    QTimer.singleShot(250, _clear_theme_change_active)

    sh = app.styleHints()
    theme_lower = str(theme_name).strip().lower()

    if theme_lower in ("ubuntu light", "ubuntulight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#f7f7f7", "#333333", "#ffffff", "#e8e8e8", "#e8e8e8", "#e95420", "#e95420", "#ffffff", accent=accent_name))
    elif theme_lower in ("ubuntu dark", "ubuntudark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#300a24", "#ffffff", "#1e0617", "#3c102d", "#3c102d", "#e95420", "#e95420", "#ffffff", accent=accent_name))
    elif theme_lower in ("idm classic", "idm", "windows classic"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#f0f0f0", "#000000", "#ffffff", "#f7f7f7", "#e1e1e1", "#0066cc", "#0078d4", "#ffffff", accent=accent_name))
    elif theme_lower in ("kirigami light", "kirigamilight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#fcfcfc", "#232629", "#ffffff", "#f5f5f5", "#f5f5f5", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("kirigami dark", "kirigamidark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#232629", "#fcfcfc", "#1b1e20", "#2a2e32", "#31363b", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower == "dracula":
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#282a36", "#f8f8f2", "#1e1f29", "#44475a", "#44475a", "#8be9fd", "#bd93f9", "#282a36", accent=accent_name))
    elif theme_lower == "nord":
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#2e3440", "#eceff4", "#242933", "#3b4252", "#3b4252", "#88c0d0", "#88c0d0", "#2e3440", accent=accent_name))
    elif theme_lower in ("obsidian flow", "obsidian", "obsidianflow"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#161218", "#e9e0e8", "#110d13", "#1e1a20", "#221e24", "#dab9ff", "#dab9ff", "#460283", accent=accent_name))
    elif theme_lower in ("material you dark", "material you", "material dark", "android 17 dark", "materialyou"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#141318", "#e6e1e9", "#0f0e13", "#1d1b20", "#2b2930", "#a8c7fa", "#a8c7fa", "#003062", accent=accent_name))
    elif theme_lower in ("material you light", "material light", "android 17 light"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#fdf8fd", "#1c1b20", "#ffffff", "#f5eff7", "#e6e0e9", "#005ac1", "#005ac1", "#ffffff", accent=accent_name))
    elif theme_lower in ("one dark", "onedark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#21252b", "#abb2bf", "#1b1d23", "#282c34", "#282c34", "#61afef", "#61afef", "#1b1d23", accent=accent_name))
    elif theme_lower in ("catppuccin", "catppuccin mocha"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#1e1e2e", "#cdd6f4", "#181825", "#313244", "#313244", "#89b4fa", "#cba6f7", "#1e1e2e", accent=accent_name))
    elif theme_lower in ("solarized light", "solarizedlight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#fdf6e3", "#657b83", "#eee8d5", "#fdf6e3", "#eee8d5", "#268bd2", "#268bd2", "#ffffff", accent=accent_name))
    elif theme_lower in ("solarized dark", "solarizeddark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#002b36", "#839496", "#073642", "#002b36", "#073642", "#268bd2", "#268bd2", "#ffffff", accent=accent_name))
    elif theme_lower in ("twilight", "twilight dark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#181424", "#f0edf8", "#13111c", "#221c33", "#2a223f", "#8b5cf6", "#8b5cf6", "#ffffff", accent=accent_name))
    elif theme_lower in ("breeze dark", "breezedark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#2a2e32", "#eff0f1", "#232629", "#31363b", "#31363b", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("breeze light", "breezelight", "breeze white", "breezewhite"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#eff0f1", "#232629", "#fcfcfc", "#eef0f2", "#eef0f2", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("stellar dark", "stellardark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#1c1c1c", "#e0e0e0", "#1e1e1e", "#252525", "#222222", "#66a3f0", "#4488dd", "#ffffff", accent=accent_name))
    elif theme_lower in ("stellar light", "stellarlight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#f0f0f0", "#1a1a1a", "#ffffff", "#f7f7f7", "#e8e8e8", "#4488dd", "#4488dd", "#ffffff", accent=accent_name))
    elif theme_lower in ("tmog dark", "tmog", "tmogdark", "cyberpunk tmog", "cyber tmog", "cyber"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#0c1017", "#eaf2fd", "#080c12", "#111722", "#151d2a", "#00e5ff", "#00b4d8", "#000000", accent=accent_name))
    elif theme_lower in ("bdm light", "bdmlight", "light"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#eff0f1", "#232629", "#ffffff", "#f8f9fa", "#eef0f2", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower == "system":
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Unknown)
        app.setPalette(app.style().standardPalette())
        if accent_name and str(accent_name).lower() == "system":
            sys_acc = detect_accent("auto", app=app)
            if sys_acc and sys_acc.isValid():
                p = QPalette(app.palette())
                p.setColor(QPalette.ColorRole.Highlight, sys_acc)
                p.setColor(QPalette.ColorRole.Link, sys_acc)
                app.setPalette(p)
        elif accent_name and accent_name in ACCENT_COLORS and ACCENT_COLORS[accent_name]:
            p = QPalette(app.palette())
            p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_COLORS[accent_name]))
            p.setColor(QPalette.ColorRole.Link, QColor(ACCENT_COLORS[accent_name]))
            app.setPalette(p)
    elif theme_lower in ("bdm dark", "bdmdark", "dark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#202326", "#eff0f1", "#141618", "#1c1e20", "#2a2e32", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))
    else:  # BDM Auto (Default) / Default Fallback
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Unknown)
        
        is_sys_dark = is_system_dark_theme(app)

        if is_sys_dark:
            app.setPalette(_build_palette("#202326", "#eff0f1", "#141618", "#1c1e20", "#2a2e32", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))
        else:
            app.setPalette(_build_palette("#eff0f1", "#232629", "#ffffff", "#f8f9fa", "#eef0f2", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))

    # Icon theme handling
    global CURRENT_ICON_THEME, CURRENT_TRAY_ICON
    if icon_theme_name:
        CURRENT_ICON_THEME = str(icon_theme_name).strip()
    else:
        CURRENT_ICON_THEME = "BDM Auto (Default)"

    if tray_icon_name:
        CURRENT_TRAY_ICON = str(tray_icon_name).strip()
    else:
        CURRENT_TRAY_ICON = "App Icon (Default)"

    if icon_theme_name and str(icon_theme_name).lower() not in ("automatic", "bdm", "bdm auto (default)", "bdm auto", "bdmauto", "bdm (default)", "bdm dark", "bdmdark", "bdm light", "bdmlight", "modern color", "modern", "prism", "color", "vivid", "vibrant", "yaru", "ubuntu yaru", "stellar", "stellar icons", "stellaricons", "tmog neon", "tmog", "tmogneon", "cyber neon", "cyberneon", "cyber"):
        icon_lower = str(icon_theme_name).strip().lower()
        icon_map = {
            "breeze": "breeze",
            "breeze dark": "breeze-dark",
            "adwaita": "Adwaita",
            "highcolor": "hicolor"
        }
        if icon_lower in icon_map:
            QIcon.setThemeName(icon_map[icon_lower])
        else:
            QIcon.setThemeName(str(icon_theme_name))
    else:
        ensure_adaptive_icon_theme(app)

    app.setStyleSheet("""
            QMainWindow#MainWindow {
                border: 1px solid palette(mid);
            }
            QDialog {
                border: 1px solid palette(mid);
            }
            QMenuBar {
                background-color: palette(window);
                color: palette(window-text);
            }
            QMenuBar::item {
                background-color: transparent;
                color: palette(window-text);
                padding: 4px 10px;
            }
            QMenuBar::item:selected, QMenuBar::item:hover {
                background-color: palette(highlight);
                color: #000000;
            }
            QMenuBar::item:disabled {
                color: #888888;
                background-color: transparent;
            }
            QMenu {
                background-color: palette(window);
                color: palette(window-text);
                border: 1px solid palette(highlight);
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: palette(window-text);
                padding: 5px 24px 5px 12px;
                border-radius: 2px;
            }
            QMenu::item:selected, QMenu::item:hover {
                background-color: palette(highlight);
                color: #000000;
            }
            QMenu::item:disabled {
                color: #888888;
                background-color: transparent;
            }
            QMenu::item:disabled:selected, QMenu::item:disabled:hover {
                color: #888888;
                background-color: transparent;
            }
            QMenu::separator {
                height: 1px;
                background-color: palette(mid);
                margin: 4px 6px;
            }
            QPushButton:disabled {
                color: palette(disabled, button-text);
                background-color: palette(disabled, window);
                border: 1px solid palette(disabled, mid);
                opacity: 0.5;
            }
            QToolBar QToolButton {
                color: palette(window-text);
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 4px 6px;
                font-weight: normal;
                opacity: 1.0;
            }
            QToolBar QToolButton:hover {
                color: palette(window-text);
                background-color: palette(midlight);
                border: 1px solid palette(highlight);
                font-weight: bold;
                opacity: 1.0;
            }
            QToolBar QToolButton:pressed {
                background-color: palette(highlight);
                color: #000000;
            }
            QToolBar QToolButton:disabled {
                opacity: 0.30;
                background-color: transparent;
                border: 1px solid transparent;
            }
            QTableWidget {
                selection-color: #000000;
                selection-background-color: palette(highlight);
            }
            QTableWidget::item:selected, QTableWidget::item:selected:active, QTableWidget::item:selected:!active {
                color: #000000;
                background-color: palette(highlight);
            }
            QTreeWidget {
                selection-color: #000000;
                selection-background-color: palette(highlight);
            }
            QTreeWidget::item:selected, QTreeWidget::item:selected:active, QTreeWidget::item:selected:!active {
                color: #000000;
                background-color: palette(highlight);
            }
            QSplitter::handle:horizontal {
                background-color: palette(window);
            }
            QToolTip {
                background-color: palette(alternate-base);
                color: palette(window-text);
                border: 1px solid palette(mid);
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)

    for w in app.allWidgets():
        try:
            w.setPalette(app.palette())
            app.style().unpolish(w)
            app.style().polish(w)
            w.update()
        except Exception:
            pass

    # Apply Title bar theme
    apply_titlebar_theme(CURRENT_TITLE_BAR_MODE, app=app)

    for top in app.topLevelWidgets():
        try:
            refresh_fn = getattr(top, "refresh_theme_ui", None)
            if callable(refresh_fn):
                refresh_fn()
            top.update()
            top.repaint()
        except Exception:
            pass


def ensure_adaptive_icon_theme(app=None):
    search_paths = QIcon.themeSearchPaths()
    for p in ["/app/share/icons", "/usr/share/icons", os.path.expanduser("~/.local/share/icons")]:
        if os.path.exists(p) and p not in search_paths:
            search_paths.append(p)
    QIcon.setThemeSearchPaths(search_paths)

    if app is None:
        app = QApplication.instance()
    if not app:
        return

    window_color = app.palette().color(QPalette.ColorRole.Window)
    text_color = app.palette().color(QPalette.ColorRole.WindowText)
    is_dark = window_color.value() < 128 or text_color.value() > 128

    current_theme = QIcon.themeName()
    if is_dark:
        if not (current_theme.endswith("-dark") or "dark" in current_theme.lower()):
            dark_candidates = [f"{current_theme}-dark", "breeze-dark", "ubuntu-mono-dark", "Adwaita-dark"]
            for candidate in dark_candidates:
                found = False
                for sp in search_paths:
                    if os.path.exists(os.path.join(sp, candidate)):
                        QIcon.setThemeName(candidate)
                        found = True
                        break
                if found:
                    break


FREEDESKTOP_MAP = {
    "add_url": ["list-add", "document-new", "add"],
    "resume": ["media-playback-start", "go-down", "start"],
    "stop": ["process-stop", "media-playback-stop", "stop"],
    "stop_all": ["process-stop", "media-playback-stop", "stop"],
    "stop_all_queues": ["process-stop", "media-playback-stop", "stop"],
    "delete": ["user-trash", "edit-delete", "delete"],
    "clear_completed": ["edit-clear-all", "edit-clear", "clear"],
    "options": ["preferences-system", "configure", "settings"],
    "open_folder": ["folder-open", "folder-download", "folder"],
    "all_downloads": ["folder-download", "emblem-downloads", "download", "folder"],
    "compressed": ["package-x-generic", "application-x-archive", "archive"],
    "documents": ["x-office-document", "document", "text-x-generic"],
    "music": ["audio-x-generic", "audio", "sound"],
    "programs": ["system-run", "application-x-executable", "system"],
    "video": ["video-x-generic", "video", "media-video"],
    "unfinished": ["emblem-synchronizing", "process-working", "sync"],
    "finished": ["emblem-default", "dialog-ok", "check"],
    "exit": ["application-exit", "system-log-out", "exit"],
    "show_hide": ["window-new", "view-restore", "go-home"],
    "scheduler": ["chronometer", "appointment-soon", "alarm-clock"],
    "grabber": ["applications-internet", "web-browser", "download"]
}


def get_themed_icon(name: str, fallback=None, glow: bool = False) -> QIcon:
    """
    Returns a QIcon for the given name, respecting the user-configured icon theme.
    Falls back gracefully if the requested theme is unavailable or incomplete.
    """
    global CURRENT_ICON_THEME
    icon_theme = CURRENT_ICON_THEME if CURRENT_ICON_THEME else "BDM Auto (Default)"
    icon_theme_lower = str(icon_theme).strip().lower()

    if icon_theme_lower in ("colorful", "bdm colorful", "modern color", "modern", "prism", "prism color", "vivid", "color", "vibrant"):
        from ui.icons import get_colorful_icon
        return get_colorful_icon(name)

    if icon_theme_lower in ("yaru", "ubuntu yaru"):
        from ui.icons import get_yaru_icon
        return get_yaru_icon(name)

    if icon_theme_lower in ("stellar", "stellar icons", "stellaricons"):
        from ui.icons import get_stellar_icon
        return get_stellar_icon(name)

    if icon_theme_lower in ("tmog neon", "tmog", "tmogneon", "cyber neon", "cyberneon", "cyber"):
        from ui.icons import get_tmog_icon
        return get_tmog_icon(name)

    if icon_theme_lower not in ("automatic", "bdm", "bdm auto (default)", "bdm auto", "bdmauto", "bdm (default)", "bdm dark", "bdmdark", "bdm light", "bdmlight"):
        aliases = FREEDESKTOP_MAP.get(name, [name])
        for alias in aliases:
            ic = QIcon.fromTheme(alias)
            if not ic.isNull() and ic.name() != "":
                return ic

    if name in ("tray", "app_icon"):
        from ui.icons import get_monochrome_app_icon
        return get_monochrome_app_icon()

    from ui.icons import get_monochrome_icon

    if icon_theme_lower in ("bdm dark (default)", "bdm dark", "bdmdark"):
        icon = get_monochrome_icon(name, color=QColor("#ffffff"), selected_color=QColor("#000000"), glow=glow)
    elif icon_theme_lower in ("bdm light", "bdmlight"):
        icon = get_monochrome_icon(name, color=QColor("#232629"), selected_color=QColor("#000000"), glow=glow)
    else:
        app = QApplication.instance()
        if is_dark_theme(app):
            icon = get_monochrome_icon(name, color=QColor("#ffffff"), selected_color=QColor("#000000"), glow=glow)
        else:
            icon = get_monochrome_icon(name, color=QColor("#232629"), selected_color=QColor("#000000"), glow=glow)

    if not icon.isNull():
        return icon
    
    ensure_adaptive_icon_theme()
    icon = QIcon.fromTheme(name)
    if (icon.isNull() or icon.name() == "") and fallback:
        icon = fallback if isinstance(fallback, QIcon) else QIcon(fallback)
    return icon


def make_faded_icon(icon: QIcon, opacity: float = 0.30) -> QIcon:
    """Returns a copy of icon with an explicit Disabled-mode pixmap at reduced opacity."""
    src = icon.pixmap(24, 24, QIcon.Mode.Normal)
    if src.isNull():
        return icon
    faded = QPixmap(src.size())
    faded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(faded)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, src)
    painter.end()
    new_icon = QIcon(icon)
    new_icon.addPixmap(faded, QIcon.Mode.Disabled, QIcon.State.Off)
    new_icon.addPixmap(faded, QIcon.Mode.Disabled, QIcon.State.On)
    return new_icon


def get_app_icon() -> QIcon:
    """Robustly finds and returns the application icon across snap, Flatpak, AppImage, and local environments."""
    _meipass   = getattr(sys, "_MEIPASS", None)
    _snap      = os.environ.get("SNAP")
    _snap_root = os.environ.get("SNAP_APP_ROOT") or (os.path.join(_snap, "share", "bengal-download-manager") if _snap else None)
    _appdir    = os.environ.get("APPDIR")
    # sys.argv[0]-relative: set by the OS at exec() time, never baked into .pyc bytecode.
    _argv0_src  = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else None
    _argv0_root = os.path.dirname(_argv0_src) if _argv0_src else None
    # Module relative (src/core/services -> repo root): safe fallback for local dev & pytest
    _module_dir  = os.path.dirname(os.path.abspath(__file__)) if __file__ else None
    _module_root = os.path.dirname(os.path.dirname(os.path.dirname(_module_dir))) if _module_dir else None

    icon_locations = [
        # 1. PyInstaller bundle (_MEIPASS set at runtime by bootloader, only when frozen)
        *([
            os.path.join(_meipass, "assets", "icons", "256x256.png"),
            os.path.join(_meipass, "assets", "icons", "512x512.png"),
            os.path.join(_meipass, "assets", "logo.svg"),
            os.path.join(_meipass, "assets", "logo.png"),
        ] if _meipass else []),

        # 2. Snap — $SNAP hicolor icons (installed by snapcraft override-build)
        *([
            os.path.join(_snap, "usr", "share", "icons", "hicolor", "scalable", "apps", "bd.com.zihad.BengalDownloadManager.svg"),
            os.path.join(_snap, "usr", "share", "icons", "hicolor", "512x512", "apps", "bd.com.zihad.BengalDownloadManager.png"),
            os.path.join(_snap, "usr", "share", "icons", "hicolor", "256x256", "apps", "bd.com.zihad.BengalDownloadManager.png"),
        ] if _snap else []),

        # 3. Snap — $SNAP_APP_ROOT bundled assets (exported by bengal-wrapper.sh)
        *([
            os.path.join(_snap_root, "assets", "icons", "256x256.png"),
            os.path.join(_snap_root, "assets", "icons", "512x512.png"),
            os.path.join(_snap_root, "assets", "logo.svg"),
            os.path.join(_snap_root, "assets", "logo.png"),
        ] if _snap_root else []),

        # 4. Flatpak — /app hicolor (fixed path per Flatpak spec)
        "/app/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg",
        "/app/share/icons/hicolor/512x512/apps/bd.com.zihad.BengalDownloadManager.png",
        "/app/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png",
        "/app/share/icons/hicolor/128x128/apps/bd.com.zihad.BengalDownloadManager.png",

        # 5. AppImage — $APPDIR hicolor
        *([
            os.path.join(_appdir, "usr", "share", "icons", "hicolor", "scalable", "apps", "bd.com.zihad.BengalDownloadManager.svg"),
            os.path.join(_appdir, "usr", "share", "icons", "hicolor", "512x512", "apps", "bd.com.zihad.BengalDownloadManager.png"),
            os.path.join(_appdir, "usr", "share", "icons", "hicolor", "256x256", "apps", "bd.com.zihad.BengalDownloadManager.png"),
            os.path.join(_appdir, "usr", "share", "icons", "hicolor", "256x256", "apps", "bengal-download-manager.png"),
            os.path.join(_appdir, "bd.com.zihad.BengalDownloadManager.png"),
        ] if _appdir else []),

        # 6. Standard system hicolor (deb / rpm / manual install)
        "/usr/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg",
        "/usr/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png",
        "/usr/local/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg",
        "/usr/local/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png",

        # 7. User XDG local icons
        os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg"),
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png"),

        # 8. sys.argv[0]-relative fallback (runtime-stable; works for snap, dev, any install layout)
        *([
            os.path.join(_argv0_root, "assets", "icons", "256x256.png"),
            os.path.join(_argv0_root, "assets", "icons", "512x512.png"),
            os.path.join(_argv0_root, "assets", "logo.svg"),
            os.path.join(_argv0_root, "assets", "logo.png"),
        ] if _argv0_root else []),

        # 9. Module directory relative (for pytest runner and local development)
        *([
            os.path.join(_module_root, "assets", "icons", "256x256.png"),
            os.path.join(_module_root, "assets", "icons", "512x512.png"),
            os.path.join(_module_root, "assets", "logo.svg"),
            os.path.join(_module_root, "assets", "logo.png"),
        ] if _module_root else []),

        # 10. User data dir (manually placed assets)
        os.path.join(get_data_dir(), "assets", "icons", "256x256.png"),
        os.path.join(get_data_dir(), "assets", "logo.svg"),
        os.path.join(get_data_dir(), "assets", "logo.png"),
    ]

    for loc in icon_locations:
        if loc and os.path.isabs(loc) and os.path.exists(loc):
            icon = QIcon(loc)
            if not icon.isNull():
                return icon

    # Theme icon fallbacks
    for theme_name in ["bd.com.zihad.BengalDownloadManager", "bengal-download-manager"]:
        icon = QIcon.fromTheme(theme_name)
        if not icon.isNull():
            return icon
                
def get_monochrome_app_icon(color=None, size=24) -> QIcon:
    """
    Converts the Bengal Download Manager application logo into a clean, sharp
    monochrome icon adapting to light/dark window text colors for system tray.
    """
    app = QApplication.instance()
    if color is None:
        if app:
            color = app.palette().color(QPalette.ColorRole.WindowText)
        else:
            color = QColor("#ffffff")

    app_ic = get_app_icon()
    if app_ic.isNull():
        return app_ic
    
    pm = app_ic.pixmap(size * 2, size * 2)
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    
    r, g, b, _ = color.getRgb()
    for x in range(img.width()):
        for y in range(img.height()):
            pixel_color = img.pixelColor(x, y)
            alpha = pixel_color.alpha()
            if alpha > 0:
                img.setPixelColor(x, y, QColor(r, g, b, alpha))
                
    mono_pm = QPixmap.fromImage(img)
    ic = QIcon()
    ic.addPixmap(mono_pm)
    return ic


def resolve_asset(filename: str) -> str:
    """Finds asset path across snap, Flatpak, AppImage, and local environments."""
    _meipass   = getattr(sys, "_MEIPASS", None)
    _snap      = os.environ.get("SNAP")
    _snap_root = os.environ.get("SNAP_APP_ROOT") or (os.path.join(_snap, "share", "bengal-download-manager") if _snap else None)
    _appdir    = os.environ.get("APPDIR")
    # sys.argv[0]-relative: set by OS at exec() time, never baked into .pyc bytecode.
    _argv0_src  = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else None
    _argv0_root = os.path.dirname(_argv0_src) if _argv0_src else None
    # Module relative (src/core/services -> repo root): safe fallback for local dev & pytest
    _module_dir  = os.path.dirname(os.path.abspath(__file__)) if __file__ else None
    _module_root = os.path.dirname(os.path.dirname(os.path.dirname(_module_dir))) if _module_dir else None

    candidates = [
        # 1. PyInstaller
        *([os.path.join(_meipass, "assets", filename)] if _meipass else []),
        # 2. Snap — $SNAP_APP_ROOT bundled assets (exported by bengal-wrapper.sh)
        *([os.path.join(_snap_root, "assets", filename)] if _snap_root else []),
        # 3. Flatpak
        f"/app/share/bengal-download-manager/assets/{filename}",
        # 4. AppImage
        *([
            os.path.join(_appdir, "usr", "lib", "bengal-download-manager", "_internal", "assets", filename),
            os.path.join(_appdir, "assets", filename),
        ] if _appdir else []),
        # 5. Standard system install (deb / rpm / manual)
        f"/usr/share/bengal-download-manager/assets/{filename}",
        f"/usr/local/share/bengal-download-manager/assets/{filename}",
        # 6. sys.argv[0]-relative fallback (runtime-stable)
        *([os.path.join(_argv0_root, "assets", filename)] if _argv0_root else []),
        # 7. Module directory relative (for pytest runner and local development)
        *([os.path.join(_module_root, "assets", filename)] if _module_root else []),
        # 8. User data dir
        os.path.join(get_data_dir(), "assets", filename),
    ]
    for c in candidates:
        if c and os.path.isabs(c) and os.path.exists(c):
            return c
    return ""


_resolve_tray_asset = resolve_asset


def get_themed_tray_icon(tray_option=None) -> QIcon:
    """Resolves system tray icon based on tray icon theme selection."""
    global CURRENT_TRAY_ICON
    if tray_option is None:
        tray_option = CURRENT_TRAY_ICON if CURRENT_TRAY_ICON else "App Icon (Default)"

    light_path = (
        _resolve_tray_asset("icons/tray/tray_monochrome_light.svg")
        or _resolve_tray_asset("icons/tray/tray_monochrome_light.png")
        or _resolve_tray_asset("tray_monochrome_light.svg")
        or _resolve_tray_asset("tray_monochrome_light.png")
    )
    dark_path = (
        _resolve_tray_asset("icons/tray/tray_monochrome_dark.svg")
        or _resolve_tray_asset("icons/tray/tray_monochrome_dark.png")
        or _resolve_tray_asset("tray_monochrome_dark.svg")
        or _resolve_tray_asset("tray_monochrome_dark.png")
    )

    if opt_lower in ("app icon (default)", "app icon", "app_icon", "bdm app icon"):
        icon = get_app_icon()
        if not icon.isNull():
            return icon
    elif opt_lower in ("monochrome light", "monochromelight"):
        if light_path:
            ic = QIcon(light_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon(color=QColor("#ffffff"))
    elif opt_lower in ("monochrome dark", "monochromedark"):
        if dark_path:
            ic = QIcon(dark_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon(color=QColor("#232629"))
    elif opt_lower == "automatic":
        app = QApplication.instance()
        text_val = app.palette().color(QPalette.ColorRole.WindowText).value() if app else 255
        target_path = light_path if text_val > 128 else dark_path
        if target_path:
            ic = QIcon(target_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon()

    icon = get_app_icon()
    if not icon.isNull():
        return icon
    app = QApplication.instance()
    if app:
        return app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    return QIcon()


from core.categories import (
    CATEGORY_EXTENSIONS,
    get_category_for_filename,
    get_all_categories,
    format_timestamp_relative,
    parse_size_to_bytes,
    parse_time_to_sec,
)


def get_file_icon(filename: str) -> QIcon:
    if not filename:
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    ext = os.path.splitext(filename)[1].lower()

    if ext in [".exe", ".msi"]:
        return get_themed_icon("exe")
    elif ext == ".appimage":
        return get_themed_icon("appimage")
    elif ext == ".flatpak":
        return get_themed_icon("flatpak")
    elif ext in [".deb", ".rpm", ".apk", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"]:
        return get_themed_icon("programs")

    db = QMimeDatabase()
    mime = db.mimeTypeForFile(filename, QMimeDatabase.MatchMode.MatchExtension)
    if mime.isValid():
        icon_name = mime.iconName()
        icon = get_themed_icon(icon_name)
        if not icon.isNull() and icon.name() != "":
            return icon
        generic_name = mime.genericIconName()
        if generic_name:
            g_icon = get_themed_icon(generic_name)
            if not g_icon.isNull() and g_icon.name() != "":
                return g_icon

    info = QFileInfo(filename)
    provider = QFileIconProvider()
    icon = provider.icon(info)
    if not icon.isNull():
        return icon

    cat = get_category_for_filename(filename)
    fallbacks = {
        "Programs": get_themed_icon("system-run", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMenuButton)),
        "Compressed": get_themed_icon("package-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DriveFDIcon)),
        "Documents": get_themed_icon("x-office-document", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)),
        "Music": get_themed_icon("audio-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)),
        "Video": get_themed_icon("video-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)),
    }
    return fallbacks.get(cat, QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

