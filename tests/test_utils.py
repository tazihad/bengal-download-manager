import time
import os
import pytest
from core.utils import (
    resolve_filename,
    get_unique_filepath,
    get_config_dir
)
from main import parse_size_to_bytes, parse_time_to_sec, format_timestamp_relative

def test_resolve_filename():
    url = "http://example.com/testfile.mp4"
    headers = {"Content-Type": "video/mp4"}
    filename = resolve_filename(url, headers)
    assert filename == "testfile.mp4"

def test_parse_size_to_bytes():
    assert parse_size_to_bytes("1.50 MB") == int(1.50 * 1024 * 1024)
    assert parse_size_to_bytes("100 KB") == 100 * 1024
    assert parse_size_to_bytes("2 GB") == 2 * 1024 * 1024 * 1024
    assert parse_size_to_bytes("500 B") == 500
    assert parse_size_to_bytes("Unknown") == 0

def test_parse_time_to_sec():
    assert parse_time_to_sec("45 sec") == 45
    assert parse_time_to_sec("2 min") == 120
    assert parse_time_to_sec("1 hr") == 3600
    assert parse_time_to_sec("Unknown") == 0

def test_format_timestamp_relative():
    now = time.time()
    recent_ts = str(now - 10)
    formatted = format_timestamp_relative(recent_ts, max_relative_seconds=30)
    assert formatted == "Just now"

    old_ts = str(now - 3600)
    formatted_old = format_timestamp_relative(old_ts, max_relative_seconds=300)
    assert ":" in formatted_old

def test_get_unique_filepath(tmp_path):
    target = tmp_path / "testfile.txt"
    target.write_text("content")

    unique = get_unique_filepath(str(target))
    assert unique != str(target)
    assert unique.endswith("(1).txt") or "(1)" in unique

def test_get_config_dir():
    config_dir = get_config_dir()
    assert os.path.exists(config_dir)
