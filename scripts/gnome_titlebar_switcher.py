import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtDBus import QDBusConnection, QDBusMessage

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

class GnomeXdgWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(600, 420)

        self.current_selection = "Automatic"

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.window_surface = QWidget(self)
        root_layout.addWidget(self.window_surface)

        surface_layout = QVBoxLayout(self.window_surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        # ----------------- Libadwaita HeaderBar -----------------
        self.header_bar = QWidget(self.window_surface)
        self.header_bar.setFixedHeight(46)

        self.header_layout = QHBoxLayout(self.header_bar)
        self.header_layout.setContentsMargins(12, 0, 12, 0)
        self.header_layout.setSpacing(6)

        self.title_label = QLabel("XDG Standard HeaderBar", self.header_bar)

        self.btn_min = QPushButton("–", self.header_bar)
        self.btn_max = QPushButton("□", self.header_bar)
        self.btn_close = QPushButton("✕", self.header_bar)

        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self.toggle_maximized)
        self.btn_close.clicked.connect(self.close)

        # Layout header items following XDG/GNOME button placement
        self.setup_header_layout()

        # ----------------- Content Area -----------------
        self.content_area = QWidget(self.window_surface)
        self.content_area.setStyleSheet("""
            QWidget {
                background-color: #242424;
                color: #dedede;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
        """)

        content_layout = QVBoxLayout(self.content_area)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt_label = QLabel("HeaderBar Theme")
        prompt_label.setStyleSheet("font-size: 14px; font-weight: 700; margin-bottom: 8px; color: #ffffff;")

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Automatic", "Light", "Dark"])
        self.theme_combo.setFixedWidth(220)
        self.theme_combo.setStyleSheet("""
            QComboBox {
                padding: 7px 14px;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                background-color: #303030;
                color: #ffffff;
                font-weight: 500;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #303030;
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: #3584e4;
                padding: 4px;
            }
        """)
        self.theme_combo.currentTextChanged.connect(self.on_selection_changed)

        content_layout.addWidget(prompt_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.theme_combo, alignment=Qt.AlignmentFlag.AlignCenter)

        surface_layout.addWidget(self.header_bar)
        surface_layout.addWidget(self.content_area)

        # ----------------- XDG DBus Monitor -----------------
        self.setup_xdg_portal_listener()
        self.apply_theme()

    def setup_header_layout(self):
        """Arranges window controls following the XDG / GNOME button layout standard."""
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.btn_min)
        self.header_layout.addWidget(self.btn_max)
        self.header_layout.addWidget(self.btn_close)

    def read_xdg_color_scheme(self) -> str:
        """
        Queries org.freedesktop.portal.Settings namespace 'org.freedesktop.appearance',
        key 'color-scheme'.
        0 = Default / Light
        1 = Prefer Dark
        2 = Prefer Light
        """
        bus = QDBusConnection.sessionBus()
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
                val = int(args[0])
                if val == 1:
                    return "dark"
        return "light"

    def setup_xdg_portal_listener(self):
        """Listens for the standard XDG SettingChanged signal."""
        bus = QDBusConnection.sessionBus()
        bus.connect(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "SettingChanged",
            self.on_xdg_setting_changed
        )

    @pyqtSlot(QDBusMessage)
    def on_xdg_setting_changed(self, msg: QDBusMessage):
        args = msg.arguments()
        if len(args) >= 3:
            namespace, key, value = args[0], args[1], args[2]
            if namespace == "org.freedesktop.appearance" and key == "color-scheme":
                if self.current_selection == "Automatic":
                    self.apply_theme()

    def on_selection_changed(self, text: str):
        self.current_selection = text
        self.apply_theme()

    def apply_theme(self):
        target = self.current_selection.lower()
        if target == "automatic":
            target = self.read_xdg_color_scheme()

        c = ADW_COLORS["dark" if target == "dark" else "light"]

        # Libadwaita HeaderBar container
        self.header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {c['headerbar_bg']};
                border-bottom: 1px solid {c['headerbar_border']};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)

        # Window title label
        self.title_label.setStyleSheet(f"""
            color: {c['window_fg']};
            font-weight: 700;
            font-size: 13px;
        """)

        # Adwaita control pill buttons
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

        self.btn_min.setStyleSheet(base_btn_style)
        self.btn_max.setStyleSheet(base_btn_style)
        self.btn_close.setStyleSheet(close_btn_style)

    def toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        # Native Wayland system move via compositor
        if event.button() == Qt.MouseButton.LeftButton and self.header_bar.underMouse():
            win = self.windowHandle()
            if win:
                win.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.header_bar.underMouse():
            self.toggle_maximized()
        super().mouseDoubleClickEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GnomeXdgWindow()
    window.show()
    sys.exit(app.exec())
