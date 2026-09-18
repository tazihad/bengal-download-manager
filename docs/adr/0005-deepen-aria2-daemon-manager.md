# 0005 Deepen Aria2 Daemon Manager

Status: accepted

## Context
`MainWindow` was responsible for managing the lifecycle of the external `aria2c` daemon process. It constructed CLI arguments, executed `subprocess.Popen`, managed background stderr logging threads, inspected TCP port occupancy, and performed graceful JSON-RPC `aria2.shutdown` calls on exit. This process supervision logic leaked into the GUI presentation layer, preventing headless runners, Kirigami QML interfaces, and unit tests from controlling the daemon without instantiating `MainWindow`.

## Decision
We introduce `Aria2DaemonManager` in `src/core/aria2_daemon.py` as a deep module encapsulating:
- Process supervision (`start`, `stop`, `restart`, `is_running`).
- Automatic pre-launch port reclamation via `port_service`.
- Proxy URL resolution and secret token CLI argument configuration.
- Background stderr stream logging.
- Graceful JSON-RPC shutdown with escalated SIGTERM/SIGKILL timeouts.
- Signal notifications (`status_changed`, `started`, `stopped`, `error_occurred`).

`MainWindow` and `DownloadBridge` now interact with `Aria2DaemonManager` via a minimal 3-method interface.

## Consequences
- Process supervision is completely severed from GUI presentation windows.
- Kirigami QML mode and automated test fixtures can inspect and manage aria2 daemon state headlessly.
- Passes the deletion test: low-level process management concentrates in a single module with high locality.
