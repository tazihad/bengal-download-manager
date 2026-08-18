"""
Memory Guard & Leak Protection Subsystem
========================================
High-performance memory management, garbage collection, and heap-trimming
architecture for Bengal Download Manager (PyQt6 / Python).

Features:
- Linux glibc malloc_trim(0) and cross-platform OS heap trimming
- Generation-2 cyclic garbage collection triggers
- QObject / QWidget safe deletion and signal disconnection
- Weakref-based active object observability and leak detection
- Non-blocking periodic memory compaction
"""

import sys
import gc
import ctypes
import logging
import weakref
import platform
from typing import Optional, Any
from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger("bengal.memory_guard")

# Load C allocator trim function once if available
_libc = None
_has_malloc_trim = False

if platform.system() == "Linux":
    try:
        import ctypes.util
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        _libc = ctypes.CDLL(libc_name)
        if hasattr(_libc, "malloc_trim"):
            _has_malloc_trim = True
    except Exception as e:
        logger.debug("glibc malloc_trim unavailable: %s", e)


class MemoryGuard:
    """
    Central memory guard providing leak protection, heap compaction,
    and life-cycle management for PyQt6 widgets, dialogs, and worker threads.
    """

    _tracked_dialogs = weakref.WeakSet()
    _tracked_workers = weakref.WeakSet()

    @classmethod
    def trim_heap(cls) -> bool:
        """
        Requests the underlying C runtime / OS to release free heap memory back to the kernel.
        - Linux: glibc malloc_trim(0)
        - Windows: SetProcessWorkingSetSize(-1, -1)
        """
        trimmed = False
        try:
            if _has_malloc_trim and _libc:
                res = _libc.malloc_trim(0)
                trimmed = bool(res)
            elif platform.system() == "Windows":
                try:
                    kernel32 = ctypes.windll.kernel32
                    current_process = kernel32.GetCurrentProcess()
                    kernel32.SetProcessWorkingSetSize(current_process, -1, -1)
                    trimmed = True
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Error trimming heap: %s", e)
        return trimmed

    @classmethod
    def collect_garbage(cls) -> int:
        """
        Executes full generation cyclic garbage collection.
        Returns number of unreachable objects collected.
        """
        try:
            return gc.collect()
        except Exception:
            return 0

    @classmethod
    def clean_and_trim(cls) -> None:
        """
        Runs cyclic garbage collection followed by OS heap trimming.
        Call on high-churn events (download completion, batch deletions, dialog closure).
        """
        try:
            cls.collect_garbage()
            cls.trim_heap()
        except Exception as e:
            logger.debug("Memory clean_and_trim failed: %s", e)

    @classmethod
    def is_widget_alive(cls, widget: Any) -> bool:
        """Checks if a QWidget is non-None and has a valid, non-deleted underlying C++ instance."""
        if widget is None:
            return False
        try:
            # Calling isVisible() on a deleted C++ QObject raises RuntimeError
            _ = widget.isVisible()
            return True
        except (RuntimeError, AttributeError, Exception):
            return False

    @classmethod
    def safe_delete_later(cls, obj: Any) -> None:
        """
        Safely schedules deleteLater() on a QObject / QWidget if it hasn't already
        been scheduled or destroyed.
        """
        if obj is None:
            return
        try:
            if isinstance(obj, QObject):
                obj.deleteLater()
        except (RuntimeError, AttributeError, Exception):
            pass

    @classmethod
    def safe_disconnect(cls, signal: Any, slot: Optional[Any] = None) -> bool:
        """
        Safely disconnects a PyQt signal without raising TypeError/RuntimeError
        if no connection exists.
        """
        if signal is None:
            return False
        try:
            if slot is not None:
                signal.disconnect(slot)
            else:
                signal.disconnect()
            return True
        except (TypeError, RuntimeError, Exception):
            return False

    @classmethod
    def auto_manage_dialog(cls, dialog: QWidget) -> None:
        """
        Configures dialog for automatic C++ and Python memory deallocation on close:
        - Sets WA_DeleteOnClose attribute
        - Registers weak reference for leak detection
        - Triggers memory compaction on finish
        """
        if not isinstance(dialog, QWidget):
            return
        try:
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            cls._tracked_dialogs.add(dialog)
            if hasattr(dialog, "finished"):
                dialog.finished.connect(lambda: cls.clean_and_trim())
        except Exception as e:
            logger.debug("Failed to auto-manage dialog: %s", e)

    @classmethod
    def track_worker(cls, worker: QObject) -> None:
        """Registers a worker thread for life-cycle tracking and automatic cleanup."""
        if not isinstance(worker, QObject):
            return
        try:
            cls._tracked_workers.add(worker)
            if hasattr(worker, "finished"):
                worker.finished.connect(lambda: cls.safe_delete_later(worker))
        except Exception as e:
            logger.debug("Failed to track worker: %s", e)

    @classmethod
    def get_tracked_counts(cls) -> dict:
        """Returns the number of currently active/alive tracked dialogs and workers."""
        return {
            "active_dialogs": len(cls._tracked_dialogs),
            "active_workers": len(cls._tracked_workers),
        }

    @classmethod
    def start_periodic_trim(cls, parent: Optional[QObject] = None, interval_ms: int = 45000) -> QTimer:
        """
        Creates and starts a low-frequency QTimer to run periodic heap compaction.
        """
        timer = QTimer(parent)
        timer.setInterval(interval_ms)
        timer.timeout.connect(cls.clean_and_trim)
        timer.start()
        return timer
