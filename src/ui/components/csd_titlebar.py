"""
Client-Side Decoration (CSD) Titlebar Component for Bengal Download Manager.
Implements the official GNOME / Libadwaita XDG HeaderBar standard for GNOME
and GTK-based Linux distributions, featuring native Wayland/X11 window dragging,
interactive edge resizing, window maximize toggling, and seamless
Automatic / Light / Dark theme styling based on official Libadwaita color tokens.
"""

import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QMainWindow, QDialog, QApplication, QStyleOption, QStyle
)
from PyQt6.QtCore import Qt, QEvent, QObject, QPoint
from PyQt6.QtGui import QMouseEvent, QCursor, QPainter

# Official Libadwaita color tokens
ADW_COLORS = {
    "dark": {
        "headerbar_bg": "#303030",
        "headerbar_border": "rgba(0, 0, 0, 0.35)",
        "window_fg": "#ffffff",
        "button_bg": "rgba(255, 255, 255, 0.10)",
        "button_hover": "rgba(255, 255, 255, 0.15)",
        "button_active": "rgba(255, 255, 255, 0.20)",
        "close_hover": "#c01c28",
        "close_active": "#9e1520",
    },
    "light": {
        "headerbar_bg": "#ebebeb",
        "headerbar_border": "rgba(0, 0, 0, 0.12)",
        "window_fg": "rgba(0, 0, 0, 0.8)",
        "button_bg": "rgba(0, 0, 0, 0.05)",
        "button_hover": "rgba(0, 0, 0, 0.10)",
        "button_active": "rgba(0, 0, 0, 0.15)",
        "close_hover": "#e01b24",
        "close_active": "#b8161e",
    }
}


def read_xdg_color_scheme() -> str:
    """
    Queries org.freedesktop.portal.Settings namespace 'org.freedesktop.appearance',
    key 'color-scheme'.
    0 = Default / Light
    1 = Prefer Dark
    2 = Prefer Light
    """
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            msg = QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings",
                "Read"
            )
            msg.setArguments(["org.freedesktop.appearance", "color-scheme"])
            reply = bus.call(msg)
            if reply.type() == QDBusMessage.MessageType.ReplyMessage:
                args = reply.arguments()
                if args:
                    val = args[0]
                    if hasattr(val, "variant"):
                        val = val.variant()
                    if int(val) == 1:
                        return "dark"
    except Exception:
        pass
    return "light"


class CsdResizeFilter(QObject):
    """
    Event filter installed on a frameless window to handle:
    1. Edge-hover resize cursor updates
    2. Wayland / X11 native system resize via windowHandle().startSystemResize(edges)
    3. Window state change (maximize / restore) to update titlebar button and border radius
    4. Window title change to keep titlebar label in sync
    """
    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._margin = 6

    def eventFilter(self, watched, event):
        win = getattr(self, "_window", None)
        if not win or watched != win:
            return super().eventFilter(watched, event)

        etype = event.type()

        # Keep titlebar synchronized with window title and state
        if etype == QEvent.Type.WindowStateChange:
            tb = getattr(win, "_csd_titlebar", None)
            if tb and hasattr(tb, "_update_maximize_state"):
                tb._update_maximize_state()
        elif etype == QEvent.Type.WindowTitleChange:
            tb = getattr(win, "_csd_titlebar", None)
            if tb and hasattr(tb, "update_title"):
                tb.update_title(win.windowTitle())

        if not (win.windowFlags() & Qt.WindowType.FramelessWindowHint):
            return super().eventFilter(watched, event)

        if win.isMaximized() or win.isFullScreen():
            return super().eventFilter(watched, event)

        if etype == QEvent.Type.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            edges = self._get_edges(pos)
            if edges:
                self._update_cursor(edges)
            else:
                win.unsetCursor()

        elif etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edges = self._get_edges(pos)
                if edges:
                    wh = win.windowHandle()
                    if wh and hasattr(wh, "startSystemResize"):
                        wh.startSystemResize(edges)
                        event.accept()
                        return True

        elif etype == QEvent.Type.Leave:
            win.unsetCursor()

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
    Libadwaita / GNOME Client-Side Decoration (CSD) HeaderBar.
    Features:
      - 46px standard Libadwaita height
      - Circular / pill-shaped window controls (–, □, ✕)
      - Native Wayland / X11 window dragging via startSystemMove()
      - Double-click maximize toggle
      - Official Libadwaita Light and Dark color tokens
    """
    def __init__(self, window: QWidget, is_dark: bool = False, is_dialog: bool = False):
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._window = window
        self._is_dialog = is_dialog
        self._is_dark = is_dark
        self.setFixedHeight(46)
        self.setObjectName("CsdTitleBar")

        self.header_layout = QHBoxLayout(self)
        self.header_layout.setContentsMargins(12, 0, 12, 0)
        self.header_layout.setSpacing(6)

        # Title Label
        title = window.windowTitle() if window else ""
        self.title_lbl = QLabel(title, self)
        self.title_lbl.setObjectName("CsdTitleLabel")
        font = self.title_lbl.font()
        font.setBold(True)
        self.title_lbl.setFont(font)

        # Window Controls: minimize, maximize/restore, and close buttons on all windows
        self.btn_min = QPushButton("–", self)
        self.btn_min.setObjectName("CsdBtnMin")
        self.btn_min.setToolTip("Minimize")
        self.btn_min.clicked.connect(self._window.showMinimized)

        self.btn_max = QPushButton("□", self)
        self.btn_max.setObjectName("CsdBtnMax")
        self.btn_max.setToolTip("Maximize")
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("CsdBtnClose")
        self.btn_close.setToolTip("Close")
        self.btn_close.clicked.connect(self._window.close)

        # Layout header items following XDG / GNOME button placement
        self.setup_header_layout()
        self.apply_style(is_dark)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        super().paintEvent(event)

    def setup_header_layout(self):
        """Arranges window controls following the XDG / GNOME button layout standard."""
        self.header_layout.addWidget(self.title_lbl)
        self.header_layout.addStretch()
        if getattr(self, "btn_min", None):
            self.header_layout.addWidget(self.btn_min)
        if getattr(self, "btn_max", None):
            self.header_layout.addWidget(self.btn_max)
        self.header_layout.addWidget(self.btn_close)

    def update_title(self, title: str):
        self.title_lbl.setText(title)

    def _toggle_maximize(self):
        if not self._window:
            return
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self._update_maximize_state()

    def _update_maximize_state(self):
        is_max = self._window.isMaximized() if self._window else False
        if getattr(self, "btn_max", None):
            self.btn_max.setText("❐" if is_max else "□")
            self.btn_max.setToolTip("Restore" if is_max else "Maximize")
        self.apply_style(self._is_dark)

    def apply_style(self, is_dark: bool):
        self._is_dark = is_dark
        c = ADW_COLORS["dark" if is_dark else "light"]

        self.setStyleSheet(f"""
            QWidget#CsdTitleBar {{
                background-color: {c['headerbar_bg']};
                border-bottom: 1px solid {c['headerbar_border']};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
        """)

        self.title_lbl.setStyleSheet(f"""
            QLabel#CsdTitleLabel {{
                color: {c['window_fg']};
                font-weight: 700;
                font-size: 13px;
                background: transparent;
            }}
        """)

        base_btn_style = f"""
            QPushButton {{
                background-color: {c['button_bg']};
                border: none;
                border-radius: 12px;
                min-width: 24px; max-width: 24px;
                min-height: 24px; max-height: 24px;
                color: {c['window_fg']};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {c['button_active']};
            }}
        """

        close_btn_style = base_btn_style + f"""
            QPushButton:hover {{
                background-color: {c['close_hover']};
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: {c['close_active']};
                color: #ffffff;
            }}
        """

        if getattr(self, "btn_min", None):
            self.btn_min.setStyleSheet(base_btn_style)
        if getattr(self, "btn_max", None):
            self.btn_max.setStyleSheet(base_btn_style)
        self.btn_close.setStyleSheet(close_btn_style)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            win = self._window.windowHandle() if self._window else None
            if not win and self.window():
                win = self.window().windowHandle()
            if win and hasattr(win, "startSystemMove"):
                win.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def attach_csd(window: QWidget, is_dark: bool = False, mode: str = "Automatic"):
    """Attaches Libadwaita Client-Side Decoration (CSD) to a window (QMainWindow or QDialog)."""
    if not window or not window.isWindow():
        return

    # Strictly reject non-dialog/non-main widgets (e.g. QComboBox popups, QMenu, ToolTips)
    if not isinstance(window, (QMainWindow, QDialog)):
        return
    if window.windowType() not in (Qt.WindowType.Window, Qt.WindowType.Dialog):
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
        window.menuBar = lambda: menubar
    else:
        lay = window.layout()
        if lay is not None:
            content_widget = QWidget(window)
            content_widget.setObjectName("CsdDialogContent")
            content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            content_widget.setStyleSheet("QWidget#CsdDialogContent { background-color: palette(window); border-radius: 0px; }")
            content_lay = QVBoxLayout(content_widget)
            m = lay.contentsMargins()
            orig_spacing = lay.spacing()
            window._csd_orig_margins = (m.left(), m.top(), m.right(), m.bottom())
            window._csd_orig_spacing = orig_spacing
            window._csd_content_widget = content_widget

            content_lay.setContentsMargins(m.left(), m.top(), m.right(), m.bottom())
            content_lay.setSpacing(orig_spacing)

            while lay.count() > 0:
                item = lay.takeAt(0)
                if item.widget():
                    content_lay.addWidget(item.widget())
                elif item.layout():
                    content_lay.addLayout(item.layout())
                elif item.spacerItem():
                    content_lay.addItem(item)

            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            lay.addWidget(titlebar)
            lay.addWidget(content_widget, 1)

    resize_filter = CsdResizeFilter(window)
    window._csd_resize_filter = resize_filter
    window.installEventFilter(resize_filter)

    if not bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint):
        is_vis = window.isVisible()
        is_max = window.isMaximized()
        geo = window.geometry()
        window.setWindowFlags(window.windowFlags() | Qt.WindowType.FramelessWindowHint)
        if is_vis:
            window.setGeometry(geo)
            if is_max:
                window.showMaximized()
            else:
                window.show()


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
            menubar = None
            if hasattr(window, "menuBar"):
                try:
                    menubar = window.menuBar()
                    del window.menuBar
                except Exception:
                    pass
            if menubar:
                window.setMenuBar(menubar)
            container = getattr(window, "_csd_container", None)
            if container:
                container.setParent(None)
            window._csd_container = None
        else:
            content_widget = getattr(window, "_csd_content_widget", None)
            lay = window.layout()
            if content_widget is not None and lay is not None:
                c_lay = content_widget.layout()
                titlebar.setParent(None)
                content_widget.setParent(None)

                if c_lay is not None:
                    while c_lay.count() > 0:
                        item = c_lay.takeAt(0)
                        if item.widget():
                            lay.addWidget(item.widget())
                        elif item.layout():
                            lay.addLayout(item.layout())
                        elif item.spacerItem():
                            lay.addItem(item)

                if hasattr(window, "_csd_orig_margins"):
                    l, t, r, b = window._csd_orig_margins
                    lay.setContentsMargins(l, t, r, b)
                    del window._csd_orig_margins
                if hasattr(window, "_csd_orig_spacing"):
                    lay.setSpacing(window._csd_orig_spacing)
                    del window._csd_orig_spacing
                if hasattr(window, "_csd_content_widget"):
                    del window._csd_content_widget
            else:
                titlebar.setParent(None)
                if hasattr(window, "_csd_orig_margins"):
                    l, t, r, b = window._csd_orig_margins
                    if lay:
                        lay.setContentsMargins(l, t, r, b)
                    del window._csd_orig_margins
        window._csd_titlebar = None

    resize_filter = getattr(window, "_csd_resize_filter", None)
    if resize_filter is not None:
        window.removeEventFilter(resize_filter)
        window._csd_resize_filter = None

    is_vis = window.isVisible()
    is_max = window.isMaximized()
    geo = window.geometry()
    window.setWindowFlags(window.windowFlags() & ~Qt.WindowType.FramelessWindowHint)
    if is_vis:
        window.setGeometry(geo)
        if is_max:
            window.showMaximized()
        else:
            window.show()

