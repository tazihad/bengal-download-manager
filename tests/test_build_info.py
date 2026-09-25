"""
Unit tests for build info, package type detection, source verification,
SHA-256 release checksum matching, and desktop integration constraints.
"""

import hashlib
import os
import sys
from unittest.mock import patch, MagicMock

from core.build_info import (
    compute_file_sha256,
    fetch_github_release_checksums,
    get_package_type,
    get_verified_source_info,
    verify_file_against_github_release,
    verify_snapcraft_store_metadata,
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


def test_compute_file_sha256(tmp_path):
    test_file = tmp_path / "sample.bin"
    test_data = b"Bengal Download Manager Verification Test 12345"
    test_file.write_bytes(test_data)

    expected_hash = hashlib.sha256(test_data).hexdigest()
    computed = compute_file_sha256(str(test_file))
    assert computed == expected_hash

    # Non-existent file returns None
    assert compute_file_sha256(str(tmp_path / "nonexistent.bin")) is None


def test_verify_file_against_github_release(tmp_path):
    appimage_file = tmp_path / "bengal-download-manager-0.2.55-x86_64.AppImage"
    content = b"Mock AppImage Content"
    appimage_file.write_bytes(content)
    actual_hash = hashlib.sha256(content).hexdigest()

    mock_checksums = {
        "bengal-download-manager-0.2.55-x86_64.AppImage": actual_hash,
        "bengal-download-manager-0.2.55-x86_64.tar.xz": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    }

    with patch("core.build_info.fetch_github_release_checksums", return_value=mock_checksums):
        # 1. Matching hash
        matched, comp, exp = verify_file_against_github_release(str(appimage_file), "0.2.55")
        assert matched is True
        assert comp == actual_hash
        assert exp == actual_hash

        # 2. Checksum mismatch with corrupted file
        corrupted_file = tmp_path / "corrupted.AppImage"
        corrupted_file.write_bytes(b"Tampered payload")
        matched, comp, exp = verify_file_against_github_release(str(corrupted_file), "0.2.55")
        assert matched is False


def test_verified_source_info_snap():
    # Verified Snap
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager", "SNAP_NAME": "bengal-download-manager"}, clear=True):
        is_verified, url, note = get_verified_source_info()
        assert is_verified is True
        assert url == OFFICIAL_SNAP_URL
        assert "Launchpad" in note or "Snap" in note

    # Unverified / third-party snap
    with patch.dict(os.environ, {"SNAP": "/snap/other-dm", "SNAP_NAME": "other-dm"}, clear=True):
        is_verified, url, note = get_verified_source_info()
        assert is_verified is False
        assert url == ""


def test_verified_source_info_dev_and_tar():
    # Official repository git checkout in dev build
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", False, create=True):
            is_verified, url, note = get_verified_source_info()
            assert is_verified is True
            assert url == OFFICIAL_GITHUB_REPO
            assert "GitHub" in note

    # Tar build / AppImage
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", True, create=True):
            is_verified, url, note = get_verified_source_info()
            assert is_verified is True
            assert url == OFFICIAL_GITHUB_REPO
            assert "SHA-256" in note


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
        assert "Verification:" in text
    window.close()
