# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for Bengal Download Manager (Windows x64).
Incorporates the native Windows DWM theming fixes, Fusion style configuration,
OpenType fonts, Kirigami QML components, and desktop metadata.
"""

import os
import sys

block_cipher = None

CONFIG_DIR = os.path.abspath(SPECPATH)
WINDOWS_DIR = os.path.abspath(os.path.join(CONFIG_DIR, ".."))
BUILD_DIR = os.path.abspath(os.path.join(WINDOWS_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(BUILD_DIR, ".."))

src_path = os.path.join(PROJECT_ROOT, "src")
fixes_path = os.path.join(WINDOWS_DIR, "fixes")
assets_path = os.path.join(PROJECT_ROOT, "assets")
version_file = os.path.join(PROJECT_ROOT, "VERSION")
icon_file = os.path.join(assets_path, "app_icon.ico")
if not os.path.exists(icon_file):
    icon_file = os.path.join(CONFIG_DIR, "assets", "app_icon.ico")
entrypoint_file = os.path.join(fixes_path, "entrypoint_windows.py")

datas = [
    (assets_path, "assets"),
    (version_file, "."),
    (os.path.join(src_path, "ui", "qml"), os.path.join("ui", "qml")),
]

# Optional third-party binaries (yt-dlp, ffmpeg, aria2c) if staged in windows/bin/
bin_dir = os.path.join(WINDOWS_DIR, "bin")
binaries = []
if os.path.isdir(bin_dir):
    for f in os.listdir(bin_dir):
        if f.endswith(".exe") or f.endswith(".dll"):
            binaries.append((os.path.join(bin_dir, f), "."))

hiddenimports = [
    "ctypes",
    "ctypes.wintypes",
    "winreg",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    "PyQt6.QtQml",
    "theme_fix",
    "theme_fix.windows_theme_fix",
]

from PyInstaller.utils.hooks import collect_all
for mod in ["core", "ui", "python_socks"]:
    try:
        tmp_ret = collect_all(mod)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

a = Analysis(
    [entrypoint_file],
    pathex=[src_path, fixes_path, WINDOWS_DIR, PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 1. Onedir Mode Executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bengal-download-manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="bengal-download-manager",
)

