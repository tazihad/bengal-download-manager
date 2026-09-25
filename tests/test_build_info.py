"""
Unit tests for build info, package type detection, source verification,
SHA-256 release checksum matching, and desktop integration constraints.
"""

import hashlib
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from core.build_info import (
    clear_build_info_cache,
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


@pytest.fixture(autouse=True)
def reset_build_info_cache():
    clear_build_info_cache()
    yield
    clear_build_info_cache()


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
        assert "Checksums (SHA-256) matched" in note

    # GitHub snap via BDM_SNAP_SOURCE override
    with patch.dict(os.environ, {"SNAP": "/snap/bengal-download-manager/current", "SNAP_NAME": "bengal-download-manager", "BDM_SNAP_SOURCE": "github"}, clear=True):
        is_verified, url, note = get_verified_source_info("0.2.56-alpha.3")
        assert is_verified is True
        assert url == f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.56-alpha.3"
        assert "Checksums (SHA-256) matched" in note

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
    from ui.dialogs.about import AboutDialog
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    # 1. Dev build opens immediately without verified badge
    dlg = AboutDialog(window)
    qtbot.addWidget(dlg)
    dlg.show()
    assert "About Bengal Download Manager" in dlg.windowTitle()
    assert dlg.pkg_type == "Dev Build"
    assert "✔ Verified Source" not in dlg.verify_label.text()
    dlg.close()

    # 2. Release Tar build with async verification
    with patch.object(sys, "frozen", True, create=True), \
         patch.dict(os.environ, {}, clear=True), \
         patch("core.build_info.verify_source_status", return_value=("verified", f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.57", "Checksums (SHA-256) matched")):
        dlg = AboutDialog(window)
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitUntil(lambda: "Verified Source" in dlg.verify_label.text(), timeout=2000)
        assert dlg.pkg_type == "Tar Build"
        assert "✔ Verified Source" in dlg.verify_label.text()
        assert "Checksums (SHA-256) matched" in dlg.verify_label.toolTip()
        dlg.close()

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


def test_about_verified_source_hover_tooltip(qtbot):
    from ui.dialogs.about import AboutDialog
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    with patch.object(sys, "frozen", True, create=True), \
         patch.dict(os.environ, {}, clear=True), \
         patch("core.build_info.verify_source_status", return_value=("verified", f"{OFFICIAL_GITHUB_REPO}/releases/tag/v0.2.57", "Checksums (SHA-256) matched")):
        dlg = AboutDialog(window)
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitUntil(lambda: "Verified Source" in dlg.verify_label.text(), timeout=2000)
        assert dlg.verify_label.isVisible()
        assert "Checksums (SHA-256) matched" in dlg.verify_label.toolTip()
        dlg.close()

    window.close()


def test_about_dialog_offline_warning(qtbot):
    """Test that About dialog displays a small size text warning when no network is available."""
    from ui.dialogs.about import AboutDialog
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    with patch.object(sys, "frozen", True, create=True), \
         patch.dict(os.environ, {}, clear=True), \
         patch("core.build_info.verify_source_status", return_value=("no_network", "", "No network connection")):
        dlg = AboutDialog(window)
        qtbot.addWidget(dlg)
        dlg.show()
        # Dialog opens immediately and spinner starts
        assert dlg.isVisible()
        assert dlg.spinner.isVisible()

        # On network failure, spinner hides and warning text displays
        qtbot.waitUntil(lambda: "No network" in dlg.verify_label.text(), timeout=2000)
        assert not dlg.spinner.isVisible()
        assert "No network" in dlg.verify_label.text()
        assert "no network connection" in dlg.verify_label.toolTip().lower()
        dlg.close()

    window.close()


def test_main_window_show_about(qtbot):
    from ui.main_window import MainWindow
    from ui.dialogs.about import AboutDialog

    window = MainWindow()
    qtbot.addWidget(window)

    with patch.object(AboutDialog, "exec") as mock_exec:
        window.show_about()
        assert mock_exec.called

    window.close()


def test_about_dialog_and_verification_instantaneous():
    import time
    t0 = time.perf_counter()
    get_verified_source_info()
    t1 = time.perf_counter()
    assert (t1 - t0) < 0.05

