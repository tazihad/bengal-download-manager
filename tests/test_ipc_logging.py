"""
Unit tests for IPC service logging and heartbeat rate-limiting.
"""

import os
import time
import logging
from unittest.mock import MagicMock
from core.services.ipc_service import IPCRequestHandler


def test_ipc_log_message_suppression(monkeypatch, caplog):
    """Verify routine GET / 200 heartbeat logs are suppressed in --debug unless verbose mode is active."""
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug"])
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.delenv("VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE_IPC", raising=False)

    handler = IPCRequestHandler.__new__(IPCRequestHandler)
    handler.client_address = ("127.0.0.1", 54321)
    handler._is_routine_heartbeat = True

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="bengal.ipc"):
        # 1. Routine heartbeat GET / with 200 status should be SUPPRESSED
        handler.log_message('"%s" %s %s', "GET / HTTP/1.1", "200", "-")
        assert len(caplog.records) == 0

        # 2. Non-routine request (e.g. POST /download) should be LOGGED
        handler._is_routine_heartbeat = False
        handler.log_message('"%s" %s %s', "POST / HTTP/1.1", "200", "-")
        assert any("POST / HTTP/1.1" in r.message for r in caplog.records)

        # 3. Heartbeat with error (e.g. 500) should be LOGGED
        caplog.clear()
        handler._is_routine_heartbeat = True
        handler.log_message('"%s" %s %s', "GET / HTTP/1.1", "500", "-")
        assert any("500" in r.message for r in caplog.records)

        # 4. If BENGAL_VERBOSE_IPC=1, routine 200 should also be LOGGED
        caplog.clear()
        monkeypatch.setenv("BENGAL_VERBOSE_IPC", "1")
        handler._is_routine_heartbeat = True
        handler.log_message('"%s" %s %s', "GET / HTTP/1.1", "200", "-")
        assert any("GET / HTTP/1.1" in r.message for r in caplog.records)


def test_ipc_do_get_heartbeat_throttling(monkeypatch, caplog):
    """Verify do_GET logs initial connection and throttles recurring pings."""
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug"])
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.delenv("VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE_IPC", raising=False)

    # Reset class state
    IPCRequestHandler._last_heartbeat_client = None
    IPCRequestHandler._last_heartbeat_time = 0.0
    IPCRequestHandler._heartbeat_count = 0

    handler = IPCRequestHandler.__new__(IPCRequestHandler)
    handler.client_address = ("127.0.0.1", 54321)
    handler.path = "/"
    handler.server = MagicMock()
    handler.server.server_address = ("127.0.0.1", 56900)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="bengal.ipc"):
        # First ping: should log "Extension heartbeat connected"
        handler.do_GET()
        assert any("Extension heartbeat connected from 127.0.0.1" in r.message for r in caplog.records)
        assert IPCRequestHandler._heartbeat_count == 1

        # Second ping immediately: should NOT log duplicate ping
        caplog.clear()
        handler.do_GET()
        assert len(caplog.records) == 0
        assert IPCRequestHandler._heartbeat_count == 2

        # Simulate 5 minutes passing
        IPCRequestHandler._last_heartbeat_time = time.time() - 305.0
        caplog.clear()
        handler.do_GET()
        assert any("Extension heartbeat active from 127.0.0.1" in r.message for r in caplog.records)
        assert IPCRequestHandler._heartbeat_count == 0


def test_verbose_mode_detection(monkeypatch):
    """Verify is_verbose_mode detects --verbose, -v, and environment variables."""
    from core.utils import is_verbose_mode
    import sys

    # Default without flags
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.delenv("VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE_IPC", raising=False)
    assert not is_verbose_mode()

    # --verbose flag
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug", "--verbose"])
    assert is_verbose_mode()

    # Environment variables
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setenv("VERBOSE", "1")
    assert is_verbose_mode()

    monkeypatch.delenv("VERBOSE")
    monkeypatch.setenv("BENGAL_VERBOSE", "1")
    assert is_verbose_mode()


def test_verbose_full_logging(monkeypatch, caplog):
    """Verify that when --debug and --verbose are present, full unrestricted logging occurs."""
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug", "--verbose"])
    monkeypatch.delenv("VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE", raising=False)
    monkeypatch.delenv("BENGAL_VERBOSE_IPC", raising=False)

    handler = IPCRequestHandler.__new__(IPCRequestHandler)
    handler.client_address = ("127.0.0.1", 54321)
    handler.path = "/"
    handler.server = MagicMock()
    handler.server.server_address = ("127.0.0.1", 56900)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler._is_routine_heartbeat = True

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="bengal.ipc"):
        # Under --verbose, GET / pings log the raw ping message
        handler.do_GET()
        assert any("Extension ping / GET request from 127.0.0.1 on /" in r.message for r in caplog.records)

        # Under --verbose, log_message does not suppress the routine 200 HTTP log
        caplog.clear()
        handler.log_message('"%s" %s %s', "GET / HTTP/1.1", "200", "-")
        assert any('"GET / HTTP/1.1" 200 -' in r.message for r in caplog.records)

