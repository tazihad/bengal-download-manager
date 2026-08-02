from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

class RenameDialog(QDialog):
    def __init__(self, current_filename, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename File")
        self.setWindowIcon(QApplication.windowIcon())
        self.setMinimumWidth(600)
        self.resize(600, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl = QLabel("Enter new file name:")
        layout.addWidget(lbl)

        self.filename_input = QLineEdit(current_filename)
        self.filename_input.setFixedHeight(28)
        self.filename_input.selectAll()
        layout.addWidget(self.filename_input)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.setFixedWidth(90)
        self.btn_ok.setFixedHeight(30)
        self.btn_ok.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def get_filename(self):
        return self.filename_input.text().strip()
