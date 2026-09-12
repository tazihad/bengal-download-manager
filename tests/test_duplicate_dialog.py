"""
Tests for Duplicate Download Dialog.
"""

import os
import pytest
from PyQt6.QtCore import Qt
from ui.dialogs.duplicate import DuplicateDownloadDialog


def test_duplicate_dialog_completed_ui(qapp, tmp_path):
    test_file = tmp_path / "sample.zip"
    test_file.write_text("dummy")

    file_data = {
        "url": "http://example.com/sample.zip",
        "filename": "sample.zip",
        "path": str(test_file),
        "size": "10 MB",
        "status": "Complete",
        "user_agent": "TestAgent",
        "cookies": "auth=1"
    }

    dialog = DuplicateDownloadDialog(file_data)
    assert dialog.windowTitle() == "Duplicate Download"
    assert dialog.is_complete is True
    assert hasattr(dialog, "btn_open")
    assert hasattr(dialog, "btn_folder")
    assert hasattr(dialog, "btn_redownload")
    assert hasattr(dialog, "btn_copy")

    # Test actions
    dialog.on_redownload()
    assert dialog.get_action() == "redownload"

    dialog.on_download_copy()
    assert dialog.get_action() == "download_copy"
    dialog.close()


def test_duplicate_dialog_incomplete_ui(qapp):
    file_data = {
        "url": "http://example.com/incomplete.iso",
        "filename": "incomplete.iso",
        "path": "/tmp/incomplete.iso",
        "size": "500 MB",
        "status": "Paused",
        "user_agent": "",
        "cookies": ""
    }

    dialog = DuplicateDownloadDialog(file_data)
    assert dialog.windowTitle() == "Download Already Exists"
    assert dialog.is_complete is False
    assert hasattr(dialog, "btn_resume")
    assert hasattr(dialog, "btn_restart")
    assert hasattr(dialog, "btn_copy")

    dialog.on_resume()
    assert dialog.get_action() == "resume"

    dialog.on_restart()
    assert dialog.get_action() == "restart"
    dialog.close()
