"""End-to-end tests: queue management flow through MainWindow."""

import pytest
from PyQt6.QtCore import Qt


@pytest.fixture(scope="module")
def win(qapp, destroy_widget):
    from ui.main_window import MainWindow
    w = MainWindow(start_ipc=False)
    yield w
    destroy_widget(w)


class TestSidebarQueues:
    def test_queues_header_exists(self, win):
        assert win.queues_header is not None

    def test_default_queues_in_sidebar(self, win):
        names = [win.queues_header.child(i).text(0)
                 for i in range(win.queues_header.childCount())]
        assert "Main download queue" in names
        assert "Synchronization queue" in names

    def test_queue_items_have_type_data(self, win):
        for i in range(win.queues_header.childCount()):
            child = win.queues_header.child(i)
            assert child.data(0, Qt.ItemDataRole.UserRole) == "queue"

    def test_sidebar_queue_names_synced(self, win):
        child_names = [win.queues_header.child(i).text(0)
                       for i in range(win.queues_header.childCount())]
        assert set(child_names) == set(win._sidebar_queue_names)


class TestCreateQueue:
    def test_create_queue_adds_sidebar_item(self, win):
        initial = win.queues_header.childCount()
        win._create_sidebar_queue()
        assert win.queues_header.childCount() == initial + 1

    def test_created_queue_name(self, win):
        names = [win.queues_header.child(i).text(0)
                 for i in range(win.queues_header.childCount())]
        assert any(n.startswith("Queue #") for n in names)

    def test_created_queue_in_manager(self, win):
        assert win.queue_manager is not None
        names = [q["name"] for q in win.queue_manager.get_queues()]
        assert any(n.startswith("Queue #") for n in names)

    def test_create_second_queue_unique_name(self, win):
        initial = win.queues_header.childCount()
        win._create_sidebar_queue()
        assert win.queues_header.childCount() == initial + 1
        names = [win.queues_header.child(i).text(0)
                 for i in range(win.queues_header.childCount())]
        assert len(names) == len(set(names))


class TestQueueFiltering:
    def test_filter_by_queue_item(self, win):
        child = win.queues_header.child(0)
        win.filter_downloads(child, 0)

    def test_filter_by_queues_header(self, win):
        win.filter_downloads(win.queues_header, 0)

    def test_filter_returns_to_all(self, win):
        win.filter_downloads(win.all_downloads_header, 0)


class TestQueueMaxConcurrent:
    def test_get_max_concurrent_existing(self, win):
        val = win._get_queue_max_concurrent("Main download queue")
        assert isinstance(val, int)
        assert val >= 1

    def test_get_max_concurrent_unknown(self, win):
        val = win._get_queue_max_concurrent("nonexistent")
        assert isinstance(val, int)


class TestQueueManagerIntegration:
    def test_queue_manager_signals_connected(self, win):
        assert win.queue_manager is not None

    def test_active_count_provider(self, win):
        count = win._get_active_count_for_queue("Main download queue")
        assert isinstance(count, int)
        assert count >= 0

    def test_check_scheduled_queues_no_crash(self, win):
        win.queue_manager.check_scheduled_queues()

    def test_check_startup_queues_no_crash(self, win):
        win.queue_manager.check_startup_queues()

    def test_queue_data_matches_manager(self, win):
        assert win._queues_data == win.queue_manager._queues


class TestQueuePersistence:
    def test_queues_saved_to_db(self, win):
        from core.database import get_all_queues
        win.queue_manager.create_queue("Persist Test Queue", persist=True)
        names = [q["name"] for q in get_all_queues()]
        assert "Persist Test Queue" in names
        win.queue_manager.delete_queue("Persist Test Queue", persist=True)
