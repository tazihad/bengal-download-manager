"""
Core UI and Integration Tests for Bengal Download Manager MainWindow and Dialogs.
"""

import time
import pytest
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication
from main import MainWindow, SingleInstanceServer, check_single_instance
from ui.dialogs import OptionsDialog
from core.utils import save_extension_config, load_extension_config


def test_main_window_table_operations(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()
    initial_count = window.download_table.rowCount()
    assert window.download_table is not None
    assert window.download_table.columnCount() == 7

    # Add a mock download row
    window.start_download(
        url="http://example.com/test.iso",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    assert window.download_table.rowCount() == initial_count + 1
    item0 = window.download_table.item(0, 0)
    assert item0 is not None
    assert item0.text() == "test.iso"

    # Test QML data conversion
    qml_data = window.get_qml_downloads_data()
    assert len(qml_data) == initial_count + 1
    assert qml_data[0]["filename"] == "test.iso"
    assert qml_data[0]["url"] == "http://example.com/test.iso"
    window.close()


def test_main_window_rename_file(qapp, tmp_path, monkeypatch):
    test_file = tmp_path / "old_name.txt"
    test_file.write_text("dummy content")

    window = MainWindow(start_ipc=False)
    window.hide()
    window.start_download(
        url="http://example.com/old_name.txt",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    row = 0
    item0 = window.download_table.item(row, 0)
    item0.setData(Qt.ItemDataRole.UserRole + 1, str(test_file))

    class MockRenameDialog:
        def __init__(self, filename, parent=None): pass
        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted
        def get_filename(self): return "new_name.txt"

    import main
    monkeypatch.setattr(main, "RenameDialog", MockRenameDialog)

    window.ctx_rename(item0)

    new_file = tmp_path / "new_name.txt"
    assert new_file.exists()
    assert not test_file.exists()
    assert item0.text() == "new_name.txt"
    assert item0.data(Qt.ItemDataRole.UserRole + 1) == str(new_file)
    window.close()


def test_main_window_move_file(qapp, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    test_file = source_dir / "move_me.zip"
    test_file.write_text("data")
    dest_file = target_dir / "moved.zip"

    window = MainWindow(start_ipc=False)
    window.hide()
    window.start_download(
        url="http://example.com/move_me.zip",
        custom_save_dir=str(source_dir),
        start_paused=True,
        show_dialog=False
    )
    row = 0
    item0 = window.download_table.item(row, 0)
    item0.setData(Qt.ItemDataRole.UserRole + 1, str(test_file))

    import main
    monkeypatch.setattr(main, "choose_portal_save_path", lambda title, filename, folder: str(dest_file))

    window.ctx_move(item0)

    assert dest_file.exists()
    assert not test_file.exists()
    assert item0.text() == "moved.zip"
    assert item0.data(Qt.ItemDataRole.UserRole + 1) == str(dest_file)
    window.close()


def test_single_instance_server_ipc(qapp, monkeypatch):
    test_key = "bengal-dm-test-single-instance-key"
    received_payloads = []

    server = SingleInstanceServer(key=test_key)
    server.messageReceived.connect(lambda p: received_payloads.append(p))
    server.start()

    # Simulate secondary instance connecting
    connected = check_single_instance(key=test_key, timeout_ms=1000)
    assert connected is True

    # Process Qt event loop to let server handle incoming socket connection
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert len(received_payloads) == 1
    assert received_payloads[0].get("command") == "show"

    server.stop()


def test_process_incoming_url_routes_media_link_to_media_downloader(qapp, monkeypatch):
    """Verify that process_incoming_url routes media streaming links directly to open_media_downloader."""
    win = MainWindow(start_ipc=False)
    win.hide()

    called_url = None
    called_auto_start = None
    called_preset = None

    def mock_open_media_downloader(url=None, auto_analyze=False, auto_start=False, target_preset=""):
        nonlocal called_url, called_auto_start, called_preset
        called_url = url
        called_auto_start = auto_start
        called_preset = target_preset

    monkeypatch.setattr(win, "open_media_downloader", mock_open_media_downloader)

    # 1. Standard YouTube URL
    win.process_incoming_url("https://www.youtube.com/watch?v=sample_vid|Mozilla/5.0|cookie1=val")
    assert called_url == "https://www.youtube.com/watch?v=sample_vid"
    assert called_preset is not None

    # 2. Vimeo URL
    called_url = None
    win.process_incoming_url("https://vimeo.com/76979871||")
    assert called_url == "https://vimeo.com/76979871"

    win.close()


def test_download_complete_persistence_on_restart(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("core.utils.get_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr("main.get_data_dir", lambda: str(tmp_path))

    downloaded_file = tmp_path / "finished_movie.mp4"
    downloaded_file.write_bytes(b"A" * 1024 * 100)

    win1 = MainWindow(start_ipc=False)
    win1.hide()
    win1.start_download(
        url="http://example.com/finished_movie.mp4",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    item_ref = win1.download_table.item(0, 0)
    item_ref.setData(Qt.ItemDataRole.UserRole + 1, str(downloaded_file))

    # Emit progress at 98.30%
    win1.update_download_row(item_ref, ("finished_movie.mp4", "100.00 KB", "Downloading", "00:01", "10.00 KB/s", 98300, 100000))
    status_item = win1.download_table.item(0, 2)
    assert status_item.text() == "98.30%"

    # Finish download
    win1.download_finished(item_ref, "Complete")
    assert win1.download_table.item(0, 2).text() == "Complete"

    # Simulate app exit: stop_all_downloads and save_data
    win1.stop_all_downloads()
    assert win1.download_table.item(0, 2).text() == "Complete"
    win1.save_data()
    win1.close()

    # Reopen window and load persisted downloads.json
    win2 = MainWindow(start_ipc=False)
    win2.hide()
    assert win2.download_table.rowCount() == 1
    assert win2.download_table.item(0, 0).text() == "finished_movie.mp4"
    assert win2.download_table.item(0, 1) is not None
    assert win2.download_table.item(0, 1).text() == "100.00 KB"
    assert win2.download_table.item(0, 2).text() == "Complete"
    assert win2.download_table.item(0, 2).data(Qt.ItemDataRole.UserRole + 1) == "Complete"
    win2.close()


def test_options_dialog_max_connections_persistence(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 8})

    dlg = OptionsDialog()
    assert hasattr(dlg, "spin_max_conn")
    assert dlg.spin_max_conn.minimum() == 1
    assert dlg.spin_max_conn.maximum() == 32
    assert dlg.spin_max_conn.value() == 8

    # Change to 16 and save
    dlg.spin_max_conn.setValue(16)
    dlg.save_and_accept()

    loaded = load_extension_config()
    assert loaded["max_connections"] == 16

    # Reopen dialog and verify 16 is displayed
    dlg2 = OptionsDialog()
    assert dlg2.spin_max_conn.value() == 16
    dlg2.reject()
