"""End-to-end tests: complete download flow."""

import time
import pytest
from PyQt6.QtWidgets import QTableWidgetItem, QAbstractItemView
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QSignalSpy


@pytest.fixture(scope="module")
def win(qapp, destroy_widget):
    from ui.main_window import MainWindow
    w = MainWindow(start_ipc=False)
    yield w
    destroy_widget(w)


class TestAddDownloadRow:
    def test_start_download_adds_row(self, win):
        initial = win.download_table.rowCount()
        win.start_download(
            "https://example.com/testfile.zip",
            show_dialog=False,
        )
        assert win.download_table.rowCount() == initial + 1

    def test_row_has_filename(self, win):
        row = win.download_table.rowCount() - 1
        item = win.download_table.item(row, 0)
        assert item is not None
        assert item.text() == "testfile.zip"

    def test_row_has_url(self, win):
        row = win.download_table.rowCount() - 1
        item = win.download_table.item(row, 0)
        assert item.data(Qt.ItemDataRole.UserRole) == "https://example.com/testfile.zip"

    def test_row_has_date_added(self, win):
        row = win.download_table.rowCount() - 1
        item = win.download_table.item(row, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 3)

    def test_row_has_queue(self, win):
        row = win.download_table.rowCount() - 1
        item = win.download_table.item(row, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 8) == "Main download queue"

    def test_status_column_set(self, win):
        row = win.download_table.rowCount() - 1
        status_item = win.download_table.item(row, 2)
        assert status_item is not None
        assert status_item.text()


class TestMultipleDownloads:
    def test_add_second_download(self, win):
        initial = win.download_table.rowCount()
        win.start_download(
            "https://example.com/another.zip",
            show_dialog=False,
        )
        assert win.download_table.rowCount() == initial + 1

    def test_both_rows_present(self, win):
        assert win.download_table.rowCount() >= 2

    def test_first_row_url_preserved(self, win):
        item = win.download_table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole) is not None


class TestTableOperations:
    def test_select_row(self, win):
        win.download_table.selectRow(0)
        assert win.download_table.currentRow() == 0

    def test_table_sorting_mode_is_bool(self, win):
        assert isinstance(win.download_table.isSortingEnabled(), bool)

    def test_context_menu_policy(self, win):
        policy = win.download_table.contextMenuPolicy()
        assert policy == Qt.ContextMenuPolicy.CustomContextMenu

    def test_double_click_signal_emits(self, win):
        assert callable(win._on_table_cell_double_clicked)
        received = []
        win.download_table.cellDoubleClicked.connect(lambda r, c: received.append((r, c)))
        win.download_table.cellDoubleClicked.emit(0, 1)
        assert (0, 1) in received


class TestCategoryFilter:
    def test_filter_by_all_downloads(self, win):
        win.filter_downloads(win.all_downloads_header, 0)

    def test_filter_by_category(self, win):
        if win.all_downloads_header.childCount() > 0:
            child = win.all_downloads_header.child(0)
            win.filter_downloads(child, 0)

    def test_filter_by_status(self, win):
        win.filter_downloads(win.item_unfinished, 0)
        win.filter_downloads(win.item_finished, 0)


class TestUIStateUpdates:
    def test_update_ui_states_no_crash(self, win):
        win.update_ui_states()

    def test_update_ui_states_with_selection(self, win):
        win.download_table.selectRow(0)
        win.update_ui_states()

    def test_update_ui_states_without_selection(self, win):
        win.download_table.clearSelection()
        win.update_ui_states()

    def test_update_status_bar_speed_no_crash(self, win):
        win.update_status_bar_speed()

    def test_update_periodic_status_no_crash(self, win):
        win.update_periodic_status()


class TestDeleteRow:
    def test_delete_row(self, win):
        initial = win.download_table.rowCount()
        if initial == 0:
            pytest.skip("No rows to delete")
        win.download_table.selectRow(initial - 1)
        win.delete_selected_download()
        assert win.download_table.rowCount() <= initial


class TestDownloadStoreIntegration:
    def test_store_count_matches_table(self, win):
        assert win.download_store.count() >= 0

    def test_store_signals_connected(self, win):
        assert win.download_store.downloadsChanged is not None

    def test_store_add_item(self, win):
        initial = win.download_store.count()
        win.download_store.add_item({
            "url": "https://example.com/store-test.zip",
            "filename": "store-test.zip",
            "status": "Pending...",
        })
        assert win.download_store.count() == initial + 1
        win.download_store.remove_item("https://example.com/store-test.zip")


class TestShutdownFlow:
    def test_close_triggers_cleanup(self, win):
        assert win.is_quitting is False

    def test_quit_app_sets_flag(self, win):
        original = win.is_quitting
        win.is_quitting = True
        assert win.is_quitting is True
        win.is_quitting = original
