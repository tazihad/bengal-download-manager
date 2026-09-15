"""
Windows Entry Point for Bengal Download Manager.
Bootstraps Windows native DWM dark title bars, dynamic Fusion/native theming, and registry integration
before executing the core application, requiring zero changes to main application sources.
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("io.github.tazihad.bengal-download-manager")
    except Exception:
        pass

# Current file is in build/windows/fixes/entrypoint_windows.py
FIXES_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOWS_DIR = os.path.dirname(FIXES_DIR)
BUILD_DIR = os.path.dirname(WINDOWS_DIR)
REPO_ROOT = os.path.dirname(BUILD_DIR)

SRC_DIR = os.path.join(REPO_ROOT, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if FIXES_DIR not in sys.path:
    sys.path.insert(1, FIXES_DIR)
if WINDOWS_DIR not in sys.path:
    sys.path.insert(2, WINDOWS_DIR)

from PyQt6.QtWidgets import QApplication
from theme_fix.windows_theme_fix import apply_windows_theme_patches

# Pre-patch theme_service and utils before main imports them
apply_windows_theme_patches()

# Hook QApplication initialization so that style and DWM hooks are active immediately
_orig_qapp_init = QApplication.__init__


def _patched_qapp_init(self, *args, **kwargs):
    _orig_qapp_init(self, *args, **kwargs)
    apply_windows_theme_patches(self)


QApplication.__init__ = _patched_qapp_init  # type: ignore

if __name__ == "__main__":
    from main import main
    main()
