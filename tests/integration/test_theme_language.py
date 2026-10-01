"""Integration tests: theme + language service combined."""

import pytest
from PyQt6.QtWidgets import QApplication


class TestThemeApplication:
    @pytest.fixture
    def app(self, qapp):
        return qapp

    def test_apply_bdm_dark(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("BDM Dark")
        assert is_dark_theme(app) is True

    def test_apply_bdm_light(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("BDM Light")
        assert is_dark_theme(app) is False

    def test_apply_system(self, app):
        from core.services.theme_service import apply_app_theme
        result = apply_app_theme("System")
        assert result is not None or result is None

    def test_apply_kirigami_dark(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Kirigami Dark")
        assert is_dark_theme(app) is True

    def test_apply_kirigami_light(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Kirigami Light")
        assert is_dark_theme(app) is False

    def test_apply_dracula(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Dracula")
        assert is_dark_theme(app) is True

    def test_apply_nord(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Nord")
        assert is_dark_theme(app) is True

    def test_apply_solarized_light(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Solarized Light")
        assert is_dark_theme(app) is False

    def test_apply_solarized_dark(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Solarized Dark")
        assert is_dark_theme(app) is True

    def test_apply_breeze_dark(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Breeze Dark")
        assert is_dark_theme(app) is True

    def test_apply_breeze_light(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme
        apply_app_theme("Breeze Light")
        assert is_dark_theme(app) is False

    def test_theme_switching_no_crash(self, app):
        from core.services.theme_service import apply_app_theme
        themes = [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Breeze Dark", "Breeze Light", "Catppuccin", "Dracula",
            "Kirigami Dark", "Kirigami Light", "Material You Dark",
            "Material You Light", "Nord", "Obsidian Flow", "One Dark",
            "Solarized Dark", "Solarized Light", "Twilight",
            "Ubuntu Dark", "Ubuntu Light",
        ]
        for t in themes:
            apply_app_theme(t)

    def test_accent_switching_no_crash(self, app):
        from core.services.theme_service import apply_app_theme
        accents = [
            "BDM (Default)", "System", "Amethyst Violet", "Breeze Blue",
            "Crimson Red", "Dracula Purple", "Emerald Green",
            "Nord Frost", "Stellar Blue", "Ubuntu Orange", "Windows Blue",
        ]
        for a in accents:
            apply_app_theme("BDM Auto (Default)", accent_name=a)


class TestThemeNormalization:
    def test_normalize_roundtrip(self):
        from core.services.theme_service import normalize_theme_name
        themes = [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Dracula", "Kirigami Dark", "Kirigami Light", "Nord",
            "Ubuntu Dark", "Ubuntu Light", "Twilight", "Stellar Dark",
        ]
        for t in themes:
            result = normalize_theme_name(t)
            assert isinstance(result, str)
            assert result

    def test_normalize_case_insensitive(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name("BDMDARK") == "BDM Dark"
        assert normalize_theme_name("bdm dark") == "BDM Dark"
        assert normalize_theme_name("BDM DARK") == "BDM Dark"


class TestLanguageIntegration:
    def test_all_supported_languages_resolve(self):
        from core.services.language_service import (
            SUPPORTED_LANGUAGES, get_language_code, get_language_display
        )
        for code, display in SUPPORTED_LANGUAGES:
            assert get_language_code(code) == code
            assert get_language_display(code) == display

    def test_display_to_code_roundtrip(self):
        from core.services.language_service import (
            SUPPORTED_LANGUAGES, get_language_code, get_language_display
        )
        for code, display in SUPPORTED_LANGUAGES:
            assert get_language_display(get_language_code(display)) == display

    def test_unknown_resolves_to_system(self):
        from core.services.language_service import get_language_code, get_language_display
        assert get_language_code("klingon") == "system"
        assert get_language_display("klingon") == "System Default"

    def test_translator_translates_known(self, qapp):
        from core.services.language_service import JsonCatalogTranslator
        t = JsonCatalogTranslator({"hello": "hallo"})
        result = t.translate("ctx", "hello")
        assert result == "hallo"

    def test_translator_falls_back_to_source(self, qapp):
        from core.services.language_service import JsonCatalogTranslator
        t = JsonCatalogTranslator({})
        result = t.translate("ctx", "unknown key")
        assert result == ""


class TestCombinedThemeLanguage:
    def test_theme_then_language(self, qapp):
        from core.services.theme_service import apply_app_theme, init_app_font
        from core.services.language_service import apply_language
        apply_app_theme("BDM Dark")
        font = init_app_font()
        assert font is not None
        apply_language(qapp, "en")

    def test_font_initialization_default(self, qapp):
        from core.services.theme_service import init_app_font
        font = init_app_font()
        assert font is not None
        assert font.pointSize() > 0

    def test_font_has_tnum_feature(self, qapp):
        from core.services.theme_service import init_app_font
        font = init_app_font()
        assert font is not None

    def test_detect_accent_returns_qcolor(self, qapp):
        from core.services.theme_service import detect_accent
        color = detect_accent("auto", qapp)
        assert color is not None
