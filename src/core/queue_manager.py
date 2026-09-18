"""
QueueManager Module for Bengal Download Manager.
Provides canonical domain models, scheduling rules, concurrency evaluation,
and lifecycle coordination for download queues.
"""

import copy
import logging
import time
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import QDateTime, QObject, QTimer, pyqtSignal

logger = logging.getLogger("bengal.core.queue_manager")

# Default queue definitions
DEFAULT_QUEUES: List[Dict] = [
    {
        "name": "Main download queue",
        "default": True,
        "mode": "onetime",          # locked to "onetime" for this queue
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",   # "once" or "daily"
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],  # Sun-Sat
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    },
    {
        "name": "Synchronization queue",
        "default": True,
        "mode": "sync",             # locked to "sync" for this queue
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    },
]


def make_default_queue(name: str) -> Dict:
    """Creates a new queue dictionary initialized with standard default properties."""
    return {
        "name": name,
        "default": False,
        "mode": "onetime",
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    }


# Backwards compatibility alias
_make_default_queue = make_default_queue


class QueueManager(QObject):
    """
    Deep core controller managing queue definitions, schedule evaluation,
    concurrency bounds, and execution signaling.
    """

    queueStartRequested = pyqtSignal(str, int)  # (queue_name, max_concurrent)
    queueStopRequested = pyqtSignal(str)        # queue_name
    queuesChanged = pyqtSignal()

    def __init__(
        self,
        queues: Optional[List[Dict]] = None,
        active_count_provider: Optional[Callable[[str], int]] = None,
        auto_start_timer: bool = True,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._active_count_provider = active_count_provider
        self._last_scheduled_minute: Dict[str, bool] = {}
        self._last_sync_times: Dict[str, float] = {}

        if queues is not None:
            self._queues = [copy.deepcopy(q) for q in queues]
        else:
            try:
                from core.database import get_all_queues
                db_q = get_all_queues()
                self._queues = [copy.deepcopy(q) for q in (db_q if db_q else DEFAULT_QUEUES)]
            except Exception as e:
                logger.warning("Failed to load queues from database: %s", e)
                self._queues = copy.deepcopy(DEFAULT_QUEUES)

        self._timer: Optional[QTimer] = None
        if auto_start_timer:
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self.check_scheduled_queues)
            self._timer.start()

    def stop_timer(self) -> None:
        """Stops the internal schedule evaluation timer."""
        if self._timer and self._timer.isActive():
            self._timer.stop()

    def start_timer(self) -> None:
        """Starts or restarts the internal schedule evaluation timer."""
        if self._timer and not self._timer.isActive():
            self._timer.start()

    def get_queues(self) -> List[Dict]:
        """Returns deep copies of all managed queue configurations."""
        return [copy.deepcopy(q) for q in self._queues]

    def get_queue(self, queue_name: str) -> Optional[Dict]:
        """Retrieves configuration for a specific queue by name."""
        for q in self._queues:
            if isinstance(q, dict) and q.get("name") == queue_name:
                return copy.deepcopy(q)
        return None

    def get_queue_max_concurrent(self, queue_name: str) -> int:
        """Returns the configured max concurrent downloads limit for a queue."""
        q = self.get_queue(queue_name)
        if q:
            try:
                return max(1, int(q.get("max_concurrent", 4)))
            except (ValueError, TypeError):
                return 4
        return 4

    def set_queues(self, queues_list: List[Dict], persist: bool = True) -> None:
        """Replaces the active queue list and optionally persists to SQLite."""
        self._queues = [copy.deepcopy(q) for q in queues_list]
        for q in self._queues:
            if "daily_days" in q and isinstance(q["daily_days"], (list, tuple)):
                q["daily_days"] = list(q["daily_days"])

        if persist:
            self.persist()
        self.queuesChanged.emit()

    def create_queue(self, name: str, persist: bool = True) -> Dict:
        """Creates and appends a new queue with default settings."""
        new_q = make_default_queue(name)
        self._queues.append(new_q)
        if persist:
            try:
                from core.database import upsert_queue
                upsert_queue(new_q)
            except Exception as e:
                logger.warning("Failed to persist new queue '%s': %s", name, e)
        self.queuesChanged.emit()
        return copy.deepcopy(new_q)

    def delete_queue(self, name: str, persist: bool = True) -> bool:
        """Deletes a custom queue by name. Default queues cannot be deleted."""
        if name in ("Main download queue", "Synchronization queue"):
            return False

        original_len = len(self._queues)
        self._queues = [q for q in self._queues if q.get("name") != name]
        if len(self._queues) < original_len:
            if persist:
                try:
                    from core.database import delete_queue as db_delete_queue
                    db_delete_queue(name)
                except Exception as e:
                    logger.warning("Failed to delete queue '%s' from database: %s", name, e)
            self.queuesChanged.emit()
            return True
        return False

    def start_queue(self, queue_name: str, max_concurrent: Optional[int] = None) -> None:
        """Dispatches an explicit request to start a queue."""
        if max_concurrent is None:
            max_concurrent = self.get_queue_max_concurrent(queue_name)
        self.queueStartRequested.emit(queue_name, max_concurrent)

    def stop_queue(self, queue_name: str) -> None:
        """Dispatches an explicit request to stop a queue."""
        self.queueStopRequested.emit(queue_name)

    def persist(self) -> None:
        """Serializes current queue configurations to SQLite database."""
        try:
            from core.database import save_all_queues
            save_all_queues(self._queues)
        except Exception as e:
            logger.warning("Failed to persist queues: %s", e)

    def check_startup_queues(self) -> None:
        """Triggers execution for queues flagged with start_on_startup."""
        for q in self._queues:
            if isinstance(q, dict) and q.get("start_on_startup", False):
                qname = q.get("name", "Main download queue")
                max_c = self.get_queue_max_concurrent(qname)
                self.start_queue(qname, max_c)

    def check_scheduled_queues(self, dt: Optional[QDateTime] = None) -> None:
        """
        Evaluates active schedule constraints across all queues.
        Accepts an optional QDateTime instance for deterministic test evaluation.
        """
        now = dt if dt is not None else QDateTime.currentDateTime()
        current_time_str = now.toString("HH:mm:ss")
        current_time_hm = now.toString("HH:mm")
        current_date_str = now.toString("yyyy-MM-dd")
        current_weekday = now.date().dayOfWeek() % 7  # 0=Sun, 1=Mon, ..., 6=Sat

        for q in self._queues:
            if not isinstance(q, dict):
                continue
            q_name = q.get("name", "Main download queue")
            max_c = self.get_queue_max_concurrent(q_name)

            # 1. Start At Check
            if q.get("start_at_enabled", False):
                sched_type = q.get("schedule_type", "daily")
                can_run_today = False
                if sched_type == "once":
                    can_run_today = (q.get("once_date") == current_date_str)
                else:
                    days = q.get("daily_days", [True] * 7)
                    if current_weekday < len(days) and days[current_weekday]:
                        can_run_today = True

                if can_run_today:
                    target_time = q.get("start_at_time", "23:00:00")
                    match_time = (
                        current_time_str == target_time
                        or (len(target_time) == 5 and current_time_hm == target_time)
                        or (
                            len(target_time) >= 5
                            and current_time_hm == target_time[:5]
                            and not target_time.endswith(":00")
                            and current_time_str == target_time
                        )
                    )
                    trigger_key = f"start_{q_name}_{current_date_str}_{target_time}"
                    if match_time and not self._last_scheduled_minute.get(trigger_key):
                        self._last_scheduled_minute[trigger_key] = True
                        self.start_queue(q_name, max_c)

            # 2. Stop At Check
            if q.get("stop_at_enabled", False):
                target_stop_time = q.get("stop_at_time", "07:30:00")
                match_stop = (
                    current_time_str == target_stop_time
                    or (len(target_stop_time) == 5 and current_time_hm == target_stop_time)
                )
                trigger_stop_key = f"stop_{q_name}_{current_date_str}_{target_stop_time}"
                if match_stop and not self._last_scheduled_minute.get(trigger_stop_key):
                    self._last_scheduled_minute[trigger_stop_key] = True
                    self.stop_queue(q_name)

            # 3. Periodic Sync Check
            if q.get("mode") == "sync" and q.get("sync_interval_enabled", False):
                interval_sec = q.get("sync_hours", 2) * 3600 + q.get("sync_minutes", 0) * 60
                if interval_sec > 0:
                    last_sync = self._last_sync_times.get(q_name, 0.0)
                    now_epoch = time.time()
                    if now_epoch - last_sync >= interval_sec:
                        self._last_sync_times[q_name] = now_epoch
                        self.start_queue(q_name, max_c)
