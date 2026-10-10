"""Unit tests for core.workers."""

import os
import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QThread


class TestDownloadWorkerFormatting:
    @pytest.fixture
    def worker(self, tmp_path, qapp):
        from core.workers.download import DownloadWorker
        w = DownloadWorker(
            url="https://example.com/file.zip",
            download_id=0,
            save_dir=str(tmp_path),
        )
        yield w
        w.workers.clear()

    def test_format_bytes_zero(self, worker):
        assert worker.format_bytes(0) == "0.00  B"

    def test_format_bytes_kilobytes(self, worker):
        assert worker.format_bytes(1024) == "1.00  KB"

    def test_format_bytes_megabytes(self, worker):
        assert worker.format_bytes(1024 * 1024) == "1.00  MB"

    def test_format_bytes_gigabytes(self, worker):
        assert worker.format_bytes(1024 ** 3) == "1.00  GB"

    def test_format_bytes_pad(self, worker):
        result = worker.format_bytes(1024, pad=True)
        assert "KB" in result

    def test_format_time_seconds(self, worker):
        assert worker.format_time(30) == "30 sec"

    def test_format_time_minutes(self, worker):
        assert worker.format_time(120) == "2 min"

    def test_format_time_hours(self, worker):
        assert worker.format_time(7200) == "2 hr"

    def test_format_time_zero(self, worker):
        assert worker.format_time(0) == "0 sec"

    def test_filename_from_url(self, worker):
        assert worker.filename == "file.zip"

    def test_opener_created(self, worker):
        assert worker.opener is not None

    def test_initial_state(self, worker):
        assert worker.is_running is True
        assert worker.is_paused is False
        assert worker.workers == []
        assert worker.segment_stats == {}

    def test_set_global_speed_limit(self, worker, qapp):
        worker.set_global_speed_limit(1024)
        assert worker.current_global_limit == 1024

    def test_set_global_speed_limit_zero(self, worker, qapp):
        worker.set_global_speed_limit(5000)
        worker.set_global_speed_limit(0)
        assert worker.current_global_limit == 0


class TestAria2WorkerFormatting:
    @pytest.fixture
    def worker(self, tmp_path, qapp):
        from core.workers.aria2 import Aria2Worker
        w = Aria2Worker(
            url="https://example.com/file.zip",
            download_id=0,
            save_dir=str(tmp_path),
        )
        yield w

    def test_format_bytes_zero(self, worker):
        assert worker.format_bytes(0) == "0.00  B"

    def test_format_bytes_kilobytes(self, worker):
        assert worker.format_bytes(1024) == "1.00  KB"

    def test_format_bytes_megabytes(self, worker):
        assert worker.format_bytes(1024 * 1024) == "1.00  MB"

    def test_format_time_seconds(self, worker):
        assert worker.format_time(30) == "30 sec"

    def test_format_time_minutes(self, worker):
        assert worker.format_time(120) == "2 min"

    def test_format_time_hours(self, worker):
        assert worker.format_time(7200) == "2 hr"

    def test_filename_from_url(self, worker):
        assert worker.filename == "file.zip"

    def test_initial_state(self, worker):
        assert worker.is_running is True
        assert worker.gid is None

    def test_rpc_url_constructed(self, worker):
        assert "jsonrpc" in worker.rpc_url
        assert "127.0.0.1" in worker.rpc_url

    def test_call_rpc_mocked(self, worker):
        with patch("core.workers.aria2.call_aria2_rpc") as mock_rpc:
            mock_rpc.return_value = {"ok": True}
            result = worker.call_rpc("aria2.getVersion")
            assert result == {"ok": True}
            mock_rpc.assert_called_once()


class TestFileInfoFetcherFormatting:
    @pytest.fixture
    def fetcher(self, tmp_path, qapp):
        from core.workers.fetcher import FileInfoFetcherWorker
        f = FileInfoFetcherWorker(
            url="https://example.com/file.zip",
        )
        yield f

    def test_format_bytes(self, fetcher):
        assert fetcher.format_bytes(1024) == "1.00  KB"

    def test_format_bytes_zero(self, fetcher):
        assert fetcher.format_bytes(0) == "0.00  B"

    def test_url_stored(self, fetcher):
        assert fetcher.url == "https://example.com/file.zip"

    def test_default_user_agent(self, fetcher):
        assert "Mozilla" in fetcher.user_agent

    def test_cookie_jar_exists(self, fetcher):
        assert fetcher.cookie_jar is not None


class TestYouTubePlayerClientArgs:
    def test_auto_client_args(self):
        from core.media.pot_provider import get_youtube_player_client_args, DYNAMIC_YOUTUBE_CLIENTS
        args = get_youtube_player_client_args(custom_client="auto")
        assert args == ["--extractor-args", f"youtube:player_client={DYNAMIC_YOUTUBE_CLIENTS}"]

    def test_dynamic_client_args(self):
        from core.media.pot_provider import get_youtube_player_client_args, DYNAMIC_YOUTUBE_CLIENTS
        args = get_youtube_player_client_args(custom_client="dynamic")
        assert args == ["--extractor-args", f"youtube:player_client={DYNAMIC_YOUTUBE_CLIENTS}"]

    def test_explicit_client_args(self):
        from core.media.pot_provider import get_youtube_player_client_args
        args = get_youtube_player_client_args(custom_client="android,ios")
        assert args == ["--extractor-args", "youtube:player_client=android,ios"]

    def test_default_client_args(self):
        from core.media.pot_provider import get_youtube_player_client_args
        args = get_youtube_player_client_args(custom_client="default")
        assert args == []

    def test_fallback_client_args(self):
        from core.media.pot_provider import get_youtube_fallback_client_args, DYNAMIC_YOUTUBE_CLIENTS
        args = get_youtube_fallback_client_args()
        assert args == ["--extractor-args", f"youtube:player_client={DYNAMIC_YOUTUBE_CLIENTS}"]

    def test_youtube_player_client_from_config(self):
        from core.media.pot_provider import get_youtube_player_client_args, DYNAMIC_YOUTUBE_CLIENTS
        # Config with auto
        cfg_auto = {"media_downloader_defaults": {"youtube_player_client": "auto"}}
        assert get_youtube_player_client_args(cfg_auto) == ["--extractor-args", f"youtube:player_client={DYNAMIC_YOUTUBE_CLIENTS}"]
        # Config with custom client list
        cfg_custom = {"media_downloader_defaults": {"youtube_player_client": "ios,android"}}
        assert get_youtube_player_client_args(cfg_custom) == ["--extractor-args", "youtube:player_client=ios,android"]
        # Config with empty / missing
        assert get_youtube_player_client_args({}) == ["--extractor-args", f"youtube:player_client={DYNAMIC_YOUTUBE_CLIENTS}"]


class TestAria2CertificateValidation:
    def test_aria2_worker_options_check_certificate_false(self, tmp_path, qapp):
        from core.workers.aria2 import Aria2Worker
        w = Aria2Worker(
            url="https://example.com/file.zip",
            download_id=1,
            save_dir=str(tmp_path),
        )
        called_params = []
        with patch("core.workers.aria2.call_aria2_rpc") as mock_rpc:
            def fake_call(method, params=None, **kwargs):
                if method == "aria2.addUri":
                    called_params.append(params)
                    return "gid-12345"
                elif method == "aria2.tellStatus":
                    w.is_running = False
                    return {
                        "status": "complete",
                        "totalLength": "1024",
                        "completedLength": "1024",
                        "downloadSpeed": "0",
                        "files": [{"path": str(tmp_path / "file.zip")}],
                    }
                return {}
            mock_rpc.side_effect = fake_call
            w.run()

        assert len(called_params) == 1
        options = called_params[0][1]
        assert options.get("check-certificate") == "false"

    def test_aria2_daemon_cmd_check_certificate_false(self):
        from core.aria2_daemon import Aria2DaemonManager
        manager = Aria2DaemonManager()
        with patch("subprocess.Popen") as mock_popen, \
             patch("core.aria2_daemon.ensure_aria2", return_value="/usr/bin/aria2c"), \
             patch.object(manager, "stop"), \
             patch.object(manager, "is_port_active", return_value=False):
            mock_proc = mock_popen.return_value
            mock_proc.poll.return_value = None
            mock_proc.pid = 99999
            mock_proc.stderr = None

            res = manager.start(port=56801, token="")
            assert res is True
            mock_popen.assert_called_once()
            cmd_args = mock_popen.call_args[0][0]
            assert "--check-certificate=false" in cmd_args
            manager._process = None


class TestMediaDependenciesAndPotProvider:
    def test_bgutil_dependency_tool_defined(self):
        from core.media.dependencies import DEPENDENCY_TOOLS, get_tool_url
        assert "bgutil-ytdlp-pot-provider" in DEPENDENCY_TOOLS
        tool = DEPENDENCY_TOOLS["bgutil-ytdlp-pot-provider"]
        assert tool["type"] == "plugin_zip"
        assert "Brainicism/bgutil-ytdlp-pot-provider" in tool["url"]
        assert get_tool_url("bgutil-ytdlp-pot-provider") == tool["url"]

    def test_pot_plugin_args_discovery(self, tmp_path, monkeypatch):
        from core.media.pot_provider import get_pot_plugin_args
        monkeypatch.setattr("core.media.dependencies.BIN_DIR", tmp_path)
        # Without yt_dlp_plugins
        args_empty = get_pot_plugin_args()
        assert isinstance(args_empty, list)

        # With yt_dlp_plugins dir
        plugins_dir = tmp_path / "yt_dlp_plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        args = get_pot_plugin_args()
        assert "--plugin-dirs" in args
        assert str(tmp_path) in args

    def test_remove_tool_metadata_when_missing(self, tmp_path, monkeypatch):
        import json
        from core.media.dependencies import _remove_tool_metadata, get_tool_version
        monkeypatch.setattr("core.media.dependencies.BIN_DIR", tmp_path)
        v_file = tmp_path / ".versions.json"
        v_file.write_text(json.dumps({
            "deno_version": "v2.9.7",
            "deno_mtime": 12345.0,
            "bgutil-ytdlp-pot-provider_version": "v2.0.1",
            "bgutil-ytdlp-pot-provider_mtime": 54321.0
        }))

        # Querying non-existent tool removes it from metadata
        assert get_tool_version("bgutil-ytdlp-pot-provider") == ""
        data = json.loads(v_file.read_text())
        assert "bgutil-ytdlp-pot-provider_version" not in data
        assert "deno_version" in data

        # Removing tool directly
        _remove_tool_metadata("deno")
        data_after = json.loads(v_file.read_text())
        assert "deno_version" not in data_after


class TestFileInfoFetcherWorker:
    def test_tier1_head_fast_probing(self, qapp):
        from core.workers.fetcher import FileInfoFetcherWorker
        worker = FileInfoFetcherWorker("https://example.com/test_image.iso")

        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://example.com/test_image.iso"
        mock_resp.headers = {
            "Content-Type": "application/x-iso9660-image",
            "Content-Length": "6128382976",
            "Content-Disposition": 'attachment; filename="ubuntu-24.04.iso"'
        }

        with patch.object(worker, "create_opener") as mock_opener:
            mock_opener_instance = MagicMock()
            mock_opener.return_value = mock_opener_instance
            mock_opener_instance.open.return_value.__enter__.return_value = mock_resp

            results = []
            worker.finished_signal.connect(results.append)
            worker.run()

            assert len(results) == 1
            res = results[0]
            assert res["filename"] == "ubuntu-24.04.iso"
            assert res["size_bytes"] == 6128382976
            assert "5.71  GB" in res["size_str"]

    def test_tier2_range_bytes_fallback(self, qapp):
        from core.workers.fetcher import FileInfoFetcherWorker
        import urllib.error

        worker = FileInfoFetcherWorker("https://example.com/stream_chunk.mkv")

        mock_range_resp = MagicMock()
        mock_range_resp.geturl.return_value = "https://example.com/stream_chunk.mkv"
        mock_range_resp.headers = {
            "Content-Type": "video/x-matroska",
            "Content-Range": "bytes 0-0/104857600"
        }

        def mock_open(req, timeout=10):
            if req.get_method() == "HEAD":
                raise urllib.error.HTTPError(req.get_full_url(), 405, "Method Not Allowed", {}, None)
            ctx = MagicMock()
            ctx.__enter__.return_value = mock_range_resp
            return ctx

        with patch.object(worker, "create_opener") as mock_opener:
            mock_opener_instance = MagicMock()
            mock_opener.return_value = mock_opener_instance
            mock_opener_instance.open.side_effect = mock_open

            results = []
            worker.finished_signal.connect(results.append)
            worker.run()

            assert len(results) == 1
            res = results[0]
            assert res["size_bytes"] == 104857600
            assert "100.00  MB" in res["size_str"]
            assert res["content_type"] == "video/x-matroska"
            assert res["supports_range"] is True


class TestAria2RangeFallback:
    def test_aria2_worker_supports_range_false_initializes_single_conn(self, tmp_path, qapp):
        from core.workers.aria2 import Aria2Worker

        w = Aria2Worker(
            url="https://codeload.github.com/repo/tar.gz",
            download_id=0,
            save_dir=str(tmp_path),
            supports_range=False
        )

        called_params = []
        with patch("core.workers.aria2.call_aria2_rpc") as mock_rpc:
            def fake_call(method, params=None, **kwargs):
                if method == "aria2.addUri":
                    called_params.append(params)
                    return "gid-single-1"
                elif method == "aria2.tellStatus":
                    w.is_running = False
                    return {
                        "status": "complete",
                        "totalLength": "2048",
                        "completedLength": "2048",
                        "downloadSpeed": "0",
                        "files": [{"path": str(tmp_path / "tar.gz")}],
                    }
                return {}

            mock_rpc.side_effect = fake_call
            w.run()

        assert len(called_params) == 1
        options = called_params[0][1]
        assert options.get("split") == "1"
        assert options.get("max-connection-per-server") == "1"
        assert options.get("continue") == "false"

    def test_aria2_worker_recovers_from_error_code_8(self, tmp_path, qapp):
        from core.workers.aria2 import Aria2Worker

        w = Aria2Worker(
            url="https://codeload.github.com/repo/tar.gz",
            download_id=0,
            save_dir=str(tmp_path),
            supports_range=True
        )

        add_calls = []
        remove_results = []
        statuses = [
            # First status check for gid-1: fails with errorCode=8
            {
                "status": "error",
                "errorCode": "8",
                "errorMessage": "Invalid range header. Request: 11534336-14680063/21110236, Response: 0-21110235/21110236",
            },
            # Second status check for gid-2: completes
            {
                "status": "complete",
                "totalLength": "21110236",
                "completedLength": "21110236",
                "downloadSpeed": "0",
                "files": [{"path": str(tmp_path / "tar.gz")}],
            }
        ]

        with patch("core.workers.aria2.call_aria2_rpc") as mock_rpc, \
             patch("core.workers.aria2.load_extension_config", return_value={"max_connections": 8}):
            def fake_call(method, params=None, **kwargs):
                if method == "aria2.addUri":
                    add_calls.append(params)
                    return f"gid-{len(add_calls)}"
                elif method == "aria2.removeDownloadResult":
                    remove_results.append(params)
                    return "OK"
                elif method == "aria2.tellStatus":
                    if statuses:
                        return statuses.pop(0)
                    return {"status": "complete", "totalLength": "0", "completedLength": "0"}
                return {}

            mock_rpc.side_effect = fake_call

            finished_events = []
            w.finished_signal.connect(lambda row, status: finished_events.append((row, status)))
            w.run()

        # Should have called addUri twice: first multi-connection, then single-connection fallback
        assert len(add_calls) == 2
        # First call used multi-connection (split 8)
        assert add_calls[0][1].get("split") == "8"
        # Second call used single connection fallback (split 1, continue false)
        assert add_calls[1][1].get("split") == "1"
        assert add_calls[1][1].get("max-connection-per-server") == "1"
        assert add_calls[1][1].get("continue") == "false"

        # Checked that removeDownloadResult was called for the failed gid-1
        assert len(remove_results) == 1
        assert remove_results[0] == ["gid-1"]

        # Verified that the download completed successfully instead of erroring out
        assert finished_events == [(0, "Complete")]

    def test_fetcher_detects_supports_range_false_when_range_ignored(self, qapp):
        from core.workers.fetcher import FileInfoFetcherWorker
        import urllib.error

        worker = FileInfoFetcherWorker("https://codeload.github.com/repo/archive.tar.gz")

        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://codeload.github.com/repo/archive.tar.gz"
        # Server ignores Range: bytes=0-0 and returns full 200 without Content-Range
        mock_resp.headers = {
            "Content-Type": "application/x-gzip",
            "Content-Length": "21110236",
        }

        def mock_open(req, timeout=10):
            if req.get_method() == "HEAD":
                raise urllib.error.HTTPError(req.get_full_url(), 405, "Method Not Allowed", {}, None)
            ctx = MagicMock()
            ctx.__enter__.return_value = mock_resp
            return ctx

        with patch.object(worker, "create_opener") as mock_opener:
            mock_opener_instance = MagicMock()
            mock_opener.return_value = mock_opener_instance
            mock_opener_instance.open.side_effect = mock_open

            results = []
            worker.finished_signal.connect(results.append)
            worker.run()

            assert len(results) == 1
            res = results[0]
            assert res["size_bytes"] == 21110236
            assert res["supports_range"] is False

    def test_aria2_worker_does_not_overwrite_with_stale_bdpart(self, tmp_path, qapp):
        from core.workers.aria2 import Aria2Worker

        save_dir = tmp_path / "save"
        save_dir.mkdir()
        temp_dir = tmp_path / "cache"
        temp_dir.mkdir()

        filename = "bengal-0.2.79.tar.gz"
        # Stale 256KB bdpart file leftover from prefetch
        stale_bdpart = temp_dir / (filename + ".bdpart")
        stale_bdpart.write_bytes(b"X" * 262144)

        # Real 20MB file downloaded by Aria2 to filename
        full_file = temp_dir / filename
        full_file.write_bytes(b"Y" * 21111276)

        w = Aria2Worker(
            url="https://codeload.github.com/repo/tar.gz",
            download_id=0,
            save_dir=str(save_dir),
            temp_dir=str(temp_dir),
            resume_filename=filename,
            allow_resume=False,
            supports_range=False
        )

        with patch("core.workers.aria2.call_aria2_rpc") as mock_rpc, \
             patch("core.workers.aria2.load_extension_config", return_value={"max_connections": 1}):
            def fake_call(method, params=None, **kwargs):
                if method == "aria2.addUri":
                    full_file.write_bytes(b"Y" * 21111276)
                    return "gid-complete-1"
                elif method == "aria2.tellStatus":
                    w.is_running = False
                    return {
                        "status": "complete",
                        "totalLength": "21111276",
                        "completedLength": "21111276",
                        "downloadSpeed": "0",
                        "files": [{"path": str(full_file)}],
                    }
                return {}

            mock_rpc.side_effect = fake_call
            w.run()

        # The finalized target file in save_dir must be the full 21MB file, NOT the 256KB stale bdpart
        target_path = save_dir / filename
        assert target_path.exists()
        assert target_path.stat().st_size == 21111276
        # The stale bdpart should have been cleaned up
        assert not stale_bdpart.exists()





