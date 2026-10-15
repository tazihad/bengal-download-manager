"""Unit tests for core.utils."""

import os
from unittest.mock import MagicMock, patch

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
    show_in_folder,
    _default_file_manager_command,
    _portal_reveal,
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


class TestUtilsModuleImports:
    def test_time_imported_in_utils(self):
        import core.utils as utils
        assert hasattr(utils, "time")
        assert callable(utils.time.time)


class TestShowInFolderXdgDefault:
    """show_in_folder() must honour the XDG-configured default file manager."""

    @staticmethod
    def _xdg_mime_result(desktop_id):
        result = MagicMock()
        result.stdout = f"{desktop_id}\n" if desktop_id else ""
        result.returncode = 0
        return result

    def test_default_file_manager_command_dolphin(self):
        with patch("core.utils.subprocess.run", return_value=self._xdg_mime_result("org.kde.dolphin.desktop")), \
             patch("core.utils.shutil.which", return_value="/usr/bin/dolphin"):
            cmd = _default_file_manager_command("/home/u/Downloads/file.zip")
        assert cmd == ["dolphin", "--select", "/home/u/Downloads/file.zip"]

    def test_default_file_manager_command_thunar_opens_parent(self):
        # Thunar has no --select flag, so it can only open the containing directory.
        with patch("core.utils.subprocess.run", return_value=self._xdg_mime_result("Thunar.desktop")), \
             patch("core.utils.shutil.which", return_value="/usr/bin/thunar"):
            cmd = _default_file_manager_command("/home/u/Downloads/file.zip")
        assert cmd == ["thunar", "/home/u/Downloads"]

    def test_default_file_manager_command_unknown_returns_none(self):
        with patch("core.utils.subprocess.run", return_value=self._xdg_mime_result("org.example.Unknown.desktop")), \
             patch("core.utils.shutil.which", return_value="/usr/bin/unknown"):
            assert _default_file_manager_command("/home/u/Downloads/file.zip") is None

    def test_show_in_folder_file_uses_xdg_default_fm(self):
        path = "/home/u/Downloads/file.zip"
        with patch("core.utils.platform.system", return_value="Linux"), \
             patch("core.utils._is_sandboxed", return_value=False), \
             patch("core.utils.os.path.isdir", return_value=False), \
             patch("core.utils.os.path.exists", return_value=True), \
             patch("core.utils._default_file_manager_command", return_value=["dolphin", "--select", path]), \
             patch("core.utils.subprocess.Popen") as mock_popen, \
             patch("core.utils._dbus_filemanager_show") as mock_dbus:
            show_in_folder(path)
        assert mock_popen.call_args[0][0] == ["dolphin", "--select", path]
        # FileManager1 must never be consulted when the XDG default resolves.
        mock_dbus.assert_not_called()

    def test_show_in_folder_file_unknown_fm_opens_parent(self):
        path = "/home/u/Downloads/file.zip"
        with patch("core.utils.platform.system", return_value="Linux"), \
             patch("core.utils._is_sandboxed", return_value=False), \
             patch("core.utils.os.path.isdir", return_value=False), \
             patch("core.utils.os.path.exists", return_value=True), \
             patch("core.utils._default_file_manager_command", return_value=None), \
             patch("core.utils.shutil.which", return_value="/usr/bin/gio"), \
             patch("core.utils.subprocess.Popen") as mock_popen, \
             patch("core.utils._portal_reveal", return_value=False), \
             patch("core.utils._dbus_filemanager_show") as mock_dbus:
            show_in_folder(path)
        assert mock_popen.call_args[0][0] == ["gio", "open", "/home/u/Downloads"]
        mock_dbus.assert_not_called()

    def test_show_in_folder_filemanager1_only_as_last_resort(self):
        path = "/home/u/Downloads/file.zip"
        with patch("core.utils.platform.system", return_value="Linux"), \
             patch("core.utils._is_sandboxed", return_value=False), \
             patch("core.utils.os.path.isdir", return_value=False), \
             patch("core.utils.os.path.exists", return_value=True), \
             patch("core.utils._default_file_manager_command", return_value=None), \
             patch("core.utils.shutil.which", return_value=None), \
             patch("core.utils.subprocess.Popen") as mock_popen, \
             patch("core.utils._portal_reveal", return_value=False), \
             patch("core.utils._dbus_filemanager_show", return_value=True) as mock_dbus:
            show_in_folder(path)
        mock_popen.assert_not_called()
        mock_dbus.assert_called_once()

    def test_show_in_folder_directory_prefers_xdg_handler(self):
        path = "/home/u/Downloads"
        with patch("core.utils.platform.system", return_value="Linux"), \
             patch("core.utils.os.path.isdir", return_value=True), \
             patch("core.utils.os.path.exists", return_value=True), \
             patch("core.utils.shutil.which", return_value="/usr/bin/gio"), \
             patch("core.utils.subprocess.Popen") as mock_popen, \
             patch("core.utils._dbus_filemanager_show") as mock_dbus:
            show_in_folder(path)
        assert mock_popen.call_args[0][0] == ["gio", "open", path]
        mock_dbus.assert_not_called()

    def test_portal_reveal_passes_target_fd_not_parent(self):
        path = "/home/u/Downloads/file.zip"
        fake_run = MagicMock()
        fake_run.returncode = 0
        with patch("core.utils.shutil.which", return_value="/usr/bin/gdbus"), \
             patch("core.utils.os.path.exists", return_value=True), \
             patch("core.utils.os.path.isdir", return_value=False), \
             patch("core.utils.os.open", return_value=7) as mock_open, \
             patch("core.utils.os.close"), \
             patch("core.utils.subprocess.run", return_value=fake_run) as mock_run:
            assert _portal_reveal(path) is True
        # The target file itself is opened (not the parent directory) so the portal
        # can highlight it; O_DIRECTORY is reserved for real directories.
        assert mock_open.call_args[0][0] == path
        flags = mock_open.call_args[0][1]
        assert not (flags & getattr(os, "O_DIRECTORY", 0))
        method_args = mock_run.call_args[0][0]
        assert "org.freedesktop.portal.OpenURI.OpenDirectory" in method_args

