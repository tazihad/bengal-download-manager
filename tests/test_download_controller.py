"""
Unit tests for DownloadController deep module.
"""

from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from core.download_controller import DownloadController, get_download_controller


class DummyWorker(QObject):
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_paused = False
        self.is_pause_requested = False
        self.pause_called = False

    def pause(self):
        self.is_paused = True
        self.pause_called = True


@pytest.fixture
def controller(qtbot):
    ctrl = DownloadController()
    yield ctrl


def test_initial_state(controller):
    assert len(controller) == 0
    assert controller.get_total_speed() == 0.0
    assert controller.get_active_count() == 0


def test_dict_protocol_and_registration(controller):
    worker = DummyWorker()
    controller["dl_1"] = worker

    assert "dl_1" in controller
    assert len(controller) == 1
    assert controller["dl_1"] is worker
    assert controller.get("dl_1") is worker
    assert controller.get_worker("dl_1") is worker
    assert controller.is_active("dl_1") is True

    # Pop
    popped = controller.pop("dl_1")
    assert popped is worker
    assert "dl_1" not in controller
    assert len(controller) == 0


def test_speed_tracking_and_aggregation(controller, qtbot):
    w1 = DummyWorker()
    w2 = DummyWorker()

    controller.register(1, w1)
    controller.register(2, w2)

    speed_signals = []
    agg_signals = []
    controller.speed_updated.connect(lambda k, s: speed_signals.append((k, s)))
    controller.aggregate_speed_changed.connect(lambda total, cnt: agg_signals.append((total, cnt)))

    controller.update_speed(1, 1024.0 * 500)
    controller.update_speed(2, 1024.0 * 500)

    assert controller.get_total_speed() == 1024.0 * 1000
    assert controller.get_active_count() == 2
    assert len(speed_signals) == 2
    assert len(agg_signals) >= 2


def test_pause_and_stop_all(controller):
    w1 = DummyWorker()
    w2 = DummyWorker()

    controller.register("item_a", w1)
    controller.register("item_b", w2)
    controller.update_speed("item_a", 5000)
    controller.update_speed("item_b", 7000)

    assert controller.get_total_speed() == 12000
    assert controller.pause("item_a") is True
    assert w1.pause_called is True

    # Stop all
    controller.stop_all()
    assert w2.pause_called is True
    assert controller.get_total_speed() == 0.0


def test_singleton_accessor():
    c1 = get_download_controller()
    c2 = get_download_controller()
    assert c1 is c2
    assert isinstance(c1, DownloadController)
