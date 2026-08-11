import time
import os
import pytest
from core.utils import (
    resolve_filename,
    get_unique_filepath,
    get_config_dir,
    is_media_downloader_url
)
from main import parse_size_to_bytes, parse_time_to_sec, format_timestamp_relative


def test_is_media_downloader_url():
    # Popular media URLs & short links
    assert is_media_downloader_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_media_downloader_url("https://youtu.be/dQw4w9WgXcQ") is True
    assert is_media_downloader_url("https://youtube.com/shorts/abc12345") is True
    assert is_media_downloader_url("https://x.com/user/status/12345678") is True
    assert is_media_downloader_url("https://twitter.com/user/status/12345678") is True
    assert is_media_downloader_url("https://www.facebook.com/watch/?v=123") is True
    assert is_media_downloader_url("https://fb.watch/abc123/") is True
    assert is_media_downloader_url("https://www.tiktok.com/@user/video/123") is True
    assert is_media_downloader_url("https://vt.tiktok.com/ZS12345/") is True
    assert is_media_downloader_url("https://www.instagram.com/reel/C123/") is True
    assert is_media_downloader_url("https://vimeo.com/123456") is True
    assert is_media_downloader_url("https://dai.ly/x1234") is True
    assert is_media_downloader_url("https://clips.twitch.tv/AbcXyz") is True
    assert is_media_downloader_url("https://v.redd.it/abc123xyz") is True

    # Standard non-media file links
    assert is_media_downloader_url("https://releases.ubuntu.com/22.04/ubuntu.iso") is False
    assert is_media_downloader_url("https://example.com/document.pdf") is False
    assert is_media_downloader_url("") is False

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

def test_find_aria2_bundled():
    from core.utils import find_aria2, get_system_arch
    arch = get_system_arch()
    assert arch in ["x86_64", "aarch64", "i686"]
    
    aria2_path = find_aria2()
    assert aria2_path is not None
    assert os.path.exists(aria2_path)
    assert os.access(aria2_path, os.X_OK)

def test_autostart_environment_command_and_file_management(monkeypatch, tmp_path):
    from core.utils import get_executable_command, set_autostart_enabled, is_autostart_enabled

    # Test AppImage environment detection
    fake_appimage = tmp_path / "Bengal.AppImage"
    fake_appimage.write_text("#!/bin/sh")
    monkeypatch.setenv("APPIMAGE", str(fake_appimage))
    cmd = get_executable_command(start_minimized=True)
    assert f'"{fake_appimage}" --minimized' in cmd
    monkeypatch.delenv("APPIMAGE", raising=False)

    # Test Flatpak environment detection
    monkeypatch.setenv("FLATPAK_ID", "io.github.tazihad.bengal-download-manager")
    cmd_flatpak = get_executable_command(start_minimized=False)
    assert "flatpak run io.github.tazihad.bengal-download-manager" in cmd_flatpak
    monkeypatch.delenv("FLATPAK_ID", raising=False)

    # Test autostart creation and removal with custom path
    test_autostart_file = str(tmp_path / "autostart" / "bengal-download-manager.desktop")
    monkeypatch.setattr("core.utils.get_autostart_filepath", lambda: test_autostart_file)

    assert is_autostart_enabled() is False
    set_autostart_enabled(True, start_minimized=True)
    assert is_autostart_enabled() is True
    with open(test_autostart_file, "r") as f:
        content = f.read()
        assert "[Desktop Entry]" in content
        assert "X-GNOME-Autostart-enabled=true" in content

    set_autostart_enabled(False)
    assert is_autostart_enabled() is False


def test_setup_logging_debug_flag():
    import logging
    from core.utils import setup_logging

    logger = setup_logging(debug=True)
    assert logger.level == logging.DEBUG

    logger_info = setup_logging(debug=False)
    assert logger_info.level == logging.INFO

