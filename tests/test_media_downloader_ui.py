"""
Core UI Tests for Media Downloader Window (MediaDownloaderDialog).
"""

import pytest
from PyQt6.QtCore import Qt
from unittest.mock import patch, MagicMock
from ui.dialogs.media_downloader import MediaDownloaderDialog
from main import MainWindow
from core.utils import sanitize_media_filename


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
            }
        ]
    }

    dlg._on_single_video_ready(sample_data)

    assert dlg.tbl_formats.rowCount() == 2
    assert dlg.tbl_formats.item(0, 1).text() == "1080p (60fps)"
    assert dlg.tbl_formats.item(1, 1).text() == "1080p (30fps)"

    assert hasattr(dlg, "cmb_fps")
    fps_items = [dlg.cmb_fps.itemText(i) for i in range(dlg.cmb_fps.count())]
    assert "Any FPS (Default)" in fps_items
    assert "60 fps" in fps_items
    assert "30 fps" in fps_items
    dlg.close()


def test_start_media_download_unique_naming_when_file_exists(qapp, tmp_path):
    """
    Verify that downloading the same media with an existing file on disk
    generates unique filenames and target paths.
    """
    mw = MainWindow(start_ipc=False)
    save_dir = str(tmp_path)

    existing_video = tmp_path / "My_Video.mp4"
    existing_video.write_bytes(b"dummy content")

    with patch("core.media_downloader.YtDlpDownloadWorker.start") as mock_start:
        item_ref = mw.start_media_download(
            url="https://www.youtube.com/watch?v=YE7VzlLtp-4",
            filename="My_Video.mp4",
            format_spec="bestvideo+bestaudio/best",
            custom_save_dir=save_dir
        )
        assert item_ref.text() == "My_Video (1).mp4"
        assert item_ref.data(Qt.ItemDataRole.UserRole + 1) == str(tmp_path / "My_Video (1).mp4")
        assert mock_start.called

    mw.close()


def test_playlist_download_enqueues_to_main_queue(qapp, tmp_path):
    """Verify that clicking download on a playlist enqueues all items into Main download queue."""
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

    assert mw.download_table.rowCount() >= 3
    for r in range(3):
        item = mw.download_table.item(r, 0)
        assert item is not None
        assert item.data(Qt.ItemDataRole.UserRole + 8) == "Main download queue"

    mw.close()
    dlg.close()
