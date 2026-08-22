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


def test_get_clean_env(monkeypatch):
    import sys
    from core.utils import get_clean_env

    # 1. Test stripping PyInstaller and Qt variables
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI12345", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/tmp/_MEI12345/PyQt6/Qt6/plugins")
    monkeypatch.setenv("PYTHONHOME", "/tmp/_MEI12345")
    monkeypatch.setenv("PYTHONPATH", "/tmp/_MEI12345")
    monkeypatch.setenv("_MEIPASS2", "/tmp/_MEI12345")
    monkeypatch.setenv("SOME_CUSTOM_VAR", "/tmp/_MEI12345/lib:/opt/custom")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.delenv("ORIG_LD_LIBRARY_PATH", raising=False)

    clean = get_clean_env(extra_paths="/custom/bin")
    assert "LD_LIBRARY_PATH" not in clean
    assert "QT_PLUGIN_PATH" not in clean
    assert "PYTHONHOME" not in clean
    assert "PYTHONPATH" not in clean
    assert "_MEIPASS2" not in clean
    assert clean["PATH"].startswith("/custom/bin:")
    assert clean["SOME_CUSTOM_VAR"] == "/opt/custom"

    # 2. Test restoring original LD_LIBRARY_PATH if present and safe
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib:/usr/lib")
    clean_restored = get_clean_env()
    assert clean_restored["LD_LIBRARY_PATH"] == "/usr/local/lib:/usr/lib"

    # 3. Test that LD_LIBRARY_PATH_ORIG containing _MEI is filtered out
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/tmp/_MEI12345:/usr/local/lib")
    clean_filtered = get_clean_env()
    assert clean_filtered["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "/tmp/_MEI12345" not in clean_filtered["LD_LIBRARY_PATH"]


def test_advance_semantic_version():
    from core.utils import advance_semantic_version
    # Standard patch increments
    assert advance_semantic_version(0, 1, 79) == (0, 1, "80")
    assert advance_semantic_version(0, 1, 0) == (0, 1, "1")
    assert advance_semantic_version(0, 2, 1) == (0, 2, "2")
    # Rollover when patch reaches 99
    assert advance_semantic_version(0, 1, 99) == (0, 2, "00")
    assert advance_semantic_version(0, 2, 99) == (0, 3, "00")
    assert advance_semantic_version(1, 9, 99) == (1, 10, "00")


def test_determine_next_release_tag():
    from core.utils import determine_next_release_tag

    # 1. Stable 0.1.79 -> Upcoming alpha on dev branch
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.1.79"])
    assert tag == "v0.1.80-alpha.1"
    assert ver == "0.1.80-alpha.1"

    # 2. In-progress alpha 0.1.80-alpha.1 -> Next alpha on dev branch
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.1.79", "v0.1.80-alpha.1"])
    assert tag == "v0.1.80-alpha.2"
    assert ver == "0.1.80-alpha.2"

    # 3. Merging alpha 0.1.80-alpha.2 to main -> Stable 0.1.80 release
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.1.79", "v0.1.80-alpha.2"])
    assert tag == "v0.1.80"
    assert ver == "0.1.80"

    # 4. Merging direct commit to main when latest stable is 0.1.79 -> Stable 0.1.80
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.1.79"])
    assert tag == "v0.1.80"
    assert ver == "0.1.80"

    # 5. Stable 0.1.99 -> Upcoming alpha on dev branch should roll over to 0.2.00-alpha.1
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.1.99"])
    assert tag == "v0.2.00-alpha.1"
    assert ver == "0.2.00-alpha.1"

    # 6. Stable 0.1.99 -> Merged directly to main should roll over to 0.2.00
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.1.99"])
    assert tag == "v0.2.00"
    assert ver == "0.2.00"

    # 7. Alpha 0.2.00-alpha.1 -> Merged to main should create 0.2.00
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.1.99", "v0.2.00-alpha.1"])
    assert tag == "v0.2.00"
    assert ver == "0.2.00"

    # 8. Stable 0.2.00 -> Next alpha on dev branch should be 0.2.1-alpha.1
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.1.99", "v0.2.00"])
    assert tag == "v0.2.1-alpha.1"
    assert ver == "0.2.1-alpha.1"

    # 9. Manual override tag input
    tag, ver = determine_next_release_tag(manual_tag="0.3.5")
    assert tag == "v0.3.5"
    assert ver == "0.3.5"


def test_get_process_memory():
    from core.utils import get_process_memory, format_bytes
    mem = get_process_memory()
    assert isinstance(mem, int)
    assert mem > 0
    formatted = format_bytes(mem)
    assert "B" in formatted


def test_sanitize_media_url():
    from core.utils import sanitize_media_url

    # 1. YouTube Mix / Radio link from search results (must strip list=RD... & start_radio=1 & pp=...)
    mix_url = "https://www.youtube.com/watch?v=obBcRhl57Zg&list=RDobBcRhl57Zg&start_radio=1&pp=ygUGamFobnZpoAcB"
    assert sanitize_media_url(mix_url) == "https://www.youtube.com/watch?v=obBcRhl57Zg"

    # 2. Genuine YouTube Playlist (must be preserved)
    real_playlist = "https://www.youtube.com/playlist?list=PL1234567890abcdef"
    assert sanitize_media_url(real_playlist) == "https://www.youtube.com/playlist?list=PL1234567890abcdef"

    # 3. YouTube Shorts & Tracking parameters
    short_url = "https://www.youtube.com/shorts/abcdef12345?si=sample_si_param&feature=share"
    assert sanitize_media_url(short_url) == "https://www.youtube.com/shorts/abcdef12345"

    # 4. Youtu.be short URL
    short_yt = "https://youtu.be/obBcRhl57Zg?si=track123&feature=shared"
    assert sanitize_media_url(short_yt) == "https://youtu.be/obBcRhl57Zg"

    # 5. TikTok tracking parameters
    tiktok_url = "https://www.tiktok.com/@creator/video/71234567890?is_from_webapp=1&sender_device=pc"
    assert sanitize_media_url(tiktok_url) == "https://www.tiktok.com/@creator/video/71234567890"

    # 6. Plain URL without tracking
def test_show_in_folder_linux(monkeypatch, tmp_path):
    from core.utils import show_in_folder
    import platform
    import subprocess

    target_file = tmp_path / "archive.tar.gz"
    target_file.write_text("dummy archive content")
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    # 1. Directory path -> opens directory directly
    opened_cmds = []
    def mock_popen_dir(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self): return ("", "")
        return MockProc()

    monkeypatch.setattr(subprocess, "Popen", mock_popen_dir)
    show_in_folder(str(target_dir))
    assert len(opened_cmds) == 1
    assert opened_cmds[0] == ["xdg-open", str(target_dir)]

    # 2. File path -> Nautilus with --select
    monkeypatch.setattr("PyQt6.QtDBus.QDBusConnection.sessionBus", lambda: (_ for _ in ()).throw(RuntimeError("no dbus")))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, returncode=1))
    def mock_popen_nautilus(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self):
                if cmd[:3] == ["xdg-mime", "query", "default"]:
                    return ("org.gnome.Nautilus.desktop\n", "")
                return ("", "")
        return MockProc()

    opened_cmds.clear()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_nautilus)
    show_in_folder(str(target_file))
    assert ["nautilus", "--select", str(target_file)] in opened_cmds

    # 3. File path -> Dolphin with --select
    def mock_popen_dolphin(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self):
                if cmd[:3] == ["xdg-mime", "query", "default"]:
                    return ("org.kde.dolphin.desktop\n", "")
                return ("", "")
        return MockProc()

    opened_cmds.clear()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_dolphin)
    show_in_folder(str(target_file))
    assert ["dolphin", "--select", str(target_file)] in opened_cmds

    # 4. File path -> Nemo with --select
    def mock_popen_nemo(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self):
                if cmd[:3] == ["xdg-mime", "query", "default"]:
                    return ("nemo.desktop\n", "")
                return ("", "")
        return MockProc()

    opened_cmds.clear()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_nemo)
    show_in_folder(str(target_file))
    assert ["nemo", "--select", str(target_file)] in opened_cmds

    # 5. File path -> Generic/Unknown fallback -> xdg-open parent dir
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "unknown")
    def mock_popen_generic(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self):
                if cmd[:3] == ["xdg-mime", "query", "default"]:
                    return ("unknown.desktop\n", "")
                return ("", "")
        return MockProc()

    opened_cmds.clear()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_generic)
    show_in_folder(str(target_file))
    assert ["xdg-open", str(tmp_path)] in opened_cmds


    # 6. File path -> dbus-send fallback success
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "unknown")
    def mock_popen_generic2(cmd, *args, **kwargs):
        class MockProc:
            def communicate(self):
                return ("", "")
        return MockProc()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_generic2)

    run_cmds = []
    def mock_run_dbus(cmd, *a, **k):
        run_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0)
    
    monkeypatch.setattr(subprocess, "run", mock_run_dbus)
    opened_cmds.clear()
    show_in_folder(str(target_file))
    assert len(run_cmds) == 1
    assert run_cmds[0][0] == "dbus-send"
    assert f"array:string:file://{target_file}" in run_cmds[0]
    assert len(opened_cmds) == 0


