"""
Unit tests for Aria2DaemonManager deep module.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject

from core.aria2_daemon import Aria2DaemonManager, get_aria2_daemon_manager


class DummyProcess:
    def __init__(self, pid=9999, returncode=None):
        self.pid = pid
        self.returncode = returncode
        self.stderr = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9


@pytest.fixture
def daemon_manager(qtbot):
    mgr = Aria2DaemonManager()
    yield mgr
    mgr.stop(timeout_sec=0.1)


def test_daemon_initial_state(daemon_manager):
    assert daemon_manager.process is None
    assert daemon_manager.pid is None
    assert daemon_manager.port == 56800
    assert daemon_manager.token == ""


def test_daemon_is_running_via_process(daemon_manager):
    dummy = DummyProcess(pid=1234, returncode=None)
    daemon_manager._process = dummy
    assert daemon_manager.is_running() is True
    assert daemon_manager.pid == 1234


def test_daemon_is_running_via_port_fallback(daemon_manager):
    daemon_manager._process = None
    with patch.object(daemon_manager, "is_port_active", return_value=True):
        assert daemon_manager.is_running() is True


def test_daemon_start_success(daemon_manager, qtbot):
    dummy = DummyProcess(pid=5432, returncode=None)

    with patch("core.aria2_daemon.ensure_aria2", return_value="/usr/bin/aria2c"), \
         patch("core.aria2_daemon.load_extension_config", return_value={"port": 56805, "token": "secret123", "max_connections": 16}), \
         patch("core.aria2_daemon.get_aria2_proxy_url", return_value="http://127.0.0.1:8080"), \
         patch("subprocess.Popen", return_value=dummy) as mock_popen, \
         patch("core.services.port_service.reclaim_port") as mock_reclaim:

        status_signals = []
        daemon_manager.status_changed.connect(lambda running, msg: status_signals.append((running, msg)))

        res = daemon_manager.start(port=56805, token="secret123")
        assert res is True
        assert daemon_manager.is_running() is True
        assert daemon_manager.pid == 5432
        assert daemon_manager.port == 56805
        assert daemon_manager.token == "secret123"

        # Verify command line arguments passed to popen
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "/usr/bin/aria2c" in cmd
        assert "--rpc-listen-port=56805" in cmd
        assert "--rpc-secret=secret123" in cmd
        assert "--all-proxy=http://127.0.0.1:8080" in cmd

        # Verify signal emitted
        assert len(status_signals) > 0
        assert status_signals[-1][0] is True
        assert "5432" in status_signals[-1][1]


def test_daemon_start_failure_immediate_exit(daemon_manager):
    dead_proc = DummyProcess(pid=1111, returncode=1)

    with patch("core.aria2_daemon.ensure_aria2", return_value="aria2c"), \
         patch("core.aria2_daemon.load_extension_config", return_value={}), \
         patch("subprocess.Popen", return_value=dead_proc), \
         patch("core.services.port_service.reclaim_port"):

        res = daemon_manager.start()
        assert res is False
        assert daemon_manager.process is None
        assert daemon_manager.is_running() is False


def test_daemon_stop_graceful_rpc(daemon_manager):
    dummy = DummyProcess(pid=4321, returncode=None)
    daemon_manager._process = dummy
    daemon_manager._port = 56800
    daemon_manager._token = "mytoken"

    with patch("urllib.request.urlopen") as mock_urlopen:
        res = daemon_manager.stop(timeout_sec=0.5)
        assert res is True
        assert daemon_manager.process is None
        mock_urlopen.assert_called_once()


def test_singleton_accessor():
    mgr1 = get_aria2_daemon_manager()
    mgr2 = get_aria2_daemon_manager()
    assert mgr1 is mgr2
    assert isinstance(mgr1, Aria2DaemonManager)
