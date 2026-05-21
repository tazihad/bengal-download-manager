from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(520)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(QLabel("Address:"))
        
        input_layout = QHBoxLayout()
        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedWidth(60)
        self.btn_paste.setFixedHeight(25)
        self.btn_paste.setToolTip("Paste from clipboard")
        self.btn_paste.clicked.connect(self.paste_url)
        input_layout.addWidget(self.btn_paste)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://")
        self.url_input.setFixedHeight(25)
        input_layout.addWidget(self.url_input)
        layout.addLayout(input_layout)
        
        layout.addSpacing(5)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_download = QPushButton("OK")
        self.btn_download.setDefault(True)
        self.btn_download.setFixedWidth(80)
        self.btn_download.setFixedHeight(30)
        self.btn_download.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Auto-paste from clipboard if it contains a URL
        clipboard_text = QApplication.clipboard().text().strip()
        if clipboard_text.startswith(("http://", "https://", "ftp://", "magnet:")):
            self.url_input.setText(clipboard_text)
            self.url_input.selectAll()

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text())

    def get_url(self):
        return self.url_input.text().strip()
