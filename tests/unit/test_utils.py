"""Unit tests for core.utils."""

import os
import pytest

from core.utils import (
    format_bytes,
    get_file_type_description,
    get_unique_filepath,
    get_user_home_dir,
    get_config_dir,
    get_cache_dir,
    is_debug_mode,
    is_verbose_mode,
    load_proxy_config,
    save_proxy_config,
    load_extension_config,
    save_extension_config,
    is_socks_proxy_config,
    get_upstream_proxy_url,
    get_aria2_proxy_url,
    get_system_arch,
    sanitize_media_filename,
    sanitize_media_folder_name,
    sanitize_media_url,
    wrap_url_tooltip,
    get_unique_media_filepath,
)


class TestFormatBytes:
    def test_zero(self):
        assert format_bytes(0) == "0 B"

    def test_negative(self):
        assert format_bytes(-100) == "0 B"

    def test_bytes(self):
        assert format_bytes(512) == "512 B"

    def test_kilobytes(self):
        assert format_bytes(1024) == "1.00 KB"

    def test_megabytes(self):
        assert format_bytes(1024 * 1024) == "1.00 MB"

    def test_gigabytes(self):
        assert format_bytes(1024 ** 3) == "1.00 GB"

    def test_terabytes(self):
        assert format_bytes(1024 ** 4) == "1.00 TB"

    def test_invalid_string(self):
        assert format_bytes("not-a-number") == "0 B"

    def test_none(self):
        assert format_bytes(None) == "0 B"

    def test_float(self):
        assert format_bytes(1536.0) == "1.50 KB"


class TestFileTypeDescription:
    def test_zip(self):
        assert "Archive" in get_file_type_description("file.zip") or "Zip" in get_file_type_description("file.zip")

    def test_exe(self):
        desc = get_file_type_description("installer.exe")
        assert desc

    def test_unknown(self):
        desc = get_file_type_description("file.xyzunknown")
        assert isinstance(desc, str)


class TestUniqueFilepath:
    def test_nonexistent_returns_original(self, tmp_path):
        p = tmp_path / "file.txt"
        assert str(get_unique_filepath(str(p))) == str(p)

    def test_existing_gets_suffix(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("x")
        result = get_unique_filepath(str(p))
        assert result != str(p)
        assert os.path.exists(str(p))

    def test_force_suffix(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("x")
        result = get_unique_filepath(str(p), force_suffix=True)
        assert result != str(p)


class TestDirectories:
    def test_get_user_home_dir(self):
        assert os.path.isdir(get_user_home_dir())

    def test_get_config_dir(self):
        assert get_config_dir()

    def test_get_cache_dir(self):
        assert get_cache_dir()


class TestDebugMode:
    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("BENGAL_DEBUG", raising=False)
        monkeypatch.setattr("sys.argv", ["prog"])
        assert is_debug_mode() is False

    def test_env_debug(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "1")
        assert is_debug_mode() is True

    def test_bengal_debug(self, monkeypatch):
        monkeypatch.setenv("BENGAL_DEBUG", "1")
        assert is_debug_mode() is True

    def test_verbose_default_false(self, monkeypatch):
        monkeypatch.delenv("VERBOSE", raising=False)
        monkeypatch.delenv("BENGAL_VERBOSE", raising=False)
        monkeypatch.delenv("BENGAL_VERBOSE_IPC", raising=False)
        monkeypatch.setattr("sys.argv", ["prog"])
        assert is_verbose_mode() is False

    def test_verbose_env(self, monkeypatch):
        monkeypatch.setenv("BENGAL_VERBOSE", "1")
        assert is_verbose_mode() is True


class TestProxyConfig:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = {"mode": "manual", "type": "http", "host": "127.0.0.1", "port": 8080, "auth": False}
        save_proxy_config(cfg)
        loaded = load_proxy_config()
        assert loaded["host"] == "127.0.0.1"
        assert loaded["port"] == 8080

    def test_default_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        loaded = load_proxy_config()
        assert loaded["mode"] in ("no_proxy", "manual")

    def test_is_socks_false_by_default(self):
        assert is_socks_proxy_config({"mode": "no_proxy"}) is False

    def test_is_socks_http(self):
        assert is_socks_proxy_config({"mode": "manual", "type": "http"}) is False

    def test_is_socks5(self):
        assert is_socks_proxy_config({"mode": "manual", "type": "socks5", "host": "127.0.0.1"}) is True

    def test_is_socks4(self):
        assert is_socks_proxy_config({"mode": "manual", "type": "socks4", "host": "127.0.0.1"}) is True

    def test_is_socks_no_host(self):
        assert is_socks_proxy_config({"mode": "manual", "type": "socks5"}) is False

    def test_upstream_proxy_url_no_proxy(self):
        assert get_upstream_proxy_url({"mode": "no_proxy"}) == ""

    def test_aria2_proxy_url_no_proxy(self):
        assert get_aria2_proxy_url({"mode": "no_proxy"}) == ""


class TestExtensionConfig:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        data = {"ipc_port": 56900, "token": "abc", "max_connections": 8}
        save_extension_config(data)
        loaded = load_extension_config()
        assert loaded["ipc_port"] == 56900
        assert loaded["token"] == "abc"


class TestSystemArch:
    def test_returns_string(self):
        arch = get_system_arch()
        assert isinstance(arch, str)
        assert arch


class TestSanitizers:
    def test_sanitize_filename(self):
        result = sanitize_media_filename("My Video: Title/Name?")
        assert "/" not in result
        assert ":" not in result or result != "My Video: Title/Name?"

    def test_sanitize_filename_empty(self):
        result = sanitize_media_filename("")
        assert isinstance(result, str)

    def test_sanitize_folder(self):
        result = sanitize_media_folder_name("Channel/Name")
        assert "/" not in result

    def test_sanitize_url_strips_tracking_params(self):
        url = "https://www.youtube.com/watch?v=abc&list=RDabc&start_radio=1&pp=xyz&si=123"
        result = sanitize_media_url(url)
        assert "start_radio" not in result
        assert "pp=" not in result
        assert "v=abc" in result

    def test_sanitize_url_valid_kept(self):
        url = "https://example.com/video.mp4"
        assert sanitize_media_url(url) == url


class TestWrapUrlTooltip:
    def test_empty(self):
        assert wrap_url_tooltip("") == ""

    def test_none(self):
        assert wrap_url_tooltip(None) == ""

    def test_short_url_unchanged(self):
        u = "https://ex.com/f.zip"
        assert wrap_url_tooltip(u) == u

    def test_long_url_wrapped(self):
        u = "https://example.com/" + "a" * 200
        wrapped = wrap_url_tooltip(u, max_line_len=80)
        assert "\n" in wrapped
        for line in wrapped.splitlines():
            assert len(line) <= 80


class TestUniqueMediaFilepath:
    def test_returns_string(self, tmp_path):
        result = get_unique_media_filepath(str(tmp_path), "video.mp4")
        assert isinstance(result, str)

    def test_avoids_collision(self, tmp_path):
        (tmp_path / "video.mp4").write_text("x")
        result = get_unique_media_filepath(str(tmp_path), "video.mp4")
        assert result != str(tmp_path / "video.mp4")
