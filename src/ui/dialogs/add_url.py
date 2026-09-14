from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)
from PyQt6.QtGui import QIcon, QColor, QPalette
from PyQt6.QtCore import Qt, QEvent, QObject
from ui.icons import get_monochrome_icon


def get_add_url_button_icon(icon_name: str, size: int = 16) -> QIcon:
    """
    Creates an icon specifically for AddUrlDialog buttons where:
    - In Dark Mode: Normal is white, pressed/clicked is white (#ffffff).
    - In Light Mode: Normal is dark, pressed/clicked is dark (#000000).
    """
    app = QApplication.instance()
    is_dark = True
    if app:
        pal = app.palette()
        bg_val = pal.color(QPalette.ColorRole.Window).value()
        fg_val = pal.color(QPalette.ColorRole.WindowText).value()
        if bg_val >= 128 and fg_val <= 128:
            is_dark = False

    normal_color = QColor("#ffffff") if is_dark else QColor("#232629")
    pressed_color = QColor("#ffffff") if is_dark else QColor("#000000")

    return get_monochrome_icon(
        icon_name,
        color=normal_color,
        selected_color=pressed_color,
        active_color=pressed_color,
        size=size
    )


class AddUrlButtonPressFilter(QObject):
    """
    Event filter for buttons in AddUrlDialog to ensure icon color on mouse click/press:
    - Dark mode: click -> white icon (#ffffff)
    - Light mode: click -> dark icon (#000000)
    """
    def __init__(self, icon_name: str, size: int = 16, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.size = size

    def _get_is_dark(self) -> bool:
        app = QApplication.instance()
        if app:
            pal = app.palette()
            bg_val = pal.color(QPalette.ColorRole.Window).value()
            fg_val = pal.color(QPalette.ColorRole.WindowText).value()
            if bg_val >= 128 and fg_val <= 128:
                return False
        return True

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and obj.isEnabled():
            if event.type() == QEvent.Type.MouseButtonPress:
                is_dark = self._get_is_dark()
                click_color = QColor("#ffffff") if is_dark else QColor("#000000")
                obj.setIcon(get_monochrome_icon(self.icon_name, color=click_color, selected_color=click_color, active_color=click_color, size=self.size))
            elif event.type() == QEvent.Type.MouseButtonRelease:
                obj.setIcon(get_add_url_button_icon(self.icon_name, size=self.size))
        return super().eventFilter(obj, event)


class AddUrlDialog(QDialog):
    def __init__(self, parent=None, paste_clipboard=False):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setWindowIcon(QApplication.windowIcon())
        
        self.setMinimumWidth(750)
        self.resize(750, 115)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        lbl_addr = QLabel("Address:")
        layout.addWidget(lbl_addr)
        
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setIcon(get_add_url_button_icon("documents", size=16))
        self._paste_filter = AddUrlButtonPressFilter("documents", size=16, parent=self)
        self.btn_paste.installEventFilter(self._paste_filter)
        self.btn_paste.setFixedWidth(80)
        self.btn_paste.setFixedHeight(28)
        self.btn_paste.setToolTip("Paste from clipboard")
        self.btn_paste.clicked.connect(self.paste_url)
        input_layout.addWidget(self.btn_paste)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://")
        self.url_input.setFixedHeight(28)
        self.url_input.setToolTip("Enter or paste the download URL address (HTTP, HTTPS, FTP, or Magnet link)")
        input_layout.addWidget(self.url_input)
        layout.addLayout(input_layout)
        
        self.is_media_mode = False
        self.is_batch_mode = False
        self.is_batch_list_mode = False
        self.batch_urls = []

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(8)
        
        self.lbl_media_status = QLabel("Media URL detected (go to Media Downloader)")
        self.lbl_media_status.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 11px;")
        self.lbl_media_status.hide()

        self.btn_send_media = QPushButton("Download Media")
        self.btn_send_media.setFixedHeight(30)
        self.btn_send_media.setToolTip("Open link in Media Downloader to extract video/audio formats")
        self.btn_send_media.setIcon(get_add_url_button_icon("media_downloader", size=16))
        self._media_filter = AddUrlButtonPressFilter("media_downloader", size=16, parent=self)
        self.btn_send_media.installEventFilter(self._media_filter)
        self.btn_send_media.clicked.connect(self._on_send_media_clicked)
        self.btn_send_media.hide()

        self.lbl_batch_status = QLabel("Batch pattern detected (go to Batch Downloader)")
        self.lbl_batch_status.setStyleSheet("color: #3498db; font-weight: bold; font-size: 11px;")
        self.lbl_batch_status.hide()

        self.btn_send_batch = QPushButton("Batch Download")
        self.btn_send_batch.setFixedHeight(30)
        self.btn_send_batch.setToolTip("Open in Batch Downloader to configure wildcard range")
        self.btn_send_batch.setIcon(get_add_url_button_icon("add_url", size=16))
        self._batch_filter = AddUrlButtonPressFilter("add_url", size=16, parent=self)
        self.btn_send_batch.installEventFilter(self._batch_filter)
        self.btn_send_batch.clicked.connect(self._on_send_batch_clicked)
        self.btn_send_batch.hide()

        btn_layout.addWidget(self.btn_send_media)
        btn_layout.addWidget(self.lbl_media_status)
        btn_layout.addWidget(self.btn_send_batch)
        btn_layout.addWidget(self.lbl_batch_status)
        btn_layout.addStretch()
        
        self.btn_download = QPushButton("OK")
        self.btn_download.setDefault(True)
        self.btn_download.setFixedWidth(80)
        self.btn_download.setFixedHeight(30)
        self.btn_download.setToolTip("Fetch file information and start download")
        self.btn_download.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip("Cancel and close dialog")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.url_input.textChanged.connect(self._check_url_type)

        # Auto-paste from clipboard
        clipboard_text = QApplication.clipboard().text().strip()
        if paste_clipboard and clipboard_text:
            self.url_input.setText(clipboard_text)
            self.url_input.setCursorPosition(0)
        elif clipboard_text.startswith(("http://", "https://", "ftp://", "magnet:")):
            self.url_input.setText(clipboard_text)
            self.url_input.setCursorPosition(0)

        self._check_url_type()

    def _check_url_type(self):
        from core.utils import is_media_downloader_url
        url = self.get_url()
        lines = [line.strip() for line in url.split("\n") if line.strip().startswith(("http://", "https://", "ftp://", "magnet:"))]
        
        if len(lines) > 1:
            self.batch_urls = lines
            self.lbl_batch_status.setText(f"{len(lines)} URLs detected (open in Batch Review)")
            self.lbl_batch_status.show()
            self.btn_send_batch.setText("Review Batch")
            self.btn_send_batch.show()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()
        elif "*" in url and url.startswith(("http://", "https://", "ftp://")):
            self.lbl_batch_status.setText("Wildcard pattern detected (open in Batch Downloader)")
            self.lbl_batch_status.show()
            self.btn_send_batch.setText("Batch Download")
            self.btn_send_batch.show()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()
        elif is_media_downloader_url(url):
            self.lbl_batch_status.hide()
            self.btn_send_batch.hide()
            self.lbl_media_status.show()
            self.btn_send_media.show()
        else:
            self.lbl_batch_status.hide()
            self.btn_send_batch.hide()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()

    def _on_send_media_clicked(self):
        self.is_media_mode = True
        self.accept()

    def _on_send_batch_clicked(self):
        url = self.get_url()
        lines = [line.strip() for line in url.split("\n") if line.strip().startswith(("http://", "https://", "ftp://", "magnet:"))]
        if len(lines) > 1:
            self.is_batch_list_mode = True
            self.batch_urls = lines
        else:
            self.is_batch_mode = True
        self.accept()

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text().strip())
        self.url_input.setCursorPosition(0)

    def get_url(self):
        return self.url_input.text().strip()
