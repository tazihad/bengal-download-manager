"""Unit tests for core.memory_guard."""

import gc
import pytest
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject


class TestMemoryGuardBasics:
    def test_is_widget_alive_with_real_widget(self, qapp):
        from core.memory_guard import MemoryGuard
        w = QWidget()
        assert MemoryGuard.is_widget_alive(w) is True
        w.deleteLater()

    def test_is_widget_alive_with_none(self):
        from core.memory_guard import MemoryGuard
        assert MemoryGuard.is_widget_alive(None) is False

    def test_is_widget_alive_with_non_widget(self):
        from core.memory_guard import MemoryGuard
        assert MemoryGuard.is_widget_alive("not a widget") is False

    def test_trim_heap_returns_bool(self):
        from core.memory_guard import MemoryGuard
        result = MemoryGuard.trim_heap()
        assert isinstance(result, bool)

    def test_collect_garbage_returns_int(self):
        from core.memory_guard import MemoryGuard
        gc.collect()
        count = MemoryGuard.collect_garbage()
        assert isinstance(count, int)
        assert count >= 0

    def test_clean_and_trim_no_crash(self):
        from core.memory_guard import MemoryGuard
        MemoryGuard.clean_and_trim()

    def test_safe_delete_later_none(self):
        from core.memory_guard import MemoryGuard
        MemoryGuard.safe_delete_later(None)

    def test_safe_delete_later_object(self, qapp):
        from core.memory_guard import MemoryGuard
        obj = QObject()
        MemoryGuard.safe_delete_later(obj)

    def test_safe_disconnect_no_signal(self):
        from core.memory_guard import MemoryGuard
        result = MemoryGuard.safe_disconnect(MagicMock())
        assert isinstance(result, bool)

    def test_auto_manage_dialog(self, qapp):
        from core.memory_guard import MemoryGuard
        w = QWidget()
        MemoryGuard.auto_manage_dialog(w)
        counts = MemoryGuard.get_tracked_counts()
        assert isinstance(counts, dict)
        w.deleteLater()

    def test_track_worker(self, qapp):
        from core.memory_guard import MemoryGuard
        obj = QObject()
        MemoryGuard.track_worker(obj)
        counts = MemoryGuard.get_tracked_counts()
        assert isinstance(counts, dict)

    def test_get_tracked_counts_returns_dict(self):
        from core.memory_guard import MemoryGuard
        counts = MemoryGuard.get_tracked_counts()
        assert isinstance(counts, dict)

    def test_start_periodic_trim(self, qapp):
        from core.memory_guard import MemoryGuard
        parent = QWidget()
        timer = MemoryGuard.start_periodic_trim(parent, interval_ms=5000)
        assert timer is not None
        assert timer.interval() == 5000
        timer.stop()
        parent.deleteLater()
