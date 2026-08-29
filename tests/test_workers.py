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


def test_fetcher_size_discovery(qapp, monkeypatch):
    from unittest.mock import MagicMock
    import io

    # 1. Test Content-Range discovery
    fetcher = FileInfoFetcherWorker("http://example.com/stream.bin")
    mock_resp = MagicMock()
    mock_resp.geturl.return_value = "http://example.com/stream.bin"
    mock_resp.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Range": "bytes 0-0/5242880",
        "Content-Disposition": "attachment; filename=stream.bin"
    }
    mock_resp.__enter__.return_value = mock_resp

    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_resp
    monkeypatch.setattr(fetcher, "create_opener", lambda: mock_opener)

    result = {}
    fetcher.finished_signal.connect(lambda r: result.update(r))
    fetcher.run()

    assert result["size_bytes"] == 5242880
    assert "5.00 MB" in result["size_str"]

    # 2. Test Content-Disposition size= discovery
    fetcher2 = FileInfoFetcherWorker("http://example.com/download.dat")
    mock_resp2 = MagicMock()
    mock_resp2.geturl.return_value = "http://example.com/download.dat"
    mock_resp2.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": "attachment; filename=download.dat; size=1048576"
    }
    mock_resp2.__enter__.return_value = mock_resp2
    mock_opener2 = MagicMock()
    mock_opener2.open.return_value = mock_resp2
    monkeypatch.setattr(fetcher2, "create_opener", lambda: mock_opener2)

    result2 = {}
    fetcher2.finished_signal.connect(lambda r: result2.update(r))
    fetcher2.run()

    assert result2["size_bytes"] == 1048576
    assert "1.00 MB" in result2["size_str"]

    # 3. Test URL query param size discovery
    fetcher3 = FileInfoFetcherWorker("http://example.com/file?size=2097152")
    mock_resp3 = MagicMock()
    mock_resp3.geturl.return_value = "http://example.com/file?size=2097152"
    mock_resp3.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": "attachment; filename=file.bin"
    }
    mock_resp3.__enter__.return_value = mock_resp3
    mock_opener3 = MagicMock()
    mock_opener3.open.return_value = mock_resp3
    monkeypatch.setattr(fetcher3, "create_opener", lambda: mock_opener3)

    result3 = {}
    fetcher3.finished_signal.connect(lambda r: result3.update(r))
    fetcher3.run()

    assert result3["size_bytes"] == 2097152
    assert "2.00 MB" in result3["size_str"]


def test_download_worker_streaming_unknown_size(qapp, tmp_path, monkeypatch):
    import os
    from unittest.mock import MagicMock

    save_dir = str(tmp_path)
    worker = DownloadWorker("http://example.com/dynamic_stream.exe", 0, save_dir, "dynamic_stream.exe", allow_resume=False)

    stream_data = b"STREAM_CHUNK_DATA_" * 100

    # Mock HEAD response (No Content-Length, chunked)
    mock_head_resp = MagicMock()
    mock_head_resp.info.return_value = {
        "Transfer-Encoding": "chunked",
        "Accept-Ranges": "none"
    }
    mock_head_resp.__enter__.return_value = mock_head_resp

    # Mock GET response streaming bytes in chunks
    mock_get_resp = MagicMock()
    mock_get_resp.info.return_value = {
        "Transfer-Encoding": "chunked",
        "Content-Type": "application/octet-stream"
    }
    chunks = [stream_data[:500], stream_data[500:], b""]
    mock_get_resp.read.side_effect = chunks
    mock_get_resp.__enter__.return_value = mock_get_resp

    mock_opener = MagicMock()
    def fake_open(req, *args, **kwargs):
        if getattr(req, "method", None) == "HEAD" or getattr(req, "get_method", lambda: "GET")() == "HEAD":
            return mock_head_resp
        return mock_get_resp
    mock_opener.open.side_effect = fake_open

    worker.opener = mock_opener

    finished_results = []
    worker.finished_signal.connect(lambda row, status: finished_results.append((row, status)))

    worker.run()

    target_file = os.path.join(save_dir, "dynamic_stream.exe")
    assert os.path.exists(target_file)
    assert os.path.getsize(target_file) == len(stream_data)
    assert len(finished_results) == 1
    assert finished_results[0][1] == "Complete"


