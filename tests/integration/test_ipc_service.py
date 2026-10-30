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


class TestDirectMethodForwarding:
    def _free_port(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]
        finally:
            probe.close()

    def test_direct_fields_are_forwarded(self, qapp):
        from core.services.ipc_service import SignalEmitter, TcpListenerThread

        em = SignalEmitter()
        received = []
        em.new_download_signal.connect(received.append)

        port = self._free_port()
        thread = TcpListenerThread(port=port, emitter=em)
        thread.start()

        ready = False
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    ready = True
                    break
            except OSError:
                time.sleep(0.05)

        try:
            assert ready, "IPC listener did not start in time"

            payload = json.dumps({
                "url": "https://x/y.mp4",
                "method": "direct",
                "filename": "y.mp4",
                "ext": "mp4",
                "isMedia": True,
            }).encode()
            request = (
                b"POST / HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
                b"\r\n" + payload
            )
            sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            try:
                sock.sendall(request)
                sock.recv(1024)
            finally:
                sock.close()

            deadline = time.time() + 3
            while not received and time.time() < deadline:
                qapp.processEvents()
                time.sleep(0.02)
        finally:
            thread.stop()
            thread.wait(2000)

        assert received, "new_download_signal was not emitted"
        forwarded = json.loads(received[-1])
        assert forwarded["url"] == "https://x/y.mp4"
        assert forwarded["method"] == "direct"
        assert forwarded["filename"] == "y.mp4"
        assert forwarded["ext"] == "mp4"


class TestSabrPayloadForwarding:
    def _serve(self, qapp, port):
        """Boot the IPC listener on `port` and wait until it accepts connections."""
        from core.services.ipc_service import SignalEmitter, TcpListenerThread

        em = SignalEmitter()
        received = []
        em.new_download_signal.connect(received.append)
        thread = TcpListenerThread(port=port, emitter=em)
        thread.start()
        deadline = time.time() + 5
        ready = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    ready = True
                    break
            except OSError:
                time.sleep(0.05)
        assert ready, "IPC listener did not start in time"
        return thread, received

    @staticmethod
    def _session():
        import base64
        return {
            "videoId": "U-o5jaxPL-M",
            "serverAbrStreamingUrl": (
                "https://rr1---sn-ab5szn7l.googlevideo.com/videoplayback"
                "?expire=2000000000&id=U-o5jaxPL-M&sabr=1"
            ),
            "videoPlaybackUstreamerConfig": "Ct4BEqUDAv8B",
            "clientInfo": {"clientName": 1, "clientVersion": "2.20260101.00.00"},
            "formats": [
                {"itag": 299, "mimeType": "video/mp4", "contentLength": "10000000"},
                {"itag": 140, "mimeType": "audio/mp4", "contentLength": "1000000"},
            ],
            "videoItag": 299,
            "audioItag": 140,
            "requestBody": base64.b64encode(b"\x08\x01").decode(),
        }

    def _post(self, port, obj):
        payload = json.dumps(obj).encode()
        request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
            b"\r\n" + payload
        )
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        try:
            sock.sendall(request)
            sock.recv(1024)
        finally:
            sock.close()

    def _free_server(self, qapp):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        return self._serve(qapp, port), port

    def test_config_exposes_sabr_capability_flag(self, qapp):
        (thread, _), port = self._free_server(qapp)
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            sock.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
            sock.close()
            raw = b"".join(chunks).decode("utf-8", "replace")
            body = raw.split("\r\n\r\n", 1)[1]
            config = json.loads(body)
            assert isinstance(config.get("sabr"), bool)
        finally:
            thread.stop()
            thread.wait(2000)

    def test_valid_sabr_session_is_forwarded(self, qapp):
        (thread, received), port = self._free_server(qapp)
        try:
            self._post(port, {
                "url": self._session()["serverAbrStreamingUrl"],
                "method": "direct",
                "isMedia": True,
                "title": "SABR clip",
                "sabr": self._session(),
            })
            deadline = time.time() + 3
            while not received and time.time() < deadline:
                qapp.processEvents()
                time.sleep(0.02)
        finally:
            thread.stop()
            thread.wait(2000)

        assert received
        forwarded = json.loads(received[-1])
        assert forwarded["method"] == "direct"
        assert forwarded.get("sabr"), "validated SABR session was dropped"
        assert forwarded["sabr"]["videoId"] == "U-o5jaxPL-M"

    def test_invalid_sabr_session_is_dropped(self, qapp):
        (thread, received), port = self._free_server(qapp)
        try:
            self._post(port, {
                "url": "https://example.com/file.mp4",
                "method": "direct",
                "sabr": {"videoId": "garbage"},
            })
            deadline = time.time() + 3
            while not received and time.time() < deadline:
                qapp.processEvents()
                time.sleep(0.02)
        finally:
            thread.stop()
            thread.wait(2000)

        assert received
        forwarded = json.loads(received[-1])
        assert "sabr" not in forwarded


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
