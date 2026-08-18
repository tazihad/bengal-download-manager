import os
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QApplication
)
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtCore import Qt, QUrl
from core.utils import show_in_folder, open_with, open_file_generic
from core.memory_guard import MemoryGuard

class DownloadCompleteDialog(QDialog):
    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Download complete")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(520)
        
        # Ensure it behaves like a separate top-level window in the OS taskbar while sharing WM_CLASS
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window)
        
        self.file_data = file_data
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)
        
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(8)
        
        # Address
        self.url_input = QLineEdit(file_data.get('url', ''))
        self.url_input.setReadOnly(True)
        self.url_input.setCursorPosition(0)
        self.url_input.setToolTip(file_data.get('url', ''))
        self.url_input.setStyleSheet("background: transparent; border: none; color: #eff0f1;")
        form.addRow("Address:", self.url_input)
        
        # Saved as
        self.path_input = QLineEdit(file_data.get('path', ''))
        self.path_input.setReadOnly(True)
        self.path_input.setCursorPosition(0)
        self.path_input.setToolTip(file_data.get('path', ''))
        self.path_input.setStyleSheet("background: transparent; border: none; font-weight: bold; color: #eff0f1;")
        form.addRow("The file saved as:", self.path_input)
        
        # Size
        self.lbl_size = QLabel(file_data.get('size', 'Unknown'))
        font_size = QFont(self.lbl_size.font())
        font_size.setBold(True)
        font_size.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.lbl_size.setFont(font_size)
        self.lbl_size.setStyleSheet("font-weight: bold;")
        self.lbl_size.setToolTip(f"Downloaded file size: {file_data.get('size', 'Unknown')}")
        form_layout_row = form.addRow("Size:", self.lbl_size)
        
        layout.addLayout(form)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 5, 0, 0)
        self.btn_open = QPushButton("Open")
        self.btn_open.setFixedWidth(80)
        self.btn_open.setToolTip("Open downloaded file with default application")
        
        self.btn_open_with = QPushButton("Open with...")
        self.btn_open_with.setFixedWidth(100)
        self.btn_open_with.setToolTip("Select application to open this file")
        
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setFixedWidth(100)
        self.btn_open_folder.setToolTip("Open folder containing the downloaded file")
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(80)
        self.btn_close.setToolTip("Close completion dialog")
        
        # Set height for buttons to look more like IDM
        for btn in [self.btn_open, self.btn_open_with, self.btn_open_folder, self.btn_close]:
            btn.setFixedHeight(30)
            btn_layout.addWidget(btn)
            
        layout.addLayout(btn_layout)
        
        # Connect
        self.btn_open.clicked.connect(self.on_open)
        self.btn_open_with.clicked.connect(self.on_open_with)
        self.btn_open_folder.clicked.connect(self.on_open_folder)
        self.btn_close.clicked.connect(self.accept)

        # Ensure the window fits snugly vertically while maintaining its fixed width
        self.adjustSize()
        
    def on_open(self):
        path = self.file_data.get('path')
        if path and os.path.exists(path):
            if open_file_generic(path):
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to open the file with the system default application.")
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")
            
    def on_open_with(self):
        path = self.file_data.get('path')
        if not path or not os.path.exists(path):
             QMessageBox.warning(self, "Error", "File does not exist.")
             return
             
        if open_with(path):
            self.accept()
            
    def on_open_folder(self):
        path = self.file_data.get('path')
        if path:
            show_in_folder(path)
            self.accept()
