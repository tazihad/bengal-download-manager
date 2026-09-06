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


def test_dependency_tools_standalone_yt_dlp_url():
    """Verify that DEPENDENCY_TOOLS uses standalone yt-dlp binary builds."""
    from core.media_downloader import DEPENDENCY_TOOLS
    url = DEPENDENCY_TOOLS["yt-dlp"]["url"]
    assert "yt-dlp_linux" in url


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
    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
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

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        worker.run()

        # Check command args sent to subprocess.Popen
        cmd = mock_popen.call_args[0][0]
        # Output template file path should be truncated under 150 bytes
        out_tmpl = cmd[cmd.index("-o") + 1]
        base_tmpl = os.path.basename(out_tmpl)
        assert len(base_tmpl.encode("utf-8")) < 150


def test_dependency_manager_worker_force_download(tmp_path):
    """Test DependencyManagerWorker force_download invokes download for installed tools."""
    from core.media_downloader import DependencyManagerWorker
    worker = DependencyManagerWorker(force_download=True)
    with patch.object(worker, "_download_and_install_tool") as mock_dl:
        with patch("os.access", return_value=True), patch("pathlib.Path.exists", return_value=True):
            worker.run()
            # yt-dlp, ffmpeg (covering ffprobe), deno, AtomicParsley -> 4 unique downloads
            assert mock_dl.call_count == 4


def test_get_tool_version_local_only_does_not_return_system_binary(tmp_path):
    """Test get_tool_version strictly queries XDG data BIN_DIR and ignores host system PATH."""
    from core.media_downloader import get_tool_version, get_local_tool_path, get_tool_path

    # Simulate local bin does not exist
    with patch("core.media_downloader.BIN_DIR", tmp_path / "empty_bin"), \
         patch("core.media_downloader.YT_DLP_BIN", tmp_path / "empty_bin" / "yt-dlp"), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert get_local_tool_path("ffmpeg") == ""
        assert get_tool_path("ffmpeg") == ""
        assert get_tool_version("ffmpeg") == ""


def test_media_downloader_subprocess_clean_env(monkeypatch, tmp_path):
    """Test MediaExtractorWorker and YtDlpDownloadWorker pass sanitized clean_env without PyInstaller LD_LIBRARY_PATH."""
    from core.media_downloader import MediaExtractorWorker, YtDlpDownloadWorker, get_tool_version

    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEItest123")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    fake_bin = tmp_path / "yt-dlp"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    # 1. Test get_tool_version
    with patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("core.media_downloader.YT_DLP_BIN", fake_bin), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="2024.08.01", stderr="", returncode=0)
        get_tool_version("yt-dlp")
        assert mock_run.called
        run_env = mock_run.call_args[1].get("env", {})
        assert "LD_LIBRARY_PATH" not in run_env

    # 2. Test MediaExtractorWorker
    extractor = MediaExtractorWorker("https://example.com/watch?v=test")
    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ('{"id":"test","title":"Test","formats":[]}', "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        extractor.run()
        assert mock_popen.called
        popen_env = mock_popen.call_args[1].get("env", {})
        assert "LD_LIBRARY_PATH" not in popen_env

    # 3. Test YtDlpDownloadWorker
    downloader = YtDlpDownloadWorker(
        url="https://example.com/watch?v=test",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test.mp4"
    )
    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        downloader.run()
        assert mock_popen.called
        popen_env = mock_popen.call_args[1].get("env", {})
        assert "LD_LIBRARY_PATH" not in popen_env


def test_media_downloader_fractional_percentage_progress(tmp_path):
    """Verify that YtDlpDownloadWorker extracts fractional percentages and dual byte metrics."""
    downloader = YtDlpDownloadWorker(
        url="https://example.com/watch?v=frac",
        row_index=0,
        save_dir=str(tmp_path),
        filename="frac.mp4"
    )

    captured_tuples = []
    downloader.main_progress_signal.connect(lambda row, data: captured_tuples.append(data))

    aria2c_line = "[#2a20b0 22.45MiB/100.00MiB(22%) CN:16 DL:5.0MiB ETA:15s]"
    ytdlp_line = "[download]  34.56% of ~ 100.00MiB at 5.00MiB/s ETA 00:13"

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = [aria2c_line, ytdlp_line]
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        downloader.run()

    # Verify aria2c fractional dual bytes parsed
    assert len(captured_tuples) >= 2
    aria2_tuple = captured_tuples[1]  # index 0 was connecting, 1 is aria2c line
    assert aria2_tuple[5] == int(22.45 * 1024 * 1024)
    assert aria2_tuple[6] == int(100.00 * 1024 * 1024)
    # Ratio calculation yields 22.45%
    aria2_pct = (aria2_tuple[5] / aria2_tuple[6]) * 100
    assert f"{aria2_pct:.2f}%" == "22.45%"

    # Verify yt-dlp fractional percentage parsed
    ytdlp_tuple = captured_tuples[2]
    ytdlp_pct = (ytdlp_tuple[5] / ytdlp_tuple[6]) * 100
    assert f"{ytdlp_pct:.2f}%" == "34.56%"


def test_yt_dlp_debug_mode_verbose_flag(tmp_path):
    """Verify that --debug mode enables --verbose in yt-dlp arguments."""
    import sys
    downloader = YtDlpDownloadWorker(
        url="https://example.com/watch?v=dbg",
        row_index=0,
        save_dir=str(tmp_path),
        filename="dbg.mp4"
    )

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch.object(sys, "argv", ["main.py", "--debug"]), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download] Destination: /tmp/test.mp4"]
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        downloader.run()

        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--verbose" in cmd
        assert "--no-warnings" not in cmd


def test_yt_dlp_extractor_args_youtube_player_client(tmp_path):
    """Verify that youtube:player_client extractor arg is passed to yt-dlp."""
    downloader = YtDlpDownloadWorker(
        url="https://example.com/watch?v=android_test",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test.mp4"
    )

    custom_cfg = {
        "media_downloader_defaults": {
            "youtube_player_client": "web,ios"
        }
    }

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("core.media_downloader.load_category_config", return_value=custom_cfg), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download] Destination: /tmp/test.mp4"]
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        downloader.run()

        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--extractor-args" in cmd
        ext_idx = cmd.index("--extractor-args")
        assert cmd[ext_idx + 1] == "youtube:player_client=web,ios"

    # Test default fallback when not configured
    downloader_def = YtDlpDownloadWorker(
        url="https://example.com/watch?v=default_test",
        row_index=1,
        save_dir=str(tmp_path),
        filename="default.mp4"
    )
    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value="/fake/bin"), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("core.media_downloader.load_category_config", return_value={}), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download] Destination: /tmp/default.mp4"]
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        downloader_def.run()

        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--extractor-args" in cmd
        ext_idx = cmd.index("--extractor-args")
        assert cmd[ext_idx + 1] == "youtube:player_client=default"


def test_media_downloader_headers_and_cookies(tmp_path):
    """Verify that MediaExtractorWorker and YtDlpDownloadWorker send Accept-Language, Origin, and Cookie headers."""
    # 1. Test MediaExtractorWorker
    extractor = MediaExtractorWorker(
        "https://cdn1017.cdn-tnmr.org/hls2/master.m3u8",
        referrer="https://lulustream.com/7kt553us8e30",
        user_agent="Mozilla/5.0 Firefox/156.0",
        cookies="session_id=xyz123"
    )

    fake_bin = tmp_path / "yt-dlp"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ('{"id":"test","title":"Test","formats":[]}', "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        extractor.run()

        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--referer" in cmd
        assert cmd[cmd.index("--referer") + 1] == "https://lulustream.com/7kt553us8e30"
        assert "--user-agent" in cmd
        assert cmd[cmd.index("--user-agent") + 1] == "Mozilla/5.0 Firefox/156.0"
        assert "Accept-Language:en-US,en;q=0.9" in cmd
        assert "Origin:https://lulustream.com" in cmd
        assert "Cookie:session_id=xyz123" in cmd

    # 2. Test YtDlpDownloadWorker
    downloader = YtDlpDownloadWorker(
        url="https://cdn1017.cdn-tnmr.org/hls2/master.m3u8",
        row_index=0,
        save_dir=str(tmp_path),
        filename="video.mp4",
        referrer="https://lulustream.com/7kt553us8e30",
        user_agent="Mozilla/5.0 Firefox/156.0",
        cookies="session_id=xyz123"
    )

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download] Destination: /tmp/video.mp4"]
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        downloader.run()

        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "--referer" in cmd
        assert cmd[cmd.index("--referer") + 1] == "https://lulustream.com/7kt553us8e30"
        assert "--user-agent" in cmd
        assert cmd[cmd.index("--user-agent") + 1] == "Mozilla/5.0 Firefox/156.0"
        assert "Accept-Language:en-US,en;q=0.9" in cmd
        assert "Origin:https://lulustream.com" in cmd
        assert "Cookie:session_id=xyz123" in cmd


def test_yt_dlp_download_worker_pause_and_stop(tmp_path):
    """Verify YtDlpDownloadWorker.pause() and stop() terminate subprocess and do not emit Error signals."""
    fake_bin = tmp_path / "yt-dlp"
    fake_bin.touch()
    fake_bin.chmod(0o755)

    # 1. Test pause()
    worker = YtDlpDownloadWorker(
        url="https://example.com/video.m3u8",
        row_index=0,
        save_dir=str(tmp_path),
        filename="test_video.mp4"
    )
    mock_proc = MagicMock()
    mock_proc.stdout = ["[download]  25.0% of 10.00MiB at 1.00MiB/s ETA 00:10"]
    mock_proc.wait.return_value = -15
    mock_proc.returncode = -15
    worker.process = mock_proc

    progress_emissions = []
    finished_emissions = []
    worker.main_progress_signal.connect(lambda row, data: progress_emissions.append(data))
    worker.finished_signal.connect(lambda row, path: finished_emissions.append(path))

    # Pause worker
    worker.pause()
    assert worker.is_paused is True
    assert worker.is_running is False
    assert mock_proc.terminate.called

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen", return_value=mock_proc):
        worker.run()

    # Verify no "Error" progress or finished signals were emitted due to pause
    assert not any(d[2] == "Error" for d in progress_emissions)
    assert len(finished_emissions) == 0

    # 2. Test stop()
    worker2 = YtDlpDownloadWorker(
        url="https://example.com/video.m3u8",
        row_index=1,
        save_dir=str(tmp_path),
        filename="test_video2.mp4"
    )
    mock_proc2 = MagicMock()
    mock_proc2.stdout = []
    mock_proc2.wait.return_value = -9
    mock_proc2.returncode = -9
    worker2.process = mock_proc2

    progress_emissions2 = []
    finished_emissions2 = []
    worker2.main_progress_signal.connect(lambda row, data: progress_emissions2.append(data))
    worker2.finished_signal.connect(lambda row, path: finished_emissions2.append(path))

    worker2.stop()
    assert worker2.is_running is False
    assert mock_proc2.terminate.called

    with patch("core.media_downloader.YtDlpManager.ensure_binary", return_value=str(fake_bin)), \
         patch("core.media_downloader.BIN_DIR", tmp_path), \
         patch("subprocess.Popen", return_value=mock_proc2):
        worker2.run()

    assert not any(d[2] == "Error" for d in progress_emissions2)
    assert len(finished_emissions2) == 0


def test_parse_single_video_data_estimates_filesize_from_tbr():
    """Verify MediaExtractorWorker estimates filesize when filesize is None/0 but duration and tbr are present."""
    raw_video = {
        "id": "stream123",
        "title": "HLS Stream Video",
        "duration": 300,  # 300 seconds
        "formats": [
            {
                "format_id": "1080p",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 1080,
                "width": 1920,
                "filesize": None,  # Missing in HLS streams
                "tbr": 4000,       # 4000 kbps
                "url": "https://example.com/hls/1080p.m3u8"
            }
        ]
    }

    worker = MediaExtractorWorker("https://example.com/hls/master.m3u8")
    parsed = worker._parse_single_video_data(raw_video)

    assert len(parsed["formats"]) == 1
    fmt = parsed["formats"][0]
    # Expected: 300 sec * 4000 kbps * 125 bytes/kb = 150,000,000 bytes (~150 MB)
    assert fmt["filesize"] == 150000000








