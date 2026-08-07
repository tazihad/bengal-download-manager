"""
Tests for Media Downloader core module (YtDlpManager & MediaExtractorWorker).
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch
from core.media_downloader import YtDlpManager, MediaExtractorWorker


def test_yt_dlp_manager_binary_detection(tmp_path):
    """Test YtDlpManager binary path check logic."""
    fake_bin = tmp_path / "yt-dlp"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    with patch("core.media_downloader.YT_DLP_BIN", fake_bin):
        assert YtDlpManager.is_binary_available() is True
        assert YtDlpManager.get_binary_path() == str(fake_bin)


def test_parse_single_video_data():
    """Test MediaExtractorWorker parsing of single video yt-dlp JSON."""
    raw_video = {
        "id": "abc12345",
        "title": "Test Video",
        "uploader": "Test Channel",
        "duration": 120,
        "thumbnail": "https://example.com/thumb.jpg",
        "webpage_url": "https://example.com/watch?v=abc12345",
        "formats": [
            {
                "format_id": "137",
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "height": 1080,
                "width": 1920,
                "fps": 30,
                "filesize": 50000000,
                "url": "https://example.com/stream_1080p.mp4"
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "height": None,
                "width": None,
                "filesize": 5000000,
                "url": "https://example.com/audio.m4a"
            }
        ]
    }

    worker = MediaExtractorWorker("https://example.com/watch?v=abc12345")
    parsed = worker._parse_single_video_data(raw_video)

    assert parsed["title"] == "Test Video"
    assert parsed["duration"] == 120
    assert len(parsed["formats"]) == 2
    assert parsed["formats"][0]["res_label"] == "1080p"
    assert parsed["formats"][0]["is_video"] is True
    assert parsed["formats"][1]["res_label"] == "Audio Only"
    assert parsed["formats"][1]["is_audio"] is True


def test_parse_playlist_data():
    """Test MediaExtractorWorker parsing of playlist yt-dlp JSON."""
    raw_playlist = {
        "_type": "playlist",
        "id": "pl123",
        "title": "Test Playlist",
        "uploader": "Test Channel",
        "entries": [
            {"id": "v1", "title": "Video 1", "duration": 60, "url": "https://example.com/watch?v=v1"},
            {"id": "v2", "title": "Video 2", "duration": 180, "url": "https://example.com/watch?v=v2"}
        ]
    }

    worker = MediaExtractorWorker("https://example.com/playlist?list=pl123")
    parsed = worker._parse_playlist_data(raw_playlist)

    assert parsed["title"] == "Test Playlist"
    assert parsed["total_items"] == 2
    assert parsed["entries"][0]["title"] == "Video 1"
    assert parsed["entries"][1]["title"] == "Video 2"
