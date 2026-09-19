"""
Core UI and Integration Tests for Bengal Download Manager MainWindow and Dialogs.
"""

import time
import pytest
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
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
    win.process_incoming_url("https://www.youtube.com/watch?v=YE7VzlLtp-4|Mozilla/5.0|cookie1=val")
    assert called_url == "https://www.youtube.com/watch?v=YE7VzlLtp-4"
    assert called_preset is not None

    # 2. Vimeo URL
    called_url = None
    win.process_incoming_url("https://vimeo.com/34321188||")
    assert called_url == "https://vimeo.com/34321188"

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


def test_options_dialog_ipc_port_persistence(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 8, "ipc_port": 56900})

    dlg = OptionsDialog()
    assert hasattr(dlg, "spin_ipc_port")
    assert dlg.spin_ipc_port.minimum() == 1024
    assert dlg.spin_ipc_port.maximum() == 65535
    assert dlg.spin_ipc_port.value() == 56900
    assert "56900" in dlg.spin_ipc_port.toolTip()
    assert "IPC" in dlg.spin_ipc_port.toolTip()

    # Change to 56905 and save
    dlg.spin_ipc_port.setValue(56905)
    dlg.save_and_accept()

    loaded = load_extension_config()
    assert loaded["ipc_port"] == 56905

    # Reopen dialog and verify 56905 is displayed
    dlg2 = OptionsDialog()
    assert dlg2.spin_ipc_port.value() == 56905
    dlg2.reject()


def test_main_window_data_usage_widget(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    assert hasattr(win, "left_panel_container")
    assert hasattr(win, "data_usage_widget")
    assert win.data_usage_widget is not None

    # Verify initial stats
    widget = win.data_usage_widget
    assert hasattr(widget, "lbl_downloaded_val")
    assert hasattr(widget, "lbl_files_val")
    assert hasattr(widget, "lbl_active_val")
    assert hasattr(widget, "lbl_speed_val")
    assert hasattr(widget, "storage_progress")

    # Refresh stats
    widget.refresh_stats(win)
    assert int(widget.lbl_files_val.text()) >= 0
    assert int(widget.lbl_files_val.text()) <= win.download_table.rowCount()
    assert widget.lbl_active_val.text() == "0"
    assert widget.storage_progress.minimum() == 0
    assert widget.storage_progress.maximum() == 100

    # Test real-time live speed synchronization with download status updates
    assert widget.lbl_speed_val.text() == "0 B/s"
    win.active_speeds["test_dl"] = 3.5 * 1024 * 1024
    win.active_downloads["test_dl"] = True
    win.update_status_bar_speed()
    assert "3.50 MB/s" in widget.lbl_speed_val.text() or "3.5 MB/s" in widget.lbl_speed_val.text()
    assert widget.lbl_active_val.text() == "1"

    win.active_speeds.pop("test_dl")
    win.active_downloads.pop("test_dl")
    win.update_status_bar_speed()
    assert widget.lbl_speed_val.text() == "0 B/s"
    assert widget.lbl_active_val.text() == "0"

    # Test toggling data usage summary via View menu action
    assert hasattr(win, "action_data_usage_toggle")
    assert not win.action_data_usage_toggle.isChecked()
    assert win.data_usage_widget.isHidden()
    win.toggle_data_usage(True, save=False)
    assert not win.data_usage_widget.isHidden()
    assert win.action_data_usage_toggle.isChecked()
    win.toggle_data_usage(False, save=False)
    assert win.data_usage_widget.isHidden()
    assert not win.action_data_usage_toggle.isChecked()

    # Test DataUsageDialog instantiation
    from ui.dialogs import DataUsageDialog
    dlg = DataUsageDialog(parent=win)
    assert dlg is not None
    dlg.close()

    # Test hiding left panel
    win.toggle_hide_categories(True, save=False)
    assert win.left_panel_container.isHidden()
    win.toggle_hide_categories(False, save=False)
    assert not win.left_panel_container.isHidden()

    win.close()


def test_clear_completed_preserves_data_usage(qapp):
    """Verify that clicking Clear Completed retains today's data in the widget and graph dialog."""
    import time
    from datetime import datetime
    from PyQt6.QtWidgets import QTableWidgetItem
    from core.database import get_month_daily_usage

    win = MainWindow(start_ipc=False)
    win.hide()

    today_ts = str(time.time())
    today_str = datetime.now().strftime("%Y-%m-%d")

    win.download_table.setRowCount(1)
    item_0 = QTableWidgetItem("test_download.iso")
    item_0.setData(Qt.ItemDataRole.UserRole, "http://example.com/test_download.iso")
    item_0.setData(Qt.ItemDataRole.UserRole + 1, "/tmp/test_download.iso")
    item_0.setData(Qt.ItemDataRole.UserRole + 2, today_ts)
    item_0.setData(Qt.ItemDataRole.UserRole + 3, today_ts)
    item_0.setData(Qt.ItemDataRole.UserRole + 11, "Complete")
    win.download_table.setItem(0, 0, item_0)

    item_1 = QTableWidgetItem("10.00 MB")
    win.download_table.setItem(0, 1, item_1)

    item_2 = QTableWidgetItem("Complete")
    item_2.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
    win.download_table.setItem(0, 2, item_2)

    # Refresh stats before clear
    win.data_usage_widget.refresh_stats(win)
    val_before = win.data_usage_widget.lbl_downloaded_val.text()
    files_before = win.data_usage_widget.lbl_files_val.text()
    assert int(files_before) >= 1

    # Clear completed downloads
    win.clear_finished_downloads()
    assert win.download_table.rowCount() == 0

    # Refresh stats after clear
    win.data_usage_widget.refresh_stats(win)
    assert win.data_usage_widget.lbl_downloaded_val.text() == val_before
    assert win.data_usage_widget.lbl_files_val.text() == files_before

    # Verify dialog graph data also preserves today's usage
    from ui.dialogs import DataUsageDialog
    dlg = DataUsageDialog(parent=win)
    assert dlg.lbl_month_total.text() != "0 B"
    assert "Today: 0 B" not in dlg.lbl_today_badge.text()
    dlg.close()

    win.close()


def test_deleted_table_item_does_not_crash_handlers(qapp):
    """Verify that late signals and helper methods never crash with RuntimeError when an item is deleted."""
    from PyQt6.QtWidgets import QTableWidgetItem

    win = MainWindow(start_ipc=False)
    win.hide()

    win.download_table.setRowCount(1)
    item_0 = QTableWidgetItem("file_to_delete.bin")
    item_0.setData(Qt.ItemDataRole.UserRole, "http://example.com/file_to_delete.bin")
    win.download_table.setItem(0, 0, item_0)
    item_1 = QTableWidgetItem("10 MB")
    win.download_table.setItem(0, 1, item_1)
    item_2 = QTableWidgetItem("Downloading")
    win.download_table.setItem(0, 2, item_2)

    assert win._is_item_valid(item_0) is True
    key = win._get_item_key(item_0)
    assert key is not None

    # Delete the row, which frees the underlying C++ QTableWidgetItem
    win.download_table.removeRow(0)

    # Now item_0 wrapper points to a deleted C++ object
    assert win._is_item_valid(item_0) is False
    assert win._get_item_key(item_0) is None

    # Simulate late worker signals arriving after deletion
    mock_data = ("file_to_delete.bin", "10 MB", "Downloading", "00:01", "1 MB/s", 5000000, 10000000, 1000000, 1)
    win.update_download_row(item_0, mock_data)
    win.download_finished(item_0, "Complete")
    win.download_finished(item_0, "Cancelled")
    win._apply_download_row_data(item_0, mock_data)
    win._on_media_download_finished(key, item_0, "/tmp/file_to_delete.bin")

    win.close()


def test_view_sort_by_checkmarks_and_status_bar_child_items(qapp):
    """Test visible checkmarks in 'Sort by' and child items in 'Status Bar' submenu."""
    win = MainWindow(start_ipc=False)
    win.hide()

    # 1. Test Sort by Menu Checkmarks
    assert hasattr(win, "sort_action_group")
    assert win.sort_action_group.isExclusive() is True
    assert hasattr(win, "sort_actions")
    assert len(win.sort_actions) == 7

    # Initial checkmark should be on a valid column
    checked_action = win.sort_action_group.checkedAction()
    assert checked_action is not None
    assert checked_action.isCheckable() is True
    assert checked_action.isChecked() is True

    # Switching sort via menu action triggers table sort and updates checkmark
    size_action = win.sort_actions[1]
    assert size_action.text() in ("Size", win.tr("Size"))
    size_action.trigger()
    assert win.sort_actions[1].isChecked() is True
    assert win.download_table.horizontalHeader().sortIndicatorSection() == 1

    # Sorting via table header click updates the menu checkmark
    win.download_table.horizontalHeader().sortIndicatorChanged.emit(4, Qt.SortOrder.AscendingOrder)
    assert win.sort_actions[4].isChecked() is True
    assert win.sort_actions[1].isChecked() is False

    # 2. Test Status Bar Submenu and Child Items
    assert hasattr(win, "status_bar_menu")
    assert hasattr(win, "action_status_bar_toggle")
    assert hasattr(win, "action_sb_memory")
    assert hasattr(win, "action_sb_aria2")
    assert hasattr(win, "action_sb_ipc")
    assert hasattr(win, "action_sb_speed")
    assert hasattr(win, "action_sb_public_ip")

    # Verify Hide left panel action
    assert hasattr(win, "action_hide_categories")
    assert "Hide left panel" in win.action_hide_categories.text()

    # Verify all child actions are checkable
    for act in [win.action_sb_memory, win.action_sb_aria2, win.action_sb_ipc, win.action_sb_speed, win.action_sb_public_ip]:
        assert act.isCheckable() is True

    # Verify initial defaults on clean config: only Memory is checked, rest are unchecked
    assert win.action_sb_memory.isChecked() is True
    assert win.action_sb_aria2.isChecked() is False
    assert win.action_sb_ipc.isChecked() is False
    assert win.action_sb_speed.isChecked() is False
    assert win.action_sb_public_ip.isChecked() is False

    # Verify initial widget visibility: only Memory is visible
    assert win.status_memory_label.isHidden() is False
    assert win.status_aria2_label.isHidden() is True
    assert win.status_ipc_label.isHidden() is True
    assert win.status_speed_label.isHidden() is True
    assert win.status_public_ip_label.isHidden() is True

    # Test toggling Memory
    win.action_sb_memory.setChecked(False)
    win._on_status_bar_child_toggled()
    assert win.status_memory_label.isHidden() is True
    win.action_sb_memory.setChecked(True)
    win._on_status_bar_child_toggled()
    assert win.status_memory_label.isHidden() is False

    # Test toggling Speed
    win.action_sb_speed.setChecked(True)
    win._on_status_bar_child_toggled()
    assert win.status_speed_label.isHidden() is False
    win.active_speeds["test_job"] = 1024 * 1024
    win.update_status_bar_speed()
    assert "Speed:" in win.status_speed_label.text()
    win.action_sb_speed.setChecked(False)
    win._on_status_bar_child_toggled()
    assert win.status_speed_label.isHidden() is True

    # Test toggling IPC Status
    win.action_sb_ipc.setChecked(True)
    win._on_status_bar_child_toggled()
    assert win.status_ipc_label.isHidden() is False
    win.update_status_bar_ipc()
    assert "IPC:" in win.status_ipc_label.text()

    # Test Public IP
    win.action_sb_public_ip.setChecked(True)
    win._on_status_bar_child_toggled()
    assert win.status_public_ip_label.isHidden() is False
    win._on_public_ip_fetched("203.0.113.195")
    assert "203.0.113.195" in win.status_public_ip_label.text()

    # Test settings persistence
    win.save_settings()
    saved_settings = win.load_settings()
    assert "status_bar_items" in saved_settings
    assert saved_settings["status_bar_items"]["memory"] is True
    assert saved_settings["status_bar_items"]["aria2"] is False
    assert saved_settings["status_bar_items"]["ipc"] is True
    assert saved_settings["status_bar_items"]["speed"] is False
    assert saved_settings["status_bar_items"]["public_ip"] is True

    win.is_quitting = True
    win.close()


def test_options_appearance_comboboxes_scrollable(qapp):
    """Verify that theme, accent, and icon dropdowns have maxVisibleItems constrained and scrollbar enabled."""
    dlg = OptionsDialog()
    assert hasattr(dlg, "combo_theme")
    assert hasattr(dlg, "combo_accent")
    assert hasattr(dlg, "combo_icon_theme")
    assert hasattr(dlg, "combo_titlebar")

    for combo in (dlg.combo_theme, dlg.combo_accent, dlg.combo_icon_theme, dlg.combo_tray_icon, dlg.combo_titlebar):
        assert combo.maxVisibleItems() == 10
        assert "combobox-popup: 0" in combo.styleSheet()
        view = combo.view()
        assert view is not None
        assert view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    dlg.reject()


def test_stellar_theme_accent_and_icons(qapp):
    """Verify Stellar Dark and Light themes, Stellar Blue accent, and Stellar icon theme."""
    from core.services.theme_service import (
        apply_app_theme, is_dark_theme, get_themed_icon,
        normalize_theme_name, normalize_accent_name, normalize_icon_theme_name
    )
    from PyQt6.QtGui import QPalette

    # Verify options in dialog
    dlg = OptionsDialog()
    assert dlg.combo_theme.findText("Stellar Dark") != -1
    assert dlg.combo_theme.findText("Stellar Light") != -1
    assert dlg.combo_accent.findText("Stellar Blue") != -1
    assert dlg.combo_icon_theme.findText("Stellar") != -1
    dlg.reject()

    # Normalization
    assert normalize_theme_name("Stellar Dark") == "Stellar Dark"
    assert normalize_theme_name("stellardark") == "Stellar Dark"
    assert normalize_theme_name("Stellar Light") == "Stellar Light"
    assert normalize_theme_name("stellarlight") == "Stellar Light"
    assert normalize_accent_name("stellar") == "Stellar Blue"
    assert normalize_accent_name("Stellar Blue") == "Stellar Blue"
    assert normalize_icon_theme_name("Stellar") == "Stellar"
    assert normalize_icon_theme_name("stellar icons") == "Stellar"

    # Stellar Dark
    apply_app_theme("Stellar Dark", accent_name="Stellar Blue", icon_theme_name="Stellar")
    assert is_dark_theme() is True
    pal_dark = qapp.palette()
    assert pal_dark.color(QPalette.ColorRole.Window).name().lower() == "#1c1c1c"
    assert pal_dark.color(QPalette.ColorRole.Highlight).name().lower() == "#4488dd"

    # Icons
    for name in ["add_url", "resume", "stop", "stop_all", "delete", "clear_completed", "options", "scheduler", "grabber", "all_downloads", "compressed", "documents", "music", "programs", "video"]:
        ic = get_themed_icon(name)
        assert not ic.isNull(), f"Icon {name} is null!"
        pm = ic.pixmap(24, 24)
        assert not pm.isNull(), f"Pixmap for {name} is null!"

    # Stellar Light
    apply_app_theme("Stellar Light", accent_name="Stellar Blue", icon_theme_name="Stellar")
    assert is_dark_theme() is False
    pal_light = qapp.palette()
    assert pal_light.color(QPalette.ColorRole.Window).name().lower() == "#f0f0f0"

    # Revert to default
    apply_app_theme("BDM Dark (Default)", accent_name="BDM (Default)", icon_theme_name="BDM Auto (Default)")


def test_menu_outer_accent_border_and_clean_menubar(qapp):
    """Verify that popup menus (QMenu) have a 1px accent border enclosing options, and menubar is clean."""
    from core.services.theme_service import apply_app_theme
    from PyQt6.QtWidgets import QMainWindow

    apply_app_theme("BDM Dark (Default)", accent_name="BDM (Default)")
    app_sheet = qapp.styleSheet()

    # Outer border of QMenu options must be 1px solid palette(highlight)
    assert "border: 1px solid palette(highlight)" in app_sheet
    assert "QMenu {" in app_sheet

    # Menubar itself should not have a bottom border
    assert "border-bottom: 1px solid palette(highlight)" not in app_sheet

    # Menubar should have no overriding border-bottom stylesheet
    win = QMainWindow()
    mb = win.menuBar()
    assert "border-bottom" not in (mb.styleSheet() or "")
    win.close()


def test_theme_defaults_and_window_perimeter_borders(qapp):
    """Verify BDM Auto is the default theme and window/dialog perimeter borders are applied."""
    from core.services.theme_service import normalize_theme_name, apply_app_theme
    
    assert normalize_theme_name(None) == "BDM Auto (Default)"
    assert normalize_theme_name("") == "BDM Auto (Default)"
    assert normalize_theme_name("auto") == "BDM Auto (Default)"
    assert normalize_theme_name("BDM Auto") == "BDM Auto (Default)"
    assert normalize_theme_name("BDM Dark (Default)") == "BDM Dark"
    assert normalize_theme_name("dark") == "BDM Dark"

    apply_app_theme("BDM Auto (Default)")
    app_sheet = qapp.styleSheet()
    assert "QMainWindow#MainWindow {" in app_sheet
    assert "border: 1px solid palette(mid);" in app_sheet
    assert "QDialog {" in app_sheet


def test_dynamic_system_theme_change_listener(qapp, monkeypatch):
    """Verify is_system_dark_theme works and on_system_theme_changed dynamically updates BDM Auto."""
    from core.services.theme_service import is_system_dark_theme, is_dark_theme, apply_app_theme
    
    # Verify is_system_dark_theme returns a bool
    sys_dark = is_system_dark_theme(qapp)
    assert isinstance(sys_dark, bool)

    win = MainWindow(start_ipc=False)
    win.settings = {"theme": "BDM Auto (Default)"}

    # Simulate portal setting change signal
    called = []
    monkeypatch.setattr(win, "apply_theme_setting", lambda t: called.append(t))
    win._on_portal_setting_changed("org.freedesktop.appearance", "color-scheme", None)
    assert called == ["BDM Auto (Default)"]

    # Verify other namespaces/keys are ignored
    called.clear()
    win._on_portal_setting_changed("org.gnome.desktop.interface", "font-name", None)
    assert called == []

    win.close()




def test_clean_config_view_menu_and_status_bar_defaults(qapp, monkeypatch, tmp_path):
    """Verify that on clean install/config, Data usage summary is unchecked,
    Hide left panel is renamed, and only Memory in status bar is checked while the rest are unchecked."""
    monkeypatch.setattr("ui.main_window.get_config_dir", lambda: str(tmp_path))
    win = MainWindow(start_ipc=False)

    # 1. View -> Data usage summary should be unchecked and widget hidden
    assert hasattr(win, "action_data_usage_toggle")
    assert win.action_data_usage_toggle.isChecked() is False
    assert hasattr(win, "data_usage_widget")
    assert win.data_usage_widget.isHidden() is True

    # 2. View -> "Hide categories" renamed to "Hide left panel"
    assert hasattr(win, "action_hide_categories")
    assert "Hide left panel" in win.action_hide_categories.text()
    assert win.action_hide_categories.isChecked() is False

    # 3. Status bar items: only Memory should be checked, rest unchecked
    assert win.action_sb_memory.isChecked() is True
    assert win.action_sb_aria2.isChecked() is False
    assert win.action_sb_ipc.isChecked() is False
    assert win.action_sb_speed.isChecked() is False
    assert win.action_sb_public_ip.isChecked() is False

    # 4. Status bar permanent widgets visibility: only Memory visible
    assert win.status_memory_label.isHidden() is False
    assert win.status_aria2_label.isHidden() is True
    assert win.status_ipc_label.isHidden() is True
    assert win.status_speed_label.isHidden() is True
    assert win.status_public_ip_label.isHidden() is True

    win.is_quitting = True
    win.close()


def test_queue_start_now_starts_hidden_and_context_menu_shows_progress(qapp, monkeypatch, tmp_path):
    """Verify queue Start now starts with show_dialog=False, and context menu allows showing progress window."""
    win = MainWindow(start_ipc=False)
    win.hide()

    captured_args = []
    def mock_start_queue(qname, max_concurrent=4, show_dialog=True):
        captured_args.append((qname, max_concurrent, show_dialog))

    monkeypatch.setattr(win, "_start_queue_downloads", mock_start_queue)
    win._queue_action_start("Main download queue")
    assert len(captured_args) == 1
    assert captured_args[0] == ("Main download queue", 4, False)

    # Now test progress dialog hidden & context menu show progress
    from ui.dialogs import DownloadProgressDialog
    from core.workers.download import DownloadWorker

    win.download_table.setRowCount(1)
    item_0 = QTableWidgetItem("queue_file.zip")
    item_0.setData(Qt.ItemDataRole.UserRole, "http://example.com/queue_file.zip")
    item_0.setData(Qt.ItemDataRole.UserRole + 1, "/tmp/queue_file.zip")
    item_0.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
    win.download_table.setItem(0, 0, item_0)

    item_2 = QTableWidgetItem("Downloading...")
    item_2.setData(Qt.ItemDataRole.UserRole + 1, "Downloading...")
    win.download_table.setItem(0, 2, item_2)

    # Create dummy worker and progress dialog (hidden, as started by queue)
    worker = DownloadWorker("http://example.com/queue_file.zip", 0, str(tmp_path), "queue_file.zip")
    dlg = DownloadProgressDialog(worker, None)
    dlg.hide()
    key = win._get_item_key(item_0)
    win.active_downloads[key] = dlg

    # Verify dialog starts hidden
    assert dlg.isHidden() is True

    # Call ctx_show_progress_dialog
    win.ctx_show_progress_dialog(item_0)
    assert dlg.isVisible() is True

    dlg.close()
    win.is_quitting = True
    win.close()


def test_stop_all_downloads_state(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)
    win = MainWindow(start_ipc=False)
    win.hide()
    win.download_table.setRowCount(0)
    win.update_ui_states()

    # When no downloads exist, Stop All action must be disabled
    assert win.action_stop_all.isEnabled() is False

    # Add a queued download
    win.download_table.setRowCount(1)
    item_queued = QTableWidgetItem("file_queued.bin")
    item_queued.setData(Qt.ItemDataRole.UserRole, "http://example.com/file_queued.bin")
    item_queued.setData(Qt.ItemDataRole.UserRole + 1, str(tmp_path / "file_queued.bin"))
    win.download_table.setItem(0, 0, item_queued)
    status_queued = QTableWidgetItem("Queued")
    status_queued.setData(Qt.ItemDataRole.UserRole + 1, "Queued")
    win.download_table.setItem(0, 2, status_queued)
    win.update_ui_states()

    # Stop All must be enabled when a download is queued
    assert win.action_stop_all.isEnabled() is True

    # Add an active downloading item
    win.download_table.setRowCount(2)
    item_active = QTableWidgetItem("file_active.bin")
    item_active.setData(Qt.ItemDataRole.UserRole, "http://example.com/file_active.bin")
    item_active.setData(Qt.ItemDataRole.UserRole + 1, str(tmp_path / "file_active.bin"))
    win.download_table.setItem(1, 0, item_active)
    status_active = QTableWidgetItem("Downloading...")
    status_active.setData(Qt.ItemDataRole.UserRole + 1, "Downloading...")
    win.download_table.setItem(1, 2, status_active)

    from core.workers.download import DownloadWorker
    worker = DownloadWorker("http://example.com/file_active.bin", 1, str(tmp_path), "file_active.bin")
    key_active = win._get_item_key(item_active)
    win.active_downloads[key_active] = worker
    win.update_ui_states()

    assert win.action_stop_all.isEnabled() is True

    # Call stop_all_downloads
    win.stop_all_downloads()

    # All items should now be paused
    assert win.download_table.item(0, 2).text() == "Paused"
    assert win.download_table.item(0, 2).data(Qt.ItemDataRole.UserRole + 1) == "Paused"
    assert win.download_table.item(1, 2).text() == "Paused"
    assert win.download_table.item(1, 2).data(Qt.ItemDataRole.UserRole + 1) == "Paused"
    assert getattr(worker, "is_paused", False) is True

    # Stop All MUST be disabled after all downloads are stopped
    assert win.action_stop_all.isEnabled() is False

    win.is_quitting = True
    win.close()


def test_options_titlebar_setting_and_persistence(qapp, monkeypatch, tmp_path):
    """Verify Title bar dropdown options (Auto, Light, Dark), default value, persistence, and live preview."""
    from core.services.theme_service import (
        normalize_titlebar_name, apply_titlebar_theme, is_system_dark_theme
    )

    # 1. Test normalization
    assert normalize_titlebar_name("Automatic") == "Automatic"
    assert normalize_titlebar_name("Auto") == "Automatic"
    assert normalize_titlebar_name("auto") == "Automatic"
    assert normalize_titlebar_name("Auto (Default)") == "Automatic"
    assert normalize_titlebar_name("system") == "Automatic"
    assert normalize_titlebar_name("Light") == "Light"
    assert normalize_titlebar_name("light") == "Light"
    assert normalize_titlebar_name("system light") == "Light"
    assert normalize_titlebar_name("Dark") == "Dark"
    assert normalize_titlebar_name("dark") == "Dark"
    assert normalize_titlebar_name("system dark") == "Dark"
    assert normalize_titlebar_name("") == "Automatic"
    assert normalize_titlebar_name(None) == "Automatic"

    # 2. Test OptionsDialog UI defaults
    dlg = OptionsDialog()
    assert hasattr(dlg, "combo_titlebar")
    items = [dlg.combo_titlebar.itemText(i) for i in range(dlg.combo_titlebar.count())]
    assert items == ["Automatic", "Light", "Dark"]
    assert dlg.combo_titlebar.currentText() == "Automatic"
    assert dlg.get_titlebar() == "Automatic"
    dlg.reject()

    # 3. Test persistence via dummy MainWindow
    dummy_win = MainWindow(start_ipc=False)
    dummy_win.hide()
    dummy_win.settings = {"theme": "BDM Auto (Default)", "title_bar": "Automatic"}

    dlg_settings = OptionsDialog(main_window=dummy_win)
    assert dlg_settings.combo_titlebar.currentText() == "Automatic"

    # Switch to Dark and accept
    dlg_settings.combo_titlebar.setCurrentText("Dark")
    dlg_settings.save_and_accept()
    assert dummy_win.settings.get("title_bar") == "Dark"

    # Reopen dialog with updated settings
    dlg_settings_reopened = OptionsDialog(main_window=dummy_win)
    assert dlg_settings_reopened.combo_titlebar.currentText() == "Dark"
    assert dlg_settings_reopened.get_titlebar() == "Dark"

    # Switch to Light and accept
    dlg_settings_reopened.combo_titlebar.setCurrentText("Light")
    dlg_settings_reopened.save_and_accept()
    assert dummy_win.settings.get("title_bar") == "Light"

    dlg_settings_reopened.close()
    dummy_win.is_quitting = True
    dummy_win.close()

    # 4. Test apply_titlebar_theme mode tracking
    from core.services.theme_service import get_current_titlebar_mode

    apply_titlebar_theme("Dark", app=qapp)
    assert get_current_titlebar_mode() == "Dark"

    apply_titlebar_theme("Light", app=qapp)
    assert get_current_titlebar_mode() == "Light"

    apply_titlebar_theme("Automatic", app=qapp)
    assert get_current_titlebar_mode() == "Automatic"

    apply_titlebar_theme("Auto", app=qapp)
    assert get_current_titlebar_mode() == "Automatic"


def test_central_container_padding(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    assert hasattr(window, "central_container")
    assert window.central_container is not None
    assert window.centralWidget() == window.central_container

    layout = window.central_container.layout()
    assert layout is not None
    margins = layout.contentsMargins()
    assert margins.left() == 4
    assert margins.right() == 4
    assert margins.top() == 0
    # Status bar shown by default -> bottom margin is 0
    assert margins.bottom() == 0

    assert hasattr(window, "splitter")
    assert window.splitter is not None
    assert window.splitter.count() == 2

    # When status bar is unchecked/hidden, bottom margin must be 4px
    window.toggle_status_bar(False)
    margins = window.central_container.layout().contentsMargins()
    assert margins.bottom() == 4
    assert margins.left() == 4
    assert margins.right() == 4

    # When status bar is re-checked/shown, bottom margin must return to 0px
    window.toggle_status_bar(True)
    margins = window.central_container.layout().contentsMargins()
    assert margins.bottom() == 0

    window.close()


def test_gnome_csd_titlebar_toggle(qapp, monkeypatch):
    """Verify GNOME/GTK Libadwaita client-side decoration (CSD) attaches on Dark/Light/Automatic and detaches cleanly."""
    from core.services.theme_service import apply_titlebar_theme, is_gnome_desktop
    from ui.components.csd_titlebar import CsdTitleBar, detach_csd

    monkeypatch.setenv("BDM_FORCE_CSD", "1")
    assert is_gnome_desktop() is True

    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        # 1. Dark mode -> CSD attached with Libadwaita dark styling
        apply_titlebar_theme("Dark", window=win, app=qapp)
        assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint) is True
        assert hasattr(win, "_csd_titlebar") and win._csd_titlebar is not None
        assert isinstance(win._csd_titlebar, CsdTitleBar)
        assert win._csd_titlebar._is_dark is True
        assert win._csd_titlebar.height() == 46
        assert win._csd_titlebar.btn_close.text() == "✕"
        assert win._csd_titlebar.btn_min.text() == "–"
        assert win._csd_titlebar.btn_max.text() == "□"

        # 2. Light mode -> CSD stays attached, styled light
        apply_titlebar_theme("Light", window=win, app=qapp)
        assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint) is True
        assert win._csd_titlebar._is_dark is False

        # 3. Automatic mode -> CSD stays attached on GNOME/GTK, follows system color scheme
        apply_titlebar_theme("Automatic", window=win, app=qapp)
        assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint) is True
        assert hasattr(win, "_csd_titlebar") and win._csd_titlebar is not None

        # 4. Explicit detach -> system frame restored
        detach_csd(win)
        assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint) is False
        assert getattr(win, "_csd_titlebar", None) is None
    finally:
        win.is_quitting = True
        win.close()


def test_dialog_csd_behavior(qapp, monkeypatch):
    """Verify dialog CSD has close button, no minimize button, and 46px height."""
    from PyQt6.QtWidgets import QDialog, QVBoxLayout
    from ui.components.csd_titlebar import attach_csd, detach_csd, CsdTitleBar

    dlg = QDialog()
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(10, 10, 10, 10)

    try:
        attach_csd(dlg, is_dark=True)
        assert hasattr(dlg, "_csd_titlebar") and dlg._csd_titlebar is not None
        tb = dlg._csd_titlebar
        assert isinstance(tb, CsdTitleBar)
        assert tb.height() == 46
        assert tb.btn_min is None
        assert tb.btn_close is not None
        assert tb.btn_close.text() == "✕"
        assert tb._is_dark is True

        # Style change to light
        attach_csd(dlg, is_dark=False)
        assert tb._is_dark is False

        # Title change
        dlg.setWindowTitle("Custom Dialog Title")
        tb.update_title(dlg.windowTitle())
        assert tb.title_lbl.text() == "Custom Dialog Title"

        # Detach
        detach_csd(dlg)
        assert getattr(dlg, "_csd_titlebar", None) is None
    finally:
        dlg.close()


def test_gtk_desktops_detection(monkeypatch):
    """Verify is_gnome_desktop detects all GNOME and GTK-based desktops properly."""
    from core.services.theme_service import is_gnome_desktop

    # GTK / GNOME environments
    for env in ["GNOME", "ubuntu:GNOME", "Unity", "Pop:GNOME", "X-Cinnamon", "MATE", "XFCE", "Budgie:GNOME", "Pantheon", "cosmic"]:
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", env)
        monkeypatch.delenv("BDM_FORCE_CSD", raising=False)
        monkeypatch.delenv("BDM_DISABLE_CSD", raising=False)
        assert is_gnome_desktop() is True, f"Failed for {env}"

    # Non-GTK / KDE Plasma
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("GDMSESSION", "plasma")
    monkeypatch.setenv("XDG_SESSION_DESKTOP", "plasma")
    monkeypatch.setenv("DESKTOP_SESSION", "plasma")
    assert is_gnome_desktop() is False

    # Force disable override
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("BDM_DISABLE_CSD", "1")
    assert is_gnome_desktop() is False

    # Force enable override
    monkeypatch.setenv("BDM_DISABLE_CSD", "0")
    monkeypatch.setenv("BDM_FORCE_CSD", "1")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert is_gnome_desktop() is True

