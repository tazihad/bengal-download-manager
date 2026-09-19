"""
Tests for Media Background Download & Media Engine Status Bar item and Auto-Update on Startup.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

from ui.main_window import MainWindow
from ui.dialogs.options import OptionsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_external_daemons():
    with patch("core.services.proxy_service.ProxyDetectorWorker.start"), \
         patch("core.services.ip_service.PublicIpWorker.start"), \
         patch("ui.main_window.MainWindow.start_aria2_daemon", return_value=None):
        yield


def test_media_status_bar_creation_and_visibility(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        # 1. Verify media status bar components
        assert hasattr(win, "status_media_label")
        assert hasattr(win, "sep_media")
        assert hasattr(win, "action_sb_media")

        # 2. Verify action exists in menu
        assert win.action_sb_media in win.status_bar_menu.actions()

        # 3. Test toggling visibility
        win.action_sb_media.setChecked(False)
        win._on_status_bar_child_toggled()
        assert win.status_media_label.isHidden() is True

        win.action_sb_media.setChecked(True)
        win._on_status_bar_child_toggled()
        assert win.status_media_label.isHidden() is False

        # 4. Test settings persistence
        win.save_settings()
        saved = win.load_settings()
        assert "status_bar_items" in saved
        assert "media" in saved["status_bar_items"]
        assert saved["status_bar_items"]["media"] is True
    finally:
        win.is_quitting = True
        win.close()


def test_media_status_bar_click_opens_dialog(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        win.open_media_downloader = MagicMock()
        dummy_event = MagicMock()
        dummy_event.button.return_value = Qt.MouseButton.LeftButton

        win._on_media_status_clicked(dummy_event)
        win.open_media_downloader.assert_called_once()
    finally:
        win.is_quitting = True
        win.close()


def test_media_status_bar_engine_idle_states(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        with patch("core.media_downloader.YtDlpManager.is_binary_available", return_value=True), \
             patch("core.media_downloader.get_tool_version", return_value="v2026.08.19"):
            win.update_status_bar_media()
            assert "● Media: Ready" in win.status_media_label.text()
            assert "Ready" in win.status_media_label.toolTip()
            assert "2026.08.19" in win.status_media_label.toolTip()

        with patch("core.media_downloader.YtDlpManager.is_binary_available", return_value=False):
            win.update_status_bar_media()
            assert "● Media: Missing" in win.status_media_label.text()
            assert "Missing" in win.status_media_label.toolTip()
    finally:
        win.is_quitting = True
        win.close()


def test_media_status_bar_engine_downloading_states(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        win._media_engine_worker = mock_worker

        # Case A: downloading with known percentage
        win._on_media_engine_status_updated("yt-dlp", "yt-dlp (15.0 MB / 30.0 MB)", "yellow")
        assert "● Media: yt-dlp 50%" in win.status_media_label.text()
        assert "15.0 MB / 30.0 MB" in win.status_media_label.toolTip()

        # Case B: downloading another tool
        win._on_media_engine_status_updated("ffmpeg", "ffmpeg (10.0 MB / 40.0 MB)", "yellow")
        assert "● Media: ffmpeg 25%" in win.status_media_label.text()

        # Case C: checking
        win._on_media_engine_status_updated("yt-dlp", "yt-dlp (Checking...)", "yellow")
        assert "● Media: Checking..." in win.status_media_label.text()

        # Case D: extracting / installing
        win._on_media_engine_status_updated("deno", "deno (Extracting...)", "yellow")
        assert "● Media: deno..." in win.status_media_label.text()

        # Case E: finished
        mock_worker.isRunning.return_value = False
        with patch("core.media_downloader.YtDlpManager.is_binary_available", return_value=True), \
             patch("core.media_downloader.get_tool_version", return_value="v2026.08.19"):
            win._on_media_engine_finished()
            assert "● Media: Ready" in win.status_media_label.text()
    finally:
        win.is_quitting = True
        win.close()


def test_media_status_bar_active_media_downloads(qapp):
    from core.media_downloader import YtDlpDownloadWorker

    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        # Mock a running YtDlpDownloadWorker
        worker1 = MagicMock(spec=YtDlpDownloadWorker)
        worker1.isRunning.return_value = True
        worker1.filename = "song.mp3"
        worker1.current_bytes = 5000000
        worker1.total_bytes = 10000000

        win.active_downloads["item_key_1"] = worker1
        win.active_speeds["item_key_1"] = 1048576.0  # 1 MB/s

        win.update_status_bar_media()
        assert "● Media: 1 active (50%)" in win.status_media_label.text()
        assert "song.mp3" in win.status_media_label.toolTip()
        assert "50%" in win.status_media_label.toolTip()
        assert "MB/s" in win.status_media_label.toolTip()

        # Add a second active media download
        worker2 = MagicMock(spec=YtDlpDownloadWorker)
        worker2.isRunning.return_value = True
        worker2.filename = "movie.mp4"
        worker2.current_bytes = 2000000
        worker2.total_bytes = 20000000

        win.active_downloads["item_key_2"] = worker2
        win.update_status_bar_media()
        assert "● Media: 2 active" in win.status_media_label.text()
        assert "song.mp3" in win.status_media_label.toolTip()
        assert "movie.mp4" in win.status_media_label.toolTip()

        # When media downloads finish
        win.active_downloads.pop("item_key_1", None)
        win.active_downloads.pop("item_key_2", None)
        with patch("core.media_downloader.YtDlpManager.is_binary_available", return_value=True):
            win.update_status_bar_media()
            assert "● Media: Ready" in win.status_media_label.text()
    finally:
        win.is_quitting = True
        win.close()


def test_media_engine_startup_check(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        win._force_media_engine_startup_test = True
        win._start_media_engine_check = MagicMock()

        # When auto_update_engine_startup is True (default)
        with patch("ui.main_window.load_category_config", return_value={"media_downloader_defaults": {"auto_update_engine_startup": True}}):
            win._check_media_engine_startup()
            win._start_media_engine_check.assert_called_once_with(force_download=True)

        win._start_media_engine_check.reset_mock()

        # When auto_update_engine_startup is False
        with patch("ui.main_window.load_category_config", return_value={"media_downloader_defaults": {"auto_update_engine_startup": False}}):
            win._check_media_engine_startup()
            win._start_media_engine_check.assert_not_called()
    finally:
        win.is_quitting = True
        win.close()


def test_options_dialog_media_auto_update_checkbox(qapp):
    with patch("ui.dialogs.options.load_category_config", return_value={
        "categories": {},
        "media_downloader_defaults": {"auto_update_engine_startup": True}
    }):
        dlg = OptionsDialog(initial_tab="Media")
        assert hasattr(dlg, "chk_auto_update_engine")
        assert dlg.chk_auto_update_engine.isChecked() is True

        dlg.chk_auto_update_engine.setChecked(False)
        dlg.save_and_accept()

        defaults = dlg.config_data.get("media_downloader_defaults", {})
        assert defaults.get("auto_update_engine_startup") is False


def test_closing_media_downloader_dialog_preserves_engine_download(qapp):
    from ui.dialogs.media_downloader import MediaDownloaderDialog

    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        dlg = MediaDownloaderDialog(main_window=win)
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        mock_worker.requestInterruption = MagicMock()
        mock_worker.terminate = MagicMock()
        mock_worker.quit = MagicMock()

        dlg._dep_worker = mock_worker

        # Close the dialog
        dlg.close()

        # Verify that closing dialog did NOT terminate or interrupt the engine download worker
        mock_worker.requestInterruption.assert_not_called()
        mock_worker.terminate.assert_not_called()
        mock_worker.quit.assert_not_called()

        # Verify that MainWindow references the worker to keep status bar updated
        assert win._media_engine_worker is mock_worker
    finally:
        win.is_quitting = True
        win.close()

