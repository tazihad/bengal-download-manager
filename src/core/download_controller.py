"""
Download Controller
===================
Deep module coordinating active download worker threads, progress dialogs,
per-download transfer rates, and aggregate bandwidth metrics.

Architecture:
- High depth: Encapsulates worker tracking, thread liveness resolution,
  speed aggregation, and graceful bulk termination behind an expressive
  signal-driven interface.
- Seam: Sits between presentation views (QWidget MainWindow, Kirigami QML DownloadBridge)
  and concrete worker adapters (DownloadWorker, Aria2Worker, YtDlpDownloadWorker).
"""

import threading
import logging
from typing import Dict, Any, Optional, List, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("bengal.core.download_controller")


class DownloadController(QObject):
    """
    Supervises active download workers, associated UI progress dialogs,
    and calculates real-time bandwidth metrics.
    """

    speed_updated = pyqtSignal(object, float)             # (download_key, speed_bytes_per_sec)
    aggregate_speed_changed = pyqtSignal(float, int)      # (total_speed_bytes_sec, active_count)
    worker_registered = pyqtSignal(object)                # (download_key)
    worker_unregistered = pyqtSignal(object)              # (download_key)
    all_stopped = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._entries: Dict[Any, Any] = {}
        self._speeds: Dict[Any, float] = {}
        self._lock = threading.RLock()

    # --- Dictionary protocol compatibility for seamless caller migration ---
    def __getitem__(self, key: Any) -> Any:
        with self._lock:
            return self._entries[key]

    def __setitem__(self, key: Any, val: Any) -> None:
        self.register(key, val)

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._entries

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._entries.get(key, default)

    def pop(self, key: Any, default: Any = None) -> Any:
        return self.unregister(key, default)

    def keys(self):
        with self._lock:
            return list(self._entries.keys())

    def values(self):
        with self._lock:
            return list(self._entries.values())

    def items(self):
        with self._lock:
            return list(self._entries.items())

    # --- Core Lifecycle Management ---
    def register(self, key: Any, entry: Any, dialog: Optional[Any] = None) -> None:
        """
        Registers an active download worker or progress dialog under a unique key/id.
        """
        with self._lock:
            self._entries[key] = entry
            # Auto-hook worker finished signal if possible to safely unregister
            worker = getattr(entry, "worker", entry)
            if worker and hasattr(worker, "finished_signal"):
                try:
                    worker.finished_signal.connect(lambda *_: self.unregister(key))
                except Exception:
                    pass

        self.worker_registered.emit(key)
        self._notify_aggregate_speed()

    def unregister(self, key: Any, default: Any = None) -> Any:
        """
        Unregisters an active download entry and cleans up its bandwidth metric.
        """
        with self._lock:
            val = self._entries.pop(key, default)
            self._speeds.pop(key, None)

        if val is not default:
            self.worker_unregistered.emit(key)
            self._notify_aggregate_speed()
        return val

    def get_worker(self, key: Any) -> Optional[Any]:
        """Resolves the underlying worker thread from the registered entry."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            return getattr(entry, "worker", entry)

    def get_dialog(self, key: Any) -> Optional[Any]:
        """Resolves the progress dialog if the entry is or owns a dialog."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if hasattr(entry, "lbl_main_status") or hasattr(entry, "worker"):
                return entry
            return None

    def is_active(self, key: Any) -> bool:
        """Checks if a download entry is currently active and unpaused."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry is True:
                return True
            worker = getattr(entry, "worker", entry)
            if worker is None:
                return False
            is_paused = getattr(worker, "is_paused", False) or getattr(worker, "is_pause_requested", False)
            return not is_paused

    def update_speed(self, key: Any, speed: float) -> None:
        """Updates instantaneous transfer speed for a specific download key."""
        with self._lock:
            self._speeds[key] = max(0.0, float(speed))

        self.speed_updated.emit(key, speed)
        self._notify_aggregate_speed()

    def clear_speed(self, key: Any) -> None:
        """Clears transfer rate for a specific download key."""
        with self._lock:
            self._speeds.pop(key, None)
        self._notify_aggregate_speed()

    def get_total_speed(self) -> float:
        """Returns the sum of all active download transfer speeds in bytes/sec."""
        with self._lock:
            return sum(self._speeds.values()) if self._speeds else 0.0

    def get_active_count(self) -> int:
        """Counts how many registered downloads are currently actively transferring."""
        with self._lock:
            active_count = 0
            for k, entry in self._entries.items():
                if self.is_active(k):
                    active_count += 1
            return active_count or len(self._speeds)

    def pause(self, key: Any) -> bool:
        """Pauses a specific active worker by key."""
        worker = self.get_worker(key)
        if worker and hasattr(worker, "pause"):
            try:
                worker.pause()
                self.clear_speed(key)
                return True
            except Exception as e:
                logger.error("[DownloadController] Error pausing worker %s: %s", key, e)
        return False

    def stop_all(self) -> None:
        """
        Gracefully pauses or cancels all registered download workers
        and clears active speed measurements.
        """
        with self._lock:
            entries_snapshot = list(self._entries.items())

        for key, entry in entries_snapshot:
            worker = getattr(entry, "worker", entry)
            if worker is not None and hasattr(worker, "pause"):
                try:
                    worker.pause()
                except Exception:
                    pass

            # Update dialog visual controls if attached
            if hasattr(entry, "lbl_main_status"):
                try:
                    entry.lbl_main_status.setText("Paused")
                    if hasattr(entry, "btn_pause"):
                        entry.btn_pause.setText("Resume")
                    if hasattr(entry, "btn_cancel"):
                        entry.btn_cancel.setText("Close")
                    if hasattr(entry, "lbl_speed"):
                        entry.lbl_speed.setText("0.00 B/s")
                    if hasattr(entry, "lbl_time"):
                        entry.lbl_time.setText("-")
                except Exception:
                    pass

        with self._lock:
            self._speeds.clear()

        self.all_stopped.emit()
        self._notify_aggregate_speed()

    def _notify_aggregate_speed(self) -> None:
        total_speed = self.get_total_speed()
        active_count = self.get_active_count()
        self.aggregate_speed_changed.emit(total_speed, active_count)


# Module-level singleton helper
_GLOBAL_DOWNLOAD_CONTROLLER: Optional[DownloadController] = None


def get_download_controller() -> DownloadController:
    """Provides a shared application-wide DownloadController instance."""
    global _GLOBAL_DOWNLOAD_CONTROLLER
    if _GLOBAL_DOWNLOAD_CONTROLLER is None:
        _GLOBAL_DOWNLOAD_CONTROLLER = DownloadController()
    return _GLOBAL_DOWNLOAD_CONTROLLER
