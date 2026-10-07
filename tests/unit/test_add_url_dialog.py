"""Unit tests for AddUrlDialog and MicroInspectorCard."""

import os
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

from ui.dialogs.add_url import AddUrlDialog, MicroInspectorCard


class TestMicroInspectorCard:
    def test_initial_state(self, qapp):
        card = MicroInspectorCard()
        assert card.lbl_filename.text() == "Enter or paste download address"
        assert card.lbl_size.text() == "0 B"
        assert card.lbl_category.text() == "Awaiting URL"

    def test_set_probing(self, qapp):
        card = MicroInspectorCard()
        card.set_probing("https://example.com/archive.zip")
        assert "archive.zip" in card.lbl_filename.text()
        assert card.lbl_size.text() == "Calculating size..."
        assert card.lbl_category.text() == "Probing server..."

    def test_set_resolved(self, qapp):
        card = MicroInspectorCard()
        card.set_resolved("ubuntu-24.04.iso", "5.7 GB", "Compressed", "/home/user/Downloads/Compressed", "compressed")
        assert card.lbl_filename.text() == "ubuntu-24.04.iso"
        assert card.lbl_size.text() == "5.7 GB"
        assert card.lbl_category.text() == "Compressed"
        assert "Downloads/Compressed" in card.lbl_destination.text()

    def test_set_error(self, qapp):
        card = MicroInspectorCard()
        card.set_error("HTTP 404 Not Found", "broken_file.zip")
        assert card.lbl_filename.text() == "broken_file.zip"
        assert card.lbl_size.text() == "Size Unknown"
        assert card.lbl_category.text() == "HTTP 404 Not Found"

    def test_reset_clean(self, qapp):
        card = MicroInspectorCard()
        card.set_resolved("file.zip", "10 MB", "Compressed", "/tmp")
        card.reset_clean()
        assert card.lbl_filename.text() == "Enter or paste download address"
        assert card.lbl_size.text() == "0 B"


class TestAddUrlDialog:
    def test_dialog_init(self, qapp):
        dlg = AddUrlDialog()
        assert dlg.windowTitle() == "Enter new address to download"
        assert dlg.url_input is not None
        assert dlg.btn_paste is not None
        assert dlg.btn_download is not None
        assert dlg.btn_cancel is not None
        assert dlg.micro_inspector is not None
        dlg.close()

    def test_url_input_change_triggers_debounce(self, qapp):
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://example.com/file.zip")
        assert dlg._debounce_timer.isActive()
        assert "file.zip" in dlg.micro_inspector.lbl_filename.text()
        dlg.close()

    def test_prefetch_complete_updates_inspector(self, qapp):
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://example.com/test_video.mp4")
        
        # Simulate prefetch response
        mock_result = {
            "url": "https://example.com/test_video.mp4",
            "filename": "test_video.mp4",
            "size_str": "120.50 MB",
            "size_bytes": 126353408,
            "content_type": "video/mp4",
            "error": None
        }
        dlg._on_prefetch_complete(mock_result)
        
        assert dlg.micro_inspector.lbl_filename.text() == "test_video.mp4"
        assert dlg.micro_inspector.lbl_size.text() == "120.50 MB"
        assert dlg.micro_inspector.lbl_category.text() == "Video"
        assert dlg.get_prefetched_info() == mock_result
        dlg.close()

    def test_batch_url_detection(self, qapp):
        dlg = AddUrlDialog()
        batch_text = "https://example.com/1.zip\nhttps://example.com/2.zip\nhttps://example.com/3.zip"
        dlg.url_input.setText(batch_text)
        assert not dlg.lbl_batch_status.isHidden()
        assert not dlg.btn_send_batch.isHidden()
        assert dlg.btn_send_batch.text() == "Review Batch"
        dlg._on_send_batch_clicked()
        assert dlg.is_batch_list_mode is True
        assert len(dlg.batch_urls) == 3
        dlg.close()

    def test_wildcard_url_detection(self, qapp):
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://example.com/file_*.zip")
        assert not dlg.lbl_batch_status.isHidden()
        assert not dlg.btn_send_batch.isHidden()
        assert dlg.btn_send_batch.text() == "Batch Download"
        dlg._on_send_batch_clicked()
        assert dlg.is_batch_mode is True
        dlg.close()

    def test_media_url_detection(self, qapp):
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert not dlg.lbl_media_status.isHidden()
        assert not dlg.btn_send_media.isHidden()
        dlg._on_send_media_clicked()
        assert dlg.is_media_mode is True
        dlg.close()

    def test_cancel_active_prefetch_on_url_clear(self, qapp):
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://example.com/file.zip")
        mock_fetcher = MagicMock()
        mock_fetcher.isRunning.return_value = True
        dlg._active_fetcher = mock_fetcher

        dlg.url_input.setText("")
        assert mock_fetcher.cancel.called
        assert dlg._active_fetcher is None
        assert dlg.micro_inspector.lbl_filename.text() == "Enter or paste download address"
        dlg.close()
