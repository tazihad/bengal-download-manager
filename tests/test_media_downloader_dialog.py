"""
Unit tests for MediaDownloaderDialog and playlist mode improvements.
Verifies scrollability, Advanced Mode toggling, Auto wording, queue selection,
and progress/complete dialog suppression flags.
"""

import pytest
from PyQt6.QtWidgets import QScrollArea
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

    # Toggling Advanced Mode displays format table and streams label
    dlg.chk_manual_selection.setChecked(True)
    qapp.processEvents()
    assert dlg.tbl_formats.isVisible()
    assert dlg.lbl_streams.isVisible()

    dlg.chk_manual_selection.setChecked(False)
    qapp.processEvents()
    assert not dlg.tbl_formats.isVisible()
    assert not dlg.lbl_streams.isVisible()

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
        assert call.get("suppress_complete_dialog") is True

    dlg.close()
