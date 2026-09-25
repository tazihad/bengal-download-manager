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
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir(parents=True)
    monkeypatch.setenv("SNAP", str(snap_dir))
    monkeypatch.setenv("SNAP_INSTANCE_NAME", "bengal-download-manager")

    assert set_autostart_enabled(True)
    active_path = autostart_dir / "bengal-download-manager.desktop"
    assert active_path.exists()
    content = active_path.read_text()
    assert "Icon=/snap/bengal-download-manager/current/meta/gui/icon.png" in content
