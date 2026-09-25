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
    is_snap_origin_github,
    verify_file_against_github_release,
    verify_snapcraft_store_metadata,
    OFFICIAL_GITHUB_REPO,
    OFFICIAL_SNAP_URL,
)


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
    # 1. Verified Snap from Canonical Snapcraft Store (numeric store revision)
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/42", "SNAP_NAME": "bengal-download-manager", "SNAP_REVISION": "42"}, clear=True):
        is_verified, url, note = get_verified_source_info()
        assert is_verified is True
        assert url == OFFICIAL_SNAP_URL
        assert "Launchpad" in note or "Snap" in note

    # Snapcraft store via BDM_SNAP_SOURCE override
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/current", "SNAP_NAME": "bengal-download-manager", "BDM_SNAP_SOURCE": "snapcraft"}, clear=True):
        is_verified, url, note = get_verified_source_info()
        assert is_verified is True
        assert url == OFFICIAL_SNAP_URL

    # 2. Verified Snap from GitHub (sideloaded revision starting with 'x', e.g. x1)
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/x1", "SNAP_NAME": "bengal-download-manager", "SNAP_REVISION": "x1"}, clear=True):
        is_verified, url, note = get_verified_source_info("0.2.56-alpha.3")
        assert is_verified is True
        assert url == f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.56-alpha.3"
        assert "GitHub" in note

    # GitHub snap via BDM_SNAP_SOURCE override
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/current", "SNAP_NAME": "bengal-download-manager", "BDM_SNAP_SOURCE": "github"}, clear=True):
        is_verified, url, note = get_verified_source_info("0.2.56-alpha.3")
        assert is_verified is True
        assert url == f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.56-alpha.3"
        assert "GitHub" in note

    # 3. Unverified / third-party snap
    with patch.dict(os.environ, {"SNAP": "/snap/other-dm", "SNAP_NAME": "other-dm"}, clear=True):
        is_verified, url, note = get_verified_source_info()
        assert is_verified is False
        assert url == ""


def test_is_snap_origin_github(tmp_path):
    # Overrides
    with patch.dict(os.environ, {"BDM_SNAP_SOURCE": "github"}, clear=True):
        assert is_snap_origin_github() is True
    with patch.dict(os.environ, {"BDM_SNAP_SOURCE": "snapcraft"}, clear=True):
        assert is_snap_origin_github() is False

    # Snap revision
    with patch.dict(os.environ, {"SNAP_REVISION": "x10"}, clear=True):
        assert is_snap_origin_github() is True
    with patch.dict(os.environ, {"SNAP_REVISION": "55"}, clear=True):
        assert is_snap_origin_github() is False

    # Mount path
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/x2"}, clear=True):
        assert is_snap_origin_github() is True
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/12"}, clear=True):
        assert is_snap_origin_github() is False

    # Build marker in version.py inside mock snap dir
    mock_snap = tmp_path / "mock_snap"
    mock_core = mock_snap / "share" / "bengal-download-manager" / "src" / "core"
    mock_core.mkdir(parents=True)
    ver_file = mock_core / "version.py"
    ver_file.write_text("# Generated by build-snap action\nVERSION = '1.0.0'\n")
    with patch.dict(os.environ, {"SNAP": str(mock_snap)}, clear=True):
        assert is_snap_origin_github() is True


def test_verified_source_info_dev_and_tar():
    # Dev build is a local checkout, not a GitHub release, so it is unverified
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", False, create=True):
            is_verified, url, note = get_verified_source_info()
            assert is_verified is False
            assert url == ""
            assert note == ""

    # Tar build / AppImage has tag-specific release URL and SHA-256 tooltip
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "frozen", True, create=True):
            is_verified, url, note = get_verified_source_info("0.2.55")
            assert is_verified is True
            assert url == f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.55"
            assert "SHA-256" in note


def test_about_dialog_formatting(qtbot):
    from PyQt6.QtWidgets import QMessageBox
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    # 1. Dev build
    with patch.object(QMessageBox, "about") as mock_about:
        window.show_about()
        assert mock_about.called
        title, text = mock_about.call_args[0][1], mock_about.call_args[0][2]
        assert "About Bengal Download Manager" in title
        assert "https://zihad.com.bd/bengal-download-manager" in text
        assert "(Dev Build)" in text
        # Dev build should not claim to be in a GitHub release
        assert "✔ Verified Source" not in text

    # 2. Release Tar build with SHA-256 verification and tooltip
    with patch.object(sys, "frozen", True, create=True), \
         patch.dict(os.environ, {}, clear=True), \
         patch.object(QMessageBox, "about") as mock_about:
        window.show_about()
        assert mock_about.called
        _, text = mock_about.call_args[0][1], mock_about.call_args[0][2]
        assert "(Tar Build)" in text
        assert "✔ Verified Source" in text
        assert "title='Verified using SHA-256 release checksum'" in text
        assert "/releases/tag/v" in text

    window.close()


def test_help_menu_homepage_url(qtbot):
    from PyQt6.QtGui import QDesktopServices
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    with patch.object(QDesktopServices, "openUrl") as mock_open:
        window.action_homepage.trigger()
        assert mock_open.called
        opened_url = mock_open.call_args[0][0].toString()
        assert opened_url == "https://zihad.com.bd/bengal-download-manager"

    window.close()
