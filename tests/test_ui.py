import pytest
from PyQt6.QtCore import Qt
from main import MainWindow

def test_main_window_table_operations(qapp):
    window = MainWindow(start_ipc=False)
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

def test_main_window_qml_row_controls(qapp):
    window = MainWindow(start_ipc=False)
    initial_count = window.download_table.rowCount()
    window.start_download(
        url="http://example.com/demo.mp4",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    assert window.download_table.rowCount() == initial_count + 1
    window.qml_delete_download(0)
    assert window.download_table.rowCount() == initial_count
