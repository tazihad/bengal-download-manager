import pytest
from core.workers.download import DownloadWorker
from core.workers.aria2 import Aria2Worker
from core.workers.fetcher import FileInfoFetcherWorker

def test_download_worker_format_bytes(qapp):
    worker = DownloadWorker("http://example.com/test.zip", 0, "/tmp/test.zip")
    assert worker.format_bytes(1024, precision=2, pad=False) == "1.00  KB"
    assert worker.format_bytes(1048576, precision=2, pad=False) == "1.00  MB"
    assert worker.format_bytes(500, precision=2, pad=False) == "500.00  B"

def test_download_worker_format_time(qapp):
    worker = DownloadWorker("http://example.com/test.zip", 0, "/tmp/test.zip")
    assert worker.format_time(45) == "45 sec"
    assert worker.format_time(120) == "2 min"
    assert worker.format_time(3600) == "1 hr"

def test_aria2_worker_format_bytes(qapp):
    aria = Aria2Worker("http://example.com/test.zip", 0, "/tmp")
    assert aria.format_bytes(2048, precision=2, pad=False) == "2.00  KB"

def test_fetcher_worker_format_bytes(qapp):
    fetcher = FileInfoFetcherWorker("http://example.com")
    assert fetcher.format_bytes(4096, precision=2, pad=False) == "4.00  KB"

def test_workers_respect_configured_max_connections(qapp, monkeypatch, tmp_path):
    from core.utils import save_extension_config, load_extension_config
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 12})
    cfg = load_extension_config()
    assert cfg["max_connections"] == 12

    # Verify clamping
    save_extension_config({"max_connections": 999})
    assert load_extension_config()["max_connections"] == 32

    save_extension_config({"max_connections": 0})
    assert load_extension_config()["max_connections"] == 1


def test_call_aria2_rpc_http_400_json_error(monkeypatch):
    import socket
    from core.utils import call_aria2_rpc

    mock_resp = (
        b"HTTP/1.1 400 Bad Request\r\n"
        b"Content-Type: application/json-rpc\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        b'{"id":"1","jsonrpc":"2.0","error":{"code":1,"message":"GID 0123456789abcdef is not found"}}'
    )

    class DummySocket:
        def __init__(self, *args, **kwargs):
            self._data = mock_resp
        def settimeout(self, t): pass
        def connect(self, addr): pass
        def sendall(self, data): pass
        def recv(self, bufsize):
            d = self._data
            self._data = b""
            return d
        def shutdown(self, how): pass
        def close(self): pass

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: DummySocket())
    res = call_aria2_rpc("aria2.tellStatus", ["0123456789abcdef"], port=56800)
    assert res is None


def test_call_aria2_rpc_http_200_json_success(monkeypatch):
    import socket
    from core.utils import call_aria2_rpc

    mock_resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json-rpc\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        b'{"id":"1","jsonrpc":"2.0","result":"gid1234"}'
    )

    class DummySocket:
        def __init__(self, *args, **kwargs):
            self._data = mock_resp
        def settimeout(self, t): pass
        def connect(self, addr): pass
        def sendall(self, data): pass
        def recv(self, bufsize):
            d = self._data
            self._data = b""
            return d
        def shutdown(self, how): pass
        def close(self): pass

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: DummySocket())
    res = call_aria2_rpc("aria2.addUri", [["http://example.com"]], port=56800)
    assert res == "gid1234"


def test_aria2_worker_exits_on_repeated_failures_file_missing(qapp, monkeypatch, tmp_path):
    worker = Aria2Worker("http://example.com/testfile.iso", 0, str(tmp_path), resume_filename="testfile.iso")
    responses = ["gid999", None, None, None, None, None]
    worker.call_rpc = lambda method, params=None: responses.pop(0) if responses else None

    monkeypatch.setattr("time.sleep", lambda s: None)

    finished_statuses = []
    worker.finished_signal.connect(lambda idx, status: finished_statuses.append(status))

    worker.run()
    assert finished_statuses == ["Error"]


def test_aria2_worker_completes_on_repeated_failures_if_file_intact(qapp, monkeypatch, tmp_path):
    test_file = tmp_path / "testfile.iso"
    test_file.write_bytes(b"hello world bytes")

    worker = Aria2Worker("http://example.com/testfile.iso", 0, str(tmp_path), resume_filename="testfile.iso")
    responses = ["gid999", None, None, None, None, None]
    worker.call_rpc = lambda method, params=None: responses.pop(0) if responses else None

    monkeypatch.setattr("time.sleep", lambda s: None)

    finished_statuses = []
    worker.finished_signal.connect(lambda idx, status: finished_statuses.append(status))

    worker.run()
    assert finished_statuses == ["Complete"]

