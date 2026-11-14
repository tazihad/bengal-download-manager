# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build description for Bengal Download Manager.

Build modes
-----------
* one-file (default): a single self-contained executable.
* one-dir: set ``BDM_ONEDIR=1`` in the environment.  Useful for inspecting or
  debugging the bundled payload.

Unused Qt modules are removed from the Analysis TOCs *before* the executable
is packed.  This matters for one-file builds, where there is no application
directory left to clean after the build.  The purge list lives in
``scripts/cleanup_application_tree.py`` and is shared with the standalone
post-build cleaner for one-dir output.

Environment
-----------
``BDM_ASSETS_DIR``
    Directory holding the prepared runtime assets (see
    ``scripts/prepare_runtime_assets.sh``).  Defaults to
    ``.pyinstaller-build/runtime_assets`` under the repository root.
``BDM_ONEDIR``
    Set to ``1`` for a one-dir build instead of the one-file default.
``BDM_SLIM``
    Set to ``0`` to keep the full, unfiltered payload.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

# Make the shared purge list importable from this spec.
sys.path.insert(0, os.path.join(SPECPATH, "scripts"))
from cleanup_application_tree import filter_toc  # noqa: E402

ROOT_DIR = os.path.abspath(SPECPATH)
ASSETS_DIR = os.path.abspath(
    os.environ.get("BDM_ASSETS_DIR") or os.path.join(ROOT_DIR, ".pyinstaller-build", "runtime_assets")
)

datas = []
if os.path.isdir(ASSETS_DIR):
    datas.append((ASSETS_DIR, "assets"))
else:
    print(f"[spec] WARNING: runtime assets directory not found: {ASSETS_DIR}")

# src/core/version.py reads VERSION from the bundle root as the last-resort
# fallback, so the canonical SSOT file must ship inside the executable.
VERSION_FILE = os.path.join(ROOT_DIR, "VERSION")
if os.path.isfile(VERSION_FILE):
    datas.append((VERSION_FILE, "."))
else:
    print(f"[spec] WARNING: canonical VERSION file not found: {VERSION_FILE}")
binaries = []
hiddenimports = []
tmp_ret = collect_all("core")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all("ui")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all("python_socks")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Drop Qt/GTK libraries, plugins, and translation catalogs that Bengal DM
# never loads.  See scripts/cleanup_application_tree.py for the full list.
# Set BDM_SLIM=0 to build the unfiltered bundle (useful for comparisons).
if os.environ.get("BDM_SLIM", "1") != "0":
    a.binaries, _removed_binaries = filter_toc(a.binaries, label="bundled binaries")
    a.datas, _removed_datas = filter_toc(a.datas, label="bundled data")

ONEDIR = os.environ.get("BDM_ONEDIR", "0") == "1"

if ONEDIR:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="bengal-download-manager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=True,
        upx=True,
        upx_exclude=[],
        name="bengal-download-manager",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="bengal-download-manager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
