"""
Unit tests for core.desktop integration module.
"""

import os
from core.desktop import (
    open_file,
    open_with,
    show_in_folder,
    get_autostart_filepath,
    is_autostart_enabled,
    get_desktop_file_name,
    ensure_desktop_integration,
)


def test_autostart_path_resolution():
    """Verify autostart desktop entry path."""
    path = get_autostart_filepath()
    assert isinstance(path, str)
    assert path.endswith(".desktop")


def test_open_file_nonexistent():
    """Verify nonexistent file returns False."""
    assert open_file("/path/to/nonexistent/file_bdm_test.xyz") is False


def test_open_with_nonexistent():
    """Verify nonexistent file returns False for open_with."""
    assert open_with("/path/to/nonexistent/file_bdm_test.xyz") is False


def test_show_in_folder_empty():
    """Verify empty path safely returns without error."""
    show_in_folder("")
    show_in_folder(None)


def test_get_desktop_file_name_snap(monkeypatch):
    """Verify snap environment returns snap namespaced ID."""
    monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
    monkeypatch.setenv("SNAP_INSTANCE_NAME", "bengal-download-manager")
    monkeypatch.setenv("SNAP_APP_NAME", "bengal-download-manager")
    assert get_desktop_file_name() == "bengal-download-manager_bengal-download-manager"


def test_get_desktop_file_name_flatpak(monkeypatch):
    """Verify flatpak environment returns FLATPAK_ID."""
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setenv("FLATPAK_ID", "io.github.tazihad.bengal-download-manager")
    assert get_desktop_file_name() == "io.github.tazihad.bengal-download-manager"


def test_get_desktop_file_name_host_discovery(tmp_path, monkeypatch):
    """Verify discovery of candidate desktop files on host."""
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)
    desktop_file = app_dir / "io.github.tazihad.bengal-download-manager.desktop"
    desktop_file.write_text("[Desktop Entry]\nName=BDM\n")

    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "fake_home"))

    assert get_desktop_file_name() == "io.github.tazihad.bengal-download-manager"


def test_ensure_desktop_integration_skipped_in_snap(monkeypatch):
    """Verify ensure_desktop_integration exits early inside Snap or Flatpak."""
    monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
    # Should not raise or perform any file writes
    ensure_desktop_integration()

