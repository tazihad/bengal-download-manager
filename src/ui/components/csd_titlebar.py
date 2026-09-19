"""
Client-Side Decoration (CSD) Titlebar Component for Bengal Download Manager.
Provides an integrated custom titlebar for GNOME Wayland and frameless windows,
supporting native window moving, interactive resizing, maximize toggling,
and seamless Light / Dark theme styling.
"""

import sys
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton,
    QMainWindow, QDialog, QApplication
)
from PyQt6.QtCore import Qt, QEvent, QObject, QPoint
from PyQt6.QtGui import QIcon, QFont, QColor, QPalette, QPainter, QCursor


class CsdResizeFilter(QObject):
    """
    Event filter installed on a frameless window to handle:
    1. Edge-hover resize cursor updates
    2. Wayland / X11 native system resize via windowHandle().startSystemResize(edges)
    """
    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._margin = 6

    def eventFilter(self, watched, event):
        if watched != self._window:
            return super().eventFilter(watched, event)

        if not (self._window.windowFlags() & Qt.WindowType.FramelessWindowHint):
            return super().eventFilter(watched, event)

        if self._window.isMaximized() or self._window.isFullScreen():
            return super().eventFilter(watched, event)

        etype = event.type()
        if etype == QEvent.Type.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            edges = self._get_edges(pos)
            if edges:
                self._update_cursor(edges)
            else:
                self._window.unsetCursor()

        elif etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edges = self._get_edges(pos)
                if edges:
                    wh = self._window.windowHandle()
                    if wh and hasattr(wh, "startSystemResize"):
                        wh.startSystemResize(edges)
                        event.accept()
                        return True

        elif etype == QEvent.Type.Leave:
            self._window.unsetCursor()

        return super().eventFilter(watched, event)

    def _get_edges(self, pos: QPoint) -> Qt.Edge:
        edges = Qt.Edge(0)
        x = pos.x()
        y = pos.y()
        w = self._window.width()
        h = self._window.height()
        m = self._margin

        if x < m:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - m:
            edges |= Qt.Edge.RightEdge

        if y < m:
            edges |= Qt.Edge.TopEdge
        elif y >= h - m:
            edges |= Qt.Edge.BottomEdge

        return edges

    def _update_cursor(self, edges: Qt.Edge):
        is_left = bool(edges & Qt.Edge.LeftEdge)
        is_right = bool(edges & Qt.Edge.RightEdge)
        is_top = bool(edges & Qt.Edge.TopEdge)
        is_bottom = bool(edges & Qt.Edge.BottomEdge)

        if (is_top and is_left) or (is_bottom and is_right):
            self._window.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (is_top and is_right) or (is_bottom and is_left):
            self._window.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif is_left or is_right:
            self._window.setCursor(Qt.CursorShape.SizeHorCursor)
        elif is_top or is_bottom:
            self._window.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self._window.unsetCursor()


class CsdTitleBar(QWidget):
    """
    Custom Client-Side Decoration (CSD) headerbar for frameless windows.
    Renders the window icon, title, and minimize/maximize/close controls,
    and supports native Wayland/X11 dragging and double-click maximize.
    """
    def __init__(self, window: QWidget, is_dark: bool = False, is_dialog: bool = False):
        super().__init__(window)
        self._window = window
        self._is_dialog = is_dialog
        self._is_dark = is_dark
        self.setFixedHeight(36)
        self.setObjectName("CsdTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        # 1. Window Icon
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(18, 18)
        self.icon_lbl.setScaledContents(True)
        self._update_icon()
        layout.addWidget(self.icon_lbl)

        # 2. Window Title
        self.title_lbl = QLabel(window.windowTitle(), self)
        font = self.title_lbl.font()
        font.setBold(True)
        self.title_lbl.setFont(font)
        layout.addWidget(self.title_lbl)

        layout.addStretch()

        # 3. Window Control Buttons
        if not is_dialog:
            self.btn_min = QToolButton(self)
            self.btn_min.setText("—")
            self.btn_min.setToolTip("Minimize")
            self.btn_min.setFixedSize(30, 26)
            self.btn_min.clicked.connect(self._window.showMinimized)
            layout.addWidget(self.btn_min)

            self.btn_max = QToolButton(self)
            self.btn_max.setText("□")
            self.btn_max.setToolTip("Maximize")
            self.btn_max.setFixedSize(30, 26)
            self.btn_max.clicked.connect(self._toggle_maximize)
            layout.addWidget(self.btn_max)
        elif bool(self._window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint):
            self.btn_max = QToolButton(self)
            self.btn_max.setText("□")
            self.btn_max.setToolTip("Maximize")
            self.btn_max.setFixedSize(30, 26)
            self.btn_max.clicked.connect(self._toggle_maximize)
            layout.addWidget(self.btn_max)

        self.btn_close = QToolButton(self)
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Close")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.clicked.connect(self._window.close)
        layout.addWidget(self.btn_close)

        self.apply_style(is_dark)

    def _update_icon(self):
        icon = self._window.windowIcon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        if not icon.isNull():
            self.icon_lbl.setPixmap(icon.pixmap(18, 18))
            self.icon_lbl.setVisible(True)
        else:
            self.icon_lbl.setVisible(False)

    def update_title(self, title: str):
        self.title_lbl.setText(title)

    def _toggle_maximize(self):
        if self._window.isMaximized():
            self._window.showNormal()
            if hasattr(self, "btn_max"):
                self.btn_max.setText("□")
                self.btn_max.setToolTip("Maximize")
        else:
            self._window.showMaximized()
            if hasattr(self, "btn_max"):
                self.btn_max.setText("❐")
                self.btn_max.setToolTip("Restore")

    def apply_style(self, is_dark: bool):
        self._is_dark = is_dark
        bg = "#242424" if is_dark else "#f4f4f4"
        fg = "#ffffff" if is_dark else "#202020"
        border = "#333333" if is_dark else "#dcdcdc"
        btn_hover = "rgba(255, 255, 255, 0.14)" if is_dark else "rgba(0, 0, 0, 0.08)"

        self.setStyleSheet(f"""
            QWidget#CsdTitleBar {{
                background-color: {bg};
                border-bottom: 1px solid {border};
            }}
            QLabel {{
                color: {fg};
                background: transparent;
            }}
            QToolButton {{
                background: transparent;
                color: {fg};
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-family: inherit;
            }}
            QToolButton:hover {{
                background-color: {btn_hover};
            }}
        """)
        self.btn_close.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-family: inherit;
            }
            QToolButton:hover {
                background-color: #e81123;
                color: #ffffff;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            wh = self._window.windowHandle()
            if wh and hasattr(wh, "startSystemMove"):
                wh.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self._is_dialog and event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def attach_csd(window: QWidget, is_dark: bool = False):
    """Attaches Client-Side Decoration (CSD) to a window (QMainWindow or QDialog)."""
    if not window or not window.isWindow():
        return

    # Check if CSD is already attached
    existing_csd = getattr(window, "_csd_titlebar", None)
    if existing_csd is not None:
        existing_csd.apply_style(is_dark)
        return

    is_dialog = isinstance(window, QDialog)
    is_main_window = isinstance(window, QMainWindow)

    titlebar = CsdTitleBar(window, is_dark=is_dark, is_dialog=is_dialog)
    window._csd_titlebar = titlebar

    if is_main_window:
        menubar = window.menuBar()
        container = QWidget(window)
        container.setObjectName("CsdContainer")
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(0)
        clayout.addWidget(titlebar)
        clayout.addWidget(menubar)
        window._csd_container = container
        window.setMenuWidget(container)
    else:
        lay = window.layout()
        if lay and hasattr(lay, "insertWidget"):
            lay.insertWidget(0, titlebar)

    resize_filter = CsdResizeFilter(window)
    window._csd_resize_filter = resize_filter
    window.installEventFilter(resize_filter)

    is_vis = window.isVisible()
    is_max = window.isMaximized()
    window.setWindowFlags(window.windowFlags() | Qt.WindowType.FramelessWindowHint)
    if is_vis:
        window.show()
        if is_max:
            window.showMaximized()


def detach_csd(window: QWidget):
    """Detaches Client-Side Decoration (CSD) and restores native system frame."""
    if not window or not window.isWindow():
        return

    titlebar = getattr(window, "_csd_titlebar", None)
    if titlebar is None and not bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint):
        return

    is_main_window = isinstance(window, QMainWindow)

    if titlebar is not None:
        if is_main_window:
            menubar = window.menuBar()
            window.setMenuWidget(menubar)
            container = getattr(window, "_csd_container", None)
            if container:
                container.setParent(None)
            window._csd_container = None
        else:
            titlebar.setParent(None)
        window._csd_titlebar = None

    resize_filter = getattr(window, "_csd_resize_filter", None)
    if resize_filter is not None:
        window.removeEventFilter(resize_filter)
        window._csd_resize_filter = None

    is_vis = window.isVisible()
    is_max = window.isMaximized()
    window.setWindowFlags(window.windowFlags() & ~Qt.WindowType.FramelessWindowHint)
    if is_vis:
        window.show()
        if is_max:
            window.showMaximized()
