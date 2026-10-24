"""Integration tests: DownloadController + workers."""

import pytest
from unittest.mock import MagicMock, PropertyMock

from PyQt6.QtCore import QThread, pyqtSignal, QObject


class FakeWorker(QObject):
    finished_signal = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.is_paused = False
        self.is_pause_requested = False
        self.paused = False

    def pause(self):
        self.paused = True
        self.is_paused = True


class TestDownloadControllerBasics:
    @pytest.fixture
    def ctrl(self, qapp):
        from core.download_controller import DownloadController
        c = DownloadController()
        yield c
        c.clear()

    def test_initially_empty(self, ctrl):
        assert len(ctrl) == 0

    def test_register_and_get(self, ctrl):
        worker = FakeWorker()
        ctrl.register("key1", worker)
        assert "key1" in ctrl
        assert ctrl.get("key1") is worker

    def test_register_emits_signal(self, ctrl, qapp):
        received = []
        ctrl.worker_registered.connect(received.append)
        ctrl.register("k", FakeWorker())
        assert "k" in received

    def test_unregister(self, ctrl):
        ctrl.register("k", FakeWorker())
        ctrl.unregister("k")
        assert "k" not in ctrl

    def test_unregister_emits_signal(self, ctrl, qapp):
        ctrl.register("k", FakeWorker())
        received = []
        ctrl.worker_unregistered.connect(received.append)
        ctrl.unregister("k")
        assert "k" in received

    def test_dict_protocol_setitem(self, ctrl):
        w = FakeWorker()
        ctrl["dk"] = w
        assert ctrl["dk"] is w

    def test_dict_protocol_contains(self, ctrl):
        ctrl["x"] = FakeWorker()
        assert "x" in ctrl
        assert "y" not in ctrl

    def test_dict_protocol_len(self, ctrl):
        assert len(ctrl) == 0
        ctrl["a"] = FakeWorker()
        assert len(ctrl) == 1

    def test_dict_protocol_keys(self, ctrl):
        ctrl["a"] = FakeWorker()
        ctrl["b"] = FakeWorker()
        keys = ctrl.keys()
        assert "a" in keys
        assert "b" in keys

    def test_dict_protocol_values(self, ctrl):
        ctrl["a"] = FakeWorker()
        vals = ctrl.values()
        assert len(vals) == 1

    def test_dict_protocol_items(self, ctrl):
        ctrl["a"] = FakeWorker()
        items = ctrl.items()
        assert len(items) == 1
        assert items[0][0] == "a"

    def test_clear(self, ctrl):
        ctrl["a"] = FakeWorker()
        ctrl["b"] = FakeWorker()
        ctrl.clear()
        assert len(ctrl) == 0

    def test_get_worker_returns_entry(self, ctrl):
        w = FakeWorker()
        ctrl["k"] = w
        assert ctrl.get_worker("k") is w

    def test_get_worker_missing_returns_none(self, ctrl):
        assert ctrl.get_worker("missing") is None


class TestDownloadControllerSpeed:
    @pytest.fixture
    def ctrl(self, qapp):
        from core.download_controller import DownloadController
        c = DownloadController()
        yield c
        c.clear()

    def test_update_speed(self, ctrl):
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", 1024.0)
        assert ctrl.get_total_speed() == 1024.0

    def test_aggregate_speed_multiple(self, ctrl):
        ctrl.register("a", FakeWorker())
        ctrl.register("b", FakeWorker())
        ctrl.update_speed("a", 100.0)
        ctrl.update_speed("b", 200.0)
        assert ctrl.get_total_speed() == 300.0

    def test_clear_speed(self, ctrl):
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", 500.0)
        ctrl.clear_speed("k")
        assert ctrl.get_total_speed() == 0.0

    def test_unregister_clears_speed(self, ctrl):
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", 500.0)
        ctrl.unregister("k")
        assert ctrl.get_total_speed() == 0.0

    def test_speed_updated_signal(self, ctrl, qapp):
        received = []
        ctrl.speed_updated.connect(lambda k, s: received.append((k, s)))
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", 42.0)
        assert ("k", 42.0) in received

    def test_aggregate_speed_changed_signal(self, ctrl, qapp):
        received = []
        ctrl.aggregate_speed_changed.connect(lambda t, c: received.append((t, c)))
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", 100.0)
        assert len(received) > 0
        assert received[-1][0] == 100.0

    def test_negative_speed_clamped(self, ctrl):
        ctrl.register("k", FakeWorker())
        ctrl.update_speed("k", -100.0)
        assert ctrl.get_total_speed() == 0.0


class TestDownloadControllerPause:
    @pytest.fixture
    def ctrl(self, qapp):
        from core.download_controller import DownloadController
        c = DownloadController()
        yield c
        c.clear()

    def test_pause_existing_worker(self, ctrl):
        w = FakeWorker()
        ctrl.register("k", w)
        result = ctrl.pause("k")
        assert result is True
        assert w.paused is True

    def test_pause_missing_key(self, ctrl):
        assert ctrl.pause("missing") is False

    def test_is_active_true_when_not_paused(self, ctrl):
        w = FakeWorker()
        w.is_paused = False
        ctrl.register("k", w)
        assert ctrl.is_active("k") is True

    def test_is_active_false_when_paused(self, ctrl):
        w = FakeWorker()
        w.is_paused = True
        ctrl.register("k", w)
        assert ctrl.is_active("k") is False

    def test_is_active_missing_key(self, ctrl):
        assert ctrl.is_active("missing") is False

    def test_stop_all_emits_all_stopped(self, ctrl, qapp):
        ctrl.register("a", FakeWorker())
        ctrl.register("b", FakeWorker())
        received = []
        ctrl.all_stopped.connect(lambda: received.append(True))
        ctrl.stop_all()
        assert received

    def test_stop_all_pauses_workers(self, ctrl):
        w1 = FakeWorker()
        w2 = FakeWorker()
        ctrl.register("a", w1)
        ctrl.register("b", w2)
        ctrl.stop_all()
        assert w1.paused is True
        assert w2.paused is True


class TestDownloadControllerActiveCount:
    @pytest.fixture
    def ctrl(self, qapp):
        from core.download_controller import DownloadController
        c = DownloadController()
        yield c
        c.clear()

    def test_empty_returns_zero(self, ctrl):
        assert ctrl.get_active_count() == 0

    def test_active_workers_counted(self, ctrl):
        w = FakeWorker()
        w.is_paused = False
        ctrl.register("a", w)
        ctrl.register("b", FakeWorker())
        count = ctrl.get_active_count()
        assert count >= 1


class TestGlobalDownloadController:
    def test_singleton_created(self, qapp):
        from core.download_controller import get_download_controller, set_global_download_controller, DownloadController
        set_global_download_controller(None)
        ctrl = get_download_controller()
        assert isinstance(ctrl, DownloadController)

    def test_set_and_get(self, qapp):
        from core.download_controller import get_download_controller, set_global_download_controller, DownloadController
        custom = DownloadController()
        set_global_download_controller(custom)
        assert get_download_controller() is custom
        set_global_download_controller(None)

    def test_worker_finished_auto_unregister(self, qapp):
        from core.download_controller import DownloadController
        ctrl = DownloadController()
        worker = FakeWorker()
        entry = MagicMock()
        entry.worker = worker
        entry.side_effect = None
        ctrl.register("k", entry)
        worker.finished_signal.emit(0, "Complete")
        assert "k" not in ctrl
