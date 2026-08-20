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

