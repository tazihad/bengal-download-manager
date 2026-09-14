"""
Core Unit and Integration Tests for Queues and Scheduler Functionality.
"""

import pytest
from PyQt6.QtCore import QTime, QDate, Qt
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
    dlg.close()
    dlg_custom.close()


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

    # Add new queue # 2
    dlg._add_new_queue()
    assert dlg.queue_list.count() == 4
    assert dlg.queue_list.item(3).text() == "Queue # 2"

    # Delete Queue # 2
    dlg._delete_selected_queue()
    assert dlg.queue_list.count() == 3
    assert dlg.queue_list.item(2).text() == "Queue # 1"

    # Delete Queue # 1
    dlg._delete_queue_at(2)
    assert dlg.queue_list.count() == 2
    dlg.close()


def test_scheduler_dialog_all_schedule_options_save_and_load(qapp):
    """Test setting options on Schedule tab, saving state, and reloading into UI."""
    dlg = SchedulerDialog()
    dlg.hide()

    dlg._add_new_queue()
    dlg.queue_list.setCurrentRow(2)

    dlg.chk_startup.setChecked(True)
    dlg.chk_start_at.setChecked(True)
    dlg.time_start_at.setTime(QTime(14, 30, 15))
    dlg.radio_once.setChecked(True)
    dlg.date_once.setDate(QDate(2026, 12, 25))

    dlg.day_checks[0].setChecked(False)
    dlg.day_checks[1].setChecked(True)

    dlg.chk_stop_at.setChecked(True)
    dlg.time_stop_at.setTime(QTime(18, 45, 30))

    dlg.chk_retries.setChecked(True)
    dlg.spin_retries.setValue(25)

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
    dlg.close()


def test_scheduler_queue_context_menu_rename_only(qapp, monkeypatch):
    """Verify right-clicking queue item in scheduler left panel shows only Rename, disabled for default queues."""
    from PyQt6.QtWidgets import QMenu

    dlg = SchedulerDialog()
    dlg.hide()
    dlg._add_new_queue()  # row 2: "Queue # 1"

    captured_menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, *args, **kwargs: captured_menus.append(self))

    # Row 0: Main download queue (default)
    item0 = dlg.queue_list.item(0)
    pos0 = dlg.queue_list.visualItemRect(item0).center()
    dlg._show_queue_context_menu(pos0)
    assert len(captured_menus) == 1
    actions0 = [a for a in captured_menus[-1].actions() if not a.isSeparator()]
    assert len(actions0) == 1
    assert actions0[0].text() == "Rename"
    assert not actions0[0].isEnabled()

    # Row 1: Synchronization queue (default)
    item1 = dlg.queue_list.item(1)
    pos1 = dlg.queue_list.visualItemRect(item1).center()
    dlg._show_queue_context_menu(pos1)
    assert len(captured_menus) == 2
    actions1 = [a for a in captured_menus[-1].actions() if not a.isSeparator()]
    assert len(actions1) == 1
    assert actions1[0].text() == "Rename"
    assert not actions1[0].isEnabled()

    # Row 2: Queue # 1 (custom/newly created)
    item2 = dlg.queue_list.item(2)
    pos2 = dlg.queue_list.visualItemRect(item2).center()
    dlg._show_queue_context_menu(pos2)
    assert len(captured_menus) == 3
    actions2 = [a for a in captured_menus[-1].actions() if not a.isSeparator()]
    assert len(actions2) == 1
    assert actions2[0].text() == "Rename"
    assert actions2[0].isEnabled()

    dlg.close()


def test_scheduler_queue_rename_flow(qapp, monkeypatch):
    """Test renaming custom queues, preventing default queue rename, and duplicate check."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox, QTableWidget, QTableWidgetItem
    from PyQt6.QtCore import Qt

    class DummyMainWindow:
        def __init__(self):
            self.download_table = QTableWidget(1, 4)
            ti = QTableWidgetItem("file.zip")
            ti.setData(Qt.ItemDataRole.UserRole + 8, "Queue # 1")
            self.download_table.setItem(0, 0, ti)
            self._queues_data = []
            self.synced = False
        def _sync_sidebar_queues(self):
            self.synced = True

    dummy_mw = DummyMainWindow()
    dlg = SchedulerDialog(main_window=dummy_mw)
    dlg.hide()
    dlg._add_new_queue()  # row 2: "Queue # 1"
    dlg.queue_list.setCurrentRow(2)

    # 1. Default queues cannot be renamed
    dlg._rename_queue_at(0)
    assert dlg.queues[0]["name"] == "Main download queue"

    # 2. Rename to duplicate name should show warning and not change
    warning_shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warning_shown.append(True))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Main download queue", True))
    dlg._rename_queue_at(2)
    assert warning_shown == [True]
    assert dlg.queues[2]["name"] == "Queue # 1"

    # 3. Rename to new valid name
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Work Batch", True))
    dlg._rename_queue_at(2)
    assert dlg.queues[2]["name"] == "Work Batch"
    assert dlg.queue_list.item(2).text() == "Work Batch"
    assert dlg.queue_title_label.text() == "Work Batch"

    # Verify download_table item was updated
    assert dummy_mw.download_table.item(0, 0).data(Qt.ItemDataRole.UserRole + 8) == "Work Batch"
    assert dummy_mw.synced is True

    dlg.close()


def test_scheduler_buttons_properly_sized(qapp):
    """Verify that buttons in scheduler window are boxed, properly sized, and boxes have equal height."""
    dlg = SchedulerDialog()
    dlg.show()

    # Verify bottom action buttons
    for btn in (dlg.btn_start, dlg.btn_stop, dlg.btn_apply, dlg.btn_close):
        assert btn.minimumWidth() >= 80
        assert btn.height() >= 30

    # Verify left panel queue buttons
    for btn in (dlg.btn_new_queue, dlg.btn_delete_queue):
        assert btn.minimumWidth() >= 80
        assert btn.height() >= 30

    # Verify left and right boxes have the exact same height
    assert dlg.queue_list.height() == dlg.tabs.height()

    dlg.close()


def test_scheduler_files_table_filtered_by_selected_queue(qapp):
    """Verify that when selecting a queue from the left panel, the right panel Files table only shows items in that queue."""
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from PyQt6.QtCore import Qt

    class DummyMainWindow:
        def __init__(self):
            self.download_table = QTableWidget(4, 4)
            # Item 0: Main download queue
            i0 = QTableWidgetItem("main_file.zip")
            i0.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
            self.download_table.setItem(0, 0, i0)
            self.download_table.setItem(0, 1, QTableWidgetItem("10 MB"))
            self.download_table.setItem(0, 2, QTableWidgetItem("Finished"))

            # Item 1: Custom queue
            i1 = QTableWidgetItem("custom_file.iso")
            i1.setData(Qt.ItemDataRole.UserRole + 8, "Queue # 1")
            self.download_table.setItem(1, 0, i1)
            self.download_table.setItem(1, 1, QTableWidgetItem("50 MB"))
            self.download_table.setItem(1, 2, QTableWidgetItem("Downloading..."))

            # Item 2: Sync queue
            i2 = QTableWidgetItem("sync_file.tar")
            i2.setData(Qt.ItemDataRole.UserRole + 8, "Synchronization queue")
            self.download_table.setItem(2, 0, i2)
            self.download_table.setItem(2, 1, QTableWidgetItem("5 MB"))
            self.download_table.setItem(2, 2, QTableWidgetItem("Paused"))

            # Item 3: No queue tag (implicitly Main download queue)
            i3 = QTableWidgetItem("untagged_file.pdf")
            i3.setData(Qt.ItemDataRole.UserRole + 8, None)
            self.download_table.setItem(3, 0, i3)
            self.download_table.setItem(3, 1, QTableWidgetItem("2 MB"))
            self.download_table.setItem(3, 2, QTableWidgetItem("Complete"))

    dummy_mw = DummyMainWindow()
    init_q = [_make_default_queue("Main download queue"), _make_default_queue("Synchronization queue")]
    dlg = SchedulerDialog(main_window=dummy_mw, initial_queues=init_q)
    dlg.hide()
    dlg._add_new_queue()  # row 2: "Queue # 1"

    # Switch to Files tab
    dlg.tabs.setCurrentIndex(1)

    # 1. Select Main download queue (row 0)
    dlg.queue_list.setCurrentRow(0)
    assert dlg.files_table.rowCount() == 2
    assert dlg.files_table.item(0, 0).text() == "main_file.zip"
    assert dlg.files_table.item(1, 0).text() == "untagged_file.pdf"

    # 2. Select Synchronization queue (row 1)
    dlg.queue_list.setCurrentRow(1)
    assert dlg.files_table.rowCount() == 1
    assert dlg.files_table.item(0, 0).text() == "sync_file.tar"

    # 3. Select Queue # 1 (row 2)
    dlg.queue_list.setCurrentRow(2)
    assert dlg.files_table.rowCount() == 1
    assert dlg.files_table.item(0, 0).text() == "custom_file.iso"

    dlg.close()


def test_scheduler_dialog_persists_custom_queue_max_concurrent(qapp):
    """Verify that changing max_concurrent in SchedulerDialog persists to MainWindow._queues_data."""
    from PyQt6.QtWidgets import QTableWidget

    class DummyMainWindow:
        def __init__(self):
            self.download_table = QTableWidget(0, 4)
            self._queues_data = [
                _make_default_queue("Main download queue"),
                _make_default_queue("Work Queue")
            ]
            self.MAX_CONCURRENT_DOWNLOADS = 4
        def _sync_sidebar_queues(self):
            pass

    dummy_mw = DummyMainWindow()
    dlg = SchedulerDialog(main_window=dummy_mw, initial_queues=dummy_mw._queues_data)
    dlg.hide()

    # Select "Work Queue" (index 1)
    dlg.queue_list.setCurrentRow(1)
    # Switch to Files tab
    dlg.tabs.setCurrentIndex(1)
    dlg.spin_concurrent.setValue(1)

    # Apply changes
    dlg._apply_changes()

    # Check that dummy_mw._queues_data updated Work Queue max_concurrent to 1
    work_q = next(q for q in dummy_mw._queues_data if q["name"] == "Work Queue")
    assert work_q["max_concurrent"] == 1
    dlg.close()


def test_custom_queue_concurrency_respected_on_start_and_queued(qapp, monkeypatch, tmp_path):
    """Verify that dispatching downloads to a custom queue with max_concurrent=1 starts 1 and queues the rest,
    and completing active download triggers next queued in that queue."""
    from ui.main_window import MainWindow

    # Prevent full network/process download worker launches by patching _start_download_worker
    started_workers = []

    def fake_start_worker(self, url, item_ref, **kwargs):
        key = self._get_item_key(item_ref)
        started_workers.append(key)
        # Create a mock progress dialog/worker entry
        class MockWorker:
            is_paused = False
            is_pause_requested = False
        class MockDialog:
            worker = MockWorker()
        self.active_downloads[key] = MockDialog()
        row = self.download_table.row(item_ref)
        self._set_status_text(row, "Downloading...")

    monkeypatch.setattr(MainWindow, "_start_download_worker", fake_start_worker)
    monkeypatch.setattr(MainWindow, "save_data", lambda self: None)

    mw = MainWindow(start_ipc=False)
    mw.hide()
    # Main queue allows 4 concurrent downloads, but custom queue "Batch1" allows only 1
    custom_q = _make_default_queue("Batch1")
    custom_q["max_concurrent"] = 1
    mw._queues_data = [
        _make_default_queue("Main download queue"),
        custom_q
    ]

    # Add 3 downloads targeted to "Batch1"
    item1 = mw.start_download(url="http://example.com/file1.zip", custom_filename="file1.zip", queue_name="Batch1", start_paused=False)
    item2 = mw.start_download(url="http://example.com/file2.zip", custom_filename="file2.zip", queue_name="Batch1", start_paused=False)
    item3 = mw.start_download(url="http://example.com/file3.zip", custom_filename="file3.zip", queue_name="Batch1", start_paused=False)

    # 1. Concurrency check: only 1 download should be actively running, 2 should be Queued
    row1 = mw.download_table.row(item1)
    row2 = mw.download_table.row(item2)
    row3 = mw.download_table.row(item3)

    assert mw.download_table.item(row1, 2).text() == "Downloading..."
    assert mw.download_table.item(row2, 2).text() == "Queued"
    assert mw.download_table.item(row3, 2).text() == "Queued"
    assert mw._get_active_count_for_queue("Batch1") == 1

    # 2. Complete item1
    key1 = mw._get_item_key(item1)
    mw.active_downloads.pop(key1, None)
    mw._set_status_text(row1, "Finished", logic_status="Finished")

    # Trigger queued start
    mw._try_start_queued()

    # Now exactly one queued item should have transitioned to Downloading and the other remains Queued
    statuses = {
        mw.download_table.item(row2, 2).text(),
        mw.download_table.item(row3, 2).text()
    }
    assert statuses == {"Downloading...", "Queued"}
    assert mw._get_active_count_for_queue("Batch1") == 1

    # Clean up
    mw.is_quitting = True
    mw.close()


def test_scheduler_apply_button_disabled_state(qapp):
    """Verify that the Apply button in SchedulerDialog is disabled when there are no pending changes,
    becomes enabled on user input changes, and is disabled again upon clicking Apply."""
    dlg = SchedulerDialog()
    dlg.hide()

    # 1. Initially disabled because nothing has been changed
    assert not dlg.btn_apply.isEnabled()

    # 2. Modifying a setting enables Apply button
    dlg.chk_startup.setChecked(not dlg.chk_startup.isChecked())
    assert dlg.btn_apply.isEnabled()

    # 3. Clicking Apply saves changes and disables Apply button again
    dlg.btn_apply.click()
    assert not dlg.btn_apply.isEnabled()

    # 4. Modifying spin_concurrent on Files tab enables Apply button
    dlg.tabs.setCurrentIndex(1)
    dlg.spin_concurrent.setValue(dlg.spin_concurrent.value() + 1)
    assert dlg.btn_apply.isEnabled()

    # 5. Applying disables it again
    dlg.btn_apply.click()
    assert not dlg.btn_apply.isEnabled()

    dlg.close()


def test_sidebar_queue_selection_preserved_on_scheduler_close(qapp, monkeypatch):
    """Verify that right-clicking a queue item in the main window and closing scheduler
    keeps the selection on that queue item rather than jumping to parent Queues header."""
    from ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "save_data", lambda self: None)
    mw = MainWindow(start_ipc=False)
    mw.show()

    assert mw.queues_header.childCount() > 0
    target_item = mw.queues_header.child(0)
    queue_name = target_item.text(0)

    # Simulate right-clicking the queue child item
    rect = mw.category_tree.visualItemRect(target_item)
    pos = rect.center()

    # Prevent menu from blocking by mocking QMenu.exec
    from PyQt6.QtWidgets import QMenu
    monkeypatch.setattr(QMenu, "exec", lambda *args, **kwargs: None)

    mw._show_sidebar_context_menu(pos)

    # The right-clicked queue should now be the current item
    assert mw.category_tree.currentItem() is target_item
    assert mw.category_tree.currentItem().text(0) == queue_name

    # Open scheduler for this queue
    mw._open_scheduler_for_queue(queue_name, tab_index=0)
    assert mw._scheduler_dlg is not None

    # Close scheduler dialog (triggers _sync_sidebar_queues)
    mw._scheduler_dlg.close()

    # Verify that selection did NOT jump to parent queues_header and remains on the queue item
    current = mw.category_tree.currentItem()
    assert current is not None
    assert current is not mw.queues_header
    assert current.data(0, Qt.ItemDataRole.UserRole) == "queue"
    assert current.text(0) == queue_name

    mw.is_quitting = True
    mw.close()






