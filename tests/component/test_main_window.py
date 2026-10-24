"""Component tests for MainWindow."""

import pytest
from PyQt6.QtWidgets import QTableWidgetItem, QToolBar
from PyQt6.QtCore import Qt


@pytest.fixture(scope="module")
def main_window(qapp, destroy_widget):
    from unittest.mock import patch
    from ui.main_window import MainWindow
    with patch.object(MainWindow, "start_aria2_daemon", return_value=None):
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

    def test_toolbar_hover_has_readable_contrast(self, main_window):
        import re
        from PyQt6.QtGui import QColor, QPalette
        from core.services.theme_service import get_color_contrast_ratio

        ss = main_window.get_toolbar_stylesheet()
        hover = re.search(r"QToolButton:hover\s*\{(.*?)\}", ss, re.S).group(1)
        bg = QColor(re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", hover).group(1))
        text = QColor(re.search(r"color:\s*(#[0-9a-fA-F]{6})", hover).group(1))
        border = QColor(re.search(r"border:\s*1px solid\s*(#[0-9a-fA-F]{6})", hover).group(1))

        window = main_window.palette().color(QPalette.ColorRole.Window)
        assert get_color_contrast_ratio(bg, window) >= 1.20
        assert get_color_contrast_ratio(text, bg) >= 4.5
        assert get_color_contrast_ratio(border, bg) >= 3.0

    def test_toolbar_icons_change_on_hover_and_press(self, main_window):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        def _press(button, qt_button):
            return QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(5, 5),
                QPointF(5, 5),
                qt_button,
                qt_button,
                Qt.KeyboardModifier.NoModifier,
            )

        button = main_window.toolbar.widgetForAction(main_window.action_add_url)
        normal_key = button.icon().cacheKey()

        main_window.toolbar_hover_filter.eventFilter(
            button, QEvent(QEvent.Type.Enter)
        )
        hover_key = button.icon().cacheKey()

        main_window.toolbar_hover_filter.eventFilter(
            button, _press(button, Qt.MouseButton.LeftButton)
        )
        pressed_key = button.icon().cacheKey()

        assert hover_key != normal_key
        assert pressed_key != hover_key

        # Leave without press - restores to normal
        main_window.toolbar_hover_filter.eventFilter(
            button, QEvent(QEvent.Type.Leave)
        )
        after_leave_key = button.icon().cacheKey()
        assert after_leave_key == normal_key, "Should return to normal on leave"
        main_window.toolbar_hover_filter._restore_icon(button)

    def test_toolbar_right_click_keeps_hover_icon(self, main_window):
        """Right click must not force the pressed icon.

        QToolButton never enters the stylesheet ``:pressed`` state on a
        secondary click, so its label and surface stay in the hover look.
        Using the pressed (highlighted-text) stroke there would render a
        white icon on the light toolbar with a dark label.
        """
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        button = main_window.toolbar.widgetForAction(main_window.action_add_url)
        main_window.toolbar_hover_filter.eventFilter(
            button, QEvent(QEvent.Type.Enter)
        )
        hover_key = button.icon().cacheKey()

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        main_window.toolbar_hover_filter.eventFilter(button, event)

        assert button.icon().cacheKey() == hover_key
        main_window.toolbar_hover_filter._restore_icon(button)

    def test_toolbar_drag_out_restores_normal_icon(self, main_window):
        """Dragging off a pressed toolbar button must drop the pressed icon.

        QAbstractButton un-presses itself while the pointer is dragged
        outside, so its label/surface return to normal immediately; the icon
        has to follow, otherwise the white pressed stroke is left stranded
        on the light toolbar.
        """
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        def _move(pos, held):
            return QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(pos),
                QPointF(pos),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )

        button = main_window.toolbar.widgetForAction(main_window.action_add_url)
        # Shared module-scoped window: start from the action's normal icon.
        main_window.toolbar_hover_filter._restore_icon(button)
        normal_key = button.icon().cacheKey()
        inside = button.rect().center()
        outside = inside - button.rect().bottomRight() * 3

        main_window.toolbar_hover_filter.eventFilter(
            button, _move(inside, held=False)
        )
        main_window.toolbar_hover_filter.eventFilter(
            button, _move(inside, held=True)
        )
        pressed_key = button.icon().cacheKey()
        assert pressed_key != normal_key

        main_window.toolbar_hover_filter.eventFilter(
            button, _move(outside, held=True)
        )
        assert button.icon().cacheKey() == normal_key, (
            "Dragging off the button should restore the normal icon"
        )

        main_window.toolbar_hover_filter.eventFilter(
            button, _move(inside, held=True)
        )
        assert button.icon().cacheKey() == pressed_key, (
            "Dragging back in while held should re-apply the pressed icon"
        )


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


class TestProcessIncomingURL:
    def test_rejects_url_without_scheme(self, main_window):
        from unittest.mock import patch
        with patch("core.workers.FileInfoFetcherWorker") as mock_fetcher:
            main_window.process_incoming_url("bengal-download-manager-0.3.10-alpha.6-aarch64.flatpak")
            mock_fetcher.assert_not_called()

    def test_rejects_local_file_path(self, main_window):
        from unittest.mock import patch
        with patch("core.workers.FileInfoFetcherWorker") as mock_fetcher:
            main_window.process_incoming_url("/home/zihad/Downloads/file.flatpak")
            mock_fetcher.assert_not_called()

    def test_accepts_https_url(self, main_window):
        from unittest.mock import patch
        with patch("core.workers.FileInfoFetcherWorker") as mock_fetcher:
            main_window.process_incoming_url("https://example.com/file.flatpak")
            mock_fetcher.assert_called_once()
