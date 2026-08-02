from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setWindowIcon(QApplication.windowIcon())
        
        self.setMinimumWidth(750)
        self.resize(750, 160)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        
        lbl_addr = QLabel("Address:")
        lbl_addr.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(lbl_addr)
        
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedWidth(75)
        self.btn_paste.setFixedHeight(32)
        self.btn_paste.setToolTip("Paste from clipboard")
        self.btn_paste.setStyleSheet("font-size: 13px;")
        self.btn_paste.clicked.connect(self.paste_url)
        input_layout.addWidget(self.btn_paste)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://")
        self.url_input.setFixedHeight(32)
        self.url_input.setStyleSheet("font-size: 13px; padding: 4px 8px;")
        input_layout.addWidget(self.url_input)
        layout.addLayout(input_layout)
        
        layout.addSpacing(6)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_download = QPushButton("OK")
        self.btn_download.setDefault(True)
        self.btn_download.setFixedWidth(90)
        self.btn_download.setFixedHeight(32)
        self.btn_download.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.btn_download.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setStyleSheet("font-size: 13px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Auto-paste from clipboard if it contains a URL
        clipboard_text = QApplication.clipboard().text().strip()
        if clipboard_text.startswith(("http://", "https://", "ftp://", "magnet:")):
            self.url_input.setText(clipboard_text)
            self.url_input.setCursorPosition(0)

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text().strip())
        self.url_input.setCursorPosition(0)

    def get_url(self):
        return self.url_input.text().strip()
