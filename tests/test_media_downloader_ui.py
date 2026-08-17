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
    assert dlg.chk_save_defaults.text() == "Remember Preset"

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


def test_android_progress_bar_expressive(qapp):
    """Verify Android 17 Material 3 Expressive linear progress bar rendering and animation timer."""
    from ui.dialogs.media_downloader import AndroidProgressBar
    from PyQt6.QtGui import QPixmap, QPainter

    bar = AndroidProgressBar()
    assert bar.height() == 5
    assert bar._anim_timer.isActive() is False

    # Indeterminate mode
    bar.setRange(0, 0)
    bar.resize(400, 5)
    bar.show()
    assert bar._anim_timer.isActive() is True

    # Render indeterminate state
    pm = QPixmap(400, 5)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    bar.paintEvent(None)
    p.end()

    # Step animation
    old_pos = bar._anim_pos
    bar._on_tick()
    assert bar._anim_pos != old_pos

    # Determinate mode
    bar.setRange(0, 100)
    bar.setValue(50)
    assert bar._anim_timer.isActive() is False

    bar.hide()
    assert bar._anim_timer.isActive() is False
    bar.close()


def test_media_downloader_auto_start_pipeline(qapp, monkeypatch):
    """Verify auto-start pipeline selects target quality preset and calls _on_download_clicked automatically."""
    dlg = MediaDownloaderDialog()
    
    download_clicked = False
    def mock_download_clicked():
        nonlocal download_clicked
        download_clicked = True

    monkeypatch.setattr(dlg, "_on_download_clicked", mock_download_clicked)

    # 1. Initialize auto-start with 1080p target preset
    dlg.analyze_and_download("https://www.youtube.com/watch?v=sample123", auto_start=True, target_preset="1080p Full HD")
    assert dlg._auto_start_pending is True
    assert dlg._auto_start_preset == "1080p Full HD"
    assert dlg.txt_url.text() == "https://www.youtube.com/watch?v=sample123"

    sample_data = {
        "title": "Sample 4K Video",
        "uploader": "Test Channel",
        "duration": 180,
        "formats": [
            {"format_id": "313", "ext": "webm", "res_label": "2160p (4K UHD)", "height": 2160, "vcodec": "vp9", "acodec": "none", "tbr": 18000, "filesize": 500000000, "is_video": True, "is_audio": False},
            {"format_id": "137", "ext": "mp4", "res_label": "1080p (Full HD)", "height": 1080, "vcodec": "avc1", "acodec": "none", "tbr": 4500, "filesize": 120000000, "is_video": True, "is_audio": False},
            {"format_id": "140", "ext": "m4a", "res_label": "Audio Only", "height": 0, "vcodec": "none", "acodec": "aac", "tbr": 128, "filesize": 10000000, "is_video": False, "is_audio": True}
        ]
    }

    # Simulate analysis finish
    dlg._on_single_video_ready(sample_data)

    # Auto-start should have triggered download and reset pending flag
    assert download_clicked is True
    assert dlg._auto_start_pending is False
    assert "1080p" in dlg.cmb_quality_preset.currentText()
    dlg.close()


def test_options_dialog_media_downloader_settings(qapp, tmp_path):
    """Verify OptionsDialog media downloader settings and dedicated Media tab persistence."""
    from ui.dialogs.options import OptionsDialog
    from core.config import load_category_config

    dlg = OptionsDialog()
    assert hasattr(dlg, "media_tab")
    assert hasattr(dlg, "chk_auto_start_media")
    assert hasattr(dlg, "cmb_media_quality")
    assert hasattr(dlg, "cmb_opt_cookies_mode")
    assert hasattr(dlg, "cmb_opt_cookies_browser")
    assert hasattr(dlg, "txt_opt_cookies_path")

    # Set new options in Media tab
    dlg.chk_auto_start_media.setChecked(True)
    dlg.cmb_media_quality.setCurrentText("720p HD")
    dlg.cmb_opt_cookies_browser.setCurrentText("Firefox")
    test_cookie_file = str(tmp_path / "test_cookies.txt")
    dlg.txt_opt_cookies_path.setText(test_cookie_file)
    dlg.save_and_accept()

    # Verify persisted in config
    cfg = load_category_config()
    media_defaults = cfg.get("media_downloader_defaults", {})
    assert media_defaults.get("auto_start_media") is True
    assert media_defaults.get("auto_media_quality_preset") == "720p HD"
    assert media_defaults.get("cookies_browser") == "Firefox"
    assert media_defaults.get("cookies_path") == test_cookie_file

    # Test dynamic enabling/disabling
    dlg.cmb_opt_cookies_mode.setCurrentIndex(0)  # File mode
    assert dlg.cmb_opt_cookies_browser.isEnabled() is False
    assert dlg.txt_opt_cookies_path.isEnabled() is True
    assert dlg.btn_opt_browse_c.isEnabled() is True

    dlg.cmb_opt_cookies_mode.setCurrentIndex(1)  # Browser mode
    assert dlg.cmb_opt_cookies_browser.isEnabled() is True
    assert dlg.txt_opt_cookies_path.isEnabled() is False
    assert dlg.btn_opt_browse_c.isEnabled() is False

    dlg.cmb_opt_cookies_mode.setCurrentIndex(2)  # None
    assert dlg.cmb_opt_cookies_browser.isEnabled() is False
    assert dlg.txt_opt_cookies_path.isEnabled() is False
    assert dlg.btn_opt_browse_c.isEnabled() is False

    # Reset
    media_defaults["auto_start_media"] = False
    media_defaults["auto_media_quality_preset"] = "Best Quality (Video + Audio merged)"
    media_defaults["cookies_browser"] = "Chrome"
    media_defaults["cookies_path"] = ""
    from core.config import save_category_config
    cfg["media_downloader_defaults"] = media_defaults
    cfg["media_downloader_cookies_browser"] = "Chrome"
    cfg["media_downloader_cookies_path"] = ""
    save_category_config(cfg)
    dlg.close()


def test_media_downloader_dialog_auto_start_browser_checkbox(qapp):
    """Verify MediaDownloaderDialog auto-start checkbox reflects and updates config."""
    from core.config import load_category_config, save_category_config

    cfg = load_category_config()
    defaults = cfg.get("media_downloader_defaults", {})
    defaults["auto_start_media"] = False
    cfg["media_downloader_defaults"] = defaults
    save_category_config(cfg)

    dlg = MediaDownloaderDialog()
    assert hasattr(dlg, "chk_auto_start_browser")
    assert dlg.chk_auto_start_browser.isChecked() is False

    # Toggle checkbox
    dlg.chk_auto_start_browser.setChecked(True)
    cfg_updated = load_category_config()
    assert cfg_updated.get("media_downloader_defaults", {}).get("auto_start_media") is True

    # Toggle back
    dlg.chk_auto_start_browser.setChecked(False)
    cfg_updated2 = load_category_config()
    assert cfg_updated2.get("media_downloader_defaults", {}).get("auto_start_media") is False
    dlg.close()


def test_media_downloader_fps_display_and_selection(qapp):
    """Verify that FPS information is formatted in table rows and quality presets."""
    dlg = MediaDownloaderDialog()
    sample_data = {
        "title": "High FPS Video Sample",
        "duration": 180,
        "uploader": "Test Channel",
        "thumbnail": None,
        "formats": [
            {
                "format_id": "137",
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "height": 1080,
                "width": 1920,
                "fps": 60,
                "filesize": 100 * 1024 * 1024,
                "tbr": 8000,
                "res_label": "1080p",
                "is_video": True,
                "is_audio": False
            },
            {
                "format_id": "248",
                "ext": "webm",
                "vcodec": "vp9",
                "acodec": "none",
                "height": 1080,
                "width": 1920,
                "fps": 30,
                "filesize": 70 * 1024 * 1024,
                "tbr": 5000,
                "res_label": "1080p",
                "is_video": True,
                "is_audio": False
            },
            {
                "format_id": "136",
                "ext": "mp4",
                "vcodec": "avc1.4d401f",
                "acodec": "none",
                "height": 720,
                "width": 1280,
                "fps": 60,
                "filesize": 50 * 1024 * 1024,
                "tbr": 4000,
                "res_label": "720p",
                "is_video": True,
                "is_audio": False
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "height": 0,
                "width": 0,
                "fps": 0,
                "filesize": 5 * 1024 * 1024,
                "tbr": 128,
                "res_label": "Audio Only",
                "is_video": False,
                "is_audio": True
            }
        ]
    }

    dlg._on_single_video_ready(sample_data)

    # 1. Format table must display FPS in Resolution column
    assert dlg.tbl_formats.rowCount() == 4
    assert dlg.tbl_formats.item(0, 1).text() == "1080p (60fps)"
    assert dlg.tbl_formats.item(1, 1).text() == "1080p (30fps)"
    assert dlg.tbl_formats.item(2, 1).text() == "720p (60fps)"
    assert dlg.tbl_formats.item(3, 1).text() == "Audio Only"

    # 2. Preset dropdown must display max FPS available per tier
    # 1080p has 60fps available -> "1080p Full HD (60fps)"
    # 720p has 60fps available -> "720p HD (60fps)"
    preset_texts = [dlg.cmb_quality_preset.itemText(i) for i in range(dlg.cmb_quality_preset.count())]
    assert any("1080p Full HD (60fps)" in t for t in preset_texts)
    assert any("720p HD (60fps)" in t for t in preset_texts)

    # 3. Selecting 1080p preset should choose the highest FPS row (format_id 137 / 60fps)
    best_row_1080 = dlg._find_format_row_by_height(1080)
    assert best_row_1080 == 0  # Row 0 has 60fps vs Row 1 has 30fps

    dlg.close()
