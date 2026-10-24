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
    QMouseEvent,
    QPalette,
)
from PyQt6.QtCore import (
    QObject,
    QEvent,
    Qt,
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
        """Pressed icon colour, matching the pressed label colour (palette HighlightedText)."""
        # Use HighlightedText directly so icon stroke exactly matches the
        # stylesheet's pressed label colour (palette(highlighted-text)).
        return pal.color(QPalette.ColorRole.HighlightedText)

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
                # NOTE: Toolbar icons and menu icons share the same QAction icons
                # created via get_themed_icon(). Menu icons use Active mode = HighlightedText
                # to match menu item hover text. Toolbar icons differ because the toolbar
                # hover surface is lighter (ensure_hover_surface) so it uses WindowText for
                # contrast; only the pressed state matches HighlightedText (full highlight bg).
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
            icon = self.get_state_icon(icon_name, state)
            # Avoid repainting on every mouse-move when the state is unchanged.
            if button.icon().cacheKey() != icon.cacheKey():
                button.setIcon(icon)

    @staticmethod
    def _restore_icon(button: QToolButton):
        action = button.defaultAction()
        if action and button.icon().cacheKey() != action.icon().cacheKey():
            button.setIcon(action.icon())

    def eventFilter(self, obj, event):
        if isinstance(obj, QToolButton) and obj.isEnabled():
            from core.services.theme_service import is_monochrome_icon_theme
            if not is_monochrome_icon_theme():
                return super().eventFilter(obj, event)

            etype = event.type()
            down = obj.isDown()
            # A QToolButton only enters the stylesheet ``:pressed`` state
            # (highlight surface + highlighted-text label) for the primary
            # button. Right/middle presses leave it visually unpressed, so
            # forcing the pressed icon there paints a white stroke on the
            # light toolbar while the label stays dark. Only the primary
            # button may switch to the pressed icon.
            is_primary_press = (
                isinstance(event, QMouseEvent)
                and event.button() == Qt.MouseButton.LeftButton
            )

            if etype == QEvent.Type.Enter:
                # While pressed, stay in pressed state so icon matches text.
                self._apply_state_icon(obj, "pressed" if down else "hover")
            elif etype == QEvent.Type.MouseButtonPress:
                # Left click uses the pressed state; secondary clicks keep
                # the hover icon so it stays matched with the hover label.
                # (If the primary button is already held, stay pressed.)
                if is_primary_press or down:
                    self._apply_state_icon(obj, "pressed")
                else:
                    self._apply_state_icon(obj, "hover")
            elif etype == QEvent.Type.Leave:
                # While pressed, keep pressed icon to match pressed text.
                # Only restore to normal when not pressed.
                if not down:
                    self._restore_icon(obj)
            elif etype == QEvent.Type.MouseButtonRelease:
                if obj.underMouse():
                    self._apply_state_icon(obj, "hover")
                else:
                    self._restore_icon(obj)
            elif etype == QEvent.Type.MouseMove:
                # While the primary button is held, QAbstractButton cancels
                # its pressed state as soon as the pointer leaves the button
                # and re-presses it when the pointer comes back. Qt applies
                # that to the stylesheet only after this filter runs, so
                # mirror the upcoming state here; otherwise the pressed
                # (highlighted-text) icon stays behind with an unpressed
                # label and surface while dragging off the button.
                if isinstance(event, QMouseEvent):
                    inside = obj.rect().contains(event.position().toPoint())
                    primary_held = bool(event.buttons() & Qt.MouseButton.LeftButton)
                else:
                    inside = obj.underMouse()
                    primary_held = down
                if inside:
                    self._apply_state_icon(
                        obj, "pressed" if (primary_held or down) else "hover"
                    )
                elif primary_held or down:
                    self._restore_icon(obj)
        return super().eventFilter(obj, event)
