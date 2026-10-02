"""
Unit tests for the Graceful Shutdown Coordinator and lifecycle metrics.
"""

import logging
import pytest
from core.shutdown import (
    ShutdownPhase,
    ShutdownCoordinator,
    get_shutdown_coordinator,
    perform_application_shutdown,
    PHASE_DESCRIPTIONS,
)


@pytest.fixture(autouse=True)
def reset_coordinator():
    """Ensure coordinator is reset before and after each test."""
    coord = get_shutdown_coordinator()
    coord.reset()
    yield
    coord.reset()


def test_shutdown_phase_execution(caplog):
    """Verify phases execute tasks sequentially and capture count and timings."""
    coord = get_shutdown_coordinator()
    caplog.set_level(logging.DEBUG, logger="bengal_dm")

    task1_executed = False
    task2_executed = False

    def task1():
        nonlocal task1_executed
        task1_executed = True

    def task2():
        nonlocal task2_executed
        task2_executed = True

    executed, failed, duration_ms = coord.execute_phase(
        ShutdownPhase.UI_TEARDOWN,
        [("task1", task1), ("task2", task2)],
    )

    assert task1_executed is True
    assert task2_executed is True
    assert executed == 2
    assert failed == 0
    assert duration_ms >= 0.0
    assert coord.executed_total == 2
    assert coord.failed_total == 0

    # Ensure debug message was logged with phase name and description
    assert any("Completed shutdown phase: UI_TEARDOWN" in record.message for record in caplog.records)


def test_shutdown_error_isolation(caplog):
    """Verify task exceptions are caught, isolated, and increment failed count without crashing."""
    coord = get_shutdown_coordinator()
    caplog.set_level(logging.DEBUG, logger="bengal_dm")

    def faulty_task():
        raise RuntimeError("Simulated connection failure during shutdown")

    def normal_task():
        pass

    executed, failed, _ = coord.execute_phase(
        ShutdownPhase.SERVICES,
        [("faulty", faulty_task), ("normal", normal_task)],
    )

    assert executed == 1
    assert failed == 1
    assert coord.executed_total == 1
    assert coord.failed_total == 1
    assert any("Completed shutdown phase: SERVICES" in record.message for record in caplog.records)


def test_shutdown_finish_summary(caplog):
    """Verify coordinator summary logs total duration and operation counts."""
    coord = get_shutdown_coordinator()
    caplog.set_level(logging.DEBUG, logger="bengal_dm")

    coord.execute_phase(ShutdownPhase.CLEANUP, [("step1", lambda: None), ("step2", lambda: None)])
    total_ms = coord.finish()

    assert total_ms >= 0.0
    assert coord.is_finished is True
    assert any("Shutdown process completed in" in record.message and "Executed: 2, Failed: 0." in record.message for record in caplog.records)


def test_perform_application_shutdown_idempotency(caplog):
    """Verify perform_application_shutdown is safe to call repeatedly."""
    coord = get_shutdown_coordinator()
    caplog.set_level(logging.DEBUG, logger="bengal_dm")

    # Mock window object
    class MockWindow:
        def __init__(self):
            self.saved = False
            self.cleaned = False
        def save_data(self):
            self.saved = True
        def save_settings(self):
            pass

    mock_win = MockWindow()
    dur1 = perform_application_shutdown(mock_win)
    assert dur1 >= 0.0
    assert mock_win.saved is True
    assert coord.is_finished is True

    # Second invocation should be a no-op returning 0.0
    dur2 = perform_application_shutdown(mock_win)
    assert dur2 == 0.0
