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

