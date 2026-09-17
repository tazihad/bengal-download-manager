"""
Core UI Tests for Media Downloader Window (MediaDownloaderDialog).
"""

import pytest
from PyQt6.QtCore import Qt
from unittest.mock import patch, MagicMock
from ui.dialogs.media_downloader import MediaDownloaderDialog
from main import MainWindow
from core.utils import sanitize_media_filename


@pytest.fixture(autouse=True)
def mock_dep_worker_run(monkeypatch):
    """Prevent background dependency downloads over network during UI tests."""
    monkeypatch.setattr("core.media_downloader.DependencyManagerWorker.run", lambda self: None)


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


def test_youtube_media_popup_filename_numeric_video_id(qapp):
    """
    Verify that YouTube URLs with IDs starting with digits (e.g. 31wLxwewzlM, 27C4pfRsf9g)
    do not mistakenly trigger the Facebook numeric ?v=(\d+) parser and generate '31.mkv' or '27.mkv'.
    """
    mw = MainWindow(start_ipc=False)
    with patch.object(mw, "start_media_download") as mock_start:
        # Simulate IPC from extension media popup:
        # url | user_agent | cookies | referrer | is_media_flag | quality | title | size_bytes | size_str
        ipc_data_1 = (
            "https://www.youtube.com/watch?v=31wLxwewzlM|"
            "Mozilla/5.0|"
            "|"
            "https://www.youtube.com/|"
            "1|"
            "1080p|"
            "Laila Full Video - Shootout At Wadala | John Abraham|"
            "104857600|"
            "~100 MB"
        )
        mw.process_incoming_url(ipc_data_1)
        assert mock_start.called
        kwargs_1 = mock_start.call_args.kwargs
        filename_1 = kwargs_1.get("filename")
        assert filename_1 != "31.mkv"
        assert "31wLxwewzlM" in filename_1
        assert "Laila Full Video" in filename_1
        assert "John Abraham" in filename_1
        assert "1080p" in filename_1

        mock_start.reset_mock()
        ipc_data_2 = (
            "https://www.youtube.com/watch?v=27C4pfRsf9g|"
            "Mozilla/5.0|"
            "|"
            "https://www.youtube.com/|"
            "1|"
            "720p|"
            "Test Video Title|"
            "52428800|"
            "~50 MB"
        )
        mw.process_incoming_url(ipc_data_2)
        assert mock_start.called
        kwargs_2 = mock_start.call_args.kwargs
        filename_2 = kwargs_2.get("filename")
        assert filename_2 != "27.mkv"
        assert "27C4pfRsf9g" in filename_2
        assert "Test Video Title" in filename_2
        assert "720p" in filename_2

    mw.close()


def test_youtube_download_name_with_pipes_from_extension(qapp):
    """Verify that YouTube video titles containing pipes '|' are not truncated and adhere to YouTube standard."""
    import json
    mw = MainWindow(start_ipc=False)
    with patch.object(mw, "start_media_download") as mock_start:
        # 1. Pipe-separated IPC format
        ipc_pipe = (
            "https://www.youtube.com/watch?v=60ItHLz5WEA|"
            "Mozilla/5.0|"
            "|"
            "https://www.youtube.com/|"
            "1|"
            "1080p|"
            "Alan Walker - Faded | Official Music Video | 4K Ultra HD|"
            "104857600|"
            "~100 MB"
        )
        mw.process_incoming_url(ipc_pipe)
        assert mock_start.called
        kwargs_pipe = mock_start.call_args.kwargs
        fn_pipe = kwargs_pipe.get("filename")
        assert "60ItHLz5WEA" in fn_pipe
        assert "Alan Walker - Faded" in fn_pipe
        assert "Official Music Video" in fn_pipe
        assert "4K Ultra HD" in fn_pipe
        assert "1080p" in fn_pipe

        # 2. JSON IPC format
        mock_start.reset_mock()
        ipc_json = json.dumps({
            "url": "https://www.youtube.com/watch?v=60ItHLz5WEA",
            "userAgent": "Mozilla/5.0",
            "cookies": "",
            "referrer": "https://www.youtube.com/",
            "isMedia": True,
            "quality": "1080p",
            "title": "Alan Walker - Faded | Official Music Video | 4K Ultra HD",
            "sizeBytes": 104857600,
            "sizeStr": "~100 MB"
        })
        mw.process_incoming_url(ipc_json)
        assert mock_start.called
        kwargs_json = mock_start.call_args.kwargs
        fn_json = kwargs_json.get("filename")
        assert "60ItHLz5WEA" in fn_json
        assert "Alan Walker - Faded" in fn_json
        assert "Official Music Video" in fn_json
        assert "4K Ultra HD" in fn_json
        assert "1080p" in fn_json
        assert fn_json == fn_pipe

    mw.close()


def test_facebook_media_popup_filename(qapp):
    """Verify that Facebook URLs continue to extract video ID properly."""
    mw = MainWindow(start_ipc=False)
    with patch.object(mw, "start_media_download") as mock_start:
        ipc_data_fb = (
            "https://www.facebook.com/watch/?v=10214828192847192|"
            "Mozilla/5.0|"
            "|"
            "https://www.facebook.com/|"
            "1|"
            "720p|"
            "Facebook Video|"
            "52428800|"
            "~50 MB"
        )
        mw.process_incoming_url(ipc_data_fb)
        assert mock_start.called
        kwargs_fb = mock_start.call_args.kwargs
        filename_fb = kwargs_fb.get("filename")
        assert filename_fb == "10214828192847192.mkv"

    mw.close()


def test_three_dots_options_hub(qapp):
    """Verify ThreeDotsButton and MediaDownloaderOptionsHub initialization and behavior."""
    dlg = MediaDownloaderDialog()
    assert hasattr(dlg, "btn_three_dots")
    assert dlg.btn_three_dots.text() == "⋮"
    assert hasattr(dlg, "options_hub")
    assert len(dlg.options_hub.engine_rows) == 5

    # Verify transparent background attribute and card styling (prevents black rectangular corners)
    assert dlg.options_hub.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
    assert hasattr(dlg.options_hub, "card")
    assert dlg.options_hub.card.objectName() == "optionsHubCard"
    assert dlg.options_hub.card.graphicsEffect() is not None

    # Toggle options hub
    dlg._toggle_options_hub()
    assert dlg.options_hub.isVisible() is True

    # Test engine status update through the hub
    dlg.options_hub.update_engine("yt-dlp", "yt-dlp (v2026.08.19)", "green")
    yt_row = dlg.options_hub.engine_rows["yt-dlp"]
    assert yt_row.lbl_version.text() == "v2026.08.19"
    assert dlg.btn_three_dots._status in ("green", "yellow", "gray")

    dlg._toggle_options_hub()
    assert dlg.options_hub.isVisible() is False
    dlg.close()


def test_three_dots_opens_media_tab(qapp):
    """Verify that clicking Media Options in the 3-dot options hub opens the Media tab in OptionsDialog."""
    from unittest.mock import MagicMock
    from ui.dialogs.options import OptionsDialog

    # Test OptionsDialog select_tab and initial_tab
    options_dlg = OptionsDialog(initial_tab="media")
    assert options_dlg.tabs.currentWidget() == options_dlg.media_tab
    assert "Media" in options_dlg.tabs.tabText(options_dlg.tabs.currentIndex())
    assert "Save To" not in options_dlg.tabs.tabText(options_dlg.tabs.currentIndex())
    options_dlg.reject()

    # Test that options hub delegates to main_win.open_options("media")
    mock_main_win = MagicMock()
    dlg = MediaDownloaderDialog(main_window=mock_main_win)
    dlg.options_hub._open_options_dialog()
    mock_main_win.open_options.assert_called_once_with("media")
    dlg.close()


def test_engine_update_check_skips_identical_version():
    """Verify that DependencyManagerWorker._is_update_available returns False when versions match."""
    from core.media_downloader import DependencyManagerWorker
    worker = DependencyManagerWorker(force_download=True)
    with patch("core.media_downloader.get_tool_version", return_value="v2026.08.19"):
        needs_update, ver = worker._is_update_available("AtomicParsley")
        assert needs_update is False
        assert ver == "v2026.08.19"


