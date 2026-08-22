import os
import pytest
from PyQt6.QtCore import Qt
from ui.dialogs.duplicate import DuplicateDownloadDialog
from main import MainWindow


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


def test_duplicate_dialog_open_actions(qapp, tmp_path, monkeypatch):
    test_file = tmp_path / "archive.tar.gz"
    test_file.write_text("test")

    opened_files = []
    opened_folders = []

    monkeypatch.setattr("ui.dialogs.duplicate.open_file_generic", lambda path: opened_files.append(path))
    monkeypatch.setattr("ui.dialogs.duplicate.show_in_folder", lambda path: opened_folders.append(path))

    file_data = {
        "url": "http://example.com/archive.tar.gz",
        "filename": "archive.tar.gz",
        "path": str(test_file),
        "size": "2.5 MB",
        "status": "Complete",
    }

    dialog = DuplicateDownloadDialog(file_data)
    dialog.on_open()
    assert dialog.get_action() == "open"
    assert opened_files == [str(test_file)]

    dialog.on_open_folder()
    assert dialog.get_action() == "open_folder"
    assert opened_folders == [str(test_file)]


def test_main_window_duplicate_detection_active(qapp, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    # Add a mock downloading row
    item = window.start_download(
        url="http://example.com/active.mp4",
        custom_filename="active.mp4",
        custom_save_dir="/tmp",
        start_paused=False,
        show_dialog=False
    )
    row = window.download_table.row(item)
    window._set_status_text(row, "Downloading", logic_status="Downloading")

    # Spy on DuplicateDownloadDialog
    dialog_opened = []
    monkeypatch.setattr("ui.dialogs.duplicate.DuplicateDownloadDialog.exec", lambda self: dialog_opened.append(True))

    # Incoming request with exact same URL
    window.process_incoming_url("http://example.com/active.mp4")

    # For active downloads, dialog should NOT open; it brings active window to front
    assert len(dialog_opened) == 0


def test_main_window_duplicate_detection_completed(qapp, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    # Add completed row
    item = window.start_download(
        url="http://example.com/finished.zip",
        custom_filename="finished.zip",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )
    row = window.download_table.row(item)
    window._set_status_text(row, "Complete", logic_status="Complete")

    actions_called = []
    def mock_exec(self):
        self.action = "download_copy"
        actions_called.append("download_copy")
        return 1

    monkeypatch.setattr("ui.dialogs.duplicate.DuplicateDownloadDialog.exec", mock_exec)
    
    copy_started = []
    monkeypatch.setattr(window, "_start_duplicate_copy", lambda u, ua, c: copy_started.append(u))

    window.process_incoming_url("http://example.com/finished.zip")

    assert "download_copy" in actions_called
    assert copy_started == ["http://example.com/finished.zip"]


def test_main_window_duplicate_detection_resume(qapp, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    item = window.start_download(
        url="http://example.com/paused.zip",
        custom_filename="paused.zip",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )
    row = window.download_table.row(item)
    window._set_status_text(row, "Paused", logic_status="Paused")

    def mock_exec(self):
        self.action = "resume"
        return 1

    monkeypatch.setattr("ui.dialogs.duplicate.DuplicateDownloadDialog.exec", mock_exec)
    
    resumed = []
    monkeypatch.setattr(window, "resume_selected_download", lambda: resumed.append(True))

    window.process_incoming_url("http://example.com/paused.zip")

    assert len(resumed) == 1


def test_get_unique_filepath_with_existing_names_and_paths():
    from core.utils import get_unique_filepath
    
    # When file does NOT exist on disk, but name is in existing_names
    res1 = get_unique_filepath("/tmp/virtual/testfile.txt", existing_names={"testfile.txt"})
    assert res1 == "/tmp/virtual/testfile (1).txt"
    
    # Incremental numbering (1) -> (2)
    res2 = get_unique_filepath("/tmp/virtual/testfile.txt", existing_names={"testfile.txt", "testfile (1).txt"})
    assert res2 == "/tmp/virtual/testfile (2).txt"

    # Base already has number
    res3 = get_unique_filepath("/tmp/virtual/testfile (1).txt", existing_names={"testfile (1).txt"})
    assert res3 == "/tmp/virtual/testfile (2).txt"


def test_download_copy_paused_renaming(qapp, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    # Add a paused item to table (not existing on disk)
    window.start_download(
        url="http://example.com/doc.pdf",
        custom_filename="doc.pdf",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    # When incoming copy arrives for doc.pdf, FileInfoDialog should auto-number as doc (1).pdf
    from ui.dialogs import DownloadFileInfoDialog
    file_info = {"url": "http://example.com/doc.pdf", "filename": "doc.pdf", "size_str": "1 MB"}
    
    existing_filenames = set()
    existing_paths = set()
    for r in range(window.download_table.rowCount()):
        it = window.download_table.item(r, 0)
        if it:
            existing_filenames.add(it.text())
            sp = it.data(Qt.ItemDataRole.UserRole + 1)
            if sp:
                existing_paths.add(os.path.normpath(sp))

    dlg = DownloadFileInfoDialog(file_info, existing_paths=existing_paths, existing_names=existing_filenames)
    results = dlg.get_results()
    assert results["filename"] == "doc (1).pdf"
    assert results["save_path"].endswith("doc (1).pdf")

    # If both doc.pdf and doc (1).pdf exist in table
    window.start_download(
        url="http://example.com/doc.pdf",
        custom_filename="doc (1).pdf",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )
    
    existing_filenames2 = {window.download_table.item(r, 0).text() for r in range(window.download_table.rowCount()) if window.download_table.item(r, 0)}
    dlg2 = DownloadFileInfoDialog(file_info, existing_names=existing_filenames2)
    results2 = dlg2.get_results()
    assert results2["filename"] == "doc (2).pdf"


def test_main_window_restart_download_clean(qapp, tmp_path, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    test_file = tmp_path / "restart_me.zip"
    test_file.write_text("old partial data")
    test_aria = tmp_path / "restart_me.zip.aria2"
    test_aria.write_text("control file")
    test_bdmx = tmp_path / "restart_me.zip.tmpbdm.bdmx"
    test_bdmx.write_text("state data")

    item = window.start_download(
        url="http://example.com/restart_me.zip",
        custom_filename="restart_me.zip",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    row = window.download_table.row(item)
    window._set_status_text(row, "Paused", logic_status="Paused")
    status_item = window.download_table.item(row, 2)
    status_item.setData(Qt.ItemDataRole.UserRole, "50%")

    workers_spawned = []
    def mock_start_worker(url, item_ref, resume_filename=None, custom_save_dir=None, show_dialog=True, user_agent=None, cookies=None, allow_resume=True):
        workers_spawned.append({"allow_resume": allow_resume, "filename": resume_filename})

    monkeypatch.setattr(window, "_start_download_worker", mock_start_worker)

    window._restart_download_row(row, item, "http://example.com/restart_me.zip")

    # Artifacts should be cleaned
    assert not test_file.exists()
    assert not test_aria.exists()
    assert not test_bdmx.exists()

    # Worker started with allow_resume=False
    assert len(workers_spawned) == 1
    assert workers_spawned[0]["allow_resume"] is False
    assert status_item.data(Qt.ItemDataRole.UserRole) == "0%"


