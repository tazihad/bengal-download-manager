"""
Tests for Site Grabber crawler, dialog, and toolbar integration.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.grabber.crawler import (
    is_private_or_loopback_host,
    wildcard_to_regex,
    LinkExtractor,
    GrabberCrawler
)
from ui.dialogs.grabber import GrabberDialog, GRABBER_PRESETS
from main import MainWindow


def test_is_private_or_loopback_host():
    """Verify SSRF gate properly identifies loopback and private hosts."""
    assert is_private_or_loopback_host("127.0.0.1") is True
    assert is_private_or_loopback_host("localhost") is True
    assert is_private_or_loopback_host("10.0.0.1") is True
    assert is_private_or_loopback_host("192.168.0.1") is True
    assert is_private_or_loopback_host("172.16.5.10") is True
    assert is_private_or_loopback_host("169.254.169.254") is True
    assert is_private_or_loopback_host("0.0.0.0") is True
    assert is_private_or_loopback_host("::1") is True
    assert is_private_or_loopback_host("") is True
    assert is_private_or_loopback_host("   ") is True

    # Public IP addresses should not be flagged as private/loopback
    assert is_private_or_loopback_host("8.8.8.8") is False
    assert is_private_or_loopback_host("1.1.1.1") is False


def test_wildcard_to_regex():
    """Verify wildcard patterns compile into accurate regexes."""
    pattern_jpg = wildcard_to_regex("*.jpg")
    assert pattern_jpg.match("photo.jpg") is not None
    assert pattern_jpg.match("PHOTO.JPG") is not None
    assert pattern_jpg.match("document.pdf") is None

    pattern_digit = wildcard_to_regex("track_?.mp3")
    assert pattern_digit.match("track_1.mp3") is not None
    assert pattern_digit.match("track_12.mp3") is None

    empty_pattern = wildcard_to_regex("")
    assert empty_pattern.match("anything.xyz") is not None


def test_link_extractor():
    """Verify HTML parser extracts anchors, media sources, and normalizes URLs."""
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <a href="/downloads/archive.zip">Zip File</a>
        <a href="https://other.com/file.tar.gz">External</a>
        <img src="images/logo.png" alt="Logo">
        <video src="/media/clip.mp4">
            <source src="/media/clip_alt.webm" type="video/webm">
        </video>
        <audio src="/sounds/song.mp3"></audio>
        <a href="#section">Fragment Link</a>
        <a href="mailto:admin@example.com">Email</a>
        <a href="javascript:void(0)">JS</a>
    </body>
    </html>
    """
    base_url = "https://example.com/section/index.html"
    extractor = LinkExtractor(base_url)
    extractor.feed(html_sample)

    extracted = extractor.links

    # Verify normalization
    assert "https://example.com/downloads/archive.zip" in extracted
    assert "https://other.com/file.tar.gz" in extracted
    assert "https://example.com/section/images/logo.png" in extracted
    assert "https://example.com/media/clip.mp4" in extracted
    assert "https://example.com/media/clip_alt.webm" in extracted
    assert "https://example.com/sounds/song.mp3" in extracted

    # Fragments, mailto, and javascript links must be excluded
    assert not any(u.startswith("mailto:") for u in extracted)
    assert not any(u.startswith("javascript:") for u in extracted)
    assert not any("#section" in u for u in extracted)


def test_main_window_grabber_toolbar_position(qapp):
    """
    Verify that the Site Grabber action is instantiated, has correct icons/tooltips,
    and is placed on the toolbar specifically between action_scheduler and action_options.
    """
    win = MainWindow(start_ipc=False)
    win.hide()

    assert hasattr(win, "action_grabber")
    assert win.action_grabber is not None
    assert "Grabber" in win.action_grabber.text()

    # Find toolbar actions
    actions = win.toolbar.actions()
    assert win.action_scheduler in actions
    assert win.action_grabber in actions
    assert win.action_options in actions

    idx_scheduler = actions.index(win.action_scheduler)
    idx_grabber = actions.index(win.action_grabber)
    idx_options = actions.index(win.action_options)

    # Position must be: scheduler -> grabber -> options
    assert idx_grabber == idx_scheduler + 1, f"Grabber ({idx_grabber}) must be immediately after Scheduler ({idx_scheduler})"
    assert idx_options == idx_grabber + 1, f"Options ({idx_options}) must be immediately after Grabber ({idx_grabber})"

    win.close()


def test_grabber_dialog_ui(qapp):
    """Verify Site Grabber dialog UI elements and controls."""
    win = MainWindow(start_ipc=False)
    win.hide()

    dlg = GrabberDialog(parent=win)
    dlg.hide()

    assert dlg.txt_url is not None
    assert dlg.spin_depth.value() == 1
    assert dlg.cmb_preset.count() > 0

    # Custom filter line edit toggle
    idx_custom = dlg.cmb_preset.findText("Custom Filters...")
    assert idx_custom != -1
    dlg.cmb_preset.setCurrentIndex(idx_custom)
    assert not dlg.txt_custom_mask.isHidden()

    # Test adding items to table
    fake_item = {
        "url": "https://example.com/files/manual.pdf",
        "filename": "manual.pdf",
        "size": 1048576,
        "type": "Documents",
        "status": "Found",
        "checked": True,
        "depth": 1
    }
    dlg._on_file_found(fake_item)

    assert dlg.table.rowCount() == 1
    assert dlg.btn_download.isEnabled() is True
    assert dlg.lbl_summary.text() != ""

    # Test Select All / Deselect All
    dlg._set_all_checked(False)
    assert dlg.discovered_items[0]["checked"] is False
    assert dlg.btn_download.isEnabled() is False

    dlg._set_all_checked(True)
    assert dlg.discovered_items[0]["checked"] is True
    assert dlg.btn_download.isEnabled() is True

    dlg.close()
    win.close()
