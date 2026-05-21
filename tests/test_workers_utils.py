import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.workers.fetcher import FileInfoFetcherWorker
from core.workers.download import DownloadWorker
from core.workers.aria2 import Aria2Worker

def test_format_bytes_precision_fetcher():
    worker = FileInfoFetcherWorker("http://example.com")
    # Default: 3 decimal places, padded with 5+3=8 spaces
    assert worker.format_bytes(1024) == "   1.000 KB"
    # Custom: 2 decimal places, no padding
    assert worker.format_bytes(1024, precision=2, pad=False) == "1.00 KB"
    # Custom: 4 decimal places, no padding
    assert worker.format_bytes(1024, precision=4, pad=False) == "1.0000 KB"

def test_format_bytes_precision_download():
    worker = DownloadWorker(0, "http://example.com", "/tmp", "test.zip")
    assert worker.format_bytes(1024) == "   1.000 KB"
    assert worker.format_bytes(1024, precision=2, pad=False) == "1.00 KB"

def test_format_bytes_precision_aria2():
    worker = Aria2Worker("http://example.com", "/tmp", "test.zip")
    assert worker.format_bytes(1024) == "   1.000 KB"
    assert worker.format_bytes(1024, precision=2, pad=False) == "1.00 KB"
