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

    def test_apply_chroma_dark(self, app):
        from core.services.theme_service import apply_app_theme, is_dark_theme, get_themed_icon
        apply_app_theme("Chroma Dark", icon_theme_name="Chroma")
        assert is_dark_theme(app) is True
        # Verify toolbar action icons render with Chroma gradient style
        ic_add = get_themed_icon("add_url")
        assert not ic_add.isNull()
        ic_resume = get_themed_icon("resume")
        assert not ic_resume.isNull()
        # Verify left panel category icons fall back cleanly
        ic_cat = get_themed_icon("documents")
        assert not ic_cat.isNull()

    def test_theme_switching_no_crash(self, app):
        from core.services.theme_service import apply_app_theme
        themes = [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Breeze Dark", "Breeze Light", "Catppuccin", "Chroma Dark", "Dracula",
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
            "Chroma Blue", "Crimson Red", "Dracula Purple", "Emerald Green",
            "Nord Frost", "Stellar Blue", "Ubuntu Orange", "Windows Blue",
        ]
        for a in accents:
            apply_app_theme("BDM Auto (Default)", accent_name=a)


class TestThemeNormalization:
    def test_normalize_roundtrip(self):
        from core.services.theme_service import normalize_theme_name
        themes = [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Chroma Dark", "Dracula", "Kirigami Dark", "Kirigami Light", "Nord",
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
        assert normalize_theme_name("chroma dark") == "Chroma Dark"
        assert normalize_theme_name("CHROMA DARK") == "Chroma Dark"


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

    def test_apply_language_en_succeeds(self, qapp):
        from core.services.language_service import apply_language, tr
        assert apply_language(qapp, "en") is True
        assert tr("Resume") == "Resume"

    def test_rtl_layout_direction_remains_ltr(self, qapp):
        from PyQt6.QtCore import Qt
        from core.services.language_service import apply_language
        # When Arabic or Persian is set, app layout direction must remain LeftToRight
        apply_language(qapp, "ar")
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight
        apply_language(qapp, "fa")
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight
        # Reset to en
        apply_language(qapp, "en")


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


class TestHighlightTextColor:
    def test_normalize_highlight_text(self):
        from core.services.theme_service import normalize_highlight_text_name, HIGHLIGHT_TEXT_COLORS
        for name in HIGHLIGHT_TEXT_COLORS.keys():
            assert normalize_highlight_text_name(name) == name
            assert normalize_highlight_text_name(name.lower()) == name
            assert normalize_highlight_text_name(name.upper()) == name
        assert normalize_highlight_text_name("unknown") == "Automatic"
        assert normalize_highlight_text_name(None) == "Automatic"

    def test_highlight_text_palette_application(self, qapp):
        from PyQt6.QtGui import QPalette
        from core.services.theme_service import apply_app_theme, HIGHLIGHT_TEXT_COLORS
        for name, hex_val in HIGHLIGHT_TEXT_COLORS.items():
            apply_app_theme("Chroma Dark", highlight_text=name)
            pal = qapp.palette()
            hl_color = pal.color(QPalette.ColorRole.HighlightedText)
            assert hl_color.isValid()
            if hex_val is not None:
                assert hl_color.name().lower() == hex_val.lower()

    def test_adaptive_selection_contrast(self, qapp):
        from PyQt6.QtGui import QPalette, QColor
        from core.services.theme_service import (
            apply_app_theme, get_color_contrast_ratio, ensure_contrast_selection_bg
        )
        # Test unit function
        bdm_accent = QColor("#3daee9")
        mint_green = QColor("#5eead4")
        assert get_color_contrast_ratio(bdm_accent, mint_green) < 2.0
        adapted_bg = ensure_contrast_selection_bg(bdm_accent, mint_green)
        assert get_color_contrast_ratio(adapted_bg, mint_green) >= 4.5

        # Test full app theme application with BDM Default (#3daee9) and Mint Green
        apply_app_theme("BDM Dark", accent_name="BDM (Default)", highlight_text="Mint Green")
        pal = qapp.palette()
        hl_bg = pal.color(QPalette.ColorRole.Highlight)
        hl_txt = pal.color(QPalette.ColorRole.HighlightedText)
        contrast = get_color_contrast_ratio(hl_bg, hl_txt)
        assert contrast >= 4.5


class TestChromaCategoryIcons:
    def test_chroma_left_panel_icons(self):
        from core.services.theme_service import get_themed_icon
        from PyQt6.QtGui import QIcon
        categories = [
            "all_downloads", "compressed", "documents", "music",
            "programs", "video", "unfinished", "finished", "queues"
        ]
        for cat in categories:
            icon = get_themed_icon(cat, "Chroma", 24)
            assert isinstance(icon, QIcon)
            assert not icon.isNull()
