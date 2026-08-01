import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QGridLayout, QApplication
)

from PyQt6.QtGui import QFont
from core.utils import open_file_generic

class PropertiesDialog(QDialog):
    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Properties - {file_data.get('filename', 'Unknown')}")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(500)
        self.file_data = file_data
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        grp_file = QGroupBox("File Information")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setSpacing(10)
        
        labels = [
            ("File Name:", file_data.get('filename', '')),
            ("Type:", os.path.splitext(file_data.get('filename', ''))[1].upper() + " File"),
            ("Status:", file_data.get('status', 'Unknown')),
            ("Size:", file_data.get('size', 'Unknown')),
            ("Saved To:", os.path.dirname(file_data.get('path', 'Unknown'))),
            ("Address:", file_data.get('url', '')),
            ("Date Added:", file_data.get('date_added', '')),
            ("Last Try:", file_data.get('last_try', ''))
        ]
        
        for i, (label_text, value) in enumerate(labels):
            lbl_widget = QLabel(label_text)
            lbl_widget.setStyleSheet("font-weight: bold;")
            
            val_widget = QLineEdit(str(value))
            val_widget.setReadOnly(True)
            val_widget.setCursorPosition(0) 
            val_font = QFont(val_widget.font())
            val_font.setFeature(QFont.Tag.fromString('tnum'), 1)
            val_widget.setFont(val_font)
            val_widget.setStyleSheet("background: transparent; border: none; color: #444;")
            
            grid.addWidget(lbl_widget, i, 0)
            grid.addWidget(val_widget, i, 1)
            
        grp_file.setLayout(grid)
        layout.addWidget(grp_file)
        
        layout.addSpacing(5)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_open = QPushButton("Open")
        self.btn_open.setFixedWidth(80)
        self.btn_open.setFixedHeight(30)
        self.btn_open.clicked.connect(self.on_open) 
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(80)
        self.btn_close.setFixedHeight(30)
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def on_open(self):
        path = self.file_data.get('path')
        if path and os.path.exists(path):
            open_file_generic(path)
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")
