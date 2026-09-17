"""
Tests for Port Service and Automatic Port Reclamation (port_service.py).
"""

import os
import time
import socket
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from core.services.port_service import (
    is_port_in_use,
    get_pid_listening_on_port,
    _is_safe_to_terminate,
    reclaim_port,
)


def test_is_port_in_use_detects_listening_socket():
    """Verify that is_port_in_use returns True for listening socket and False when closed."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    try:
        assert is_port_in_use(port) is True
    finally:
        s.close()

    time.sleep(0.05)
    assert is_port_in_use(port) is False


def test_get_pid_listening_on_port_detects_current_process():
    """Verify that get_pid_listening_on_port finds current process PID on local bound port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    try:
        res = get_pid_listening_on_port(port)
        assert res is not None
        pid, cmdline = res
        assert pid == os.getpid()
    finally:
        s.close()


def test_is_safe_to_terminate_constraints():
    """Verify that _is_safe_to_terminate strictly obeys UID, self-PID, and pattern filters."""
    my_pid = os.getpid()

    # Never kill self
    assert _is_safe_to_terminate(my_pid, "python3 src/main.py", ["python"]) is False

    # Never kill process with mismatching command line
    assert _is_safe_to_terminate(999999, "/usr/bin/nginx -g daemon off;", ["aria2c", "aria2"]) is False
    assert _is_safe_to_terminate(999999, "systemd", ["bengal", "python"]) is False

    # Allow matching process if UID matches
    with patch("os.stat") as mock_stat:
        mock_res = MagicMock()
        mock_res.st_uid = os.getuid()
        mock_stat.return_value = mock_res

        assert _is_safe_to_terminate(999999, "/usr/bin/aria2c --enable-rpc", ["aria2c", "aria2"]) is True
        assert _is_safe_to_terminate(999999, "python3 /path/bengal-download-manager", ["python", "bengal"]) is True

        # Reject if UID mismatch
        mock_res.st_uid = os.getuid() + 1
        assert _is_safe_to_terminate(999999, "/usr/bin/aria2c --enable-rpc", ["aria2c"]) is False


def test_reclaim_port_on_already_free_port():
    """Verify reclaim_port immediately returns True for an open/free port."""
    # Find a free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    assert reclaim_port(port, "aria2", ["aria2c"]) is True


def test_reclaim_port_refuses_unauthorized_process():
    """Verify reclaim_port will not kill an unauthorized process on port collision."""
    with patch("core.services.port_service.is_port_in_use", return_value=True), \
         patch("core.services.port_service.get_pid_listening_on_port", return_value=(12345, "unrelated_service")):
        res = reclaim_port(56800, "aria2", ["aria2c"], timeout_sec=0.1)
        assert res is False


def test_reclaim_port_terminates_orphan_subprocess():
    """Spawn a real child process binding a port, verify reclaim_port detects and terminates it."""
    child_code = (
        "import socket, time\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.bind(('127.0.0.1', 0))\n"
        "port = s.getsockname()[1]\n"
        "s.listen(1)\n"
        "print(port, flush=True)\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    try:
        port_line = proc.stdout.readline().strip()
        port = int(port_line)
        assert is_port_in_use(port) is True

        # Reclaim the port from this orphan python process
        reclaimed = reclaim_port(port, "ipc", ["python"], timeout_sec=2.0)
        assert reclaimed is True
        assert is_port_in_use(port) is False
    finally:
        try:
            proc.kill()
            proc.wait(timeout=0.5)
        except Exception:
            pass


def test_watchdog_auto_restarts_services(qapp):
    """Verify MainWindow._check_and_recover_services auto-restarts inactive aria2 and IPC."""
    from ui.main_window import MainWindow

    win = MainWindow(start_ipc=False)
    try:
        with patch.object(win, "start_aria2_daemon") as mock_start_aria, \
             patch.object(win, "restart_ipc_listener") as mock_restart_ipc:

            # Mark aria2 as dead
            win.aria2_process = None
            win.start_ipc = True
            win.listener_thread = None

            win._check_and_recover_services()

            assert mock_start_aria.called
            assert mock_restart_ipc.called
    finally:
        win.is_quitting = True
        win.close()


def test_tcp_listener_fallback_on_unreclaimable_port():
    """Verify that TcpListenerThread gracefully activates fallback port if primary port is held."""
    from core.services.ipc_service import TcpListenerThread, SignalEmitter
    import time

    # Bind a dummy port that won't be killed
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    emitter = SignalEmitter()
    # When port is occupied by s, TcpListenerThread should fall back to safe ports 26900..26902
    thread = TcpListenerThread(port, emitter)
    try:
        thread.start()
        for _ in range(50):
            if thread.port != port:
                break
            time.sleep(0.05)
        assert thread.isRunning() is True
        assert thread.port != port
        assert thread.port in (26900, 26901, 26902)
    finally:
        thread.stop()
        thread.wait(2000)
        s.close()

