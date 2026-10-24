"""
Toolbar Manager & Hover Filters
===============================
Toolbar hover event filters and action icon glow handling.
"""

from PyQt6.QtWidgets import (
    QApplication,
    QToolButton,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QPalette,
)
from PyQt6.QtCore import (
    QObject,
    QEvent,
)


class ToolbarHoverFilter(QObject):
    """
    Event filter applied to toolbar buttons to provide bold icon glow
    and distinct hover/selection styling in both light and dark themes.

    Icon strokes are derived from the same palette roles as the toolbar
    labels (``window-text`` for normal/hover, ``highlighted-text`` for
    pressed), so the icon and its label always stay readable together on
    light and dark accents.
    """
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._action_icon_map = {
            "action_add_url": "add_url",
            "action_resume": "resume",
            "action_stop": "stop",
            "action_stop_all": "stop_all",
            "action_delete": "delete",
            "action_clear": "clear_completed",
            "action_scheduler": "scheduler",
            "action_grabber": "grabber",
            "action_options": "options",
            "action_media_downloader": "media_downloader",
        }
        self._state_icons = {}

    def _palette(self) -> QPalette:
        app = QApplication.instance()
        if app:
            return app.palette()
        return self.main_window.palette()

    def _hover_stroke(self, pal: QPalette) -> QColor:
        """Hover icon colour, matching the hover label colour."""
        from core.services.theme_service import (
            ensure_control_contrast,
            ensure_hover_surface,
        )
        hover_bg = ensure_hover_surface(pal.color(QPalette.ColorRole.Window))
        return ensure_control_contrast(
            pal.color(QPalette.ColorRole.WindowText),
            hover_bg,
            min_contrast=4.5,
        )

    def _pressed_stroke(self, pal: QPalette) -> QColor:
        """Pressed icon colour, matching the pressed label colour."""
        from core.services.theme_service import ensure_control_contrast
        return ensure_control_contrast(
            pal.color(QPalette.ColorRole.HighlightedText),
            pal.color(QPalette.ColorRole.Highlight),
            min_contrast=4.5,
        )

    def get_state_icon(self, icon_name: str, state: str = "hover") -> QIcon:
        key = (icon_name, state)
        if key not in self._state_icons:
            from core.services.theme_service import is_monochrome_icon_theme, get_themed_icon
            if is_monochrome_icon_theme():
                from ui.icons import get_monochrome_icon
                pal = self._palette()
                stroke_color = (
                    self._pressed_stroke(pal)
                    if state == "pressed"
                    else self._hover_stroke(pal)
                )
                self._state_icons[key] = get_monochrome_icon(
                    icon_name,
                    color=stroke_color,
                    selected_color=stroke_color,
                    active_color=stroke_color,
                    glow=state != "pressed",
                )
            else:
                self._state_icons[key] = get_themed_icon(icon_name)
        return self._state_icons[key]

    def get_glow_icon(self, icon_name: str) -> QIcon:
        """Backwards-compatible alias for the hover icon."""
        return self.get_state_icon(icon_name, "hover")

    def clear_cache(self):
        self._state_icons.clear()

    def _icon_name_for(self, button: QToolButton):
        action = button.defaultAction()
        if not action:
            return None
        for attr, icon_name in self._action_icon_map.items():
            if getattr(self.main_window, attr, None) is action:
                return icon_name
        return None

    def _apply_state_icon(self, button: QToolButton, state: str):
        icon_name = self._icon_name_for(button)
        if icon_name:
            button.setIcon(self.get_state_icon(icon_name, state))

    @staticmethod
    def _restore_icon(button: QToolButton):
        action = button.defaultAction()
        if action:
            button.setIcon(action.icon())

    def eventFilter(self, obj, event):
        if isinstance(obj, QToolButton) and obj.isEnabled():
            from core.services.theme_service import is_monochrome_icon_theme
            if not is_monochrome_icon_theme():
                return super().eventFilter(obj, event)

            etype = event.type()
            if etype == QEvent.Type.Enter:
                self._apply_state_icon(obj, "hover")
            elif etype == QEvent.Type.MouseButtonPress:
                self._apply_state_icon(obj, "pressed")
            elif etype == QEvent.Type.Leave:
                if not obj.isDown():
                    self._restore_icon(obj)
            elif etype == QEvent.Type.MouseButtonRelease:
                if obj.underMouse():
                    self._apply_state_icon(obj, "hover")
                else:
                    self._restore_icon(obj)
        return super().eventFilter(obj, event)
