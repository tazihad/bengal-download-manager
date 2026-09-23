import pytest
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QComboBox, QMenu, QWidget
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QPaintEvent
from ui.components.csd_titlebar import CsdTitleBar, attach_csd, detach_csd
from core.services.theme_service import apply_titlebar_theme, _TitleBarEventFilter


@pytest.fixture
def qapp(qapp):
    return qapp


def test_csd_titlebar_has_styled_background(qapp):
    win = QMainWindow()
    titlebar = CsdTitleBar(win, is_dark=False)
    assert titlebar.testAttribute(Qt.WidgetAttribute.WA_StyledBackground) is True
    assert titlebar.autoFillBackground() is True


def test_csd_titlebar_has_min_max_close_on_all_windows(qapp):
    # Test on QMainWindow
    main_win = QMainWindow()
    tb_main = CsdTitleBar(main_win, is_dark=False, is_dialog=False)
    assert tb_main.btn_min is not None
    assert tb_main.btn_max is not None
    assert tb_main.btn_close is not None
    assert tb_main.btn_min.text() == "–"
    assert tb_main.btn_max.text() == "□"
    assert tb_main.btn_close.text() == "✕"

    # Test on QDialog
    dialog = QDialog()
    tb_dialog = CsdTitleBar(dialog, is_dark=False, is_dialog=True)
    assert tb_dialog.btn_min is not None
    assert tb_dialog.btn_max is not None
    assert tb_dialog.btn_close is not None
    assert tb_dialog.btn_min.text() == "–"
    assert tb_dialog.btn_max.text() == "□"
    assert tb_dialog.btn_close.text() == "✕"


def test_csd_titlebar_toggle_maximize(qapp):
    dialog = QDialog()
    tb = CsdTitleBar(dialog, is_dark=False, is_dialog=True)
    assert tb.btn_max.text() == "□"
    
    tb._toggle_maximize()
    assert dialog.isMaximized()
    assert tb.btn_max.text() == "❐"

    tb._toggle_maximize()
    assert not dialog.isMaximized()
    assert tb.btn_max.text() == "□"


def test_attach_csd_ignores_popups_and_menus(qapp):
    # Test QComboBox popup
    combo = QComboBox()
    combo.addItems(["Item 1", "Item 2"])
    popup = combo.view().window()
    assert popup.windowType() == Qt.WindowType.Popup or bool(popup.windowFlags() & Qt.WindowType.Popup)

    attach_csd(popup, is_dark=False)
    assert getattr(popup, "_csd_titlebar", None) is None

    # Test QMenu
    menu = QMenu()
    attach_csd(menu, is_dark=False)
    assert getattr(menu, "_csd_titlebar", None) is None

    # Test raw non-window QWidget
    widget = QWidget()
    attach_csd(widget, is_dark=False)
    assert getattr(widget, "_csd_titlebar", None) is None


def test_attach_and_detach_csd_main_window_and_dialog(qapp):
    main_win = QMainWindow()
    attach_csd(main_win, is_dark=True)
    assert getattr(main_win, "_csd_titlebar", None) is not None
    assert main_win._csd_titlebar._is_dark is True

    # Options / Dialog
    dialog = QDialog()
    attach_csd(dialog, is_dark=True)
    assert getattr(dialog, "_csd_titlebar", None) is not None
    assert dialog._csd_titlebar._is_dark is True

    # Detach
    detach_csd(main_win)
    assert getattr(main_win, "_csd_titlebar", None) is None

    detach_csd(dialog)
    assert getattr(dialog, "_csd_titlebar", None) is None


def test_csd_titlebar_paint_event(qapp):
    win = QMainWindow()
    tb = CsdTitleBar(win, is_dark=True)
    tb.show()
    # Ensure paintEvent does not crash
    tb.repaint()


def test_titlebar_event_filter_ignores_popups(qapp):
    event_filter = _TitleBarEventFilter(qapp)
    combo = QComboBox()
    combo.addItems(["A", "B"])
    popup = combo.view().window()

    show_event = QEvent(QEvent.Type.Show)
    res = event_filter.eventFilter(popup, show_event)
    assert getattr(popup, "_csd_titlebar", None) is None


def test_apply_titlebar_theme_sync_all_windows(qapp, monkeypatch):
    import os
    monkeypatch.setenv("BDM_FORCE_CSD", "1")

    main_win = QMainWindow()
    dialog = QDialog()

    apply_titlebar_theme("Dark", window=main_win)
    assert getattr(main_win, "_csd_titlebar", None) is not None
    assert main_win._csd_titlebar._is_dark is True

    attach_csd(dialog, is_dark=True)
    assert getattr(dialog, "_csd_titlebar", None) is not None
    assert dialog._csd_titlebar._is_dark is True

    # Switch to Light
    apply_titlebar_theme("Light", window=main_win)
    assert main_win._csd_titlebar._is_dark is False
    assert dialog._csd_titlebar._is_dark is False

    # Switch back to Dark
    apply_titlebar_theme("Dark", window=main_win)
    assert main_win._csd_titlebar._is_dark is True
    assert dialog._csd_titlebar._is_dark is True

