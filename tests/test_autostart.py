"""
Tests for autostart desktop entry resolution, creation, and cleanup.
"""

import os
import sys
import tempfile
import pytest

from core.utils import (
    get_autostart_filepath,
    is_autostart_enabled,
    set_autostart_enabled,
    get_executable_command,
    is_running_in_flatpak,
    is_user_flatpak,
    get_flatpak_autostart_icon,
    LEGACY_AUTOSTART_FILENAMES,
)


def test_get_autostart_filepath_default(monkeypatch):
    """Default autostart filepath should point to bd.com.zihad.BengalDownloadManager.desktop."""
    monkeypatch.delenv("SNAP", raising=False)
    path = get_autostart_filepath()
    assert os.path.basename(path) == "bd.com.zihad.BengalDownloadManager.desktop"
    assert ".config/autostart" in path


def test_get_autostart_filepath_snap_custom(tmp_path, monkeypatch):
    """Under Snap, get_autostart_filepath should inspect snap.yaml for autostart field."""
    snap_meta = tmp_path / "meta"
    snap_meta.mkdir(parents=True)
    snap_yaml = snap_meta / "snap.yaml"
    snap_yaml.write_text("name: bengal-download-manager\napps:\n  bdm:\n    autostart: bd.com.zihad.BengalDownloadManager.desktop\n")

    monkeypatch.setenv("SNAP", str(tmp_path))
    path = get_autostart_filepath()
    assert os.path.basename(path) == "bd.com.zihad.BengalDownloadManager.desktop"


def test_autostart_enable_disable_lifecycle(tmp_path, monkeypatch):
    """Verify set_autostart_enabled creates entry, cleans orphans, and disables cleanly."""
    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))

    # Pre-populate orphan legacy files
    orphan = autostart_dir / "bengal-download-manager.desktop"
    orphan.write_text("[Desktop Entry]\nName=Legacy\n")
    assert orphan.exists()

    # Enable autostart
    assert set_autostart_enabled(True, start_minimized=True)
    active_path = autostart_dir / "bd.com.zihad.BengalDownloadManager.desktop"
    assert active_path.exists()
    content = active_path.read_text()
    assert "--minimized" in content
    assert "StartupWMClass=bd.com.zihad.BengalDownloadManager" in content

    # Verify orphan was cleaned up
    assert not orphan.exists()
    assert is_autostart_enabled()

    # Disable autostart
    assert set_autostart_enabled(False)
    assert not active_path.exists()
    assert not is_autostart_enabled()


def test_get_executable_command_modes(monkeypatch):
    """Verify get_executable_command correctly detects Flatpak, Snap, AppImage, and Dev."""
    # Flatpak
    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert get_executable_command(start_minimized=True) == "flatpak run bd.com.zihad.BengalDownloadManager --minimized"

    # Snap
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("SNAP_NAME", "bengal-download-manager")
    monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
    assert get_executable_command(start_minimized=False) == "bengal-download-manager"
    assert get_executable_command(start_minimized=True) == "bengal-download-manager --minimized"


def test_snap_desktop_entry_icon_specification():
    """Verify snap desktop entry declares canonical ${SNAP}/meta/gui/icon.png for start menu integration."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop_path = os.path.join(repo_root, "snap", "gui", "bengal-download-manager.desktop")
    assert os.path.exists(desktop_path)

    with open(desktop_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Icon=${SNAP}/meta/gui/icon.png" in content
    assert "Exec=bengal-download-manager %u" in content
    assert "StartupWMClass=bengal-download-manager_bengal-download-manager" in content


def test_autostart_snap_icon_path(tmp_path, monkeypatch):
    """Under Snap, set_autostart_enabled should write canonical snap icon path."""
    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir(parents=True)
    monkeypatch.setenv("SNAP", str(snap_dir))
    monkeypatch.setenv("SNAP_INSTANCE_NAME", "bengal-download-manager")

    assert set_autostart_enabled(True)
    active_path = autostart_dir / "bengal-download-manager.desktop"
    assert active_path.exists()
    content = active_path.read_text()
    assert "Icon=/snap/bengal-download-manager/current/meta/gui/icon.png" in content


def test_flatpak_autostart_portal_lifecycle(tmp_path, monkeypatch):
    """Under Flatpak, set_autostart_enabled should invoke org.freedesktop.portal.Background and manage sandbox desktop entry."""
    import subprocess
    from unittest.mock import MagicMock

    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")

    assert is_running_in_flatpak()

    gdbus_calls = []

    def mock_run(cmd, *args, **kwargs):
        gdbus_calls.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "(objectpath '/org/freedesktop/portal/desktop/request/1_99/t',)"
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)

    # 1. Enable autostart with minimized
    assert set_autostart_enabled(True, start_minimized=True)

    assert len(gdbus_calls) == 1
    call_str = " ".join(gdbus_calls[0])
    assert "org.freedesktop.portal.Background.RequestBackground" in call_str
    assert "'autostart': <true>" in call_str
    assert "'--minimized'" in call_str

    sandbox_file = autostart_dir / "bd.com.zihad.BengalDownloadManager.desktop"
    assert sandbox_file.exists()
    content = sandbox_file.read_text()
    assert "Icon=" in content
    assert is_autostart_enabled()

    # 2. Disable autostart
    assert set_autostart_enabled(False)
    assert len(gdbus_calls) == 2
    disable_call_str = " ".join(gdbus_calls[1])
    assert "org.freedesktop.portal.Background.RequestBackground" in disable_call_str
    assert "'autostart': <false>" in disable_call_str

    assert not sandbox_file.exists()
    assert not is_autostart_enabled()


def test_flatpak_icon_resolution_user_and_system(tmp_path, monkeypatch):
    """Verify get_flatpak_autostart_icon returns user icon for --user and system icon for system-wide."""
    fake_info = tmp_path / ".flatpak-info"
    monkeypatch.setattr(os.path, "exists", lambda p: True if p == "/.flatpak-info" else (p == str(fake_info)))
    
    # User flatpak info
    fake_info.write_text("[Instance]\napp-path=/home/testuser/.local/share/flatpak/app/bd.com.zihad.BengalDownloadManager\n")
    import builtins
    orig_open = builtins.open
    def mock_open(path, *args, **kwargs):
        if path == "/.flatpak-info":
            return orig_open(str(fake_info), *args, **kwargs)
        return orig_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", mock_open)

    assert is_user_flatpak()
    user_icon = get_flatpak_autostart_icon()
    assert ".local/share/flatpak" in user_icon

    # System flatpak info
    fake_info.write_text("[Instance]\napp-path=/var/lib/flatpak/app/bd.com.zihad.BengalDownloadManager\n")
    assert not is_user_flatpak()
    sys_icon = get_flatpak_autostart_icon()
    assert "/var/lib/flatpak" in sys_icon
