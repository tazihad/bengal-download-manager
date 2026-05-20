from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

class RefreshAddressDialog(QDialog):
    def __init__(self, current_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Refresh download address")
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
        
        self.url_input = QLineEdit(current_url)
        self.url_input.setPlaceholderText("http://")
        self.url_input.setFixedHeight(25)
        input_layout.addWidget(self.url_input)
        layout.addLayout(input_layout)
        
        layout.addSpacing(5)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.setFixedWidth(80)
        self.btn_ok.setFixedHeight(30)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text())

    def get_url(self):
        return self.url_input.text().strip()
