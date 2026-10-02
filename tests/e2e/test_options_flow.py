"""End-to-end tests: options dialog flow with MainWindow."""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def win(qapp, destroy_widget):
    from ui.main_window import MainWindow
    w = MainWindow(start_ipc=False)
    yield w
    destroy_widget(w)


@pytest.fixture
def dialog(win):
    from ui.dialogs import OptionsDialog
    dlg = OptionsDialog(main_window=win)
    yield dlg
    try:
        dlg.reject()
    except Exception:
        pass
    try:
        dlg.deleteLater()
    except Exception:
        pass


class TestOpenOptionsFlow:
    def test_open_options_creates_dialog(self, win):
        win.open_options()
        assert win._options_dlg is not None
        try:
            win._options_dlg.reject()
        except Exception:
            pass
        try:
            win._options_dlg.deleteLater()
        except Exception:
            pass

    def test_open_options_twice_reuses(self, win):
        win.open_options()
        first = win._options_dlg
        win.open_options()
        assert win._options_dlg is first
        try:
            first.reject()
        except Exception:
            pass
        try:
            first.deleteLater()
        except Exception:
            pass


class TestOptionsGetters:
    def test_get_theme_default(self, dialog):
        assert dialog.get_theme() in [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Breeze Dark", "Breeze Light", "Catppuccin", "Dracula",
            "Kirigami Dark", "Kirigami Light", "Material You Dark",
            "Material You Light", "Nord", "Obsidian Flow", "One Dark",
            "Solarized Dark", "Solarized Light", "Twilight",
            "Ubuntu Dark", "Ubuntu Light",
        ]

    def test_get_accent(self, dialog):
        assert isinstance(dialog.get_accent(), str)

    def test_get_language(self, dialog):
        assert isinstance(dialog.get_language(), str)

    def test_get_silent_download(self, dialog):
        assert isinstance(dialog.get_silent_download(), bool)

    def test_get_show_complete_dialog(self, dialog):
        assert isinstance(dialog.get_show_complete_dialog(), bool)

    def test_theme_selection_changes(self, dialog):
        combo = dialog.combo_theme
        original = combo.currentIndex()
        combo.setCurrentText("Dracula")
        assert dialog.get_theme() == "Dracula"
        combo.setCurrentIndex(original)

    def test_language_selection_changes(self, dialog):
        combo = dialog.combo_language
        original = combo.currentIndex()
        combo.setCurrentText("English")
        assert dialog.get_language() == "en"
        combo.setCurrentIndex(original)


class TestOptionsTabs:
    def test_select_tab_appearance(self, dialog):
        dialog.select_tab("Appearance")

    def test_select_tab_by_index(self, dialog):
        dialog.select_tab(0)

    def test_tab_count_positive(self, dialog):
        assert dialog.tabs.count() > 0


class TestOptionsAcceptance:
    def test_accept_hides_dialog(self, dialog):
        dialog.show()
        dialog.accept()
        assert not dialog.isVisible()

    def test_settings_reflected_in_main_window_after_apply(self, win):
        original_theme = win.settings.get("theme", "BDM Auto (Default)")
        win.settings["theme"] = "BDM Dark"
        win.apply_theme_setting("BDM Dark")
        assert win.settings["theme"] == "BDM Dark"
        win.settings["theme"] = original_theme
        win.apply_theme_setting(original_theme)


class TestOptionsPersistenceRoundTrip:
    def test_theme_roundtrip_through_save_load(self, win):
        win.settings["theme"] = "Solarized Dark"
        win.save_settings()
        reloaded = win.load_settings()
        assert reloaded.get("theme") == "Solarized Dark"

    def test_silent_download_roundtrip(self, win):
        original = win.settings.get("silent_download", False)
        win.settings["silent_download"] = not original
        win.save_settings()
        reloaded = win.load_settings()
        assert reloaded.get("silent_download") == (not original)
        win.settings["silent_download"] = original
        win.save_settings()
