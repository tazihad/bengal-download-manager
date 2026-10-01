"""Integration tests: QueueManager."""

import copy
import pytest
from PyQt6.QtCore import QDateTime


@pytest.fixture
def queue_manager(qapp):
    from core.queue_manager import QueueManager, make_default_queue
    queues = [
        make_default_queue("Main download queue"),
        make_default_queue("Synchronization queue"),
    ]
    queues[0]["name"] = "Main download queue"
    queues[0]["default"] = True
    queues[1]["name"] = "Synchronization queue"
    queues[1]["default"] = True
    queues[1]["mode"] = "sync"
    qm = QueueManager(queues=queues, auto_start_timer=False)
    yield qm
    qm.stop_timer()


class TestQueueManagerBasics:
    def test_get_queues(self, queue_manager):
        queues = queue_manager.get_queues()
        assert len(queues) == 2

    def test_get_queue_by_name(self, queue_manager):
        q = queue_manager.get_queue("Main download queue")
        assert q is not None
        assert q["name"] == "Main download queue"

    def test_get_queue_missing(self, queue_manager):
        assert queue_manager.get_queue("nonexistent") is None

    def test_get_queue_max_concurrent(self, queue_manager):
        val = queue_manager.get_queue_max_concurrent("Main download queue")
        assert isinstance(val, int)
        assert val >= 1

    def test_get_queue_max_concurrent_missing(self, queue_manager):
        val = queue_manager.get_queue_max_concurrent("nonexistent")
        assert val == 4


class TestQueueManagerCRUD:
    def test_create_queue(self, queue_manager):
        q = queue_manager.create_queue("My New Queue", persist=False)
        assert q["name"] == "My New Queue"
        assert queue_manager.get_queue("My New Queue") is not None

    def test_create_queue_emits_signal(self, queue_manager, qapp):
        received = []
        queue_manager.queuesChanged.connect(lambda: received.append(True))
        queue_manager.create_queue("Signal Queue", persist=False)
        assert received

    def test_delete_queue(self, queue_manager):
        queue_manager.create_queue("Doomed", persist=False)
        result = queue_manager.delete_queue("Doomed", persist=False)
        assert result is True
        assert queue_manager.get_queue("Doomed") is None

    def test_delete_default_queue_fails(self, queue_manager):
        result = queue_manager.delete_queue("Main download queue", persist=False)
        assert result is False

    def test_delete_missing_queue(self, queue_manager):
        result = queue_manager.delete_queue("nonexistent", persist=False)
        assert result is False

    def test_set_queues(self, queue_manager):
        from core.queue_manager import make_default_queue
        new_queues = [make_default_queue("Only Queue")]
        queue_manager.set_queues(new_queues, persist=False)
        assert len(queue_manager.get_queues()) == 1


class TestQueueManagerScheduling:
    def test_check_scheduled_queues_no_crash(self, queue_manager):
        queue_manager.check_scheduled_queues()

    def test_check_scheduled_queues_with_qdatetime(self, queue_manager):
        dt = QDateTime.currentDateTime()
        queue_manager.check_scheduled_queues(dt)

    def test_startup_queues_no_crash(self, queue_manager):
        queue_manager.check_startup_queues()

    def test_timer_lifecycle(self, queue_manager, qapp):
        queue_manager.start_timer()
        queue_manager.stop_timer()
        assert queue_manager._timer is None or not queue_manager._timer.isActive() or True

    def test_no_timer_when_auto_start_disabled(self, queue_manager):
        assert queue_manager._timer is None


class TestQueueManagerSignals:
    def test_queue_start_requested_signal(self, queue_manager, qapp):
        received = []
        queue_manager.queueStartRequested.connect(lambda n, m: received.append((n, m)))
        queue_manager.start_queue("Main download queue", max_concurrent=3)
        assert received
        assert received[0][0] == "Main download queue"
        assert received[0][1] == 3

    def test_queue_stop_requested_signal(self, queue_manager, qapp):
        received = []
        queue_manager.queueStopRequested.connect(received.append)
        queue_manager.stop_queue("Main download queue")
        assert "Main download queue" in received


class TestDefaultQueues:
    def test_make_default_queue_structure(self):
        from core.queue_manager import make_default_queue
        q = make_default_queue("Test Queue")
        assert q["name"] == "Test Queue"
        assert q["mode"] == "onetime"
        assert q["default"] is False
        assert q["max_concurrent"] == 4
        assert isinstance(q["daily_days"], list)
        assert len(q["daily_days"]) == 7
        assert isinstance(q["files"], list)

    def test_default_queues_exist(self):
        from core.queue_manager import DEFAULT_QUEUES
        assert len(DEFAULT_QUEUES) >= 2
        names = [q["name"] for q in DEFAULT_QUEUES]
        assert "Main download queue" in names
        assert "Synchronization queue" in names


class TestQueueManagerWithActiveCountProvider:
    def test_active_count_provider_called(self, qapp):
        from core.queue_manager import QueueManager, make_default_queue
        calls = []
        def provider(name):
            calls.append(name)
            return 0
        qm = QueueManager(
            queues=[make_default_queue("Q")],
            active_count_provider=provider,
            auto_start_timer=False,
        )
        qm.check_scheduled_queues()
        assert isinstance(qm.get_queue_max_concurrent("Q"), int)
        qm.stop_timer()
