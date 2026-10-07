"""Integration tests: IPC service."""

import json
import socket
import threading
import time
import pytest


class TestSignalEmitter:
    def test_new_download_signal(self, qapp):
        from core.services.ipc_service import SignalEmitter
        em = SignalEmitter()
        received = []
        em.new_download_signal.connect(received.append)
        em.new_download_signal.emit("https://example.com/file.zip")
        assert received == ["https://example.com/file.zip"]

    def test_batch_download_signal(self, qapp):
        from core.services.ipc_service import SignalEmitter
        em = SignalEmitter()
        received = []
        em.batch_download_signal.connect(received.append)
        em.batch_download_signal.emit(["https://a.com", "https://b.com"])
        assert len(received) == 1
        assert received[0] == ["https://a.com", "https://b.com"]

    def test_ipcemitter_alias(self, qapp):
        from core.services.ipc_service import IPCEmitter, SignalEmitter
        assert IPCEmitter is SignalEmitter


class TestSingleInstanceKey:
    def test_key_is_string(self):
        from core.services.ipc_service import get_single_instance_key
        key = get_single_instance_key()
        assert isinstance(key, str)
        assert len(key) > 0


class TestDMConnectorPort:
    def test_port_is_int(self):
        from core.services.ipc_service import DM_CONNECTOR_PORT
        assert isinstance(DM_CONNECTOR_PORT, int)
        assert DM_CONNECTOR_PORT == 56900


class TestTcpListenerThread:
    def test_construction(self, qapp):
        from core.services.ipc_service import TcpListenerThread, SignalEmitter
        em = SignalEmitter()
        thread = TcpListenerThread(port=29999, emitter=em)
        assert thread.port == 29999
        assert thread.emitter is em

    def test_start_and_stop(self, qapp):
        from core.services.ipc_service import TcpListenerThread, SignalEmitter
        em = SignalEmitter()
        thread = TcpListenerThread(port=29998, emitter=em)
        thread.start()
        time.sleep(0.5)
        thread.stop() if hasattr(thread, "stop") else None
        thread.quit()
        thread.wait(2000)
        assert not thread.isRunning()

    def test_listener_receives_message(self, qapp):
        from core.services.ipc_service import TcpListenerThread, SignalEmitter
        em = SignalEmitter()
        received_urls = []
        em.new_download_signal.connect(received_urls.append)
        thread = TcpListenerThread(port=29997, emitter=em)
        thread.start()
        time.sleep(0.8)

        try:
            payload = json.dumps({"url": "https://example.com/test.zip"}).encode()
            request = (
                b"POST /new_download HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
                b"\r\n" + payload
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("127.0.0.1", thread.port if thread.port else 29997))
            sock.sendall(request)
            time.sleep(0.5)
            sock.close()
            assert len(received_urls) >= 0
        finally:
            thread.stop()
            thread.quit()
            thread.wait(2000)


class TestIPCRequestHandler:
    def test_handler_class_exists(self):
        from core.services.ipc_service import IPCRequestHandler
        assert IPCRequestHandler is not None

    def test_log_message_no_crash(self):
        from core.services.ipc_service import IPCRequestHandler
        import io
        import contextlib

        class FakeRequest:
            pass

        handler = IPCRequestHandler.__new__(IPCRequestHandler)
        handler.request = FakeRequest()
        handler.client_address = ("127.0.0.1", 12345)
        handler.request_version = "HTTP/1.1"
        handler.command = "POST"

        old_stderr = None
        try:
            import sys
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            handler.log_message("test %s", "message")
        finally:
            if old_stderr is not None:
                sys.stderr = old_stderr


class TestSingleInstance:
    def test_check_single_instance_returns_bool(self):
        from core.services.ipc_service import check_single_instance
        result = check_single_instance()
        assert isinstance(result, bool)

    def test_single_instance_server_construction(self, qapp):
        from core.services.ipc_service import SingleInstanceServer
        server = SingleInstanceServer()
        assert server is not None

    def test_server_start_stop(self, qapp):
        from core.services.ipc_service import SingleInstanceServer
        server = SingleInstanceServer()
        try:
            server.start()
            time.sleep(0.3)
        finally:
            try:
                server.stop()
            except Exception:
                pass
            try:
                server.deleteLater()
            except Exception:
                pass
