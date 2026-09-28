"""
Unit tests for MediaDownloaderDialog and playlist mode improvements.
Verifies scrollability, Advanced Mode toggling, Auto wording, queue selection,
progress/complete dialog suppression flags, and unified scope selector.
"""

import pytest
from PyQt6.QtWidgets import QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt


def test_media_downloader_dialog_ui_elements(qapp):
    from ui.dialogs.media_downloader import MediaDownloaderDialog

    dlg = MediaDownloaderDialog()
    dlg.show()
    qapp.processEvents()

    # 1. Scroll area wraps stack and is resizable
    assert hasattr(dlg, "scroll_area")
    assert isinstance(dlg.scroll_area, QScrollArea)
    assert dlg.scroll_area.widgetResizable() is True
    assert dlg.scroll_area.widget() == dlg.stack

    # Switch to single video page to inspect widgets
    dlg.stack.setCurrentWidget(dlg.page_video)
    qapp.processEvents()

    # 2. Advanced Mode checkbox and table hidden by default
    assert dlg.chk_manual_selection.text() == "Advanced Mode"
    assert not dlg.chk_manual_selection.isChecked()
    assert not dlg.tbl_formats.isVisible()
    assert not dlg.lbl_streams.isVisible()
    assert dlg.video_bottom_spacer.isVisible()

    # Toggling Advanced Mode displays format table and streams label
    dlg.chk_manual_selection.setChecked(True)
    qapp.processEvents()
    assert dlg.tbl_formats.isVisible()
    assert dlg.lbl_streams.isVisible()
    assert not dlg.video_bottom_spacer.isVisible()

    dlg.chk_manual_selection.setChecked(False)
    qapp.processEvents()
    assert not dlg.tbl_formats.isVisible()
    assert not dlg.lbl_streams.isVisible()
    assert dlg.video_bottom_spacer.isVisible()

    # 3. Auto wording in FPS, Video format, Audio format combo boxes
    assert "Auto" in dlg.cmb_fps.itemText(0)
    assert "Auto" in dlg.cmb_video_format.itemText(0)
    assert "Auto" in dlg.cmb_audio_format.itemText(0)

    # 4. Status label is hidden on completion / initial state
    dlg._finish_loading()
    assert not dlg.lbl_status.isVisible()
    assert dlg.lbl_status.text() == ""

    # Switch to playlist page
    dlg.stack.setCurrentWidget(dlg.page_playlist)
    qapp.processEvents()

    # 5. Playlist options: Auto audio format at top (index 0)
    assert dlg.cmb_playlist_audio_format.currentIndex() == 0
    assert dlg.cmb_playlist_audio_format.itemData(0) == "best"
    assert "Auto" in dlg.cmb_playlist_audio_format.itemText(0)

    # 6. Playlist queue combo exists and defaults to "Main download queue"
    assert hasattr(dlg, "cmb_playlist_queue")
    assert dlg.cmb_playlist_queue.currentText() == "Main download queue"

    # 7. Playlist table vertical header is hidden
    assert not dlg.tbl_playlist.verticalHeader().isVisible()
    assert dlg.tbl_playlist.minimumHeight() >= 160

    dlg.close()


def test_scope_radio_buttons_behavior(qapp):
    from ui.dialogs.media_downloader import MediaDownloaderDialog

    dlg = MediaDownloaderDialog()
    dlg.show()
    qapp.processEvents()

    # Both radio buttons are permanently part of UI
    assert hasattr(dlg, "rad_single_video")
    assert hasattr(dlg, "rad_whole_playlist")

    # Initial state (empty URL): single video checked, playlist disabled
    assert dlg.rad_single_video.isChecked()
    assert dlg.rad_single_video.isEnabled()
    assert not dlg.rad_whole_playlist.isEnabled()

    # Single video URL (no playlist)
    dlg.txt_url.setText("https://www.youtube.com/watch?v=r2ecLFsdbzI")
    qapp.processEvents()
    assert dlg.rad_single_video.isChecked()
    assert dlg.rad_single_video.isEnabled()
    assert not dlg.rad_whole_playlist.isEnabled()

    # Playlist URL with video (mixed)
    dlg.txt_url.setText("https://www.youtube.com/watch?v=r2ecLFsdbzI&list=PL9bw4S5ePsEGgHMPYsEJQJaKOs9RBKDxs")
    qapp.processEvents()
    assert dlg.rad_whole_playlist.isEnabled()
    assert dlg.rad_whole_playlist.isChecked()
    assert dlg.rad_single_video.isEnabled()

    # User can switch back to single video
    dlg.rad_single_video.setChecked(True)
    qapp.processEvents()
    assert dlg.rad_single_video.isChecked()

    # Pure playlist URL
    dlg.txt_url.setText("https://www.youtube.com/playlist?list=PL9bw4S5ePsEGgHMPYsEJQJaKOs9RBKDxs")
    qapp.processEvents()
    assert dlg.rad_whole_playlist.isEnabled()
    assert dlg.rad_whole_playlist.isChecked()
    assert not dlg.rad_single_video.isEnabled()

    # Back to single video URL: playlist becomes disabled again
    dlg.txt_url.setText("https://www.youtube.com/watch?v=r2ecLFsdbzI")
    qapp.processEvents()
    assert dlg.rad_single_video.isChecked()
    assert not dlg.rad_whole_playlist.isEnabled()

    dlg.close()


def test_playlist_enqueue_parameters(qapp, monkeypatch):
    from ui.dialogs.media_downloader import MediaDownloaderDialog

    dlg = MediaDownloaderDialog()
    dlg.show()
    qapp.processEvents()

    captured_calls = []

    class DummyMainWindow:
        def start_media_download(self, **kwargs):
            captured_calls.append(kwargs)

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

        def get_default_download_directory(self, category):
            return "/tmp"

    dummy_mw = DummyMainWindow()
    dlg._main_window = dummy_mw

    # Switch to playlist page and set mock playlist data
    dlg.stack.setCurrentWidget(dlg.page_playlist)
    dlg._current_playlist_data = {
        "title": "Test Playlist",
        "entries": [
            {"id": "abc123", "title": "Track 1", "url": "https://example.com/1", "duration": 180},
            {"id": "def456", "title": "Track 2", "url": "https://example.com/2", "duration": 200},
        ]
    }
    dlg._on_playlist_ready(dlg._current_playlist_data)
    qapp.processEvents()

    assert dlg.tbl_playlist.rowCount() == 2

    # Click download
    dlg._on_download_clicked()

    assert len(captured_calls) == 2
    for call in captured_calls:
        assert call.get("queue_name") == "Main download queue"
        assert call.get("show_progress_dialog") is False
    dlg.close()


def test_single_video_auto_extension_resolution(qapp, monkeypatch):
    """
    Verifies that when downloading a single video with all options set to Auto,
    the filename ends in '.mp4' (never '.auto' or '.best').
    """
    from ui.dialogs.media_downloader import MediaDownloaderDialog
    from core.utils import sanitize_media_filename, get_unique_media_filepath

    # 1. Direct utils verification
    assert sanitize_media_filename("My Test Video", ext=".auto") == "My Test Video.mp4"
    assert sanitize_media_filename("My Test Video.auto", ext="") == "My Test Video.mp4"
    assert sanitize_media_filename("My Test Video", ext="auto") == "My Test Video.mp4"
    assert sanitize_media_filename("My Test Video", ext=".best") == "My Test Video.mp4"
    assert get_unique_media_filepath("/tmp", "My Test Video.auto").endswith("My Test Video.mp4")

    # 2. MediaDownloaderDialog verification with all Auto settings
    dlg = MediaDownloaderDialog()
    dlg.show()
    qapp.processEvents()

    captured_calls = []

    class DummyMainWindow:
        def start_media_download(self, **kwargs):
            captured_calls.append(kwargs)

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    dlg._main_window = DummyMainWindow()
    dlg.close = lambda: None

    # Setup single video data with auto format
    dlg.stack.setCurrentWidget(dlg.page_video)
    dlg._current_video_data = {
        "id": "r2ecLFsdbzI",
        "title": "Bengali Test Video",
        "webpage_url": "https://www.youtube.com/watch?v=r2ecLFsdbzI",
        "formats": [
            {"format_id": "137", "ext": "mp4", "height": 1080, "is_video": True, "vcodec": "avc1.640028"},
            {"format_id": "140", "ext": "m4a", "is_audio": True, "acodec": "mp4a.40.2"},
        ]
    }
    # Quality preset is 0 ("Auto / Best"), video format is "auto", audio format is "auto"
    dlg.cmb_quality_preset.setCurrentIndex(0)
    dlg.cmb_video_format.setCurrentIndex(0)
    dlg.cmb_audio_format.setCurrentIndex(0)
    qapp.processEvents()

    dlg._on_download_clicked()

    assert len(captured_calls) == 1
    call_args = captured_calls[0]
    filename = call_args.get("filename")
    assert filename is not None
    assert not filename.endswith(".auto"), f"Filename should not end with .auto: {filename}"
    assert not filename.endswith(".best"), f"Filename should not end with .best: {filename}"
    assert filename.endswith(".mp4"), f"Filename should end with .mp4: {filename}"

    # 3. Audio-only with Auto format
    captured_calls.clear()
    dlg.cmb_quality_preset.setCurrentIndex(7)  # Audio Only
    qapp.processEvents()
    dlg._on_download_clicked()
    assert len(captured_calls) == 1
    audio_fn = captured_calls[0].get("filename")
    assert audio_fn is not None
    assert not audio_fn.endswith(".auto"), f"Audio filename should not end with .auto: {audio_fn}"
    assert not audio_fn.endswith(".best"), f"Audio filename should not end with .best: {audio_fn}"
    assert audio_fn.endswith(".mp3") or audio_fn.endswith(".opus"), f"Audio filename should have audio ext: {audio_fn}"

    dlg.close()
