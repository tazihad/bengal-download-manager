"""Unit tests for toolbar hover/tooltip contrast helpers.

The toolbar hover state must be perceivable and readable in every shipped
theme, light or dark.  ``palette(midlight)`` and ``palette(highlight)`` are
frequently too subtle (or too dark) for that job, so
``ensure_hover_surface()`` / ``ensure_control_contrast()`` derive the surface,
label and border colours from the active palette instead.
"""

import pytest

from PyQt6.QtGui import QColor


THEME_OPTIONS = [
    "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
    "Breeze Dark", "Breeze Light", "Catppuccin", "Chroma Dark",
    "Dracula", "IDM Classic", "Kirigami Dark",
    "Kirigami Light", "Material You Dark", "Material You Light",
    "Nord", "Obsidian Flow", "One Dark",
    "Solarized Dark", "Solarized Light",
    "Stellar Dark", "Stellar Light",
    "TMOG Dark", "Twilight", "Ubuntu Dark", "Ubuntu Light",
]


class TestBlendColors:
    def test_midpoint(self):
        from core.services.theme_service import _blend_colors
        assert _blend_colors(QColor("#ffffff"), QColor("#000000"), 0.5).name() == "#808080"

    def test_alpha_is_clamped(self):
        from core.services.theme_service import _blend_colors
        assert _blend_colors(QColor("#ffffff"), QColor("#000000"), 2.0).name() == "#ffffff"
        assert _blend_colors(QColor("#ffffff"), QColor("#000000"), -1.0).name() == "#000000"


class TestEnsureHoverSurface:
    def test_dark_theme_lighter_and_perceptible(self):
        from core.services.theme_service import ensure_hover_surface, get_color_contrast_ratio
        window = QColor("#181424")  # Twilight
        surface = ensure_hover_surface(window)
        assert surface.value() > window.value()
        assert get_color_contrast_ratio(surface, window) >= 1.20

    def test_light_theme_darker_and_perceptible(self):
        from core.services.theme_service import ensure_hover_surface, get_color_contrast_ratio
        window = QColor("#eff0f1")  # Breeze Light
        surface = ensure_hover_surface(window)
        assert surface.value() < window.value()
        assert get_color_contrast_ratio(surface, window) >= 1.20

    def test_near_black_theme_stays_visible(self):
        from core.services.theme_service import ensure_hover_surface, get_color_contrast_ratio
        window = QColor("#002b36")  # Solarized Dark
        surface = ensure_hover_surface(window)
        assert get_color_contrast_ratio(surface, window) >= 1.20

    def test_near_white_theme_stays_visible(self):
        from core.services.theme_service import ensure_hover_surface, get_color_contrast_ratio
        window = QColor("#fdf6e3")  # Solarized Light
        surface = ensure_hover_surface(window)
        assert get_color_contrast_ratio(surface, window) >= 1.20


class TestEnsureControlContrast:
    def test_compliant_color_is_returned_unchanged(self):
        from core.services.theme_service import ensure_control_contrast
        color = QColor("#ffffff")
        assert ensure_control_contrast(color, QColor("#000000"), 3.0).name() == "#ffffff"

    def test_dark_background_lightens(self):
        from core.services.theme_service import ensure_control_contrast, get_color_contrast_ratio
        result = ensure_control_contrast(QColor("#6342b0"), QColor("#1d182b"), 3.0)
        assert get_color_contrast_ratio(result, QColor("#1d182b")) >= 3.0
        assert result.value() > QColor("#6342b0").value()

    def test_light_background_darkens(self):
        from core.services.theme_service import ensure_control_contrast, get_color_contrast_ratio
        result = ensure_control_contrast(QColor("#88c0d0"), QColor("#fdf6e3"), 4.5)
        assert get_color_contrast_ratio(result, QColor("#fdf6e3")) >= 4.5
        assert result.value() < QColor("#88c0d0").value()


@pytest.mark.parametrize("theme", THEME_OPTIONS)
def test_toolbar_hover_contrast_for_every_theme(qapp, theme):
    """Every shipped theme must produce a readable, visible toolbar hover."""
    from PyQt6.QtGui import QPalette
    from core.services.theme_service import (
        apply_app_theme,
        ensure_control_contrast,
        ensure_hover_surface,
        get_color_contrast_ratio,
    )

    try:
        apply_app_theme(theme, app=qapp)
        pal = qapp.palette()
        window = pal.color(QPalette.ColorRole.Window)
        text = pal.color(QPalette.ColorRole.WindowText)
        link = pal.color(QPalette.ColorRole.Link)
        highlight = pal.color(QPalette.ColorRole.Highlight)
        highlighted_text = pal.color(QPalette.ColorRole.HighlightedText)

        hover_bg = ensure_hover_surface(window)
        hover_text = ensure_control_contrast(text, hover_bg, min_contrast=4.5)
        hover_border = ensure_control_contrast(link, hover_bg)

        assert get_color_contrast_ratio(hover_bg, window) >= 1.20, theme
        assert get_color_contrast_ratio(hover_text, hover_bg) >= 4.5, theme
        assert get_color_contrast_ratio(hover_border, hover_bg) >= 3.0, theme
        # Pressed state must keep the selected label readable too.
        assert get_color_contrast_ratio(highlighted_text, highlight) >= 4.5, theme
    finally:
        apply_app_theme("BDM Auto (Default)", app=qapp)
