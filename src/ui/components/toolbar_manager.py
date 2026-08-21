"""
Toolbar Manager & Hover Filters
===============================
Toolbar hover event filters and action icon glow handling.
"""

from PyQt6.QtWidgets import (
    QToolButton,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
)
from PyQt6.QtCore import (
    QObject,
    QEvent,
)


class ToolbarHoverFilter(QObject):
    """
    Event filter applied to toolbar buttons to provide bold icon glow
    and distinct hover/selection styling in both light and dark themes.
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
            "action_options": "options",
            "action_media_downloader": "media_downloader",
        }
        self._glow_icons = {}

    def get_glow_icon(self, icon_name: str) -> QIcon:
        if icon_name not in self._glow_icons:
            from core.services.theme_service import is_monochrome_icon_theme, get_themed_icon
            if is_monochrome_icon_theme():
                from ui.icons import get_monochrome_icon
                is_dark = self.main_window.is_dark_theme() if hasattr(self.main_window, "is_dark_theme") else True
                stroke_color = QColor("#ffffff") if is_dark else QColor("#232629")
                self._glow_icons[icon_name] = get_monochrome_icon(
                    icon_name,
                    color=stroke_color,
                    selected_color=stroke_color,
                    active_color=stroke_color,
                    glow=True
                )
            else:
                self._glow_icons[icon_name] = get_themed_icon(icon_name)
        return self._glow_icons[icon_name]

    def clear_cache(self):
        self._glow_icons.clear()

    def eventFilter(self, obj, event):
        if isinstance(obj, QToolButton) and obj.isEnabled():
            from core.services.theme_service import is_monochrome_icon_theme
            if not is_monochrome_icon_theme():
                return super().eventFilter(obj, event)

            if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseButtonPress):
                action = obj.defaultAction()
                if action:
                    for attr, icon_name in self._action_icon_map.items():
                        if getattr(self.main_window, attr, None) is action:
                            obj.setIcon(self.get_glow_icon(icon_name))
                            break
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.MouseButtonRelease):
                if not obj.isDown() and not obj.underMouse():
                    action = obj.defaultAction()
                    if action:
                        obj.setIcon(action.icon())
        return super().eventFilter(obj, event)
