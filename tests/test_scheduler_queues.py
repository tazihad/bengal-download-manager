"""
Core Unit and Integration Tests for Queues and Scheduler Functionality.
"""

import pytest
from PyQt6.QtCore import QTime, QDate
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
