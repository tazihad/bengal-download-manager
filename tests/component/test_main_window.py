"""Component tests for MainWindow."""

import pytest
from PyQt6.QtWidgets import QTableWidgetItem, QToolBar
from PyQt6.QtCore import Qt


@pytest.fixture(scope="class")
def main_window(qapp, destroy_widget):
    from ui.main_window import MainWindow
    win = MainWindow(start_ipc=False)
    yield win
    destroy_widget(win)


class TestMainWindowConstruction:
    def test_window_created(self, main_window):
        assert main_window is not None

    def test_window_title(self, main_window):
        assert main_window.windowTitle() == "Bengal Download Manager"

    def test_has_download_table(self, main_window):
        assert main_window.download_table is not None
        assert main_window.download_table.columnCount() == 7

    def test_has_category_tree(self, main_window):
        assert main_window.category_tree is not None

    def test_has_toolbar(self, main_window):
        assert main_window.toolbar is not None
        assert isinstance(main_window.toolbar, QToolBar)

    def test_has_status_bar(self, main_window):
        assert main_window.statusBar() is not None

    def test_has_menu_bar(self, main_window):
        assert main_window.menuBar() is not None

    def test_has_download_store(self, main_window):
        assert main_window.download_store is not None

    def test_has_download_controller(self, main_window):
        assert main_window.download_controller is not None


class TestMainWindowActions:
    def test_has_add_url_action(self, main_window):
        assert main_window.action_add_url is not None

    def test_has_paste_url_action(self, main_window):
        assert main_window.action_paste_url is not None

    def test_has_resume_action(self, main_window):
        assert main_window.action_resume is not None

    def test_has_stop_action(self, main_window):
        assert main_window.action_stop is not None

    def test_has_delete_action(self, main_window):
        assert main_window.action_delete is not None

    def test_has_options_action(self, main_window):
        assert main_window.action_options is not None

    def test_has_scheduler_action(self, main_window):
        assert main_window.action_scheduler is not None

    def test_delete_has_shortcut(self, main_window):
        assert not main_window.action_delete.shortcut().isEmpty()

    def test_add_url_has_shortcut(self, main_window):
        assert not main_window.action_add_url.shortcut().isEmpty()

    def test_stop_initially_disabled(self, main_window):
        assert main_window.action_stop.isEnabled() is False

    def test_resume_initially_disabled(self, main_window):
        assert main_window.action_resume.isEnabled() is False


class TestMainWindowMenus:
    def test_menu_bar_not_empty(self, main_window):
        assert len(main_window.menuBar().actions()) > 0

    def test_has_tasks_menu(self, main_window):
        menu_titles = [a.text().replace("&", "") for a in main_window.menuBar().actions()]
        assert any("Tasks" in t for t in menu_titles)

    def test_has_file_menu(self, main_window):
        menu_titles = [a.text().replace("&", "") for a in main_window.menuBar().actions()]
        assert any("File" in t for t in menu_titles)

    def test_has_downloads_menu(self, main_window):
        menu_titles = [a.text().replace("&", "") for a in main_window.menuBar().actions()]
        assert any("Downloads" in t for t in menu_titles)

    def test_has_view_menu(self, main_window):
        menu_titles = [a.text().replace("&", "") for a in main_window.menuBar().actions()]
        assert any("View" in t for t in menu_titles)

    def test_has_help_menu(self, main_window):
        menu_titles = [a.text().replace("&", "") for a in main_window.menuBar().actions()]
        assert any("Help" in t for t in menu_titles)


class TestMainWindowToolbar:
    def test_toolbar_not_movable(self, main_window):
        assert main_window.toolbar.isMovable() is False

    def test_toolbar_has_actions(self, main_window):
        assert len(main_window.toolbar.actions()) > 0

    def test_toolbar_has_add_url(self, main_window):
        actions = main_window.toolbar.actions()
        assert main_window.action_add_url in actions

    def test_toolbar_has_options(self, main_window):
        actions = main_window.toolbar.actions()
        assert main_window.action_options in actions


class TestMainWindowSettings:
    def test_load_settings_returns_dict(self, main_window):
        settings = main_window.load_settings()
        assert isinstance(settings, dict)
        assert "theme" in settings
        assert "accent" in settings

    def test_settings_defaults(self, main_window):
        settings = main_window.load_settings()
        assert settings["theme"] == "BDM Auto (Default)"
        assert settings["accent"] == "BDM (Default)"

    def test_is_dark_theme_returns_bool(self, main_window):
        assert isinstance(main_window.is_dark_theme(), bool)

    def test_get_toolbar_stylesheet_returns_str(self, main_window):
        ss = main_window.get_toolbar_stylesheet()
        assert isinstance(ss, str)
        assert "QToolBar" in ss


class TestMainWindowViewState:
    def test_table_style_default(self, main_window):
        assert main_window.table_style == "classic"

    def test_set_table_style_modern(self, main_window):
        main_window.set_table_style("modern")
        assert main_window.table_style == "modern"

    def test_set_table_style_classic(self, main_window):
        main_window.set_table_style("modern")
        main_window.set_table_style("classic")
        assert main_window.table_style == "classic"

    def test_toggle_status_bar_hide(self, main_window):
        main_window.toggle_status_bar(False, save=False)
        assert not main_window.statusBar().isVisible()
        main_window.toggle_status_bar(True, save=False)

    def test_toggle_data_usage(self, main_window):
        main_window.toggle_data_usage(True, save=False)
        main_window.toggle_data_usage(False, save=False)
        assert True

    def test_update_ui_states_no_crash(self, main_window):
        main_window.update_ui_states()


class TestMainWindowTable:
    def test_initial_row_count_zero(self, main_window):
        assert main_window.download_table.rowCount() == 0

    def test_column_count(self, main_window):
        assert main_window.download_table.columnCount() == 7

    def test_selection_mode(self, main_window):
        from PyQt6.QtWidgets import QAbstractItemView
        mode = main_window.download_table.selectionMode()
        assert mode == QAbstractItemView.SelectionMode.ExtendedSelection

    def test_no_edit_triggers(self, main_window):
        from PyQt6.QtWidgets import QAbstractItemView
        triggers = main_window.download_table.editTriggers()
        assert triggers == QAbstractItemView.EditTrigger.NoEditTriggers

    def test_header_labels(self, main_window):
        header = main_window.download_table.horizontalHeader()
        labels = [header.model().headerData(i, Qt.Orientation.Horizontal) for i in range(7)]
        assert labels[0] == "File Name"
        assert "Size" in labels


class TestMainWindowCategoryTree:
    def test_has_all_downloads_header(self, main_window):
        assert main_window.all_downloads_header is not None

    def test_has_categories_header(self, main_window):
        assert main_window.header_categories is not None

    def test_has_status_header(self, main_window):
        assert main_window.header_status is not None

    def test_has_schedule_header(self, main_window):
        assert main_window.header_schedule is not None

    def test_sidebar_queue_names_exists(self, main_window):
        assert hasattr(main_window, "_sidebar_queue_names")
        assert isinstance(main_window._sidebar_queue_names, list)
