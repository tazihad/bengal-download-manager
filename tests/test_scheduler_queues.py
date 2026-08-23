"""
Unit and integration tests for Queues and Scheduler functionality.
Tests every option, dependency state, and interaction in SchedulerDialog and MainWindow sidebar queues.
"""
import os
import pytest
from PyQt6.QtCore import Qt, QTime, QDate, QPoint
from PyQt6.QtWidgets import QDialog, QTreeWidgetItem, QMenu

from main import MainWindow
from ui.dialogs.scheduler import SchedulerDialog, DEFAULT_QUEUES, _make_default_queue


def test_default_queues_and_factory():
    """Verify DEFAULT_QUEUES structure and _make_default_queue factory helper."""
    assert len(DEFAULT_QUEUES) == 2
    main_q = DEFAULT_QUEUES[0]
    sync_q = DEFAULT_QUEUES[1]

    assert main_q["name"] == "Main download queue"
    assert main_q["default"] is True
    assert main_q["mode"] == "onetime"
    assert main_q["max_concurrent"] == 4
    assert len(main_q["daily_days"]) == 7

    assert sync_q["name"] == "Synchronization queue"
    assert sync_q["default"] is True
    assert sync_q["mode"] == "sync"

    custom_q = _make_default_queue("Custom Queue # 1")
    assert custom_q["name"] == "Custom Queue # 1"
    assert custom_q["default"] is False
    assert custom_q["mode"] == "onetime"
    assert custom_q["max_concurrent"] == 4


def test_scheduler_dialog_initialization(qapp):
    """Verify SchedulerDialog initialization with default and custom queues."""
    dlg = SchedulerDialog()
    dlg.hide()

    assert dlg.windowTitle() == "Scheduler"
    assert dlg.queue_list.count() == 2
    assert dlg.queue_list.item(0).text() == "Main download queue"
    assert dlg.queue_list.item(1).text() == "Synchronization queue"
    assert dlg._selected_index == 0
    assert dlg.queue_title_label.text() == "Main download queue"
    assert not dlg.btn_delete_queue.isEnabled()

    # Custom queues initialization
    custom_list = [
        _make_default_queue("Custom Queue A"),
        _make_default_queue("Custom Queue B"),
    ]
    dlg_custom = SchedulerDialog(initial_queues=custom_list)
    dlg_custom.hide()
    assert dlg_custom.queue_list.count() == 2
    assert dlg_custom.queue_list.item(0).text() == "Custom Queue A"
    assert dlg_custom.btn_delete_queue.isEnabled()


def test_scheduler_dialog_selection_and_mode_locking(qapp):
    """Verify queue selection, mode locking, and widget visibility."""
    dlg = SchedulerDialog()
    dlg.hide()

    # Row 0: Main download queue (locked to onetime)
    dlg.queue_list.setCurrentRow(0)
    assert dlg.queue_title_label.text() == "Main download queue"
    assert dlg.radio_onetime.isChecked()
    assert dlg.radio_onetime.isEnabled()
    assert not dlg.radio_sync.isEnabled()
    assert not dlg.onetime_widget.isHidden()
    assert dlg.sync_widget.isHidden()
    assert not dlg.btn_delete_queue.isEnabled()

    # Row 1: Synchronization queue (locked to sync)
    dlg.queue_list.setCurrentRow(1)
    assert dlg.queue_title_label.text() == "Synchronization queue"
    assert dlg.radio_sync.isChecked()
    assert dlg.radio_sync.isEnabled()
    assert not dlg.radio_onetime.isEnabled()
    assert dlg.onetime_widget.isHidden()
    assert not dlg.sync_widget.isHidden()
    assert not dlg.btn_delete_queue.isEnabled()


def test_scheduler_dialog_add_and_delete_queues(qapp):
    """Verify adding new queues and deleting custom queues."""
    dlg = SchedulerDialog()
    dlg.hide()

    # Add new queue # 1
    dlg._add_new_queue()
    assert dlg.queue_list.count() == 3
    assert dlg.queue_list.item(2).text() == "Queue # 1"
    assert dlg.queue_list.currentRow() == 2
    assert dlg.btn_delete_queue.isEnabled()
    assert dlg.radio_onetime.isEnabled()
    assert dlg.radio_sync.isEnabled()

    # Add new queue # 2
    dlg._add_new_queue()
    assert dlg.queue_list.count() == 4
    assert dlg.queue_list.item(3).text() == "Queue # 2"
    assert dlg.queue_list.currentRow() == 3

    # Delete Queue # 2 via btn_delete_queue
    dlg._delete_selected_queue()
    assert dlg.queue_list.count() == 3
    assert dlg.queue_list.currentRow() == 2
    assert dlg.queue_list.item(2).text() == "Queue # 1"

    # Attempt to delete default queue (should be no-op)
    dlg.queue_list.setCurrentRow(0)
    assert not dlg.btn_delete_queue.isEnabled()
    dlg._delete_selected_queue()
    assert dlg.queue_list.count() == 3

    # Delete Queue # 1 via _delete_queue_at
    dlg._delete_queue_at(2)
    assert dlg.queue_list.count() == 2
    assert dlg.queue_list.item(0).text() == "Main download queue"
    assert dlg.queue_list.item(1).text() == "Synchronization queue"


def test_scheduler_dialog_start_at_and_dependencies(qapp):
    """Test start_at checkbox enabling/disabling dependent controls in both onetime and sync modes."""
    dlg = SchedulerDialog()
    dlg.hide()

    # Create a custom queue to freely switch between modes
    dlg._add_new_queue()
    dlg.queue_list.setCurrentRow(2)

    # 1. By default, start_at is unchecked
    assert not dlg.chk_start_at.isChecked()
    assert not dlg.time_start_at.isEnabled()
    assert not dlg.radio_once.isEnabled()
    assert not dlg.radio_daily.isEnabled()
    assert not dlg.date_once.isEnabled()
    for chk in dlg.day_checks:
        assert not chk.isEnabled()

    # 2. Check start_at in onetime mode
    dlg.chk_start_at.setChecked(True)
    assert dlg.time_start_at.isEnabled()
    assert dlg.radio_once.isEnabled()
    assert dlg.radio_daily.isEnabled()
    for chk in dlg.day_checks:
        assert chk.isEnabled()

    # Daily is selected by default -> date_once is disabled
    assert dlg.radio_daily.isChecked()
    assert not dlg.date_once.isEnabled()

    # Select 'Once at' -> date_once becomes enabled
    dlg.radio_once.setChecked(True)
    assert dlg.date_once.isEnabled()

    # 3. Switch to Periodic synchronization mode
    dlg.radio_sync.setChecked(True)
    assert dlg.onetime_widget.isHidden()
    assert not dlg.sync_widget.isHidden()

    # start_at is still checked
    assert dlg.chk_sync_interval.isEnabled()
    for chk in dlg.sync_day_checks:
        assert chk.isEnabled()

    # sync interval spinboxes disabled until chk_sync_interval is checked
    assert not dlg.spin_sync_hours.isEnabled()
    assert not dlg.spin_sync_mins.isEnabled()

    dlg.chk_sync_interval.setChecked(True)
    assert dlg.spin_sync_hours.isEnabled()
    assert dlg.spin_sync_mins.isEnabled()

    # 4. Uncheck start_at -> all sync sub-controls should disable
    dlg.chk_start_at.setChecked(False)
    assert not dlg.time_start_at.isEnabled()
    assert not dlg.chk_sync_interval.isEnabled()
    assert not dlg.spin_sync_hours.isEnabled()
    assert not dlg.spin_sync_mins.isEnabled()
    for chk in dlg.sync_day_checks:
        assert not chk.isEnabled()


def test_scheduler_dialog_all_schedule_options_save_and_load(qapp):
    """Test setting every option on the Schedule tab, saving state, and reloading into UI."""
    dlg = SchedulerDialog()
    dlg.hide()

    dlg._add_new_queue()
    dlg.queue_list.setCurrentRow(2)

    # Configure every option
    dlg.chk_startup.setChecked(True)
    dlg.chk_start_at.setChecked(True)
    dlg.time_start_at.setTime(QTime(14, 30, 15))
    dlg.radio_once.setChecked(True)
    dlg.date_once.setDate(QDate(2026, 12, 25))

    dlg.day_checks[0].setChecked(False)  # Sunday unchecked
    dlg.day_checks[1].setChecked(True)   # Monday checked

    dlg.chk_stop_at.setChecked(True)
    dlg.time_stop_at.setTime(QTime(18, 45, 30))

    dlg.chk_retries.setChecked(True)
    dlg.spin_retries.setValue(25)

    dlg.chk_open_file.setChecked(True)
    dlg.txt_open_file.setText("/path/to/script.sh")

    dlg.chk_exit_app.setChecked(True)
    dlg.chk_turn_off.setChecked(True)
    dlg.combo_turn_off.setCurrentText("Hibernate")
    dlg.chk_force.setChecked(True)

    # Save UI to queue
    dlg._save_ui_to_queue(2)

    saved_q = dlg.queues[2]
    assert saved_q["start_on_startup"] is True
    assert saved_q["start_at_enabled"] is True
    assert saved_q["start_at_time"] == "14:30:15"
    assert saved_q["schedule_type"] == "once"
    assert saved_q["once_date"] == "2026-12-25"
    assert saved_q["daily_days"][0] is False
    assert saved_q["daily_days"][1] is True
    assert saved_q["stop_at_enabled"] is True
    assert saved_q["stop_at_time"] == "18:45:30"
    assert saved_q["retries_enabled"] is True
    assert saved_q["retries_count"] == 25
    assert saved_q["open_file_enabled"] is True
    assert saved_q["open_file_path"] == "/path/to/script.sh"
    assert saved_q["exit_app_when_done"] is True
    assert saved_q["turn_off_enabled"] is True
    assert saved_q["turn_off_action"] == "Hibernate"
    assert saved_q["force_terminate"] is True

    # Switch away to queue 0, then switch back to queue 2 to test _load_queue_to_ui
    dlg.queue_list.setCurrentRow(0)
    assert dlg.queue_title_label.text() == "Main download queue"

    dlg.queue_list.setCurrentRow(2)
    assert dlg.queue_title_label.text() == "Queue # 1"
    assert dlg.chk_startup.isChecked() is True
    assert dlg.chk_start_at.isChecked() is True
    assert dlg.time_start_at.time() == QTime(14, 30, 15)
    assert dlg.radio_once.isChecked() is True
    assert dlg.date_once.date() == QDate(2026, 12, 25)
    assert dlg.day_checks[0].isChecked() is False
    assert dlg.day_checks[1].isChecked() is True
    assert dlg.chk_stop_at.isChecked() is True
    assert dlg.time_stop_at.time() == QTime(18, 45, 30)
    assert dlg.chk_retries.isChecked() is True
    assert dlg.spin_retries.value() == 25
    assert dlg.chk_open_file.isChecked() is True
    assert dlg.txt_open_file.text() == "/path/to/script.sh"
    assert dlg.chk_exit_app.isChecked() is True
    assert dlg.chk_turn_off.isChecked() is True
    assert dlg.combo_turn_off.currentText() == "Hibernate"
    assert dlg.chk_force.isChecked() is True


def test_scheduler_dialog_turn_off_interactions(qapp):
    """Test turn off checkbox enabling/disabling combo and force terminate."""
    dlg = SchedulerDialog()
    dlg.hide()

    # Initially unchecked
    assert not dlg.chk_turn_off.isChecked()
    assert not dlg.combo_turn_off.isEnabled()
    assert not dlg.chk_force.isEnabled()

    # Check turn_off
    dlg.chk_turn_off.setChecked(True)
    assert dlg.combo_turn_off.isEnabled()
    assert dlg.chk_force.isEnabled()

    dlg.chk_force.setChecked(True)
    assert dlg.chk_force.isChecked()

    # Unchecking turn_off disables and unchecks force
    dlg.chk_turn_off.setChecked(False)
    assert not dlg.combo_turn_off.isEnabled()
    assert not dlg.chk_force.isEnabled()
    assert not dlg.chk_force.isChecked()


def test_scheduler_dialog_browse_file(qapp, monkeypatch):
    """Test browse open file button dialog integration."""
    dlg = SchedulerDialog()
    dlg.hide()

    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("/usr/bin/custom_cmd", "All Files (*)"))

    dlg._browse_open_file()
    assert dlg.txt_open_file.text() == "/usr/bin/custom_cmd"


def test_scheduler_dialog_files_tab_and_table_population(qapp):
    """Test Files tab concurrent downloads spinbox and download table reflection."""
    win = MainWindow(start_ipc=False)
    win.hide()
    win.download_table.setRowCount(0)

    # Add mock downloads to MainWindow table (first added ends up at row 1, second at row 0)
    win.start_download(
        url="http://example.com/video.mp4",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )
    win.start_download(
        url="http://example.com/archive.zip",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    # Identify row for archive.zip vs video.mp4
    for r in range(win.download_table.rowCount()):
        item = win.download_table.item(r, 0)
        if item.text() == "video.mp4":
            win.download_table.item(r, 1).setText("150.00 MB")
            win.download_table.item(r, 2).setText("Downloading...")
            win.download_table.item(r, 2).setData(Qt.ItemDataRole.UserRole, "55.40%")
            win.download_table.item(r, 3).setText("00:02:15")
        elif item.text() == "archive.zip":
            win.download_table.item(r, 1).setText("25.00 MB")
            win.download_table.item(r, 2).setText("Paused")
            win.download_table.item(r, 3).setText("Paused")

    dlg = SchedulerDialog(main_window=win)
    dlg.hide()

    # Switch to Files in the queue tab
    dlg.tabs.setCurrentIndex(1)

    assert dlg.files_table.rowCount() == 2
    # Verify both rows are present with formatted columns
    row0_name = dlg.files_table.item(0, 0).text()
    row1_name = dlg.files_table.item(1, 0).text()

    if row0_name == "archive.zip":
        assert dlg.files_table.item(0, 1).text() == "25.00 MB"
        assert dlg.files_table.item(0, 2).text() == "Paused"
        assert dlg.files_table.item(1, 0).text() == "video.mp4"
        assert dlg.files_table.item(1, 1).text() == "150.00 MB"
        assert dlg.files_table.item(1, 2).text() == "55.40%"
        assert dlg.files_table.item(1, 3).text() == "00:02:15"
    else:
        assert dlg.files_table.item(0, 0).text() == "video.mp4"
        assert dlg.files_table.item(0, 1).text() == "150.00 MB"
        assert dlg.files_table.item(0, 2).text() == "55.40%"
        assert dlg.files_table.item(1, 0).text() == "archive.zip"
        assert dlg.files_table.item(1, 1).text() == "25.00 MB"


def test_scheduler_dialog_apply_changes(qapp):
    """Test Apply button saves state and updates MainWindow.MAX_CONCURRENT_DOWNLOADS."""
    win = MainWindow(start_ipc=False)
    win.hide()
    win.MAX_CONCURRENT_DOWNLOADS = 4

    dlg = SchedulerDialog(main_window=win)
    dlg.hide()
    dlg.queue_list.setCurrentRow(0)  # Main download queue

    dlg.spin_concurrent.setValue(8)
    dlg._apply_changes()

    assert dlg.queues[0]["max_concurrent"] == 8
    assert win.MAX_CONCURRENT_DOWNLOADS == 8


def test_scheduler_dialog_context_menu(qapp, monkeypatch):
    """Test context menu actions and event handlers on the queue list."""
    dlg = SchedulerDialog()
    dlg.hide()

    dlg._add_new_queue()
    assert dlg.queue_list.count() == 3

    # Mock QMenu.exec to avoid blocking test execution
    menu_exec_called = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: menu_exec_called.append(pos))

    item = dlg.queue_list.item(2)
    rect = dlg.queue_list.visualItemRect(item)

    # Test _show_queue_context_menu with non-default queue
    dlg._show_queue_context_menu(rect.center())
    assert len(menu_exec_called) == 1

    # Start now and stop handlers (placeholders should not crash)
    dlg._on_start_now()
    dlg._on_stop()


def test_mainwindow_sidebar_queues_integration(qapp):
    """Test MainWindow sidebar queues creation, opening scheduler, deletion, and sync."""
    win = MainWindow(start_ipc=False)
    win.hide()

    assert hasattr(win, "queues_header")
    assert win.queues_header.childCount() == 2
    assert win._sidebar_queue_names == ["Main download queue", "Synchronization queue"]

    # 1. Create a queue from sidebar
    win._create_sidebar_queue()
    assert win.queues_header.childCount() == 3
    assert "Queue # 1" in win._sidebar_queue_names
    assert len(win._queues_data) == 3

    # 2. Open scheduler for specific queue
    win._open_scheduler_for_queue("Queue # 1")
    assert hasattr(win, "_scheduler_dlg")
    assert win._scheduler_dlg.isVisible()
    assert win._scheduler_dlg.queue_title_label.text() == "Queue # 1"

    # 3. Prevent deleting default queues from sidebar
    main_item = win.queues_header.child(0)
    assert main_item.text(0) == "Main download queue"
    win._delete_sidebar_queue(main_item)
    assert win.queues_header.childCount() == 3

    # 4. Delete custom queue from sidebar
    custom_item = win.queues_header.child(2)
    assert custom_item.text(0) == "Queue # 1"
    win._delete_sidebar_queue(custom_item)
    assert win.queues_header.childCount() == 2
    assert "Queue # 1" not in win._sidebar_queue_names
    assert len(win._queues_data) == 2
    assert win._scheduler_dlg.queue_list.count() == 2

    # 5. Add a queue in scheduler dialog, then sync sidebar
    win._scheduler_dlg._add_new_queue()
    assert win._scheduler_dlg.queue_list.count() == 3
    win._sync_sidebar_queues()
    assert win.queues_header.childCount() == 3
    assert win._sidebar_queue_names[-1] == "Queue # 1"

    # 6. Test _notify_views_changed updating scheduler files table
    win._scheduler_dlg.tabs.setCurrentIndex(1)
    win._notify_views_changed()
    assert win._scheduler_dlg.files_table is not None

    win._scheduler_dlg.close()


def test_queue_context_menu_stylesheet_and_disabled_delete(qapp, monkeypatch):
    """Verify QMenu stylesheet rules for hover text color (black) and disabled item text color (#888888)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    app_stylesheet = app.styleSheet()

    # Verify global QMenu stylesheet rules
    assert "QMenu::item:selected" in app_stylesheet
    assert "color: #000000;" in app_stylesheet
    assert "QMenu::item:disabled" in app_stylesheet
    assert "color: #888888;" in app_stylesheet

    # Verify SchedulerDialog stylesheet rules
    dlg = SchedulerDialog()
    dlg.hide()
    dlg_stylesheet = dlg.styleSheet()
    assert "QMenu::item:selected" in dlg_stylesheet
    assert "color: #000000;" in dlg_stylesheet
    assert "QMenu::item:disabled" in dlg_stylesheet
    assert "color: #888888;" in dlg_stylesheet

    # Verify context menu on default queue has disabled Delete action
    captured_menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: captured_menus.append(self))

    # Scheduler queue list context menu for default queue (row 0)
    item0 = dlg.queue_list.item(0)
    dlg._show_queue_context_menu(dlg.queue_list.visualItemRect(item0).center())
    assert len(captured_menus) == 1
    actions = {act.text(): act for act in captured_menus[0].actions()}
    assert "Delete" in actions
    assert actions["Delete"].isEnabled() is False

    # MainWindow sidebar context menu for default queue
    win = MainWindow(start_ipc=False)
    win.hide()
    main_child = win.queues_header.child(0)
    rect = win.category_tree.visualItemRect(main_child)
    win._show_sidebar_context_menu(rect.center())
    assert len(captured_menus) == 2
    sb_actions = {act.text(): act for act in captured_menus[1].actions()}
    assert "Delete" in sb_actions
    assert sb_actions["Delete"].isEnabled() is False


def test_download_context_menu_queue_operations(qapp, monkeypatch):
    """Verify Move to queue submenu, Delete from queue, and creating a new queue from context menu."""
    from PyQt6.QtWidgets import QTableWidgetItem, QInputDialog

    win = MainWindow(start_ipc=False)
    win.hide()
    win.download_table.setRowCount(0)

    # Insert 2 test downloads
    win.download_table.insertRow(0)
    item0 = QTableWidgetItem("fileA.zip")
    item0.setData(Qt.ItemDataRole.UserRole, "http://example.com/fileA.zip")
    item0.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
    win.download_table.setItem(0, 0, item0)
    win.download_table.setItem(0, 2, QTableWidgetItem("Complete"))

    win.download_table.insertRow(1)
    item1 = QTableWidgetItem("fileB.zip")
    item1.setData(Qt.ItemDataRole.UserRole, "http://example.com/fileB.zip")
    item1.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
    win.download_table.setItem(1, 0, item1)
    win.download_table.setItem(1, 2, QTableWidgetItem("Complete"))

    # Select item0 and inspect context menu
    captured_menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: captured_menus.append(self))

    win.download_table.selectRow(0)
    win.show_context_menu(QPoint(10, 10))

    assert len(captured_menus) == 1
    ctx_menu = captured_menus[0]

    action_texts = [act.text() for act in ctx_menu.actions()]
    assert "Delete" in action_texts
    assert "Move to queue" in action_texts
    assert "Delete from queue" in action_texts
    assert "Properties" in action_texts

    idx_delete = action_texts.index("Delete")
    idx_move = action_texts.index("Move to queue")
    idx_del_q = action_texts.index("Delete from queue")
    idx_props = action_texts.index("Properties")

    # Assert queue options are below Delete and above Properties
    assert idx_delete < idx_move < idx_del_q < idx_props

    # Move to Synchronization queue
    win.download_table.selectRow(0)
    win._move_selected_to_queue("Synchronization queue")
    assert item0.data(Qt.ItemDataRole.UserRole + 8) == "Synchronization queue"

    # Delete from queue
    win._delete_selected_from_queue()
    assert item0.data(Qt.ItemDataRole.UserRole + 8) == ""

    # Create new queue via dialog mock and move selected
    monkeypatch.setattr(QInputDialog, "getText", lambda parent, title, label: ("Nightly Queue", True))
    win.download_table.selectRow(1)
    win._create_new_queue_and_move_selected()

    assert item1.data(Qt.ItemDataRole.UserRole + 8) == "Nightly Queue"
    assert any(q.get("name") == "Nightly Queue" for q in win._queues_data)
    assert "Nightly Queue" in win._sidebar_queue_names

    win.close()


def test_scheduler_start_download_on_app_startup(qapp, monkeypatch):
    """Verify that queues configured with start_on_startup trigger downloads on startup."""
    import time
    import tempfile
    from main import MainWindow
    from PyQt6.QtWidgets import QTableWidgetItem
    from core.database import save_all_queues, save_all_downloads

    db_file = os.path.join(tempfile.gettempdir(), f"bdm_test_startup_q_{time.time()}.db")
    monkeypatch.setattr("core.database.get_db_path", lambda: db_file)

    test_queues = [
        {
            "name": "Main download queue",
            "default": True,
            "mode": "onetime",
            "start_on_startup": True,
            "max_concurrent": 2,
        }
    ]
    test_downloads = [
        {
            "url": "http://example.com/startup_test.zip",
            "filename": "startup_test.zip",
            "path": "/tmp/startup_test.zip",
            "size": "10 MB",
            "status": "Paused",
            "time_left": "",
            "rate": "",
            "last_try": "",
            "date_added": "",
            "queue": "Main download queue",
        }
    ]
    save_all_queues(test_queues, db_path=db_file)
    save_all_downloads(test_downloads, db_path=db_file)

    started_downloads = []
    monkeypatch.setattr(MainWindow, "_start_download_worker", lambda self, url, item_ref, **kw: started_downloads.append((url, item_ref.text())))

    win = MainWindow(start_ipc=False)
    win.hide()

    win._check_startup_queues()

    assert len(started_downloads) == 1
    assert started_downloads[0][0] == "http://example.com/startup_test.zip"
    assert started_downloads[0][1] == "startup_test.zip"

    win.close()



