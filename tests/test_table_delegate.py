"""Unit tests for ModernTableDelegate."""
import pytest
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QStyleOptionViewItem
from PyQt6.QtGui import QPainter, QPixmap, QIcon

from ui.delegates.table_delegate import ModernTableDelegate, _get_category_for_filename


def test_get_category_for_filename():
    assert _get_category_for_filename("archive.zip") == "Compressed"
    assert _get_category_for_filename("installer.exe") == "Programs"
    assert _get_category_for_filename("movie.mp4") == "Video"
    assert _get_category_for_filename("song.mp3") == "Music"
    assert _get_category_for_filename("photo.jpg") == "Pictures"
    assert _get_category_for_filename("doc.pdf") == "Documents"
    assert _get_category_for_filename("unknown.xyz") == "General"


def test_modern_table_delegate_size_hint(qapp):
    table = QTableWidget(1, 7)
    delegate = ModernTableDelegate(table)
    opt = QStyleOptionViewItem()
    idx = table.model().index(0, 0)
    size = delegate.sizeHint(opt, idx)
    assert size.height() == 50


def test_modern_table_delegate_painting(qapp):
    table = QTableWidget(2, 7)
    item_name = QTableWidgetItem("setup.exe")
    item_name.setIcon(QIcon())
    table.setItem(0, 0, item_name)

    item_status = QTableWidgetItem("35.00%")
    item_status.setData(Qt.ItemDataRole.UserRole, "35.00%")
    table.setItem(0, 2, item_status)

    item_complete = QTableWidgetItem("Complete")
    table.setItem(1, 2, item_complete)

    delegate = ModernTableDelegate(table)
    pixmap = QPixmap(300, 50)
    painter = QPainter(pixmap)

    # Paint column 0 (name)
    opt0 = QStyleOptionViewItem()
    opt0.rect = QRect(0, 0, 150, 50)
    delegate.paint(painter, opt0, table.model().index(0, 0))

    # Paint column 2 (downloading status with progress bar)
    opt2 = QStyleOptionViewItem()
    opt2.rect = QRect(150, 0, 150, 50)
    delegate.paint(painter, opt2, table.model().index(0, 2))

    # Paint column 2 complete status
    opt_complete = QStyleOptionViewItem()
    opt_complete.rect = QRect(150, 0, 150, 50)
    delegate.paint(painter, opt_complete, table.model().index(1, 2))

    # Item with numeric timestamp in UserRole+3 (date_added)
    item_with_ts = QTableWidgetItem("archive.zip")
    item_with_ts.setData(Qt.ItemDataRole.UserRole + 3, 1755315482.123)
    table.setItem(1, 0, item_with_ts)
    opt_ts = QStyleOptionViewItem()
    opt_ts.rect = QRect(0, 0, 150, 50)
    delegate.paint(painter, opt_ts, table.model().index(1, 0))

    # Test status formatting for Paused download (e.g. 19% Paused)
    item_paused = QTableWidgetItem("19%")
    item_paused.setData(Qt.ItemDataRole.UserRole, "19%")
    item_paused.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
    table.setItem(0, 2, item_paused)
    delegate.paint(painter, opt2, table.model().index(0, 2))

    # Test status formatting for Active download (e.g. 20.00% Downloading)
    item_dl = QTableWidgetItem("20%")
    item_dl.setData(Qt.ItemDataRole.UserRole, "20%")
    item_dl.setData(Qt.ItemDataRole.UserRole + 1, "Downloading...")
    table.setItem(0, 2, item_dl)
    delegate.paint(painter, opt2, table.model().index(0, 2))

    # Test painting hyphenated filename (should not crash or drop whole hyphen-separated words)
    item_hyphen = QTableWidgetItem("my-super-long-hyphenated-file-name-v1.0.tar.gz")
    table.setItem(0, 0, item_hyphen)
    opt_narrow = QStyleOptionViewItem()
    opt_narrow.rect = QRect(0, 0, 80, 50)
    delegate.paint(painter, opt_narrow, table.model().index(0, 0))

    painter.end()


def test_table_word_wrap_and_elide_mode(qapp):
    from ui.main_window import MainWindow
    window = MainWindow(start_ipc=False)
    assert window.download_table.wordWrap() is False
    assert window.download_table.textElideMode() == Qt.TextElideMode.ElideRight
    window.close()

