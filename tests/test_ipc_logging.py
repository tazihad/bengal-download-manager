"""
Unit tests for IPC service logging and heartbeat rate-limiting.
"""

import os
import time
import logging
from unittest.mock import MagicMock
from core.services.ipc_service import IPCRequestHandler


def test_ipc_log_message_suppression(monkeypatch, caplog):
    """Verify routine GET / 200 heartbeat logs are suppressed in --debug unless BENGAL_VERBOSE_IPC=1."""
    monkeypatch.setenv("DEBUG", "1")
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
    monkeypatch.setenv("DEBUG", "1")
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
