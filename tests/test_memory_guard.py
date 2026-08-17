import pytest
from PyQt6.QtWidgets import QDialog, QWidget, QLabel
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from core.memory_guard import MemoryGuard


class DummyEmitter(QObject):
    test_signal = pyqtSignal(str)


def test_memory_guard_collect_garbage():
    collected = MemoryGuard.collect_garbage()
    assert isinstance(collected, int)
    assert collected >= 0


def test_memory_guard_trim_heap():
    result = MemoryGuard.trim_heap()
    assert isinstance(result, bool)


def test_memory_guard_clean_and_trim():
    # Should execute without errors
    MemoryGuard.clean_and_trim()


def test_memory_guard_safe_delete_later(qapp):
    widget = QWidget()
    MemoryGuard.safe_delete_later(widget)
    # None or non-QObject should also safely pass without error
    MemoryGuard.safe_delete_later(None)
    MemoryGuard.safe_delete_later("not_a_qobject")


def test_memory_guard_safe_disconnect():
    emitter = DummyEmitter()
    called = []
    slot = lambda msg: called.append(msg)
    emitter.test_signal.connect(slot)
    
    # Successful disconnect
    assert MemoryGuard.safe_disconnect(emitter.test_signal, slot) is True
    
    # Safe repeated disconnect (no crash)
    assert MemoryGuard.safe_disconnect(emitter.test_signal, slot) is False
    assert MemoryGuard.safe_disconnect(None) is False


def test_memory_guard_auto_manage_dialog(qapp):
    dlg = QDialog()
    MemoryGuard.auto_manage_dialog(dlg)
    counts = MemoryGuard.get_tracked_counts()
    assert "active_dialogs" in counts
    assert counts["active_dialogs"] >= 1
    
    # Finish dialog
    dlg.accept()
    dlg.close()


def test_memory_guard_track_worker(qapp):
    worker = DummyEmitter()
    MemoryGuard.track_worker(worker)
    counts = MemoryGuard.get_tracked_counts()
    assert "active_workers" in counts
    assert counts["active_workers"] >= 1


def test_memory_guard_periodic_timer(qapp):
    timer = MemoryGuard.start_periodic_trim(interval_ms=1000)
    assert isinstance(timer, QTimer)
    assert timer.isActive()
    timer.stop()
