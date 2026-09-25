"""
Unit tests for build info, package type detection, source verification,
and desktop integration constraints.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from core.build_info import (
    get_package_type,
    get_verified_source_info,
    OFFICIAL_GITHUB_REPO,
    OFFICIAL_SNAP_URL,
)
from core.desktop import ensure_desktop_integration


def test_package_type_detection():
    # 1. Dev build default (unfrozen)
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", False, create=True):
            assert get_package_type() == "Dev Build"

    # 2. Flatpak via FLATPAK_ID
    with patch.dict(os.environ, {"FLATPAK_ID": "bd.com.zihad.BengalDownloadManager"}, clear=True):
        assert get_package_type() == "Flatpak"

    # 3. Snap via SNAP
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/current"}, clear=True):
        assert get_package_type() == "Snap"

    # 4. AppImage via APPIMAGE
    with patch.dict(os.environ, {"APPIMAGE": "/path/to/bdm.AppImage"}, clear=True):
        assert get_package_type() == "AppImage"

    # 5. Tar build via sys.frozen
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", True, create=True):
            assert get_package_type() == "Tar Build"

    # 6. Override via BDM_PACKAGE_TYPE
    with patch.dict(os.environ, {"BDM_PACKAGE_TYPE": "Custom Build"}, clear=True):
        assert get_package_type() == "Custom Build"


def test_verified_source_info_snap():
    # Verified Snap
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager", "SNAP_NAME": "bengal-download-manager"}, clear=True):
        is_verified, url = get_verified_source_info()
        assert is_verified is True
        assert url == OFFICIAL_SNAP_URL

    # Unverified / third-party snap
    with patch.dict(os.environ, {"SNAP": "/snap/other-dm", "SNAP_NAME": "other-dm"}, clear=True):
        is_verified, url = get_verified_source_info()
        assert is_verified is False
        assert url == ""


def test_verified_source_info_dev_and_tar():
    # Official repository git checkout in dev build
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", False, create=True):
            is_verified, url = get_verified_source_info()
            assert is_verified is True
            assert url == OFFICIAL_GITHUB_REPO

    # Tar build / AppImage
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", True, create=True):
            is_verified, url = get_verified_source_info()
            assert is_verified is True
            assert url == OFFICIAL_GITHUB_REPO


def test_ensure_desktop_integration_skips_in_dev_build(tmp_path):
    fake_home = str(tmp_path / "home")
    apps_dir = os.path.join(fake_home, ".local", "share", "applications")
    os.makedirs(apps_dir, exist_ok=True)

    with patch("os.path.expanduser", return_value=fake_home), \
         patch.object(sys, "platform", "linux"), \
         patch.object(sys, "frozen", False, create=True), \
         patch.dict(os.environ, {"BDM_TESTING": "0"}, clear=True), \
         patch.dict(sys.modules, {"pytest": MagicMock()}):
        # Even if BDM_TESTING is cleared, sys.frozen is False, so dev build must NOT create desktop file
        ensure_desktop_integration()
        desktop_file = os.path.join(apps_dir, "bd.com.zihad.BengalDownloadManager.desktop")
        assert not os.path.exists(desktop_file)


def test_about_dialog_formatting(qtbot):
    from PyQt6.QtWidgets import QMessageBox
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    with patch.object(QMessageBox, "about") as mock_about:
        window.show_about()
        assert mock_about.called
        title, text = mock_about.call_args[0][1], mock_about.call_args[0][2]
        assert "About Bengal Download Manager" in title
        assert "https://zihad.com.bd/bengal-download-manager" in text
        assert "✔ Verified Source" in text
        assert "(Dev Build)" in text
    window.close()
