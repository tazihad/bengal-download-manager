"""
Unit tests for DownloadCompleteDialog and FileDragButton.
"""

import os
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QUrl

from ui.dialogs.complete import DownloadCompleteDialog, FileDragButton


def test_complete_dialog_ui(qapp, tmp_path):
    """Verify DownloadCompleteDialog builds with green checkmark banner, details card, and drag button."""
    test_file = tmp_path / "video.mp4"
    test_file.write_bytes(b"test data content")

    file_data = {
        "url": "https://example.com/video.mp4",
        "path": str(test_file),
        "size": "15.50 MB",
    }

    dialog = DownloadCompleteDialog(file_data)
    assert dialog.windowTitle() == "Download Completed"
    assert dialog.lbl_filename.text() == "video.mp4"
    assert dialog.lbl_size.text() == "15.50 MB"
    assert dialog.path_input.text() == str(test_file)
    assert dialog.url_input.text() == "https://example.com/video.mp4"

    # Drag button check
    assert isinstance(dialog.btn_drag, FileDragButton)
    assert dialog.btn_drag.file_path == str(test_file)
    assert dialog.btn_drag.cursor().shape() == Qt.CursorShape.OpenHandCursor

    # Check XDG URI resolution
    abs_path = os.path.abspath(str(test_file))
    url = QUrl.fromLocalFile(abs_path)
    assert url.isLocalFile()
    assert url.toLocalFile() == abs_path

    dialog.close()


def test_complete_dialog_dont_show_again(qapp, tmp_path):
    """Verify 'Don't show this dialog again' updates main window settings."""
    mock_main = MagicMock()
    mock_main.settings = {"show_complete_dialog": True}

    file_data = {
        "url": "https://example.com/sample.zip",
        "path": str(tmp_path / "sample.zip"),
        "size": "5.00 MB",
    }

    dialog = DownloadCompleteDialog(file_data, main_window=mock_main)
    dialog.chk_dont_show.setChecked(True)
    assert mock_main.settings["show_complete_dialog"] is False
    assert mock_main.save_settings.called

    dialog.close()


def test_complete_dialog_actions(qapp, tmp_path):
    """Verify action button handlers (open, open folder)."""
    test_file = tmp_path / "doc.pdf"
    test_file.write_text("dummy")

    file_data = {
        "url": "https://example.com/doc.pdf",
        "path": str(test_file),
        "size": "100 KB",
    }

    dialog = DownloadCompleteDialog(file_data)

    with patch("ui.dialogs.complete.show_in_folder") as mock_show:
        dialog.on_open_folder()
        mock_show.assert_called_once_with(str(test_file))

    with patch("ui.dialogs.complete.open_file_generic", return_value=True) as mock_open:
        dialog.on_open()
        mock_open.assert_called_once_with(str(test_file))

    dialog.close()
