"""Unit tests for toolbar hover/pressed contrast helpers.

``palette(midlight)`` and ``palette(highlight)`` are frequently too subtle
(or too dark) for hover and pressed states, so the toolbar derives its
surface, border, label and icon colours from the active palette instead.
"""

import pytest

from PyQt6.QtGui import QColor


# Representative of every palette family: dark/light, blue/violet accents,
# near-black and near-white windows, and light accents with dark labels.
REPRESENTATIVE_THEMES = [
    "BDM Dark",
    "BDM Light",
    "Twilight",
    "Catppuccin",
    "Solarized Dark",
    "Solarized Light",
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


@pytest.mark.parametrize("theme", REPRESENTATIVE_THEMES)
def test_toolbar_states_have_readable_contrast(qapp, theme):
    """Hover and pressed toolbar states must stay visible and readable.

    The icon stroke uses the same palette roles as its label, otherwise a
    light theme shows a dark icon on the dark pressed accent (and light
    accents such as Catppuccin show a white icon on a light background).
    """
    from PyQt6.QtGui import QPalette
    from core.services.theme_service import (
        apply_app_theme,
        ensure_control_contrast,
        ensure_hover_surface,
        get_color_contrast_ratio,
    )
    from ui.components.toolbar_manager import ToolbarHoverFilter

    hover_filter = ToolbarHoverFilter(None)
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
        assert get_color_contrast_ratio(highlighted_text, highlight) >= 4.5, theme

        pressed_stroke = hover_filter._pressed_stroke(pal)
        hover_stroke = hover_filter._hover_stroke(pal)
        assert get_color_contrast_ratio(pressed_stroke, highlight) >= 4.5, theme
        assert get_color_contrast_ratio(hover_stroke, hover_bg) >= 4.5, theme
    finally:
        apply_app_theme("BDM Auto (Default)", app=qapp)
