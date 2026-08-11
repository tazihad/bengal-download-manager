"""
Tests for Media Downloader core module (YtDlpManager, MediaExtractorWorker, and YtDlpDownloadWorker).
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch
from core.media_downloader import YtDlpManager, MediaExtractorWorker, YtDlpDownloadWorker, parse_size_str_to_bytes


def test_parse_size_str_to_bytes():
    """Test helper parsing size strings to bytes."""
    assert parse_size_str_to_bytes("10.00MiB") == 10.0 * 1024 * 1024
    assert parse_size_str_to_bytes("500KiB") == 500.0 * 1024
    assert parse_size_str_to_bytes("1.5GB") == 1.5 * 1000 * 1000 * 1000


def test_yt_dlp_manager_binary_detection(tmp_path):
    """Test YtDlpManager binary path check logic."""
    fake_bin = tmp_path / "yt-dlp"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    with patch("core.media_downloader.YT_DLP_BIN", fake_bin):
        assert YtDlpManager.is_binary_available() is True
        assert YtDlpManager.get_binary_path() == str(fake_bin)


def test_parse_single_video_data_sorting_and_filtering():
    """Test MediaExtractorWorker parsing of single video yt-dlp JSON with sorting and mhtml filtering."""
    raw_video = {
        "id": "abc12345",
        "title": "Test Video",
        "uploader": "Test Channel",
        "duration": 120,
        "thumbnail": "https://example.com/thumb.jpg",
        "webpage_url": "https://example.com/watch?v=abc12345",
        "formats": [
            {
                "format_id": "140",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "height": None,
                "width": None,
                "filesize": 5000000,
                "url": "https://example.com/audio.m4a"
            },
            {
                "format_id": "136",
                "ext": "mp4",
                "vcodec": "avc1.4d401f",
                "acodec": "none",
                "height": 720,
                "width": 1280,
                "fps": 30,
                "filesize": 25000000,
                "url": "https://example.com/stream_720p.mp4"
            },
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
                "format_id": "mhtml",
                "ext": "mhtml",
                "vcodec": "none",
                "acodec": "none",
                "filesize": 1000,
                "url": "https://example.com/page.mhtml"
            }
        ]
    }

    worker = MediaExtractorWorker("https://example.com/watch?v=abc12345")
    parsed = worker._parse_single_video_data(raw_video)

    assert parsed["title"] == "Test Video"
    assert parsed["duration"] == 120
    # Mhtml format should be filtered out -> 3 remaining valid media formats
    assert len(parsed["formats"]) == 3
    # High to low resolution sorting verification:
    # Index 0 -> 1080p, Index 1 -> 720p, Index 2 -> Audio Only (at the bottom)
    assert parsed["formats"][0]["height"] == 1080
    assert parsed["formats"][1]["height"] == 720
    assert parsed["formats"][2]["res_label"] == "Audio Only"
    assert parsed["formats"][2]["is_audio"] is True


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


def test_yt_dlp_download_worker_init(tmp_path):
    """Test YtDlpDownloadWorker configuration and parameters."""
    worker = YtDlpDownloadWorker(
        url="https://example.com/watch?v=test",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test_video.mp4",
        format_spec="bestvideo[height<=1080]+bestaudio/best",
        is_audio_only=False
    )
    assert worker.url == "https://example.com/watch?v=test"
    assert worker.format_spec == "bestvideo[height<=1080]+bestaudio/best"
    assert worker.is_audio_only is False


def test_yt_dlp_download_worker_status_format(tmp_path):
    """Test YtDlpDownloadWorker emits standard 'Downloading' status string."""
    worker = YtDlpDownloadWorker(
        url="https://example.com/watch?v=test",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test_video.mp4"
    )
    emitted = []
    worker.main_progress_signal.connect(lambda idx, data: emitted.append(data))

    # Mock subprocess stdout parsing block
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download]  29.4% of 100.00MiB at 2.50MiB/s ETA 00:30\n"]
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=104857600):
            worker.run()

    assert len(emitted) > 1
    # Status field (index 2) of progress update must be 'Downloading', not 'Downloading (29.4%)'
    assert emitted[1][2] == "Downloading"


def test_yt_dlp_long_filename_truncation(tmp_path):
    """Test YtDlpDownloadWorker truncates long filenames to prevent OS Errno 36."""
    long_filename = ("83K views · 1.9K reactions ｜ চায়নিজ প্রোডাক্" * 5) + " [1294473729421596].mp4"
    worker = YtDlpDownloadWorker(
        url="https://example.com/watch?v=long",
        row_index=0,
        save_dir=str(tmp_path),
        filename=long_filename
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        worker.run()

        # Check command args sent to subprocess.Popen
        cmd = mock_popen.call_args[0][0]
        assert "--trim-filenames" in cmd
        assert "100" in cmd
        # Output template file path should be truncated under 100 bytes
        out_tmpl = cmd[cmd.index("-o") + 1]
        base_tmpl = os.path.basename(out_tmpl)
        assert len(base_tmpl.encode("utf-8")) < 150

