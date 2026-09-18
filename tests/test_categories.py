"""
Unit tests for core.categories domain module.
"""

import time
from core.categories import (
    CATEGORY_EXTENSIONS,
    get_category_for_filename,
    get_all_categories,
    parse_size_to_bytes,
    parse_time_to_sec,
    format_timestamp_relative,
)


def test_category_classification():
    """Verify file categorization by extension."""
    assert get_category_for_filename("archive.zip") == "Compressed"
    assert get_category_for_filename("document.pdf") == "Documents"
    assert get_category_for_filename("song.mp3") == "Music"
    assert get_category_for_filename("installer.exe") == "Programs"
    assert get_category_for_filename("app.AppImage") == "Programs"
    assert get_category_for_filename("movie.mp4") == "Video"
    assert get_category_for_filename("unknown.xyz") == "General"
    assert get_category_for_filename("") == "General"


def test_get_all_categories():
    """Verify all category names are accessible."""
    cats = get_all_categories()
    assert "Compressed" in cats
    assert "Documents" in cats
    assert "Music" in cats
    assert "Programs" in cats
    assert "Video" in cats


def test_parse_size_to_bytes():
    """Verify size string parsing."""
    assert parse_size_to_bytes("100 B") == 100.0
    assert parse_size_to_bytes("1 KB") == 1024.0
    assert parse_size_to_bytes("5 MB") == 5 * 1024 * 1024.0
    assert parse_size_to_bytes("2 GB") == 2 * 1024 * 1024 * 1024.0
    assert parse_size_to_bytes("") == 0.0
    assert parse_size_to_bytes("...") == 0.0


def test_parse_time_to_sec():
    """Verify time string parsing."""
    assert parse_time_to_sec("01:00:00") == 3600.0
    assert parse_time_to_sec("00:01:30") == 90.0
    assert parse_time_to_sec("2 hr") == 7200.0
    assert parse_time_to_sec("5 min") == 300.0
    assert parse_time_to_sec("--") == 0.0
    assert parse_time_to_sec("") == 0.0
    assert parse_time_to_sec("Unknown") == 0.0
    assert parse_time_to_sec("45 sec") == 45.0


def test_format_timestamp_relative():
    """Verify timestamp formatting and relative text."""
    now = time.time()
    assert format_timestamp_relative(str(now)) == "Just now"
    assert format_timestamp_relative(str(now - 10)) == "Just now"
    assert format_timestamp_relative("") == "..."
    assert format_timestamp_relative("...") == "..."
