"""Component tests for UI dialogs."""

import pytest
from PyQt6.QtWidgets import QApplication


class TestDeleteDialog:
    def test_construction(self, qapp):
        from ui.dialogs.delete import DeleteDialog
        dlg = DeleteDialog(count=3)
        assert dlg is not None
        assert dlg.windowTitle() == "Delete"
        dlg.close()

    def test_completed_flag(self, qapp):
        from ui.dialogs.delete import DeleteDialog
        dlg = DeleteDialog(count=1, is_completed=True)
        assert "Completed" in dlg.windowTitle()
        dlg.close()

    def test_has_yes_no_buttons(self, qapp):
        from ui.dialogs.delete import DeleteDialog
        dlg = DeleteDialog(count=1)
        assert dlg.btn_yes is not None
        assert dlg.btn_no is not None
        dlg.close()

    def test_should_delete_from_disk_default(self, qapp):
        from ui.dialogs.delete import DeleteDialog
        dlg = DeleteDialog(count=1, default_delete_disk=False)
        assert dlg.should_delete_from_disk() is False
        dlg.close()

    def test_should_delete_from_disk_checked(self, qapp):
        from ui.dialogs.delete import DeleteDialog
        dlg = DeleteDialog(count=1, default_delete_disk=True)
        assert dlg.should_delete_from_disk() is True
        dlg.close()


class TestRenameDialog:
    def test_construction(self, qapp):
        from ui.dialogs.rename import RenameDialog
        dlg = RenameDialog(current_filename="file.zip")
        assert dlg is not None
        dlg.close()

    def test_has_input(self, qapp):
        from ui.dialogs.rename import RenameDialog
        dlg = RenameDialog(current_filename="file.zip")
        from PyQt6.QtWidgets import QLineEdit
        edits = dlg.findChildren(QLineEdit)
        assert len(edits) > 0
        dlg.close()


class TestColumnDialog:
    def test_construction(self, qapp):
        from ui.dialogs.column import ColumnDialog
        columns = [
            {"name": "File Name", "visible": True},
            {"name": "Size", "visible": True},
            {"name": "Status", "visible": False},
        ]
        dlg = ColumnDialog(columns_data=columns)
        assert dlg is not None
        dlg.close()

    def test_list_widget_items(self, qapp):
        from ui.dialogs.column import ColumnDialog
        columns = [
            {"name": "File Name", "visible": True},
            {"name": "Size", "visible": True},
        ]
        dlg = ColumnDialog(columns_data=columns)
        assert dlg.list_widget.count() == 2
        dlg.close()

    def test_move_buttons_exist(self, qapp):
        from ui.dialogs.column import ColumnDialog
        columns = [{"name": "File Name", "visible": True}]
        dlg = ColumnDialog(columns_data=columns)
        assert dlg.btn_up is not None
        assert dlg.btn_down is not None
        dlg.close()


class TestPropertiesDialog:
    def test_construction(self, qapp):
        from ui.dialogs.properties import PropertiesDialog
        data = {
            "filename": "file.zip",
            "status": "Complete",
            "size": "10 MB",
            "path": "/tmp/file.zip",
            "url": "https://example.com/file.zip",
            "date_added": "2025-01-01",
            "last_try": "2025-01-01",
        }
        dlg = PropertiesDialog(file_data=data)
        assert dlg is not None
        assert dlg.file_data["filename"] == "file.zip"
        dlg.close()

    def test_window_title(self, qapp):
        from ui.dialogs.properties import PropertiesDialog
        dlg = PropertiesDialog(file_data={"filename": "test.pdf"})
        assert "test.pdf" in dlg.windowTitle()
        dlg.close()

    def test_missing_fields_handled(self, qapp):
        from ui.dialogs.properties import PropertiesDialog
        dlg = PropertiesDialog(file_data={})
        assert dlg is not None
        dlg.close()


class TestDownloadCompleteDialog:
    def test_construction(self, qapp):
        from ui.dialogs.complete import DownloadCompleteDialog
        data = {
            "path": "/tmp/downloads/file.zip",
            "url": "https://example.com/file.zip",
            "filename": "file.zip",
        }
        dlg = DownloadCompleteDialog(file_data=data)
        assert dlg is not None
        assert dlg.file_data["filename"] == "file.zip"
        dlg.close()

    def test_missing_path_handled(self, qapp):
        from ui.dialogs.complete import DownloadCompleteDialog
        dlg = DownloadCompleteDialog(file_data={})
        assert dlg is not None
        dlg.close()


class TestAddUrlDialog:
    def test_construction(self, qapp):
        from ui.dialogs.add_url import AddUrlDialog
        dlg = AddUrlDialog()
        assert dlg is not None
        assert "address" in dlg.windowTitle().lower()
        dlg.close()

    def test_has_url_input(self, qapp):
        from ui.dialogs.add_url import AddUrlDialog
        dlg = AddUrlDialog()
        assert dlg.url_input is not None
        assert dlg.url_input.placeholderText() == "https://"
        dlg.close()

    def test_url_input_settable(self, qapp):
        from ui.dialogs.add_url import AddUrlDialog
        dlg = AddUrlDialog()
        dlg.url_input.setText("https://example.com/file.zip")
        assert dlg.url_input.text() == "https://example.com/file.zip"
        dlg.close()

    def test_paste_button_exists(self, qapp):
        from ui.dialogs.add_url import AddUrlDialog
        dlg = AddUrlDialog()
        assert dlg.btn_paste is not None
        dlg.close()


class TestOptionsDialogTabs:
    def test_construction(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        assert dlg is not None
        assert dlg.tabs.count() >= 6
        dlg.close()

    def test_theme_combobox_contains_kirigami_themes(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        items = [dlg.combo_theme.itemText(i) for i in range(dlg.combo_theme.count())]
        assert "Kirigami Dark" in items
        assert "Kirigami Light" in items
        dlg.close()

    def test_select_tab_by_name(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        dlg.select_tab("media")
        current = dlg.tabs.currentWidget()
        assert current is dlg.media_tab
        dlg.close()

    def test_select_tab_by_index(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        dlg.select_tab(0)
        assert dlg.tabs.currentIndex() == 0
        dlg.close()

    def test_getters(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        assert isinstance(dlg.get_theme(), str)
        assert isinstance(dlg.get_accent(), str)
        assert isinstance(dlg.get_icon_theme(), str)
        assert isinstance(dlg.get_tray_icon(), str)
        assert isinstance(dlg.get_titlebar(), str)
        assert isinstance(dlg.get_language(), str)
        dlg.close()

    def test_youtube_player_client_options(self, qapp):
        from ui.dialogs.options import OptionsDialog
        dlg = OptionsDialog(main_window=None)
        dlg.select_tab("media")
        assert hasattr(dlg, "txt_opt_youtube_client")
        assert dlg.txt_opt_youtube_client.text().lower() in ("auto", "dynamic")
        # Test manual editing
        dlg.txt_opt_youtube_client.setText("android,ios")
        assert dlg.txt_opt_youtube_client.text() == "android,ios"
        # Test reset button resets to auto
        dlg.btn_opt_reset_youtube_client.click()
        assert dlg.txt_opt_youtube_client.text() == "auto"
        dlg.close()


class TestTwoRowTabWidget:
    def test_construction(self, qapp):
        from ui.dialogs.options import TwoRowTabWidget
        w = TwoRowTabWidget()
        assert w.count() == 0
        w.deleteLater()

    def test_add_tabs(self, qapp):
        from ui.dialogs.options import TwoRowTabWidget
        from PyQt6.QtWidgets import QWidget
        w = TwoRowTabWidget()
        idx1 = w.addTab(QWidget(), "First", row=1)
        idx2 = w.addTab(QWidget(), "Second", row=2)
        assert idx1 == 0
        assert idx2 == 1
        assert w.count() == 2
        assert w.tabText(0) == "First"
        assert w.tabText(1) == "Second"
        w.deleteLater()

    def test_set_current_index(self, qapp):
        from ui.dialogs.options import TwoRowTabWidget
        from PyQt6.QtWidgets import QWidget
        w = TwoRowTabWidget()
        w.addTab(QWidget(), "A", row=1)
        w.addTab(QWidget(), "B", row=1)
        w.setCurrentIndex(1)
        assert w.currentIndex() == 1
        w.deleteLater()
