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
    assert dlg.width() == 1000
    assert dlg.height() == 600
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

    # 3. Dialog single video thumbnail hookup with QPixmap and QImage
    dlg = MediaDownloaderDialog()
    assert hasattr(dlg, "lbl_thumbnail")
    assert not dlg.lbl_thumbnail.pixmap().isNull()

    dlg._on_thumbnail_loaded(raw_pm)
    assert dlg.lbl_thumbnail.pixmap().width() == 160

    from PyQt6.QtGui import QImage
    raw_img = raw_pm.toImage()
    dlg._on_thumbnail_loaded(raw_img)
    assert dlg.lbl_thumbnail.pixmap().width() == 160

    # 4. Playlist thumbnail placeholder and loading
    assert hasattr(dlg, "lbl_playlist_thumbnail")
    assert not dlg.lbl_playlist_thumbnail.pixmap().isNull()
    dlg._on_playlist_thumbnail_loaded(raw_img)
    assert dlg.lbl_playlist_thumbnail.pixmap().width() == 160
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
    monkeypatch.setattr(dlg, "start_analysis", lambda: None)

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

    # 2. Dedicated FPS dropdown must contain all available video stream framerates
    assert hasattr(dlg, "cmb_fps")
    fps_items = [dlg.cmb_fps.itemText(i) for i in range(dlg.cmb_fps.count())]
    assert "Any FPS (Default)" in fps_items
    assert "60 fps" in fps_items
    assert "30 fps" in fps_items

    # 3. Clean quality presets are preserved
    preset_texts = [dlg.cmb_quality_preset.itemText(i) for i in range(dlg.cmb_quality_preset.count())]
    assert any("1080p Full HD" in t for t in preset_texts)
    assert any("720p HD" in t for t in preset_texts)

    # 4. Selecting 1080p preset + 30 fps passes [fps<=30] to yt-dlp format spec
    dlg.cmb_quality_preset.setCurrentIndex(3)  # 1080p Full HD
    dlg.cmb_fps.setCurrentIndex(2)             # 30 fps
    spec, is_audio = dlg._get_single_video_format_spec()
    assert "[fps<=30]" in spec
    assert "height<=1080" in spec
    assert is_audio is False

    # 5. Selecting 1080p preset + 60 fps passes [fps<=60] to yt-dlp format spec
    dlg.cmb_fps.setCurrentIndex(1)             # 60 fps
    spec60, _ = dlg._get_single_video_format_spec()
    assert "[fps<=60]" in spec60

    # 6. Selecting target_fps=30 highlights the 30fps row
    best_row_30 = dlg._find_format_row_by_height(1080, target_fps=30)
    assert best_row_30 == 1  # Row 1 is 1080p 30fps

    best_row_60 = dlg._find_format_row_by_height(1080, target_fps=60)
    assert best_row_60 == 0  # Row 0 is 1080p 60fps

    dlg.close()


def test_start_media_download_unique_naming_when_file_exists(qapp, tmp_path):
    """
    Verify that downloading the same media with an existing file on disk
    (e.g., first in 720p, then in 1080p, including long titles) generates unique filenames and target paths.
    """
    from main import MainWindow
    from core.utils import sanitize_media_filename
    from unittest.mock import patch, MagicMock

    mw = MainWindow(start_ipc=False)
    save_dir = str(tmp_path)

    # 1. Standard filename collision
    existing_video = tmp_path / "My_Video.mp4"
    existing_video.write_bytes(b"dummy 720p video content")

    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_start:
        item_ref = mw.start_media_download(
            url="https://youtube.com/watch?v=sample",
            filename="My_Video.mp4",
            format_spec="bestvideo[height<=1080][fps<=60]+bestaudio/best",
            custom_save_dir=save_dir
        )
        assert item_ref.text() == "My_Video (1).mp4"
        assert item_ref.data(Qt.ItemDataRole.UserRole + 1) == str(tmp_path / "My_Video (1).mp4")
        assert mock_start.called

    # 2. Long title filename collision (e.g. YouTube radio mix / complex metadata)
    long_title = "Manike (8k-60fps) : Thank God Nora, Sidharth| Tanishk,Yohani,Jubin,Surya R |Rashmi Virag|Bhushan K"
    sanitized_first = sanitize_media_filename(long_title, ext=".mp4")
    first_file = tmp_path / sanitized_first
    first_file.write_bytes(b"first 720p download")

    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_start2:
        item_ref2 = mw.start_media_download(
            url="https://www.youtube.com/watch?v=WIs2K6nBD8A",
            filename=sanitized_first,
            format_spec="bestvideo[height<=1080][fps<=60]+bestaudio/best",
            custom_save_dir=save_dir
        )
        # Suffix (1) must be preserved despite length
        assert item_ref2.text().endswith(" (1).mp4")
        assert item_ref2.data(Qt.ItemDataRole.UserRole + 1).endswith(" (1).mp4")
        assert mock_start2.called

    mw.close()


def test_playlist_download_enqueues_to_main_queue(qapp, tmp_path):
    """Verify that clicking download on a playlist enqueues all items into Main download queue."""
    from main import MainWindow
    from unittest.mock import patch

    mw = MainWindow(start_ipc=False)
    dlg = MediaDownloaderDialog(main_window=mw)

    sample_playlist = {
        "title": "My Test Playlist",
        "total_items": 3,
        "entries": [
            {"index": 1, "title": "Track 1", "duration": 60, "url": "https://example.com/track1"},
            {"index": 2, "title": "Track 2", "duration": 120, "url": "https://example.com/track2"},
            {"index": 3, "title": "Track 3", "duration": 180, "url": "https://example.com/track3"}
        ]
    }
    dlg._on_playlist_ready(sample_playlist)

    with patch("core.media_downloader.YtDlpDownloadWorker.start"):
        dlg._on_download_clicked()

    # Verify rows in main download table have queue set to "Main download queue"
    assert mw.download_table.rowCount() >= 3
    for r in range(3):
        item = mw.download_table.item(r, 0)
        assert item is not None
        assert item.data(Qt.ItemDataRole.UserRole + 8) == "Main download queue"

    mw.close()
    dlg.close()


def test_video_and_audio_codec_availability_dropdowns(qapp):
    """Verify that video and audio codec dropdowns display unavailable codecs as disabled."""
    dlg = MediaDownloaderDialog()

    # Video with only H264 video and M4A audio (no WebM VP9, no AV1, no Opus, no MP3)
    sample_video = {
        "title": "H264 Only Video",
        "formats": [
            {"format_id": "1", "vcodec": "avc1.4d401e", "acodec": "none", "ext": "mp4", "height": 720, "is_video": True, "is_audio": False},
            {"format_id": "2", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "is_video": False, "is_audio": True}
        ]
    }
    dlg._on_single_video_ready(sample_video)

    # Video dropdown verification
    v_model = dlg.cmb_video_format.model()
    # 0: Any Format (Enabled)
    assert v_model.item(0).isEnabled() is True
    # 1: MP4 (H.264 / AVC) (Enabled)
    assert v_model.item(1).isEnabled() is True
    # 2: WebM (VP9) (Disabled)
    assert v_model.item(2).isEnabled() is False
    assert "(Not Available)" in dlg.cmb_video_format.itemText(2)
    # 3: AV1 Codec (Disabled)
    assert v_model.item(3).isEnabled() is False
    assert "(Not Available)" in dlg.cmb_video_format.itemText(3)

    # Audio dropdown verification
    a_model = dlg.cmb_audio_format.model()
    # 0: Any Format (Enabled)
    assert a_model.item(0).isEnabled() is True
    # 1: M4A (AAC Audio) (Enabled)
    assert a_model.item(1).isEnabled() is True
    # 2: Opus (WebM Audio) (Disabled)
    assert a_model.item(2).isEnabled() is False
    assert "(Not Available)" in dlg.cmb_audio_format.itemText(2)
    # 3: MP3 Audio (Disabled)
    assert a_model.item(3).isEnabled() is False
    assert "(Not Available)" in dlg.cmb_audio_format.itemText(3)

    dlg.close()


def test_start_media_download_shows_download_file_info_dialog(qapp, tmp_path):
    """Verify that start_media_download with show_file_info=True displays DownloadFileInfoDialog before downloading."""
    from main import MainWindow
    from unittest.mock import patch
    from PyQt6.QtCore import Qt

    mw = MainWindow(start_ipc=False)
    mw.hide()

    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_start:
        item_ref = mw.start_media_download(
            url="https://example.com/stream.m3u8",
            filename="Test_Stream.mp4",
            format_spec="bestvideo+bestaudio/best",
            custom_save_dir=str(tmp_path),
            total_size_bytes=104857600,
            show_file_info=True
        )

        assert item_ref is not None
        dialog_key = mw._get_item_key(item_ref)
        assert dialog_key in mw.active_file_info_dialogs
        file_info_dlg = mw.active_file_info_dialogs[dialog_key]
        assert file_info_dlg is not None
        assert file_info_dlg.file_info["filename"] == "Test_Stream.mp4"
        assert file_info_dlg.file_info["size_bytes"] == 104857600
        # Worker has not started yet while waiting for user confirmation
        assert not mock_start.called

        # Simulate user clicking "Start Download" in DownloadFileInfoDialog
        file_info_dlg.on_start()
        assert mock_start.called
        file_info_dlg.close()

    mw.close()


def test_media_downloader_pause_and_resume_lifecycle(qapp, tmp_path):
    """Verify pausing and resuming media downloads via MainWindow and QML bridge methods."""
    from ui.main_window import MainWindow
    from core.media_downloader import YtDlpDownloadWorker
    from PyQt6.QtCore import Qt
    from unittest.mock import patch

    mw = MainWindow(start_ipc=False)
    mw.hide()

    with patch("core.media_downloader.YtDlpDownloadWorker.start"):
        item_ref = mw.start_media_download(
            url="https://example.com/video.m3u8",
            filename="Paused_Video.mp4",
            format_spec="bestvideo+bestaudio/best",
            custom_save_dir=str(tmp_path),
            show_file_info=False
        )

    assert item_ref is not None
    key = mw._get_item_key(item_ref)
    entry = mw.active_downloads[key]
    from ui.dialogs.progress import DownloadProgressDialog
    assert isinstance(entry, DownloadProgressDialog)
    worker = getattr(entry, "worker", entry)
    assert isinstance(worker, YtDlpDownloadWorker)
    assert worker.is_paused is False

    row = mw.download_table.row(item_ref)
    mw.download_table.selectRow(row)

    # 1. Stop / Pause the media download
    with patch.object(worker, "pause", wraps=worker.pause) as mock_pause:
        mw.stop_selected_download()
        assert mock_pause.called
        assert worker.is_paused is True
        # Worker popped from active_downloads upon pause
        assert key not in mw.active_downloads
        assert item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Paused"
        status_item = mw.download_table.item(row, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole + 1) == "Paused"

    # 2. Resume the media download
    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_resume_start:
        mw.resume_selected_download()
        assert mock_resume_start.called
        new_entry = mw.active_downloads[key]
        assert isinstance(new_entry, DownloadProgressDialog)
        new_worker = getattr(new_entry, "worker", new_entry)
        assert isinstance(new_worker, YtDlpDownloadWorker)
        assert new_worker is not worker
        assert item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Normal"

    # 3. Test QML pause and resume
    with patch.object(new_worker, "pause", wraps=new_worker.pause) as mock_qml_pause:
        mw.qml_pause_download(row)
        assert mock_qml_pause.called
        assert key not in mw.active_downloads
        assert item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Paused"

    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_qml_resume_start:
        mw.qml_resume_download(row)
        assert mock_qml_resume_start.called
        assert key in mw.active_downloads
        resumed_entry = mw.active_downloads[key]
        assert isinstance(resumed_entry, DownloadProgressDialog)
        resumed_worker = getattr(resumed_entry, "worker", resumed_entry)
        assert isinstance(resumed_worker, YtDlpDownloadWorker)
    mw.close()


def test_extension_media_download_passes_size_to_file_info_dialog(qapp, tmp_path):
    """Verify that size passed from browser extension via process_incoming_url renders in DownloadFileInfoDialog."""
    from ui.main_window import MainWindow
    from unittest.mock import patch

    mw = MainWindow(start_ipc=False)
    mw.hide()

    # 1. Test start_media_download directly with size
    item_ref = mw.start_media_download(
        url="https://example.com/video.m3u8",
        filename="Test_Stream.mp4",
        format_spec="bestvideo+bestaudio/best",
        custom_save_dir=str(tmp_path),
        total_size_bytes=131489000,
        show_file_info=True
    )

    assert item_ref is not None
    dialog_key = mw._get_item_key(item_ref)
    assert dialog_key in mw.active_file_info_dialogs
    file_info_dlg = mw.active_file_info_dialogs[dialog_key]
    assert file_info_dlg is not None
    # Verify file size label displays the formatted size and NOT 'Unknown'
    assert "Unknown" not in file_info_dlg.lbl_size.text()
    assert "125.40 MB" in file_info_dlg.lbl_size.text()
    file_info_dlg.close()

    # 2. Test process_incoming_url parses 8-part IPC payload with size
    payload_data = "https://example.com/video2.m3u8|TestUA|TestCookie|https://referrer.com|1|1080p|Custom Video Title|150000000|150 MB"
    with patch.object(mw, "open_media_downloader") as mock_open_media:
        mw.process_incoming_url(payload_data)
        assert mock_open_media.called
        kwargs = mock_open_media.call_args[1]
        assert kwargs["estimated_size_bytes"] == 150000000
        assert kwargs["custom_title"] == "Custom Video Title"

    mw.close()


def test_media_downloader_estimated_size_preserved_and_progress_dialog_shown(qapp, tmp_path):
    """Verify that 1.24 GB estimated size is preserved when formats have smaller single stream (245 MB)
    and DownloadProgressDialog is displayed when starting media download."""
    from unittest.mock import patch
    from ui.main_window import MainWindow
    from ui.dialogs.media_downloader import MediaDownloaderDialog
    from ui.dialogs.progress import DownloadProgressDialog

    mw = MainWindow(start_ipc=False)
    mw.hide()

    dlg = MediaDownloaderDialog(main_window=mw)
    dlg.hide()
    # Mock video data where single legacy format is 245 MB but estimated size from extension is 1.24 GB (1331439861)
    dlg._current_video_data = {
        "title": "Large Movie 1080p",
        "webpage_url": "https://example.com/movie",
        "duration": 7200,
        "formats": [
            {"format_id": "22", "height": 720, "vcodec": "avc1", "acodec": "mp4a", "filesize": 256901120}  # ~245 MB
        ]
    }
    dlg._estimated_size_bytes = 1331439861  # 1.24 GB
    dlg.stack.setCurrentWidget(dlg.page_video)

    with patch.object(mw, "start_media_download") as mock_start:
        dlg._on_download_clicked()
        assert mock_start.called
        kwargs = mock_start.call_args[1]
        assert kwargs["total_size_bytes"] == 1331439861

    # Verify start_media_download instantiates and displays DownloadProgressDialog
    with patch("core.media_downloader.YtDlpDownloadWorker.start"):
        item_ref = mw.start_media_download(
            url="https://example.com/movie",
            filename="Large_Movie.mp4",
            format_spec="bestvideo+bestaudio/best",
            custom_save_dir=str(tmp_path),
            total_size_bytes=1331439861,
            show_file_info=False
        )

    key = mw._get_item_key(item_ref)
    assert key in mw.active_downloads
    prog_dlg = mw.active_downloads[key]
    assert isinstance(prog_dlg, DownloadProgressDialog)
    assert prog_dlg.isVisible()
    # Verify file size label in progress dialog shows 1.24 GB
    assert "1.24" in prog_dlg.lbl_size.text()

    prog_dlg.close()
    dlg.close()
    mw.close()


def test_media_downloader_details_split_connections_update_during_download(qapp, tmp_path):
    """Verify that during media download, the Details panel updates all split connections
    from 'Pending...' to 'Receiving data...', 'Paused', 'Resuming...', and 'Complete'."""
    from core.media_downloader import YtDlpDownloadWorker
    from ui.dialogs.progress import DownloadProgressDialog
    from PyQt6.QtGui import QFont
    from unittest.mock import patch

    worker = YtDlpDownloadWorker(
        url="https://example.com/test_video.m3u8",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test_video.mp4",
        total_bytes=100000000  # 100 MB
    )
    assert worker.supports_resume is True

    with patch("core.media_downloader.YtDlpDownloadWorker.start"):
        prog_dlg = DownloadProgressDialog(worker, None)
        prog_dlg.hide()

    # 1. Verify Resume capability is "Yes"
    assert prog_dlg.lbl_resume.text() == "Yes"

    # 2. Verify seg_table font has OpenType tabular figures (tnum)
    assert prog_dlg.seg_table.font().featureValue(QFont.Tag.fromString('tnum')) == 1

    # 3. Open details view
    prog_dlg.btn_details.setChecked(True)
    prog_dlg.toggle_details(True)
    assert not prog_dlg.details_frame.isHidden()

    # 4. Initially or on startup, worker emits "Connecting..."
    worker._emit_segment_updates(0, worker.total_bytes, 0.0, status_text="Connecting...")
    num_conn = worker.max_connections
    for i in range(num_conn):
        item_status = prog_dlg.seg_table.item(i, 3)
        assert item_status is not None
        assert item_status.text() == "Connecting..."

    # 5. During download: 30 MB downloaded at 5 MB/s
    worker.current_bytes = 30000000
    worker._emit_segment_updates(30000000, 100000000, 5242880.0)
    for i in range(num_conn):
        item_status = prog_dlg.seg_table.item(i, 3)
        assert item_status is not None
        assert item_status.text() in ("Downloading", "Receiving data...")
        assert item_status.text() != "Pending..."
        item_dl = prog_dlg.seg_table.item(i, 1)
        assert item_dl is not None and item_dl.text() != "0.00  B"
        item_speed = prog_dlg.seg_table.item(i, 2)
        assert item_speed is not None and "B/s" in item_speed.text() and item_speed.text() != "0.00  B/s"
        assert prog_dlg.segment_bars[i].value() > 0

    # 6. Pause worker -> Connections reflect "Paused"
    worker.pause()
    for i in range(num_conn):
        item_status = prog_dlg.seg_table.item(i, 3)
        assert item_status is not None
        assert item_status.text() == "Paused"

    # 7. Resume worker -> Connections reflect "Resuming..."
    worker.resume()
    for i in range(num_conn):
        item_status = prog_dlg.seg_table.item(i, 3)
        assert item_status is not None
        assert item_status.text() == "Resuming..."

    # 8. Completion -> All connections reflect "Complete" with 100% progress
    worker.current_bytes = 100000000
    worker._emit_segment_updates(100000000, 100000000, 0.0, status_text="Complete")
    prog_dlg.on_finished(0, "Complete")
    for i in range(num_conn):
        item_status = prog_dlg.seg_table.item(i, 3)
        assert item_status is not None
        assert item_status.text() == "Complete"
        assert prog_dlg.segment_bars[i].value() == 10000

    prog_dlg.close()


def test_progress_dialog_no_flicker_and_raw_stdout_isolation(qapp, tmp_path):
    """Verify that raw stdout lines do not corrupt lbl_main_status and that
    all status column labels maintain stable fixed widths to eliminate flickering."""
    from core.media_downloader import YtDlpDownloadWorker
    from ui.dialogs.progress import DownloadProgressDialog
    from unittest.mock import patch

    worker = YtDlpDownloadWorker(
        url="https://example.com/test_video.m3u8",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test_video.mp4",
        total_bytes=100000000
    )

    with patch("core.media_downloader.YtDlpDownloadWorker.start"):
        prog_dlg = DownloadProgressDialog(worker, None)
        prog_dlg.hide()

    # 1. Verify all value widgets have stable fixed width to prevent layout horizontal jumping
    assert prog_dlg.lbl_main_status.width() == 280
    assert prog_dlg.lbl_size.width() == 280
    assert prog_dlg.lbl_downloaded.width() == 280
    assert prog_dlg.lbl_speed.width() == 280
    assert prog_dlg.lbl_time.width() == 280
    assert prog_dlg.lbl_resume.width() == 280

    # 2. Update to Downloading
    prog_dlg.update_stats(0, ("test_video.mp4", "100.00 MB", "Downloading", "00:10", "10.00 MB/s", 50000000, 100000000))
    assert prog_dlg.lbl_main_status.text() == "Downloading"

    # 3. Simulate incoming raw yt-dlp stdout lines — verify lbl_main_status ignores them and remains "Downloading"
    raw_stdout_lines = [
        "[download]  15.2% of ~ 100.00MiB at  5.40MiB/s ETA 01:45",
        "[download] Destination: /tmp/test_video.mp4",
        "[download] 100% of 100.00MiB in 00:10",
        "[info] Extracting video metadata..."
    ]
    for line in raw_stdout_lines:
        worker.log_signal.emit(line)
        assert prog_dlg.lbl_main_status.text() == "Downloading"

    # 4. Valid lifecycle messages still update properly
    worker.log_signal.emit("Pausing download...")
    assert prog_dlg.lbl_main_status.text() == "Paused"
    worker.log_signal.emit("Resuming download...")
    assert prog_dlg.lbl_main_status.text() == "Resuming..."

    prog_dlg.close()


def test_media_downloader_dialog_youtube_naming_convention(qapp):
    """Verify that MediaDownloaderDialog formats filenames using the media downloader naming convention for YouTube."""
    from main import MainWindow
    from ui.dialogs import MediaDownloaderDialog
    from unittest.mock import patch, MagicMock

    mw = MainWindow(start_ipc=False)
    dlg = MediaDownloaderDialog(main_window=mw)

    sample_video = {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "extractor": "youtube",
        "duration": 213,
        "formats": [
            {"format_id": "137", "ext": "mp4", "height": 1080, "is_video": True, "is_audio": False, "vcodec": "avc1"},
            {"format_id": "140", "ext": "m4a", "height": None, "is_video": False, "is_audio": True, "acodec": "mp4a"}
        ]
    }
    dlg._on_single_video_ready(sample_video)

    # 1. Test 1080p Preset -> should format as 'Title [id] [1080p].mkv'
    dlg.cmb_quality_preset.setCurrentIndex(3)  # 1080p Full HD
    with patch.object(mw, "start_media_download") as mock_dl:
        dlg._on_download_clicked()
        assert mock_dl.called
        call_kwargs = mock_dl.call_args[1]
        fn = call_kwargs["filename"]
        assert "[dQw4w9WgXcQ]" in fn
        assert "[1080p]" in fn
        assert fn.endswith(".mkv")

    # 2. Test Audio-only Preset -> should format as 'Title [id].opus' without height tag
    dlg.cmb_quality_preset.setCurrentIndex(7)  # Audio Only (Opus / MP3)
    with patch.object(mw, "start_media_download") as mock_dl_audio:
        dlg._on_download_clicked()
        assert mock_dl_audio.called
        call_kwargs_a = mock_dl_audio.call_args[1]
        fn_a = call_kwargs_a["filename"]
        assert "[dQw4w9WgXcQ]" in fn_a
        assert "[1080p]" not in fn_a
        assert fn_a.endswith(".opus")

    mw.close()
    dlg.close()


def test_ytdlp_download_worker_youtube_output_template(tmp_path):
    """Verify YtDlpDownloadWorker applies media downloader template for YouTube when generic filename is passed."""
    from core.media_downloader import YtDlpDownloadWorker
    from unittest.mock import patch, MagicMock

    worker = YtDlpDownloadWorker(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        row_index=0,
        save_dir=str(tmp_path),
        filename="media.mp4"
    )

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        worker.run()

        cmd = mock_popen.call_args[0][0]
        out_tmpl = cmd[cmd.index("-o") + 1]
        assert "[%(id)s]" in out_tmpl
        assert "%(title).100B" in out_tmpl

