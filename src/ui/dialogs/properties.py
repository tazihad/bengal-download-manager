import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QGridLayout
)

class PropertiesDialog(QDialog):
    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Properties - {file_data.get('filename', 'Unknown')}")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
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
            val_widget.setStyleSheet("""
                QLineEdit { 
                    background: transparent; 
                    color: white; 
                    border: none; 
                }
            """)
            
            grid.addWidget(lbl_widget, i, 0)
            grid.addWidget(val_widget, i, 1)
            
        grp_file.setLayout(grid)
        layout.addWidget(grp_file)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_open = QPushButton("Open")
        self.btn_open.clicked.connect(self.accept) 
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
