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



