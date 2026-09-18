"""
Unit tests for the deep QueueManager module.
Verifies queue defaults, CRUD lifecycle, concurrency bounds, schedule evaluation,
and signal dispatching in headless execution.
"""

import pytest
from PyQt6.QtCore import QDate, QDateTime, QTime

from core.queue_manager import (
    DEFAULT_QUEUES,
    QueueManager,
    make_default_queue,
    _make_default_queue,
)


def test_default_queues_and_factory():
    """Verify DEFAULT_QUEUES structure and make_default_queue factory."""
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

    custom_q = make_default_queue("Custom Test Queue")
    assert custom_q["name"] == "Custom Test Queue"
    assert custom_q["default"] is False
    assert custom_q["mode"] == "onetime"
    assert custom_q["max_concurrent"] == 4

    # Test backward compatibility alias
    alias_q = _make_default_queue("Alias Queue")
    assert alias_q["name"] == "Alias Queue"


def test_queue_manager_crud():
    """Test QueueManager CRUD operations and default queue protections."""
    qm = QueueManager(queues=DEFAULT_QUEUES, auto_start_timer=False)

    queues = qm.get_queues()
    assert len(queues) == 2
    assert qm.get_queue("Main download queue") is not None
    assert qm.get_queue("Nonexistent Queue") is None

    # Max concurrent lookup
    assert qm.get_queue_max_concurrent("Main download queue") == 4
    assert qm.get_queue_max_concurrent("Nonexistent") == 4

    # Create new queue
    new_q = qm.create_queue("Night Queue", persist=False)
    assert new_q["name"] == "Night Queue"
    assert len(qm.get_queues()) == 3
    assert qm.get_queue("Night Queue") is not None

    # Cannot delete default queue
    assert not qm.delete_queue("Main download queue", persist=False)
    assert len(qm.get_queues()) == 3

    # Delete custom queue
    assert qm.delete_queue("Night Queue", persist=False)
    assert len(qm.get_queues()) == 2
    assert qm.get_queue("Night Queue") is None


def test_queue_manager_signals():
    """Verify queueStartRequested and queueStopRequested signal emissions."""
    qm = QueueManager(queues=DEFAULT_QUEUES, auto_start_timer=False)

    started = []
    stopped = []

    qm.queueStartRequested.connect(lambda name, max_c: started.append((name, max_c)))
    qm.queueStopRequested.connect(lambda name: stopped.append(name))

    qm.start_queue("Main download queue")
    assert started == [("Main download queue", 4)]

    qm.start_queue("Synchronization queue", max_concurrent=2)
    assert started == [("Main download queue", 4), ("Synchronization queue", 2)]

    qm.stop_queue("Main download queue")
    assert stopped == ["Main download queue"]


def test_queue_manager_startup_queues():
    """Verify check_startup_queues triggers queues flagged with start_on_startup."""
    custom_queues = [
        {
            **DEFAULT_QUEUES[0],
            "start_on_startup": True,
            "max_concurrent": 3,
        },
        {
            **DEFAULT_QUEUES[1],
            "start_on_startup": False,
        },
    ]

    qm = QueueManager(queues=custom_queues, auto_start_timer=False)
    started = []
    qm.queueStartRequested.connect(lambda name, max_c: started.append((name, max_c)))

    qm.check_startup_queues()
    assert started == [("Main download queue", 3)]


def test_queue_manager_schedule_daily_evaluation():
    """Verify check_scheduled_queues starts and stops queues based on daily schedules."""
    test_queues = [
        {
            **DEFAULT_QUEUES[0],
            "start_at_enabled": True,
            "start_at_time": "22:00:00",
            "schedule_type": "daily",
            "daily_days": [True] * 7,
            "stop_at_enabled": True,
            "stop_at_time": "06:00:00",
            "max_concurrent": 5,
        }
    ]

    qm = QueueManager(queues=test_queues, auto_start_timer=False)
    started = []
    stopped = []
    qm.queueStartRequested.connect(lambda name, max_c: started.append((name, max_c)))
    qm.queueStopRequested.connect(lambda name: stopped.append(name))

    # Time that does not match
    dt_mismatch = QDateTime(QDate(2026, 9, 18), QTime(12, 0, 0))
    qm.check_scheduled_queues(dt=dt_mismatch)
    assert len(started) == 0
    assert len(stopped) == 0

    # Matching start time
    dt_start = QDateTime(QDate(2026, 9, 18), QTime(22, 0, 0))
    qm.check_scheduled_queues(dt=dt_start)
    assert started == [("Main download queue", 5)]

    # Repeating in the same minute is deduplicated
    qm.check_scheduled_queues(dt=dt_start)
    assert len(started) == 1

    # Matching stop time
    dt_stop = QDateTime(QDate(2026, 9, 19), QTime(6, 0, 0))
    qm.check_scheduled_queues(dt=dt_stop)
    assert stopped == ["Main download queue"]


def test_queue_manager_schedule_once_evaluation():
    """Verify once-only date schedule matching."""
    test_queues = [
        {
            **DEFAULT_QUEUES[0],
            "start_at_enabled": True,
            "start_at_time": "14:30:00",
            "schedule_type": "once",
            "once_date": "2026-10-01",
            "max_concurrent": 2,
        }
    ]

    qm = QueueManager(queues=test_queues, auto_start_timer=False)
    started = []
    qm.queueStartRequested.connect(lambda name, max_c: started.append((name, max_c)))

    # Wrong date, matching time
    qm.check_scheduled_queues(dt=QDateTime(QDate(2026, 9, 30), QTime(14, 30, 0)))
    assert len(started) == 0

    # Correct date, matching time
    qm.check_scheduled_queues(dt=QDateTime(QDate(2026, 10, 1), QTime(14, 30, 0)))
    assert started == [("Main download queue", 2)]
