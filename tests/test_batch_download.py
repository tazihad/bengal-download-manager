"""
Tests for Batch Download functionality in Bengal Download Manager.
Covers BatchPatternDialog, BatchDownloadDialog, BatchItemEditDialog,
BatchProberManager, and MainWindow batch integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.dialogs.batch_pattern import BatchPatternDialog
from ui.dialogs.batch_download import BatchDownloadDialog, BatchItemEditDialog
from core.workers.batch_prober import BatchProberManager, ProbeTask
from main import MainWindow


# ---------------------------------------------------------------------------
# BatchPatternDialog Tests
# ---------------------------------------------------------------------------

def test_batch_pattern_dialog_numeric_generation(qapp):
    """Test generating numeric sequences with zero padding."""
    dlg = BatchPatternDialog(initial_url="https://example.com/files/img*.png")
    dlg.hide()

    # Numbers mode: 1 to 5, padding 3 -> 001 to 005
    dlg.radio_numbers.setChecked(True)
    dlg.spin_num_from.setValue(1)
    dlg.spin_num_to.setValue(5)
    dlg.spin_wildcard_size.setValue(3)

    urls = dlg.generate_urls()
    assert len(urls) == 5
    assert urls[0] == "https://example.com/files/img001.png"
    assert urls[1] == "https://example.com/files/img002.png"
    assert urls[-1] == "https://example.com/files/img005.png"

    # Numbers mode: descending 10 down to 8, padding 2
    dlg.spin_num_from.setValue(10)
    dlg.spin_num_to.setValue(8)
    dlg.spin_wildcard_size.setValue(2)
    urls = dlg.generate_urls()
    assert urls == [
        "https://example.com/files/img10.png",
        "https://example.com/files/img09.png",
        "https://example.com/files/img08.png",
    ]


def test_batch_pattern_dialog_letter_generation(qapp):
    """Test generating alphabetical sequences."""
    dlg = BatchPatternDialog(initial_url="https://example.com/archive/data_*.tar.gz")
    dlg.hide()

    dlg.radio_letters.setChecked(True)
    dlg._on_mode_toggled()
    dlg.txt_let_from.setText("a")
    dlg.txt_let_to.setText("d")

    urls = dlg.generate_urls()
    assert len(urls) == 4
    assert urls == [
        "https://example.com/archive/data_a.tar.gz",
        "https://example.com/archive/data_b.tar.gz",
        "https://example.com/archive/data_c.tar.gz",
        "https://example.com/archive/data_d.tar.gz",
    ]


def test_batch_pattern_dialog_no_wildcard(qapp):
    """Ensure URLs without an asterisk return an empty list and disable OK button."""
    dlg = BatchPatternDialog(initial_url="https://example.com/file.zip")
    dlg.hide()
    urls = dlg.generate_urls()
    assert urls == []
    dlg._refresh_preview()
    assert not dlg.btn_ok.isEnabled()


def test_batch_pattern_dialog_accept_signal(qapp):
    """Verify that clicking OK emits the urls_generated signal."""
    dlg = BatchPatternDialog(initial_url="https://example.com/part*.bin")
    dlg.hide()
    dlg.spin_num_from.setValue(1)
    dlg.spin_num_to.setValue(2)
    dlg.spin_wildcard_size.setValue(1)

    received = []
    dlg.urls_generated.connect(lambda lst: received.extend(lst))

    dlg._on_accept()
    assert len(received) == 2
    assert received[0] == "https://example.com/part1.bin"
    assert received[1] == "https://example.com/part2.bin"
    assert dlg.get_generated_urls() == received


# ---------------------------------------------------------------------------
# BatchItemEditDialog Tests
# ---------------------------------------------------------------------------

def test_batch_item_edit_dialog(qapp):
    """Test viewing and modifying item details in BatchItemEditDialog."""
    data = {
        "filename": "old.zip",
        "custom_save_dir": "/tmp/custom",
        "url": "https://example.com/old.zip",
        "description": "Old file",
        "referer": "https://example.com",
        "username": "user1",
        "password": "pass1"
    }
    dlg = BatchItemEditDialog(data)
    dlg.hide()

    dlg.txt_filename.setText("new.zip")
    dlg.txt_desc.setText("Updated description")
    dlg._on_save()

    updated = dlg.get_data()
    assert updated["filename"] == "new.zip"
    assert updated["description"] == "Updated description"
    assert updated["custom_save_dir"] == "/tmp/custom"


# ---------------------------------------------------------------------------
# BatchDownloadDialog Tests
# ---------------------------------------------------------------------------

def test_batch_download_dialog_init_and_counts(qapp):
    """Test item initialization and table population."""
    urls = [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg",
        "https://example.com/doc.html",
        "https://example.com/data.zip"
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    assert dlg.table.rowCount() == 4
    assert dlg._items[0]["filename"] == "image1.jpg"
    assert dlg._items[3]["filename"] == "data.zip"
    assert dlg.btn_ok.isEnabled()


def test_batch_download_dialog_filtering(qapp):
    """Test filtering HTML, images, and duplicates in BatchDownloadDialog."""
    urls = [
        "https://example.com/file1.zip",
        "https://example.com/index.html",
        "https://example.com/photo.png",
        "https://example.com/file1.zip"  # duplicate
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    assert dlg.table.rowCount() == 4

    # Hide HTML
    dlg.chk_hide_html.setChecked(True)
    dlg._apply_filters()
    assert dlg.table.rowCount() == 3
    visible_names = [dlg.table.item(r, dlg.COL_NAME).text() for r in range(dlg.table.rowCount())]
    assert "index.html" not in visible_names

    # Hide Images
    dlg.chk_hide_images.setChecked(True)
    dlg._apply_filters()
    assert dlg.table.rowCount() == 2
    visible_names = [dlg.table.item(r, dlg.COL_NAME).text() for r in range(dlg.table.rowCount())]
    assert "photo.png" not in visible_names

    # Hide Duplicates
    dlg.chk_hide_duplicates.setChecked(True)
    dlg._apply_filters()
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, dlg.COL_NAME).text() == "file1.zip"


def test_batch_download_dialog_wildcard_renaming(qapp):
    """Test wildcard renaming on batch filenames."""
    urls = [
        "https://example.com/part1.rar",
        "https://example.com/part2.rar",
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    # Renaming pattern: bdm_*
    dlg.txt_pattern.setText("bdm_*")
    dlg._on_pattern_changed()

    assert dlg.table.item(0, dlg.COL_NAME).text() == "bdm_part1.rar"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "bdm_part2.rar"

    # Clear pattern resets back to base filename
    dlg.txt_pattern.setText("")
    dlg._on_pattern_changed()
    assert dlg.table.item(0, dlg.COL_NAME).text() == "part1.rar"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "part2.rar"


def test_batch_download_dialog_selection_buttons(qapp):
    """Test Select All, Deselect All, and check state summary."""
    urls = [
        "https://example.com/a.zip",
        "https://example.com/b.zip",
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    # Deselect all
    dlg._set_all_checked(False)
    for r in range(dlg.table.rowCount()):
        assert dlg.table.item(r, dlg.COL_CHECK).checkState() == Qt.CheckState.Unchecked
    assert not dlg.btn_ok.isEnabled()

    # Select all
    dlg._set_all_checked(True)
    for r in range(dlg.table.rowCount()):
        assert dlg.table.item(r, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    assert dlg.btn_ok.isEnabled()


def test_batch_download_dialog_destination_routing(qapp, tmp_path):
    """Test perCategory, oneCategory, and oneDirectory destination paths."""
    urls = [
        "https://example.com/video.mp4",
        "https://example.com/song.mp3",
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    # Default: perCategory
    dlg.radio_per_category.setChecked(True)
    dlg._on_dest_mode_changed()
    path_video = dlg.table.item(0, dlg.COL_SAVETO).text()
    path_song = dlg.table.item(1, dlg.COL_SAVETO).text()
    assert path_video != ""
    assert path_song != ""

    # Mode: oneDirectory
    custom_dir = str(tmp_path / "batch_out")
    dlg.radio_one_dir.setChecked(True)
    dlg.txt_save_dir.setText(custom_dir)
    dlg._on_dest_mode_changed()

    assert dlg.table.item(0, dlg.COL_SAVETO).text() == custom_dir
    assert dlg.table.item(1, dlg.COL_SAVETO).text() == custom_dir


def test_batch_download_dialog_probe_result(qapp):
    """Test updating table item when probe result arrives."""
    urls = ["https://example.com/archive.zip"]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    result = {
        "status": "Found",
        "size_bytes": 1048576,
        "size_str": "1.00 MB",
        "filename": "archive_resolved.zip"
    }
    dlg._on_probe_result(0, result)

    assert dlg.table.item(0, dlg.COL_SIZE).text() == "1.00 MB"
    assert dlg.table.item(0, dlg.COL_STATUS).text() == "Found"
    assert dlg.table.item(0, dlg.COL_NAME).text() == "archive_resolved.zip"


def test_batch_download_dialog_accept_submission(qapp, monkeypatch):
    """Test submitting batch downloads and invoking main_window.start_download."""
    urls = [
        "https://example.com/f1.zip",
        "https://example.com/f2.zip",
    ]
    mock_window = MagicMock()
    dlg = BatchDownloadDialog(urls, main_window=mock_window, auto_probe=False)
    dlg.hide()

    # Monkeypatch QMessageBox to not block
    monkeypatch.setattr("ui.dialogs.batch_download.QMessageBox.information", lambda *args, **kwargs: None)

    accepted_list = []
    dlg.batch_accepted.connect(lambda lst: accepted_list.extend(lst))

    dlg._on_accept()

    assert len(accepted_list) == 2
    assert accepted_list[0]["url"] == "https://example.com/f1.zip"
    assert accepted_list[1]["url"] == "https://example.com/f2.zip"
    assert mock_window.add_batch_downloads.call_count == 1


# ---------------------------------------------------------------------------
# BatchProberManager Unit Test
# ---------------------------------------------------------------------------

def test_batch_prober_worker(qapp):
    """Test BatchProberManager ProbeTask run execution with mocked urllib."""
    results = []
    manager = BatchProberManager(max_concurrent=2)

    def on_finished(idx, res):
        results.append((idx, res))

    manager.probe_finished.connect(on_finished)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.geturl.return_value = "https://example.com/test.iso"
    mock_resp.headers = {
        "Content-Length": "2048",
        "Content-Disposition": 'attachment; filename="probed.iso"'
    }

    mock_opener = MagicMock()
    mock_opener.open.return_value.__enter__.return_value = mock_resp

    task = ProbeTask(
        row_index=0,
        url="https://example.com/test.iso",
        signals=manager.signals
    )
    with patch.object(task, "_create_opener", return_value=mock_opener):
        task.run()

    assert len(results) == 1
    idx, res = results[0]
    assert idx == 0
    assert res["status"] == "Found"
    assert res["size_bytes"] == 2048
    assert res["filename"] == "probed.iso"


# ---------------------------------------------------------------------------
# MainWindow Integration Tests
# ---------------------------------------------------------------------------

def test_main_window_open_batch_dialogs(qapp, monkeypatch):
    """Test MainWindow helper methods for opening batch pattern and batch download dialogs."""
    window = MainWindow(start_ipc=False)
    window.hide()

    # Test open_batch_pattern
    opened_pattern = []
    class MockPatternDialog:
        def __init__(self, parent=None, initial_url=""):
            self.parent = parent
            self.initial_url = initial_url
            opened_pattern.append(self)
        def exec(self):
            return 0
        def get_generated_urls(self):
            return []

    monkeypatch.setattr("ui.dialogs.BatchPatternDialog", MockPatternDialog)
    window.open_batch_pattern("https://example.com/test*.zip")
    assert len(opened_pattern) == 1
    assert opened_pattern[0].initial_url == "https://example.com/test*.zip"

    # Test open_batch_download
    opened_batch = []
    class MockBatchDialog:
        def __init__(self, urls, parent=None, main_window=None, is_import=False, auto_probe=True):
            self.urls = urls
            self.is_import = is_import
            opened_batch.append(self)
        def exec(self):
            return 0

    monkeypatch.setattr("ui.dialogs.BatchDownloadDialog", MockBatchDialog)
    window.open_batch_download(["https://example.com/1.zip", "https://example.com/2.zip"], is_import=True)
    assert len(opened_batch) == 1
    assert len(opened_batch[0].urls) == 2
    assert opened_batch[0].is_import is True

    window.is_quitting = True
    window.close()


def test_main_window_add_batch_downloads(qapp, tmp_path, monkeypatch):
    """Test MainWindow.add_batch_downloads batch ingestion and queue concurrency."""
    monkeypatch.setattr("core.config.get_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr("core.database.get_db_path", lambda: str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.dialogs.batch_download.QMessageBox.information", lambda *args, **kwargs: None)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.information", lambda *args, **kwargs: None)

    from ui.main_window import MainWindow
    window = MainWindow(start_ipc=False)
    window.hide()

    started_workers = []
    window._start_download_worker = MagicMock(side_effect=lambda *args, **kwargs: started_workers.append(args))

    batch_items = [
        {"url": f"https://example.com/img-{i}.jpg", "filename": f"img-{i}.jpg", "save_dir": str(tmp_path)}
        for i in range(10)
    ]

    window.add_batch_downloads(batch_items, queue_name="Main download queue", start_immediate=True)

    assert window.download_table.rowCount() >= 10
    queue_max = window._get_queue_max_concurrent("Main download queue")
    assert len(started_workers) == min(10, queue_max)

    window.is_quitting = True
    window.close()


def test_batch_checkbox_delegate_paint_and_interaction(qapp):
    """Verify BatchCheckBoxDelegate renders without errors and toggles check states."""
    from ui.dialogs.batch_download import BatchDownloadDialog, BatchCheckBoxDelegate
    from PyQt6.QtGui import QPainter, QPixmap, QMouseEvent
    from PyQt6.QtWidgets import QStyleOptionViewItem, QAbstractItemView, QStyle
    from PyQt6.QtCore import QEvent, QPoint, QRect, QPointF

    urls = ["https://example.com/item1.zip", "https://example.com/item2.zip"]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    delegate = dlg.table.itemDelegateForColumn(dlg.COL_CHECK)
    assert isinstance(delegate, BatchCheckBoxDelegate)
    assert dlg.table.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel

    # Paint test with QPainter onto a pixmap
    pixmap = QPixmap(100, 30)
    painter = QPainter(pixmap)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 36, 28)
    opt.state = QStyle.StateFlag.State_Selected

    model_idx_0 = dlg.table.model().index(0, dlg.COL_CHECK)
    delegate.paint(painter, opt, model_idx_0)

    # Test unselected state
    opt.state = QStyle.StateFlag.State_None
    delegate.paint(painter, opt, model_idx_0)
    painter.end()

    # Test mouse click toggle via editorEvent
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    initial_checked = dlg.table.item(0, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    handled = delegate.editorEvent(press_event, dlg.table.model(), opt, model_idx_0)
    assert handled is True
    toggled_checked = dlg.table.item(0, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    assert toggled_checked != initial_checked

    dlg.close()


def test_batch_download_dialog_sorting(qapp):
    """Test column sorting for all columns in BatchDownloadDialog."""
    urls = [
        "https://example.com/zebra.mp4",
        "https://example.com/apple.pdf",
        "https://example.com/banana.zip",
    ]
    dlg = BatchDownloadDialog(urls, auto_probe=False)
    dlg.hide()

    assert dlg.table.isSortingEnabled() is True
    assert dlg.table.horizontalHeader().sectionsClickable() is True

    # Simulate probe results for distinct sizes
    dlg._on_probe_result(0, {"status": "Ready", "size_bytes": 5000000, "size_str": "5.0 MB", "filename": "zebra.mp4"})
    dlg._on_probe_result(1, {"status": "Ready", "size_bytes": 10000000, "size_str": "10.0 MB", "filename": "apple.pdf"})
    dlg._on_probe_result(2, {"status": "Ready", "size_bytes": 100000, "size_str": "100.0 KB", "filename": "banana.zip"})

    # 1. Sort by File name (COL_NAME = 1) Ascending
    dlg.table.sortByColumn(dlg.COL_NAME, Qt.SortOrder.AscendingOrder)
    assert dlg.table.item(0, dlg.COL_NAME).text() == "apple.pdf"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "banana.zip"
    assert dlg.table.item(2, dlg.COL_NAME).text() == "zebra.mp4"

    # Sort Descending
    dlg.table.sortByColumn(dlg.COL_NAME, Qt.SortOrder.DescendingOrder)
    assert dlg.table.item(0, dlg.COL_NAME).text() == "zebra.mp4"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "banana.zip"
    assert dlg.table.item(2, dlg.COL_NAME).text() == "apple.pdf"

    # 2. Sort by Size (COL_SIZE = 2) Ascending: 100KB, 5MB, 10MB
    dlg.table.sortByColumn(dlg.COL_SIZE, Qt.SortOrder.AscendingOrder)
    assert dlg.table.item(0, dlg.COL_NAME).text() == "banana.zip"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "zebra.mp4"
    assert dlg.table.item(2, dlg.COL_NAME).text() == "apple.pdf"

    # Sort by Size Descending: 10MB, 5MB, 100KB
    dlg.table.sortByColumn(dlg.COL_SIZE, Qt.SortOrder.DescendingOrder)
    assert dlg.table.item(0, dlg.COL_NAME).text() == "apple.pdf"
    assert dlg.table.item(1, dlg.COL_NAME).text() == "zebra.mp4"
    assert dlg.table.item(2, dlg.COL_NAME).text() == "banana.zip"

    # 3. Verify _get_row_data returns the correct item on sorted row
    # In descending size sort, row 0 is apple.pdf
    item_row0 = dlg._get_row_data(0)
    assert item_row0["filename"] == "apple.pdf"

    # 4. Sort by Checkbox (COL_CHECK = 0)
    # Uncheck apple.pdf (row 0)
    dlg.table.item(0, dlg.COL_CHECK).setCheckState(Qt.CheckState.Unchecked)
    dlg._on_table_item_changed(dlg.table.item(0, dlg.COL_CHECK))

    # Sort Ascending: Unchecked first, then Checked
    dlg.table.sortByColumn(dlg.COL_CHECK, Qt.SortOrder.AscendingOrder)
    assert dlg.table.item(0, dlg.COL_CHECK).checkState() == Qt.CheckState.Unchecked
    assert dlg.table.item(0, dlg.COL_NAME).text() == "apple.pdf"
    assert dlg.table.item(1, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    assert dlg.table.item(2, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked

    # Sort Descending: Checked first, then Unchecked
    dlg.table.sortByColumn(dlg.COL_CHECK, Qt.SortOrder.DescendingOrder)
    assert dlg.table.item(0, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    assert dlg.table.item(1, dlg.COL_CHECK).checkState() == Qt.CheckState.Checked
    assert dlg.table.item(2, dlg.COL_CHECK).checkState() == Qt.CheckState.Unchecked
    assert dlg.table.item(2, dlg.COL_NAME).text() == "apple.pdf"

    dlg.close()
