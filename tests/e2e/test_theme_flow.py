"""End-to-end tests: theme switching flow through MainWindow."""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def win(qapp, destroy_widget):
    from ui.main_window import MainWindow
    w = MainWindow(start_ipc=False)
    yield w
    destroy_widget(w)


class TestApplyThemeSetting:
    def test_apply_dark(self, win):
        win.settings["theme"] = "BDM Dark"
        win.apply_theme_setting("BDM Dark")
        from core.services.theme_service import is_dark_theme
        assert is_dark_theme(QApplication.instance()) is True

    def test_apply_light(self, win):
        win.settings["theme"] = "BDM Light"
        win.apply_theme_setting("BDM Light")
        from core.services.theme_service import is_dark_theme
        assert is_dark_theme(QApplication.instance()) is False

    def test_settings_theme_updated(self, win):
        win.settings["theme"] = "Nord"
        win.apply_theme_setting("Nord")
        assert win.settings["theme"] == "Nord"

    def test_refresh_theme_ui_no_crash(self, win):
        win.refresh_theme_ui()

    def test_window_palette_updated(self, win):
        win.apply_theme_setting("BDM Dark")
        app = QApplication.instance()
        assert win.palette() is not None
        assert app.palette() is not None

    def test_accent_change(self, win):
        original = win.settings.get("accent", "BDM (Default)")
        win.settings["accent"] = "Ubuntu Orange"
        win.apply_appearance_setting(
            win.settings.get("theme", "BDM Auto (Default)"),
            "Ubuntu Orange",
            win.settings.get("icon_theme", "BDM Auto (Default)"),
            win.settings.get("tray_icon", "App Icon (Default)"),
            win.settings.get("title_bar", "Automatic"),
        )
        win.settings["accent"] = original


class TestThemePersistence:
    def test_save_settings_persists_theme(self, win):
        win.settings["theme"] = "Dracula"
        win.save_settings()
        reloaded = win.load_settings()
        assert reloaded.get("theme") == "Dracula"

    def test_save_settings_persists_accent(self, win):
        win.settings["accent"] = "Nord Frost"
        win.save_settings()
        reloaded = win.load_settings()
        assert reloaded.get("accent") == "Nord Frost"

    def test_save_settings_persists_language(self, win):
        win.settings["language"] = "en"
        win.save_settings()
        reloaded = win.load_settings()
        assert reloaded.get("language") == "en"


class TestThemeSwitchSequence:
    def test_rapid_theme_switching(self, win):
        themes = ["BDM Dark", "BDM Light", "Nord", "Dracula",
                  "Solarized Light", "BDM Auto (Default)"]
        for t in themes:
            win.settings["theme"] = t
            win.apply_theme_setting(t)
        win.refresh_theme_ui()

    def test_theme_tree_icons_refreshed(self, win):
        win.apply_theme_setting("BDM Dark")
        win.refresh_theme_ui()
        assert win.all_downloads_header.icon(0) is not None
