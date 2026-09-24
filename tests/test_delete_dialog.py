"""
Unit tests for DeleteDialog and pre-check delete files setting.
"""

from unittest.mock import MagicMock
from ui.dialogs.delete import DeleteDialog
from ui.dialogs.options import OptionsDialog


def test_delete_dialog_defaults(qapp):
    """Verify default behavior is unchecked when setting is false/unset."""
    dialog = DeleteDialog(count=1, is_completed=False)
    assert dialog.should_delete_from_disk() is False
    dialog.close()


def test_delete_dialog_explicit_default(qapp):
    """Verify DeleteDialog respects explicit default_delete_disk param."""
    dialog_true = DeleteDialog(count=2, is_completed=True, default_delete_disk=True)
    assert dialog_true.should_delete_from_disk() is True
    dialog_true.close()

    dialog_false = DeleteDialog(count=2, is_completed=True, default_delete_disk=False)
    assert dialog_false.should_delete_from_disk() is False
    dialog_false.close()


def test_delete_dialog_parent_settings(qapp):
    """Verify DeleteDialog inherits default from parent window settings."""
    from PyQt6.QtWidgets import QWidget
    parent_widget = QWidget()
    parent_widget.settings = {"precheck_delete_files_from_disk": True}

    dialog = DeleteDialog(count=3, is_completed=False, parent=parent_widget)
    assert dialog.should_delete_from_disk() is True
    dialog.close()

    parent_widget.settings = {"precheck_delete_files_from_disk": False}
    dialog2 = DeleteDialog(count=3, is_completed=False, parent=parent_widget)
    assert dialog2.should_delete_from_disk() is False
    dialog2.close()


def test_options_dialog_precheck_delete_setting(qapp):
    """Verify Options dialog exposes precheck delete checkbox and updates settings."""
    from PyQt6.QtWidgets import QWidget
    parent_widget = QWidget()
    parent_widget.settings = {
        "theme": "BDM Auto (Default)",
        "accent": "BDM (Default)",
        "icon_theme": "BDM Auto (Default)",
        "tray_icon": "App Icon (Default)",
        "title_bar": "Automatic",
        "language": "en",
        "precheck_delete_files_from_disk": True,
    }

    dialog = OptionsDialog(parent=parent_widget)
    assert hasattr(dialog, "chk_precheck_delete_files")
    assert dialog.chk_precheck_delete_files.isChecked() is True
    assert dialog.get_precheck_delete_files_from_disk() is True

    dialog.chk_precheck_delete_files.setChecked(False)
    assert dialog.get_precheck_delete_files_from_disk() is False
    dialog.close()
