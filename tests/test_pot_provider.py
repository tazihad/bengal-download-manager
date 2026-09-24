"""
Unit tests for YouTube Proof-of-Origin (PO) Token Provider module.
"""

import json
from unittest.mock import patch, MagicMock
import urllib.error

from core.media.pot_provider import (
    check_pot_provider_status,
    is_pot_provider_available,
    get_pot_extractor_args,
    get_deno_executable_path,
    get_pot_env,
    DEFAULT_POT_PROVIDER_URL,
    _POT_PROVIDER_CACHE,
)


def test_check_pot_provider_status_success():
    """Verify check_pot_provider_status correctly reports when daemon is online."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({"status": "ok", "version": "1.0.4"}).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        ok, msg = check_pot_provider_status("http://127.0.0.1:4416")
        assert ok is True
        assert "1.0.4" in msg


def test_check_pot_provider_status_unreachable():
    """Verify check_pot_provider_status reports failure when server is down."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        ok, msg = check_pot_provider_status("http://127.0.0.1:4416")
        assert ok is False
        assert "Connection refused" in msg


def test_is_pot_provider_available_caching():
    """Verify is_pot_provider_available caches check results to avoid stalling."""
    _POT_PROVIDER_CACHE.clear()
    _POT_PROVIDER_CACHE.update({"url": "", "available": None, "timestamp": 0})

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"status":"ok"}'
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        # First call hits network
        res1 = is_pot_provider_available("http://127.0.0.1:4416")
        assert res1 is True
        assert mock_urlopen.call_count == 1

        # Second call within TTL uses cache
        res2 = is_pot_provider_available("http://127.0.0.1:4416")
        assert res2 is True
        assert mock_urlopen.call_count == 1


def test_get_deno_executable_path():
    """Verify get_deno_executable_path finds media download tools Deno or system Deno."""
    with patch("core.media.dependencies.get_tool_path", return_value="/home/user/.local/share/bengal/bin/deno"), \
         patch("os.path.exists", return_value=True), \
         patch("os.access", return_value=True):
        assert get_deno_executable_path() == "/home/user/.local/share/bengal/bin/deno"


def test_get_pot_env():
    """Verify get_pot_env injects DENO variable when deno executable exists."""
    with patch("core.media.pot_provider.get_deno_executable_path", return_value="/opt/deno/bin/deno"):
        env = get_pot_env()
        assert env.get("DENO") == "/opt/deno/bin/deno"


def test_get_pot_extractor_args_disabled():
    """Verify disabled configuration returns youtube:fetch_pot=never."""
    cfg = {
        "media_downloader_defaults": {
            "youtube_pot_enabled": False
        }
    }
    assert get_pot_extractor_args(cfg) == ["--extractor-args", "youtube:fetch_pot=never"]


def test_get_pot_extractor_args_auto_with_deno():
    """Verify auto mode when Deno is present generates tokens automatically (empty args)."""
    cfg = {
        "media_downloader_defaults": {
            "youtube_pot_enabled": True
        }
    }
    with patch("core.media.pot_provider.is_pot_provider_available", return_value=False), \
         patch("core.media.pot_provider.get_deno_executable_path", return_value="/bin/deno"):
        assert get_pot_extractor_args(cfg) == []


def test_get_pot_extractor_args_auto_with_daemon():
    """Verify auto mode when local HTTP daemon is active injects daemon base_url."""
    cfg = {
        "media_downloader_defaults": {
            "youtube_pot_enabled": True
        }
    }
    with patch("core.media.pot_provider.is_pot_provider_available", return_value=True):
        args = get_pot_extractor_args(cfg)
        assert "--extractor-args" in args
        assert "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416" in args


def test_get_pot_extractor_args_no_js_runtime():
    """Verify auto mode when no JS runtime is available disables fetch_pot to prevent format corruption."""
    cfg = {
        "media_downloader_defaults": {
            "youtube_pot_enabled": True
        }
    }
    with patch("core.media.pot_provider.is_pot_provider_available", return_value=False), \
         patch("core.media.pot_provider.get_deno_executable_path", return_value=None), \
         patch("shutil.which", return_value=None):
        assert get_pot_extractor_args(cfg) == ["--extractor-args", "youtube:fetch_pot=never"]


def test_ytdlp_channel_and_urls():
    """Verify yt-dlp stable and nightly update channel resolution."""
    from core.media.dependencies import get_ytdlp_channel, set_ytdlp_channel, get_tool_url

    with patch("core.config.load_category_config", return_value={}):
        assert get_ytdlp_channel() == "stable"
        stable_url = get_tool_url("yt-dlp", channel="stable")
        assert "yt-dlp/releases/latest" in stable_url

        nightly_url = get_tool_url("yt-dlp", channel="nightly")
        assert "yt-dlp-nightly-builds/releases/latest" in nightly_url

    with patch("core.config.load_category_config", return_value={"media_downloader_defaults": {"ytdlp_channel": "nightly"}}):
        assert get_ytdlp_channel() == "nightly"
        assert "yt-dlp-nightly-builds/releases/latest" in get_tool_url("yt-dlp")

