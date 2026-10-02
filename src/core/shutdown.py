"""
Bengal Download Manager - Graceful Shutdown Coordinator
======================================================
Structured, phased application shutdown manager tracking execution metrics,
phase timings, error isolation, and detailed lifecycle diagnostics under --debug mode.
"""

import sys
import time
import logging
import threading
from typing import Callable, List, Tuple, Dict, Any, Optional

from core.utils import is_debug_mode

logger = logging.getLogger("bengal_dm")


class ShutdownPhase:
    """Standard lifecycle shutdown phase identifiers."""
    UI_TEARDOWN = "UI_TEARDOWN"
    WORKERS = "WORKERS"
    SERVICES = "SERVICES"
    PERSISTENCE = "PERSISTENCE"
    CLEANUP = "CLEANUP"


PHASE_DESCRIPTIONS: Dict[str, str] = {
    ShutdownPhase.UI_TEARDOWN: "UI teardown - dismissing interface windows, system tray, and active dialogs",
    ShutdownPhase.WORKERS: "Active workers - stopping download tasks, fetchers, and auxiliary threads",
    ShutdownPhase.SERVICES: "Network services - stopping IPC listener, single-instance server, and Aria2 daemon",
    ShutdownPhase.PERSISTENCE: "Data persistence - saving download records, queue state, and user preferences",
    ShutdownPhase.CLEANUP: "Resource cleanup - final cleanup operations, memory trimming, and cache sync",
}


class ShutdownCoordinator:
    """
    Coordinates structured, phased application shutdown.
    
    Provides isolated execution of shutdown tasks per phase, captures duration
    and success/failure counts, and outputs structured diagnostics in debug mode.
    """
    
    _instance: Optional["ShutdownCoordinator"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> "ShutdownCoordinator":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(ShutdownCoordinator, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.Lock()
        self._executed_total: int = 0
        self._failed_total: int = 0
        self._completed_phases: Dict[str, Dict[str, Any]] = {}
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._finished: bool = False
        self._initialized = True

    def reset(self):
        """Reset coordinator state (primarily for automated testing)."""
        with self._lock:
            self._executed_total = 0
            self._failed_total = 0
            self._completed_phases.clear()
            self._start_time = None
            self._end_time = None
            self._finished = False

    @property
    def executed_total(self) -> int:
        return self._executed_total

    @property
    def failed_total(self) -> int:
        return self._failed_total

    @property
    def is_finished(self) -> bool:
        return self._finished

    def execute_phase(
        self,
        phase_name: str,
        tasks: List[Tuple[str, Callable[[], Any]]],
        description: Optional[str] = None,
    ) -> Tuple[int, int, float]:
        """
        Execute a batch of shutdown tasks within a named phase.
        
        Args:
            phase_name: Unique name of the shutdown phase.
            tasks: List of (task_name, callable) pairs to execute.
            description: Optional human-readable description for the phase.
            
        Returns:
            Tuple of (executed_count, failed_count, duration_ms)
        """
        with self._lock:
            if self._start_time is None:
                self._start_time = time.perf_counter()

            if phase_name in self._completed_phases:
                # Phase was already completed
                prev = self._completed_phases[phase_name]
                return prev["executed"], prev["failed"], prev["duration_ms"]

            phase_desc = description or PHASE_DESCRIPTIONS.get(phase_name, phase_name)
            phase_start = time.perf_counter()
            phase_executed = 0
            phase_failed = 0

            for task_name, task_fn in tasks:
                try:
                    if callable(task_fn):
                        task_fn()
                    phase_executed += 1
                    self._executed_total += 1
                except Exception as e:
                    phase_failed += 1
                    self._failed_total += 1
                    logger.debug("[Shutdown] Error during task '%s' in phase '%s': %s", task_name, phase_name, e)

            phase_duration_ms = (time.perf_counter() - phase_start) * 1000.0

            self._completed_phases[phase_name] = {
                "executed": phase_executed,
                "failed": phase_failed,
                "duration_ms": phase_duration_ms,
                "description": phase_desc,
            }

            logger.debug(
                "Completed shutdown phase: %s - %s (Duration: %.1fms, Executed: %d, Failed: %d)",
                phase_name,
                phase_desc,
                phase_duration_ms,
                phase_executed,
                phase_failed,
            )

            return phase_executed, phase_failed, phase_duration_ms

    def finish(self) -> float:
        """
        Mark the shutdown lifecycle as finalized and emit the total execution summary.
        
        Returns:
            Total elapsed duration in milliseconds.
        """
        with self._lock:
            if self._finished:
                if self._start_time and self._end_time:
                    return (self._end_time - self._start_time) * 1000.0
                return 0.0

            self._end_time = time.perf_counter()
            total_duration_ms = 0.0
            if self._start_time:
                total_duration_ms = (self._end_time - self._start_time) * 1000.0

            self._finished = True

            logger.debug(
                "Shutdown process completed in %.0fms. Executed: %d, Failed: %d.",
                total_duration_ms,
                self._executed_total,
                self._failed_total,
            )

            return total_duration_ms


def get_shutdown_coordinator() -> ShutdownCoordinator:
    """Retrieve the singleton ShutdownCoordinator instance."""
    return ShutdownCoordinator()


def perform_application_shutdown(window: Optional[Any] = None) -> float:
    """
    Executes the phased application shutdown lifecycle for the given window/application.
    Safe to call multiple times (idempotent).
    """
    coordinator = get_shutdown_coordinator()
    if coordinator.is_finished:
        return 0.0

    if window is not None:
        # ---------------------------------------------------------
        # Phase 1: UI Teardown
        # ---------------------------------------------------------
        ui_tasks: List[Tuple[str, Callable[[], Any]]] = []
        if hasattr(window, "hide"):
            ui_tasks.append(("hide_main_window", window.hide))
        if hasattr(window, "tray_icon") and window.tray_icon:
            ui_tasks.append(("hide_tray_icon", window.tray_icon.hide))

        def close_dialogs():
            if hasattr(window, "active_file_info_dialogs"):
                for dlg in list(window.active_file_info_dialogs.values()):
                    try:
                        dlg.close()
                        dlg.deleteLater()
                    except Exception:
                        pass
                window.active_file_info_dialogs.clear()
            if hasattr(window, "active_complete_dialogs"):
                for dlg in list(window.active_complete_dialogs.values()):
                    try:
                        dlg.close()
                        dlg.deleteLater()
                    except Exception:
                        pass
                window.active_complete_dialogs.clear()
            for dlg_attr in ("_options_dlg", "_media_downloader_dlg", "_scheduler_dlg"):
                dlg = getattr(window, dlg_attr, None)
                if dlg:
                    try:
                        dlg.close()
                        dlg.deleteLater()
                    except Exception:
                        pass
                    setattr(window, dlg_attr, None)

        ui_tasks.append(("close_active_dialogs", close_dialogs))

        def stop_timers():
            for timer_attr in ("timestamp_timer", "status_bar_timer", "memory_guard_timer"):
                t = getattr(window, timer_attr, None)
                if t:
                    try:
                        t.stop()
                    except Exception:
                        pass
            if hasattr(window, "_active_retry_timers"):
                for t in list(window._active_retry_timers):
                    try:
                        t.stop()
                    except Exception:
                        pass
                window._active_retry_timers.clear()

        ui_tasks.append(("stop_ui_timers", stop_timers))

        def close_all_qt_windows():
            from PyQt6.QtWidgets import QApplication
            try:
                QApplication.closeAllWindows()
            except Exception:
                pass

        ui_tasks.append(("close_all_windows", close_all_qt_windows))

        coordinator.execute_phase(ShutdownPhase.UI_TEARDOWN, ui_tasks)

        # ---------------------------------------------------------
        # Phase 2: Active Workers & Threads
        # ---------------------------------------------------------
        worker_tasks: List[Tuple[str, Callable[[], Any]]] = []

        def stop_aux_workers():
            for w_attr in ("_proxy_sb_worker", "_media_engine_worker", "_ip_worker"):
                w = getattr(window, w_attr, None)
                if w and hasattr(w, "isRunning") and w.isRunning():
                    try:
                        if hasattr(w, "requestInterruption"):
                            w.requestInterruption()
                        if hasattr(w, "terminate"):
                            w.terminate()
                        elif hasattr(w, "quit"):
                            w.quit()
                        if hasattr(w, "wait"):
                            w.wait(300)
                    except Exception:
                        pass
                    setattr(window, w_attr, None)

        worker_tasks.append(("stop_auxiliary_workers", stop_aux_workers))

        if hasattr(window, "stop_all_downloads"):
            worker_tasks.append(("stop_download_workers", window.stop_all_downloads))

        def stop_fetchers():
            if hasattr(window, "active_fetchers"):
                for fetcher in list(window.active_fetchers):
                    try:
                        if hasattr(fetcher, "requestInterruption"):
                            fetcher.requestInterruption()
                        if hasattr(fetcher, "quit"):
                            fetcher.quit()
                        if hasattr(fetcher, "wait"):
                            fetcher.wait(300)
                    except Exception:
                        pass
                window.active_fetchers.clear()

        worker_tasks.append(("stop_active_fetchers", stop_fetchers))

        if hasattr(window, "download_controller") and window.download_controller:
            worker_tasks.append(("clear_download_controller", window.download_controller.clear))

        coordinator.execute_phase(ShutdownPhase.WORKERS, worker_tasks)

        # ---------------------------------------------------------
        # Phase 3: Services & Daemons
        # ---------------------------------------------------------
        service_tasks: List[Tuple[str, Callable[[], Any]]] = []

        def stop_ipc():
            if hasattr(window, "listener_thread") and window.listener_thread:
                try:
                    window.listener_thread.stop(timeout_ms=1500)
                except Exception:
                    pass
                window.listener_thread = None

        service_tasks.append(("stop_ipc_listener", stop_ipc))

        def stop_single_instance():
            if hasattr(window, "single_instance_server") and window.single_instance_server:
                try:
                    window.single_instance_server.stop()
                except Exception:
                    pass
                window.single_instance_server = None

        service_tasks.append(("stop_single_instance_server", stop_single_instance))

        if hasattr(window, "stop_aria2_daemon"):
            service_tasks.append(("stop_aria2_daemon", window.stop_aria2_daemon))

        coordinator.execute_phase(ShutdownPhase.SERVICES, service_tasks)

        # ---------------------------------------------------------
        # Phase 4: Data Persistence
        # ---------------------------------------------------------
        persist_tasks: List[Tuple[str, Callable[[], Any]]] = []
        if hasattr(window, "save_data"):
            persist_tasks.append(("save_download_records", window.save_data))
        if hasattr(window, "save_settings"):
            persist_tasks.append(("save_user_settings", window.save_settings))

        coordinator.execute_phase(ShutdownPhase.PERSISTENCE, persist_tasks)

    # ---------------------------------------------------------
    # Phase 5: Resource Cleanup & Memory Trim
    # ---------------------------------------------------------
    cleanup_tasks: List[Tuple[str, Callable[[], Any]]] = []

    def cleanup_mem():
        from core.memory_guard import MemoryGuard
        MemoryGuard.clean_and_trim()

    cleanup_tasks.append(("memory_trim_and_gc", cleanup_mem))

    coordinator.execute_phase(ShutdownPhase.CLEANUP, cleanup_tasks)

    return coordinator.finish()
