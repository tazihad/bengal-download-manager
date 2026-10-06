"""
Sanity tests for Bengal Download Manager.
Verifies core package imports, version definitions, and basic utility functions.
"""

import os
import sys


def test_version_defined():
    """Verify application version is defined and non-empty."""
    from core.version import VERSION
    assert VERSION
    assert isinstance(VERSION, str)


def test_core_imports():
    """Verify core modules can be imported without errors."""
    import core.utils
    import core.config
    import core.categories
    from core.utils import format_bytes
    from core.categories import parse_size_to_bytes
    assert format_bytes(1024) == "1.00 KB"
    assert parse_size_to_bytes("1.00 KB") == 1024


def test_media_extractor_helpers():
    """Verify media extractor resolution and container helpers."""
    from core.media.extractor import get_effective_resolution, determine_media_container_ext
    # Landscape
    assert get_effective_resolution({"width": 1920, "height": 1080}) == 1080
    # Portrait
    assert get_effective_resolution({"width": 1080, "height": 1920}) == 1080
    assert get_effective_resolution({"width": 720, "height": 1280}) == 720
    # Container resolution
    assert determine_media_container_ext([{"ext": "mp4"}, {"ext": "webm"}]) == ".mkv"
    assert determine_media_container_ext([{"ext": "mp4"}, {"ext": "m4a"}]) == ".mp4"
    assert determine_media_container_ext([{"ext": "webm"}, {"ext": "webm"}]) == ".webm"


def test_themed_tray_icon():
    """Verify system tray icon resolution succeeds without NameError or crash."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["-platform", "offscreen"])
    from core.services.theme_service import get_themed_tray_icon
    for opt in [None, "App Icon (Default)", "Monochrome Light", "Monochrome Dark", "Automatic"]:
        icon = get_themed_tray_icon(opt)
        assert icon is not None
        assert not icon.isNull()


def test_wrap_url_tooltip():
    """Verify wrap_url_tooltip wraps long URLs and leaves short URLs untouched."""
    from core.utils import wrap_url_tooltip

    # 1. Empty or None
    assert wrap_url_tooltip("") == ""
    assert wrap_url_tooltip(None) == ""

    # 2. Short URL
    short_url = "https://example.com/test.zip"
    assert wrap_url_tooltip(short_url) == short_url

    # 3. Long URL with query parameters
    long_url = (
        "https://downloads.example.org/path/to/archive/release/v1.0.0/bigfile.iso"
        "?token=abcdef1234567890&session=xyz987654321&auth=yes&expires=999999999"
    )
    wrapped = wrap_url_tooltip(long_url, max_line_len=80)
    assert "\n" in wrapped
    for line in wrapped.splitlines():
        assert len(line) <= 80

    # 4. Long URL without delimiters (hard wrap)
    long_opaque_url = "https://example.com/" + "a" * 200
    wrapped_opaque = wrap_url_tooltip(long_opaque_url, max_line_len=80)
    assert "\n" in wrapped_opaque
    for line in wrapped_opaque.splitlines():
        assert len(line) <= 80


def test_parse_size_to_bytes_utils_export():
    """Verify parse_size_to_bytes and parse_time_to_sec are exported from core.utils and core.categories."""
    from core.utils import parse_size_to_bytes, parse_time_to_sec
    from core.categories import parse_size_to_bytes as cat_parse_size, parse_time_to_sec as cat_parse_time

    assert parse_size_to_bytes is cat_parse_size
    assert parse_time_to_sec is cat_parse_time

    # Test size parsing
    assert parse_size_to_bytes("1.00 KB") == 1024.0
    assert parse_size_to_bytes("500 MB") == 500 * 1024 * 1024.0
    assert parse_size_to_bytes("~12.5 MiB") == 12.5 * 1024 * 1024.0
    assert parse_size_to_bytes("0 B") == 0.0
    assert parse_size_to_bytes("...") == 0.0
    assert parse_size_to_bytes("Size unavailable") == 0.0
    assert parse_size_to_bytes(None) == 0.0

    # Test time parsing
    assert parse_time_to_sec("01:00:00") == 3600.0
    assert parse_time_to_sec("02:30") == 150.0
    assert parse_time_to_sec("--") == 0.0


def test_handle_media_fetch_complete_safety(monkeypatch):
    """Verify MainWindow._handle_media_fetch_complete handles fallback payload without crashing."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["-platform", "offscreen"])

    from ui.main_window import MainWindow
    # Create window or mock
    mw = MainWindow.__new__(MainWindow)
    mw.active_media_fetchers = []
    mw.active_file_info_dialogs = {}
    from PyQt6.QtWidgets import QTableWidget
    mw.download_table = QTableWidget(0, 5)
    mw.workers = {}
    mw.save_data = lambda: None

    started = []
    def mock_start_media_download(**kwargs):
        started.append(kwargs)
    mw.start_media_download = mock_start_media_download

    # Simulate fallback media_info payload (similar to YouTube 413 error)
    payload = {
        "url": "https://www.youtube.com/watch?v=u_wB6byrl5k",
        "filename": "media.mp4",
        "size_bytes": 0,
        "size_str": "Size unavailable",
        "size_is_approximate": False,
        "format_spec": "bestvideo+bestaudio/best",
        "is_audio_only": False,
        "video_container": None,
        "audio_format": None,
        "cookies_file": None,
        "cookies_browser": None,
        "referrer": None,
        "user_agent": None,
        "cookies": None,
        "success": False,
    }

    # Should not throw any exception
    mw._handle_media_fetch_complete(payload)
    assert len(started) == 1
    assert started[0]["url"] == "https://www.youtube.com/watch?v=u_wB6byrl5k"


def test_properties_dialog_missing_file_warning(monkeypatch):
    """Verify PropertiesDialog.on_open displays QMessageBox warning on missing file without NameError."""
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(["-platform", "offscreen"])
    from ui.dialogs.properties import PropertiesDialog

    dlg = PropertiesDialog({"filename": "ghost_file.iso", "path": "/nonexistent/ghost_file.iso", "status": "Error"})

    warning_shown = []
    def mock_warning(parent, title, message):
        warning_shown.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    dlg.on_open()

    assert len(warning_shown) == 1
    assert warning_shown[0][0] == "Error"
    assert "File does not exist" in warning_shown[0][1]
    dlg.close()


