"""
Tests for Media Downloader UI Window (MediaDownloaderDialog).
"""

import pytest
from PyQt6.QtCore import Qt
from ui.dialogs.media_downloader import MediaDownloaderDialog


def test_media_downloader_dialog_init(qapp):
    """Verify MediaDownloaderDialog initialization, window flags, and title."""
    dlg = MediaDownloaderDialog()
    assert dlg.windowTitle() == "Media Downloader"
    assert bool(dlg.windowFlags() & Qt.WindowType.Window) is True
    assert dlg.txt_url is not None
    assert dlg.btn_analyze is not None
    assert dlg.btn_download is not None
    dlg.close()


def test_media_downloader_single_video_view(qapp):
    """Verify single video metadata handling and preset selection."""
    dlg = MediaDownloaderDialog()
    sample_data = {
        "title": "Sample Video Title",
        "uploader": "Test Channel",
        "duration": 300,
        "webpage_url": "https://example.com/watch?v=sample",
        "formats": [
            {"format_id": "1", "res_label": "1080p", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "tbr": 2500, "filesize": 50000000, "url": "https://example.com/v1080.mp4", "height": 1080, "is_video": True, "is_audio": True},
            {"format_id": "2", "res_label": "720p", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "tbr": 1200, "filesize": 25000000, "url": "https://example.com/v720.mp4", "height": 720, "is_video": True, "is_audio": True}
        ]
    }
    dlg._on_single_video_ready(sample_data)
    assert dlg.lbl_video_title.text() == "Sample Video Title"
    assert dlg.tbl_formats.rowCount() == 2
    assert dlg.btn_download.isEnabled() is True
    dlg.close()


def test_media_downloader_playlist_view(qapp):
    """Verify playlist metadata handling, check-all, and selection counts."""
    dlg = MediaDownloaderDialog()
    sample_playlist = {
        "title": "Sample Playlist",
        "total_items": 3,
        "entries": [
            {"index": 1, "title": "Item 1", "duration": 60, "url": "https://example.com/1"},
            {"index": 2, "title": "Item 2", "duration": 120, "url": "https://example.com/2"},
            {"index": 3, "title": "Item 3", "duration": 180, "url": "https://example.com/3"}
        ]
    }
    dlg._on_playlist_ready(sample_playlist)
    assert dlg.tbl_playlist.rowCount() == 3
    assert "3 of 3 items selected" in dlg.lbl_select_count.text()

    dlg._set_all_playlist_checked(False)
    assert "0 of 3 items selected" in dlg.lbl_select_count.text()
    assert dlg.btn_download.isEnabled() is False
    dlg.close()


def test_media_downloader_manual_selection_toggle(qapp):
    """Verify checking/unchecking manual stream selection enables/disables format table."""
    dlg = MediaDownloaderDialog()
    assert dlg.chk_manual_selection.text() == "Enable Manual Stream Selection"
    assert dlg.chk_save_defaults.text() == "Remember"

    # Default is unchecked -> table disabled & unselected
    assert dlg.chk_manual_selection.isChecked() is False
    assert dlg.tbl_formats.isEnabled() is False
    assert dlg.tbl_formats.selectedItems() == []

    # Check manual selection -> table enabled
    dlg.chk_manual_selection.setChecked(True)
    assert dlg.tbl_formats.isEnabled() is True

    # Uncheck manual selection -> table disabled & unselected
    dlg.chk_manual_selection.setChecked(False)
    assert dlg.tbl_formats.isEnabled() is False
    assert dlg.tbl_formats.selectedItems() == []
    dlg.close()


def test_media_downloader_cookies_prefs_panel(qapp, tmp_path):
    """Verify 3-dot button toggles cookies preferences, and cookies.txt path selection."""
    dlg = MediaDownloaderDialog()
    assert dlg.btn_prefs is not None
    assert dlg.frame_cookies_prefs.isHidden() is True

    # 1. Click 3-dot button -> Frame shown
    dlg.btn_prefs.click()
    assert dlg.frame_cookies_prefs.isHidden() is False
    assert "never shared" in dlg.lbl_cookies_info.text()

    # 2. Set cookies.txt path & verify persistence
    cookies_file = str(tmp_path / "my_cookies.txt")
    with open(cookies_file, "w") as f:
        f.write("# Netscape HTTP Cookie File")

    dlg.txt_cookies_path.setText(cookies_file)
    assert dlg._get_cookies_args() == (None, cookies_file)
    dlg.close()

    # 3. Open new dialog instance -> path remembered automatically
    dlg2 = MediaDownloaderDialog()
    assert dlg2.txt_cookies_path.text() == cookies_file
    assert dlg2._get_cookies_args() == (None, cookies_file)

    # 4. Clear button clears path & persists change
    dlg2.btn_clear_cookies.click()
    assert dlg2.txt_cookies_path.text() == ""
    assert dlg2._get_cookies_args() == (None, None)
    dlg2.close()


def test_media_downloader_thumbnail_support(qapp):
    """Verify thumbnail placeholder and rounded thumbnail rendering."""
    from PyQt6.QtGui import QPixmap, QColor
    from ui.dialogs.media_downloader import make_rounded_thumbnail, create_thumbnail_placeholder

    # 1. Placeholder generator
    ph = create_thumbnail_placeholder(160, 90, radius=8, is_playlist=False)
    assert not ph.isNull()
    assert ph.width() == 160
    assert ph.height() == 90

    # 2. Rounded thumbnail cropping & border
    raw_pm = QPixmap(300, 200)
    raw_pm.fill(QColor("red"))
    rounded = make_rounded_thumbnail(raw_pm, 160, 90, radius=8)
    assert not rounded.isNull()
    assert rounded.width() == 160
    assert rounded.height() == 90

    # 3. Dialog thumbnail label hookup
    dlg = MediaDownloaderDialog()
    assert hasattr(dlg, "lbl_thumbnail")
    assert not dlg.lbl_thumbnail.pixmap().isNull()

    dlg._on_thumbnail_loaded(raw_pm)
    assert dlg.lbl_thumbnail.pixmap().width() == 160
    dlg.close()


def test_media_downloader_cookies_mode_switch_and_validation(qapp, tmp_path):
    """Verify switching between File, Browser, and None cookie modes with live validation."""
    dlg = MediaDownloaderDialog()
    assert dlg.cmb_cookies_mode.count() == 3

    # Mode 0: File Mode
    dlg.cmb_cookies_mode.setCurrentIndex(0)
    assert dlg.stack_cookies.currentIndex() == 0

    valid_file = str(tmp_path / "valid_cookies.txt")
    with open(valid_file, "w") as f:
        f.write("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1700000000\tSID\t12345\n")

    dlg.txt_cookies_path.setText(valid_file)
    assert "✓ Valid Netscape" in dlg.lbl_cookies_status.text()
    assert dlg._get_cookies_args() == (None, valid_file)

    # Mode 1: Browser Auto-Extract Mode
    dlg.cmb_cookies_mode.setCurrentIndex(1)
    assert dlg.stack_cookies.currentIndex() == 1
    dlg.cmb_cookies_browser.setCurrentText("Firefox")
    assert dlg._get_cookies_args() == ("firefox", None)

    # Mode 2: None / Anonymous Mode
    dlg.cmb_cookies_mode.setCurrentIndex(2)
    assert dlg.stack_cookies.currentIndex() == 2
    assert dlg._get_cookies_args() == (None, None)

    dlg.close()
