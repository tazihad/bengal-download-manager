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
    # 1. Standard URL with MIME type
    url = "http://example.com/testfile.mp4"
    headers = {"Content-Type": "video/mp4"}
    assert resolve_filename(url, headers) == "testfile.mp4"

    # 2. GitHub APK Release URL with Content-Disposition & Android APK MIME
    apk_url = "https://github.com/andrewginns/chromium-browser-snapshots-AndroidDesktop_arm64/releases/download/1687988/ChromePublic.apk"
    apk_headers = {
        "Content-Disposition": "attachment; filename=ChromePublic.apk",
        "Content-Type": "application/vnd.android.package-archive"
    }
    assert resolve_filename(apk_url, apk_headers) == "ChromePublic.apk"
    assert resolve_filename(apk_url, {}) == "ChromePublic.apk"

    # 3. Azure/S3 Redirect URL with UUID path and response-content-disposition query parameter
    redirect_url = "https://release-assets.githubusercontent.com/github-production-release-asset/1083868986/0562723c-f190-4894-b57c-2b2b2c955bfd?sp=r&response-content-disposition=attachment%3B%20filename%3DChromePublic.apk"
    assert resolve_filename(redirect_url, {}) == "ChromePublic.apk"

    # 4. Unknown MIME type with filename in URL path (must download as-is)
    unknown_mime_url = "https://example.com/builds/app_binary.customext"
    assert resolve_filename(unknown_mime_url, {"Content-Type": "application/x-custom-unknown-type"}) == "app_binary.customext"

    # 5. Unknown MIME type with Content-Disposition
    cd_unknown_url = "https://example.com/api/v1/download?id=4928"
    cd_unknown_headers = {
        "Content-Disposition": "attachment; filename=\"special_package.pkgx\"",
        "Content-Type": "application/x-unknown-mimetype"
    }
    assert resolve_filename(cd_unknown_url, cd_unknown_headers) == "special_package.pkgx"

    # 6. Fallback when neither URL nor headers provide a filename
    api_url = "https://example.com/api/get/987654321"
    assert resolve_filename(api_url, {"Content-Type": "application/x-unknown-mimetype"}) == "downloaded_file"

    # 7. Script extension replacement with recognized MIME
    script_url = "https://example.com/get.php?id=1"
    assert resolve_filename(script_url, {"Content-Type": "application/pdf"}) == "get.pdf"

def test_get_file_type_description():
    from core.utils import get_file_type_description

    assert get_file_type_description("ChromePublic.apk") == "APK File"
    assert get_file_type_description("installer.exe") == "Executable Application"
    assert get_file_type_description("archive.zip") == "ZIP Archive"
    assert get_file_type_description("package.tar.gz") == "TAR GZ Archive"
    assert get_file_type_description("video.mp4") == "MP4 Video"
    assert get_file_type_description("song.mp3") == "MP3 Audio"
    assert get_file_type_description("document.pdf") == "PDF Document"
    assert get_file_type_description("image.png") == "PNG Image"
    assert get_file_type_description("custom.xyz") == "XYZ File"
    assert get_file_type_description("stream", "application/vnd.android.package-archive") == "APK File"

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

    # Test Snap environment detection
    monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
    monkeypatch.setenv("SNAP_NAME", "bengal-download-manager")
    cmd_snap = get_executable_command(start_minimized=True)
    assert cmd_snap == "bengal-download-manager --minimized"
    cmd_snap_normal = get_executable_command(start_minimized=False)
    assert cmd_snap_normal == "bengal-download-manager"
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("SNAP_NAME", raising=False)

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
    assert advance_semantic_version(0, 1, 0) == (0, 1, "01")
    assert advance_semantic_version(0, 2, 1) == (0, 2, "02")
    assert advance_semantic_version(0, 2, 2) == (0, 2, "03")
    # Rollover when patch reaches 99
    assert advance_semantic_version(0, 1, 99) == (0, 2, "00")
    assert advance_semantic_version(0, 2, 99) == (0, 3, "00")
    assert advance_semantic_version(0, 3, 0) == (0, 3, "01")
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

    # 8. Stable 0.2.00 -> Next alpha on dev branch should be 0.2.01-alpha.1
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.1.99", "v0.2.00"])
    assert tag == "v0.2.01-alpha.1"
    assert ver == "0.2.01-alpha.1"

    # 9. Stable 0.2.01 -> Next alpha on dev branch should be 0.2.02-alpha.1
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.2.01"])
    assert tag == "v0.2.02-alpha.1"
    assert ver == "0.2.02-alpha.1"

    # 10. Stable 0.2.02 -> Merged directly to main should increment to 0.2.03
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.2.02"])
    assert tag == "v0.2.03"
    assert ver == "0.2.03"

    # 11. Stable 0.2.99 -> Next stable on main should rollover to 0.3.00
    tag, ver = determine_next_release_tag(ref="refs/heads/main", tags_list=["v0.2.99"])
    assert tag == "v0.3.00"
    assert ver == "0.3.00"

    # 12. Stable 0.3.00 -> Next alpha on dev branch should be 0.3.01-alpha.1
    tag, ver = determine_next_release_tag(ref="refs/heads/dev", tags_list=["v0.3.00"])
    assert tag == "v0.3.01-alpha.1"
    assert ver == "0.3.01-alpha.1"

    # 13. Manual override tag input
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
    import shutil

    target_file = tmp_path / "archive.tar.gz"
    target_file.write_text("dummy archive content")
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    # 1. Directory path -> DBus ShowFolders success
    run_cmds = []
    def mock_run_dbus(cmd, *a, **k):
        run_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run_dbus)
    show_in_folder(str(target_dir))
    assert len(run_cmds) >= 1
    assert "ShowFolders" in str(run_cmds[0])

    # 2. File path -> DBus ShowItems success
    run_cmds.clear()
    show_in_folder(str(target_file))
    assert len(run_cmds) >= 1
    assert "ShowItems" in str(run_cmds[0])

    # 3. File path -> Nautilus with --select when DBus fails
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, returncode=1))
    opened_cmds = []
    def mock_popen_nautilus(cmd, *args, **kwargs):
        opened_cmds.append(cmd)
        class MockProc:
            def communicate(self):
                if cmd[:3] == ["xdg-mime", "query", "default"]:
                    return ("org.gnome.Nautilus.desktop\n", "")
                return ("", "")
        return MockProc()

    monkeypatch.setattr(shutil, "which", lambda cmd: True)
    opened_cmds.clear()
    monkeypatch.setattr(subprocess, "Popen", mock_popen_nautilus)
    show_in_folder(str(target_file))
    assert ["nautilus", "--select", str(target_file)] in opened_cmds

    # 4. File path -> Dolphin with --select when DBus fails
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

    # 5. File path -> Nemo with --select when DBus fails
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

    # 6. File path -> Generic fallback to xdg-open / gio open parent dir
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd == "xdg-open")
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

    # 7. Non-existent file with existing parent directory -> opens parent directory
    non_existent_file = tmp_path / "downloads" / "does_not_exist.bin"
    opened_cmds.clear()
    show_in_folder(str(non_existent_file))
    assert ["xdg-open", str(target_dir)] in opened_cmds


def test_get_aria2_proxy_url():
    from core.utils import get_aria2_proxy_url

    # 1. No proxy mode
    assert get_aria2_proxy_url({"mode": "no_proxy"}) == ""
    assert get_aria2_proxy_url(None) == ""

    # 2. Manual HTTP proxy without auth
    conf_http = {"mode": "manual", "type": "http", "host": "127.0.0.1", "port": 8080, "auth": False}
    assert get_aria2_proxy_url(conf_http) == "http://127.0.0.1:8080"

    # 3. Manual HTTPS proxy with auth
    conf_https_auth = {
        "mode": "manual", "type": "https", "host": "proxy.example.com", "port": 8443,
        "auth": True, "user": "admin", "password": "secret!password"
    }
    assert get_aria2_proxy_url(conf_https_auth) == "https://admin:secret%21password@proxy.example.com:8443"

    # 4. Manual without host returns empty
    assert get_aria2_proxy_url({"mode": "manual", "host": ""}) == ""


def test_user_home_and_downloads_dir_in_snap(monkeypatch, tmp_path):
    from core.utils import get_user_home_dir, get_user_downloads_dir
    from core.config import get_default_categories, load_category_config, save_category_config

    real_user_home = tmp_path / "home_user"
    real_user_home.mkdir()
    real_downloads = real_user_home / "Downloads"
    real_downloads.mkdir()

    snap_user_data = tmp_path / "snap" / "bengal-download-manager" / "x1"
    snap_user_data.mkdir(parents=True)
    snap_downloads = snap_user_data / "Downloads"
    snap_downloads.mkdir()

    # Simulate standard environment
    monkeypatch.delenv("SNAP_REAL_HOME", raising=False)
    monkeypatch.delenv("SNAP_USER_DATA", raising=False)
    monkeypatch.setenv("HOME", str(real_user_home))
    assert get_user_home_dir() == str(real_user_home)
    assert get_user_downloads_dir() == str(real_downloads)

    # Simulate Snap confinement environment
    monkeypatch.setenv("SNAP_REAL_HOME", str(real_user_home))
    monkeypatch.setenv("SNAP_USER_DATA", str(snap_user_data))
    monkeypatch.setenv("HOME", str(snap_user_data))

    assert get_user_home_dir() == str(real_user_home)
    assert get_user_downloads_dir() == str(real_downloads)

    # Test XDG user-dirs custom download directory in Snap
    custom_down = real_user_home / "MyCustomDownloads"
    custom_down.mkdir()
    config_dir = real_user_home / ".config"
    config_dir.mkdir()
    (config_dir / "user-dirs.dirs").write_text(f'XDG_DOWNLOAD_DIR="{custom_down}"\n')
    assert get_user_downloads_dir() == str(custom_down)

    # Reset config_dir user-dirs.dirs
    (config_dir / "user-dirs.dirs").unlink()
    assert get_user_downloads_dir() == str(real_downloads)

    # Test default categories reflect real downloads folder
    cats = get_default_categories()
    assert cats["General"]["path"] == str(real_downloads)
    assert cats["Compressed"]["path"] == str(real_downloads / "Compressed")

    # Test load_category_config migrates snap user data paths to real home
    fake_config_dir = tmp_path / "app_config"
    monkeypatch.setattr("core.config.get_config_dir", lambda: str(fake_config_dir))
    fake_config_dir.mkdir()

    old_snap_categories = {
        "categories": {
            "General": {
                "path": str(snap_downloads),
                "extensions": "plj"
            },
            "Compressed": {
                "path": str(snap_downloads / "Compressed"),
                "extensions": "7z zip"
            }
        },
        "temp_dir": "/tmp"
    }
    save_category_config(old_snap_categories)

    loaded = load_category_config()
    assert loaded["categories"]["General"]["path"] == str(real_downloads)
    assert loaded["categories"]["Compressed"]["path"] == str(real_downloads / "Compressed")


def test_portal_open_directory_and_single_invocation(monkeypatch, tmp_path):
    from core.utils import _portal_open_directory, show_in_folder
    import subprocess
    import shutil
    import platform

    target_dir = tmp_path / "sandbox_test"
    target_dir.mkdir()
    target_file = target_dir / "item.pdf"
    target_file.write_text("dummy")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd in ("gdbus", "xdg-open"))

    portal_cmds = []
    def mock_run_portal(cmd, *a, **k):
        portal_cmds.append(cmd)
        cmd_str = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "org.freedesktop.FileManager1" in cmd_str:
            return subprocess.CompletedProcess(cmd, returncode=1)
        if "OpenDirectory" in cmd_str:
            return subprocess.CompletedProcess(cmd, returncode=0)
        return subprocess.CompletedProcess(cmd, returncode=1)

    popen_cmds = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, *a, **k: popen_cmds.append(cmd))
    monkeypatch.setattr(subprocess, "run", mock_run_portal)

    # Portal OpenDirectory helper directly
    assert _portal_open_directory(str(target_dir)) is True

    # Show in folder for directory triggers Portal OpenDirectory and stops (no popen fallback)
    show_in_folder(str(target_dir))
    assert len(popen_cmds) == 0

    # Show in folder for file triggers Portal OpenDirectory fallback and stops (no file manager spawned via popen)
    portal_cmds.clear()
    popen_cmds.clear()
    show_in_folder(str(target_file))
    fm_spawns = [c for c in popen_cmds if c[0] in ("xdg-open", "gio", "dolphin", "nautilus", "nemo", "caja", "thunar", "pcmanfm")]
    assert len(fm_spawns) == 0
    assert any("OpenDirectory" in " ".join(cmd) for cmd in portal_cmds)





