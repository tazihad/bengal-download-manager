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

    # Filename tooltip setting
    btn.set_filename("ubuntu-26.04.1-desktop-amd64.iso")
    assert "ubuntu" in btn.toolTip()


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
    assert panel.gen_icon_label.pixmap() is not None
    assert not panel.gen_icon_label.pixmap().isNull()

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

    # 6. Test live row update updates details panel
    win.toggle_details_panel()
    assert win.details_panel.isVisible()

    # Add a mock row
    from PyQt6.QtWidgets import QTableWidgetItem
    win.download_table.setRowCount(0)
    win.download_table.insertRow(0)
    item_ref = QTableWidgetItem("test.iso")
    item_ref.setData(Qt.ItemDataRole.UserRole, "https://example.com/test.iso")
    item_ref.setData(Qt.ItemDataRole.UserRole + 1, "/tmp/test.iso")
    win.download_table.setItem(0, 0, item_ref)
    win._set_sortable_item(0, 1, "1000.00 KB", lambda x: 1000000)
    win._set_status_text(0, "Downloading...")
    win._set_sortable_item(0, 3, "1m", lambda x: 60)
    win._set_sortable_item(0, 4, "500 KB/s", lambda x: 500000)

    # Simulate progress update data: [filename, size, status, time_left, rate, comp_bytes, tot_bytes, raw_speed]
    data = ["test.iso", "1000.00 KB", "Downloading...", "1m", "500 KB/s", 500000, 1000000, 500000]
    win._apply_download_row_data(item_ref, data)

    # Verify details panel updated with live downloaded bytes and active segments
    assert "488.28 KB" in win.details_panel.gen_size_label.text()
    assert "488.28 KB" in win.details_panel.prog_bytes_label.text()
    assert "50.00%" in win.details_panel.prog_percent_label.text()
    assert "Active: 8" in win.details_panel.prog_active_stat.text()

    win.close()


def test_details_panel_persistence(qapp, monkeypatch, tmp_path):
    """Test that closing and reopening the app remembers the panel's open/closed state, active tab, and sizes."""
    config_dir = str(tmp_path / "bengal_config")
    import os
    os.makedirs(config_dir, exist_ok=True)

    monkeypatch.setattr("core.utils.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("ui.main_window.get_config_dir", lambda: config_dir)

    from ui.main_window import MainWindow

    # 1. Open app, panel starts closed by default
    win1 = MainWindow(start_ipc=False)
    win1.show()
    assert not win1.details_panel.isVisible()

    # 2. User opens details panel, switches to Progress tab (index 1)
    win1.show_details_panel()
    win1.details_panel.switch_tab(1)
    assert win1.details_panel.isVisible()
    assert win1.details_panel.stacked_widget.currentIndex() == 1

    # Save settings and close app
    win1.save_settings()
    win1.close()

    # 3. Reopen app: panel must restore to open state and Progress tab
    win2 = MainWindow(start_ipc=False)
    win2.show()
    assert win2.details_panel.isVisible()
    assert win2.btn_details_toggle.lbl_arrow.text() == "▼"
    assert win2.details_panel.stacked_widget.currentIndex() == 1

    # 4. User closes details panel
    win2.hide_details_panel()
    assert not win2.details_panel.isVisible()
    win2.save_settings()
    win2.close()

    # 5. Reopen app: panel must restore to closed state
    win3 = MainWindow(start_ipc=False)
    win3.show()
    assert not win3.details_panel.isVisible()
    assert win3.btn_details_toggle.lbl_arrow.text() == "▲"
    win3.close()


def test_details_panel_accent_color_adaptation(qapp):
    """Test that details panel indicators and block visualizer derive colors from accent/palette."""
    from PyQt6.QtGui import QPalette, QColor

    panel = DetailsPanel()
    # Check legend widgets exist
    assert hasattr(panel, "legend_sq_downloaded")
    assert hasattr(panel, "legend_sq_active")
    assert hasattr(panel, "legend_sq_failed")

    # Set custom palette highlight (e.g. emerald green)
    pal = panel.palette()
    pal.setColor(QPalette.ColorRole.Highlight, QColor(16, 185, 129))
    pal.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    panel.setPalette(pal)
    panel.update_palette_colors()

    # The active indicator stylesheet should be updated with derived active color
    active_style = panel.legend_sq_active.styleSheet()
    assert "background-color:" in active_style
    # Ensure arrow icon uses palette highlight
    toggle_btn = DetailsToggleButton()
    assert "palette(highlight)" in toggle_btn.lbl_arrow.styleSheet()


def test_selected_item_and_proxy_tab_restoration_on_startup(qapp, monkeypatch, tmp_path):
    """Test that the last session's selected item, details panel open state, and Connections/Proxy tab (tab 2) are restored on startup."""
    config_dir = str(tmp_path / "bengal_config")
    import os
    os.makedirs(config_dir, exist_ok=True)

    monkeypatch.setattr("core.utils.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("ui.main_window.get_config_dir", lambda: config_dir)

    # Mock downloads list
    mock_downloads = [
        {"filename": "archlinux-2026.iso", "url": "https://arch.org/archlinux-2026.iso", "path": "/downloads/archlinux-2026.iso", "size": "1.2 GB", "status": "Complete"},
        {"filename": "debian-13.iso", "url": "https://debian.org/debian-13.iso", "path": "/downloads/debian-13.iso", "size": "650 MB", "status": "Downloading", "rate": "3 MB/s"},
        {"filename": "fedora-42.iso", "url": "https://fedora.org/fedora-42.iso", "path": "/downloads/fedora-42.iso", "size": "2.1 GB", "status": "Paused"}
    ]
    monkeypatch.setattr("ui.main_window.get_all_downloads", lambda: mock_downloads)
    monkeypatch.setattr("core.download_store.DownloadStore.load_from_database", lambda self: mock_downloads)

    from ui.main_window import MainWindow

    # Session 1: Start app, select item 1 (debian-13.iso), open details panel, switch to Connections tab (index 2)
    win1 = MainWindow(start_ipc=False)
    win1.show()

    assert win1.download_table.rowCount() == 3
    # Select row 1
    win1.download_table.selectRow(1)
    win1.download_table.setCurrentCell(1, 0)
    win1.show_details_panel()
    win1.details_panel.switch_tab(2)  # Connections / Proxy tab

    assert win1.details_panel.stacked_widget.currentIndex() == 2
    assert win1.btn_details_toggle.lbl_arrow.text() == "▼"
    assert "debian-13.iso" in win1.btn_details_toggle.toolTip()

    # Save settings and close
    win1.save_settings()
    win1.close()

    # Session 2: Start app afresh
    win2 = MainWindow(start_ipc=False)
    win2.show()

    # Verify:
    # 1. Row 1 (debian-13.iso) is selected
    assert win2.download_table.currentRow() == 1
    selected_items = win2.download_table.selectedItems()
    assert len(selected_items) > 0
    assert win2.download_table.item(1, 0).text() == "debian-13.iso"

    # 2. Toggle button shows open arrow ▼ and tooltip for selected item
    assert win2.btn_details_toggle.lbl_arrow.text() == "▼"
    assert "debian-13.iso" in win2.btn_details_toggle.toolTip()

    # 3. Details panel is visible
    assert win2.details_panel.isVisible()

    # 4. Connections / Proxy tab (index 2) is restored
    assert win2.details_panel.stacked_widget.currentIndex() == 2

    # 5. Connections table is populated with host and proxy info
    assert win2.details_panel.conn_table.rowCount() >= 1
    assert win2.details_panel.conn_table.item(0, 0).text() == "debian.org"
    assert win2.details_panel.conn_table.item(0, 3).text() in ["Direct", "HTTP", "SOCKS5"]

    win2.close()


def test_eliding_widgets_and_long_filename(qapp):
    """Verify ElidingLabel and ElidingButton truncate text without expanding minimum size."""
    from ui.components.details_panel import ElidingLabel, ElidingButton, DetailsPanel
    from core.utils import wrap_url_tooltip
    from PyQt6.QtWidgets import QSizePolicy

    long_title = "A" * 300 + ".mp4"
    lbl = ElidingLabel(long_title)
    lbl.resize(200, 30)

    assert lbl.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert lbl.minimumWidth() == 0
    assert lbl.toolTip() == wrap_url_tooltip(long_title)

    # Button
    btn = ElidingButton("/very/long/path/" + "B" * 200)
    btn.resize(200, 30)
    assert btn.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert btn.minimumWidth() == 0
    assert btn.toolTip() == wrap_url_tooltip("/very/long/path/" + "B" * 200)

    # Panel with long filename
    panel = DetailsPanel()
    panel.resize(400, 220)
    panel.set_download_data({
        "filename": long_title,
        "filepath": "/home/user/Downloads/" + long_title,
        "url": "https://example.com/" + "C" * 200,
        "total_bytes": 1000000,
        "downloaded_bytes": 500000,
        "status": "Downloading",
        "percent": 50.0
    })

    # The panel should not force an enormous minimum width
    assert panel.minimumWidth() == 0
    assert panel.gen_filename_label.text() != ""
    assert panel.gen_filename_label.toolTip() == wrap_url_tooltip(long_title)
    assert panel.gen_url_label.toolTip() == wrap_url_tooltip("https://example.com/" + "C" * 200)


def test_eliding_label_copy_without_truncation(qapp):
    """Verify selecting all and copying on ElidingLabel copies full untruncated text to clipboard."""
    from ui.components.details_panel import ElidingLabel
    from PyQt6.QtGui import QKeyEvent, QKeySequence
    from PyQt6.QtCore import QEvent, Qt

    full_url = "https://downloads.example.org/releases/v2.5.0/very_long_distribution_package_archive_name_x86_64.tar.gz?auth=token123456789&session=active"
    lbl = ElidingLabel(full_url)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
    lbl.resize(250, 30)

    # 1. Verify text displayed is elided / shorter than full text
    assert lbl.text() == full_url  # internal text() returns fullText
    assert super(ElidingLabel, lbl).text() != full_url
    assert "…" in super(ElidingLabel, lbl).text() or "..." in super(ElidingLabel, lbl).text() or len(super(ElidingLabel, lbl).text()) < len(full_url)

    # 2. Verify tooltip is wrapped with wrap_url_tooltip
    assert "\n" in lbl.toolTip()
    for line in lbl.toolTip().splitlines():
        assert len(line) <= 80

    # 3. Simulate Select All (Ctrl+A)
    event_ctrl_a = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    lbl.keyPressEvent(event_ctrl_a)
    assert lbl.hasSelectedText()

    # 4. Simulate Copy (Ctrl+C)
    event_ctrl_c = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    lbl.keyPressEvent(event_ctrl_c)

    clipboard = QApplication.clipboard()
    assert clipboard.text() == full_url

    # 5. Direct copy_selection when all visible text is selected
    lbl.setSelection(0, len(super(ElidingLabel, lbl).text()))
    lbl.copy_selection()
    assert clipboard.text() == full_url

    # 6. copy_selection when nothing is selected does not overwrite clipboard
    clipboard.setText("sentinel")
    lbl.setSelection(0, 0)
    assert not lbl.hasSelectedText()
    lbl.copy_selection()
    assert clipboard.text() == "sentinel"

    # 7. copy_full_text explicitly copies full URL
    lbl.copy_full_text()
    assert clipboard.text() == full_url

    # 8. Test select_all method
    lbl.select_all()
    assert lbl.hasSelectedText()
    assert lbl.selectedText() == super(ElidingLabel, lbl).text()


def test_details_panel_thumbnail_update(qapp, tmp_path):
    """Verify DetailsPanel updates thumbnail preview when thumbnail_ready is fired."""
    from ui.components.details_panel import DetailsPanel
    from core.video_thumbnail import VideoThumbnailManager, register_thumbnail_file
    from PyQt6.QtGui import QImage

    # Create dummy video and thumbnail
    video_path = str(tmp_path / "test_movie.mp4")
    thumb_path = str(tmp_path / "thumb.jpg")
    img = QImage(160, 90, QImage.Format.Format_RGB32)
    img.fill(0xFF00FF)
    img.save(thumb_path, "JPEG")

    register_thumbnail_file(video_path, thumb_path)

    panel = DetailsPanel()
    panel.set_download_data({
        "filename": "test_movie.mp4",
        "filepath": video_path,
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "total_bytes": 5000000,
        "downloaded_bytes": 5000000,
        "status": "Complete",
        "percent": 100.0
    })

    # Trigger thumbnail_ready signal
    VideoThumbnailManager.instance().thumbnail_ready.emit(video_path, thumb_path)

    # gen_icon_label should have a non-null pixmap
    pm = panel.gen_icon_label.pixmap()
    assert pm is not None
    assert not pm.isNull()


def test_eta_and_speed_formatting_and_alignment(qapp):
    """Verify ETA and speed formatting and label alignments."""
    from ui.components.details_panel import (
        format_eta_string,
        format_speed_string,
        DetailsPanel,
    )
    from PyQt6.QtCore import Qt

    # Test format_eta_string
    assert format_eta_string("0") == "ETA --"
    assert format_eta_string("0s") == "ETA --"
    assert format_eta_string("--") == "ETA --"
    assert format_eta_string("") == "ETA --"
    assert format_eta_string(None) == "ETA --"
    assert format_eta_string("10s", is_complete=True) == "ETA --"
    assert format_eta_string("1 hour") == "ETA 1 hour"
    assert format_eta_string("59 mints") == "ETA 59 mints"
    assert format_eta_string("ETA 59 mints") == "ETA 59 mints"
    assert format_eta_string("active") == "ETA active"

    # Test format_speed_string
    assert format_speed_string("0 B/s") == "0 B/s"
    assert format_speed_string("") == "0 B/s"
    assert format_speed_string("--") == "0 B/s"
    assert format_speed_string(None) == "0 B/s"
    assert format_speed_string("12.5 MB/s") == "12.5 MB/s"

    # Test panel label alignments and widths
    panel = DetailsPanel()
    assert panel.prog_speed_label.alignment() & Qt.AlignmentFlag.AlignRight
    assert panel.prog_eta_label.alignment() & Qt.AlignmentFlag.AlignLeft
    assert panel.prog_speed_label.width() > 0 or panel.prog_speed_label.maximumWidth() == 100
    assert panel.prog_eta_label.width() > 0 or panel.prog_eta_label.maximumWidth() == 140


def test_details_panel_worker_progress_updates_segments_stat(qapp):
    """Verify that _on_worker_progress updates segment and active stats without NameError."""
    panel = DetailsPanel()
    panel.show()
    panel.set_download_data({
        "filename": "test_video.mp4",
        "url": "https://example.com/test_video.mp4",
        "num_connections": 8,
        "status": "Receiving data..."
    })

    # data tuple: (filename, size_str, status_str, time_left, speed_str, dl_bytes, total_bytes, raw_speed, generation)
    progress_data = ("test_video.mp4", "100.00 MB", "Receiving data...", "10 sec", "5.00 MB/s", 50 * 1024 * 1024, 100 * 1024 * 1024, 5 * 1024 * 1024, 1)
    panel._on_worker_progress(0, progress_data)

    assert "Segments:" in panel.prog_segments_stat.text()
    assert "Active:" in panel.prog_active_stat.text()
    assert panel.prog_active_stat.text() == "Active: 8"
    assert panel.prog_segments_stat.text() == "Segments: 4 / 8"
    panel.close()


