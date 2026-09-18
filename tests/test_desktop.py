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
