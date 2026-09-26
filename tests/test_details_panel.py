"""
Unit tests for Bottom Details Panel and Toggle Button components.
"""

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.components.details_panel import (
    DetailsPanel,
    DetailsToggleButton,
    SegmentGridWidget,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_segment_grid_widget_fallback(qapp):
    widget = SegmentGridWidget()
    # Test 0%
    widget.set_fallback_progress(0.0, num_segments=8, is_complete=False)
    assert len(widget._segments) == 8
    assert all(s["percent"] == 0.0 for s in widget._segments)

    # Test 100%
    widget.set_fallback_progress(100.0, num_segments=8, is_complete=True)
    assert len(widget._segments) == 8
    assert all(s["percent"] == 100.0 for s in widget._segments)

    # Test partial
    widget.set_fallback_progress(25.0, num_segments=8, is_complete=False)
    assert len(widget._segments) == 8
    total_pct = sum(s["percent"] for s in widget._segments)
    assert abs(total_pct - 200.0) < 0.1  # 25% of 8 * 100 = 200


def test_details_toggle_button(qapp):
    btn = DetailsToggleButton()
    assert btn.lbl_arrow.text() == "▲"
    assert not btn.is_open()

    btn.set_open(True)
    assert btn.lbl_arrow.text() == "▼"
    assert btn.is_open()

    btn.set_open(False)
    assert btn.lbl_arrow.text() == "▲"
    assert not btn.is_open()

    # Filename setting and eliding
    btn.set_filename("ubuntu-26.04.1-desktop-amd64.iso")
    assert "ubuntu" in btn.lbl_name.text()


def test_details_panel_tabs(qapp):
    panel = DetailsPanel()
    assert panel.stacked_widget.count() == 3
    assert len(panel.tab_buttons) == 3

    # Switch tabs
    panel.switch_tab(1)
    assert panel.stacked_widget.currentIndex() == 1
    assert panel.tab_buttons[1].isChecked()

    panel.switch_tab(2)
    assert panel.stacked_widget.currentIndex() == 2
    assert panel.tab_buttons[2].isChecked()

    panel.switch_tab(0)
    assert panel.stacked_widget.currentIndex() == 0
    assert panel.tab_buttons[0].isChecked()


def test_details_panel_data_population(qapp):
    panel = DetailsPanel()

    test_data = {
        "filename": "test-file.iso",
        "url": "https://releases.ubuntu.com/26.04/test-file.iso",
        "filepath": "/home/user/Downloads/test-file.iso",
        "total_bytes": 1024 * 1024 * 100,  # 100 MB
        "downloaded_bytes": 1024 * 1024 * 50,  # 50 MB
        "status": "Downloading",
        "percent": 50.0,
        "speed": "5.50 MB/s",
        "time_left": "10s",
        "date_added": "9:21 PM",
        "num_connections": 8,
    }

    panel.set_download_data(test_data)

    # General Tab checks
    assert panel.gen_filename_label.text() == "test-file.iso"
    assert "50%" in panel.gen_status_label.text()
    assert "50.00 MB" in panel.gen_size_label.text()
    assert panel.gen_url_label.text() == "https://releases.ubuntu.com/26.04/test-file.iso"
    assert "/home/user/Downloads" in panel.gen_folder_btn.text()

    # Progress Tab checks
    assert panel.prog_percent_label.text() == "50.00%"
    assert panel.prog_speed_label.text() == "5.50 MB/s"
    assert "ETA 10s" in panel.prog_eta_label.text()
    assert "8" in panel.prog_segments_stat.text()

    # Connections Tab checks
    assert panel.conn_table.rowCount() == 1
    assert panel.conn_table.item(0, 0).text() == "releases.ubuntu.com"
    assert panel.conn_table.item(0, 1).text() == "443"
    assert panel.conn_table.item(0, 3).text() in ["Direct", "HTTP", "SOCKS5"]


def test_main_window_details_integration(qapp, monkeypatch):
    from ui.main_window import MainWindow
    win = MainWindow(start_ipc=False)
    win.show()

    # 1. Verify layout containment: details_panel is in table_details_splitter and NOT in left pane
    assert hasattr(win, "details_panel")
    assert hasattr(win, "table_details_splitter")
    assert win.table_details_splitter.indexOf(win.download_table) != -1
    assert win.table_details_splitter.indexOf(win.details_panel) != -1
    assert win.splitter.indexOf(win.left_panel_container) != -1
    assert win.splitter.indexOf(win.table_details_splitter) != -1

    # Initially details panel is hidden and arrow is ▲
    assert not win.details_panel.isVisible()
    assert win.btn_details_toggle.lbl_arrow.text() == "▲"

    # 2. Toggle open
    win.toggle_details_panel()
    assert win.details_panel.isVisible()
    assert win.btn_details_toggle.lbl_arrow.text() == "▼"

    # 3. Close via panel's close button (✕)
    win.details_panel.btn_close.click()
    assert not win.details_panel.isVisible()
    assert win.btn_details_toggle.lbl_arrow.text() == "▲"

    # 4. Toggle open again
    win.toggle_details_panel()
    assert win.details_panel.isVisible()
    assert win.btn_details_toggle.lbl_arrow.text() == "▼"

    # 5. Toggle closed via toggle button
    win.toggle_details_panel()
    assert not win.details_panel.isVisible()
    assert win.btn_details_toggle.lbl_arrow.text() == "▲"

    win.close()

