from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

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

        from ui.icons import get_monochrome_icon
        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setIcon(get_monochrome_icon("documents", size=16))
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

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(8)
        
        self.lbl_media_status = QLabel("Media URL detected (go to Media Downloader)")
        self.lbl_media_status.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 11px;")
        self.lbl_media_status.hide()

        self.btn_send_media = QPushButton("Download Media")
        self.btn_send_media.setFixedHeight(30)
        self.btn_send_media.setToolTip("Open link in Media Downloader to extract video/audio formats")
        from ui.icons import get_monochrome_icon
        self.btn_send_media.setIcon(get_monochrome_icon("media_downloader", size=16))
        self.btn_send_media.clicked.connect(self._on_send_media_clicked)
        self.btn_send_media.hide()

        btn_layout.addWidget(self.btn_send_media)
        btn_layout.addWidget(self.lbl_media_status)
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
        if is_media_downloader_url(url):
            self.lbl_media_status.show()
            self.btn_send_media.show()
        else:
            self.lbl_media_status.hide()
            self.btn_send_media.hide()

    def _on_send_media_clicked(self):
        self.is_media_mode = True
        self.accept()

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text().strip())
        self.url_input.setCursorPosition(0)

    def get_url(self):
        return self.url_input.text().strip()
