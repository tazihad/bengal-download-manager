# 0001 Deepen Queue Manager and Sever UI Inverted Seam

Status: accepted

## Context
Queue domain definitions (`DEFAULT_QUEUES`, `_make_default_queue`) were historically declared inside `ui.dialogs.scheduler`, forcing `core.database` to import from a PyQt UI dialog across an inverted seam. Furthermore, `MainWindow` drove queue schedule checks and concurrency limits by polling GUI table widgets every minute.

## Decision
We consolidate queue definitions, defaults, schedule evaluation, and execution signals inside a deep `QueueManager` module in `src/core/queue_manager.py`. `QueueManager` runs autonomous scheduling timers and dispatches `queueStartRequested` and `queueStopRequested` Qt signals without depending on presentation widgets. To ensure backward compatibility, `ui.dialogs.scheduler` re-exports `DEFAULT_QUEUES` and `make_default_queue as _make_default_queue`.

## Consequences
- `core.database` imports `DEFAULT_QUEUES` directly from `core.queue_manager`, severing UI dependencies.
- Queue scheduling and concurrency limits are decoupled from GUI widgets and fully testable in headless unit tests.
- `ui.dialogs.scheduler` and `MainWindow` act as presentation callers rather than domain owners.
