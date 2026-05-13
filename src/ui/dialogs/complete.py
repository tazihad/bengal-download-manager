import os
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QFileDialog
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import Qt, QUrl
from core.utils import show_in_folder

class DownloadCompleteDialog(QDialog):
    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download complete")
        self.setFixedWidth(520)
        self.file_data = file_data
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Address
        self.url_input = QLineEdit(file_data.get('url', ''))
        self.url_input.setReadOnly(True)
        self.url_input.setCursorPosition(0)
        self.url_input.setStyleSheet("background: transparent; border: none; color: #555;")
        form.addRow("Address:", self.url_input)
        
        # Saved as
        self.path_input = QLineEdit(file_data.get('path', ''))
        self.path_input.setReadOnly(True)
        self.path_input.setCursorPosition(0)
        self.path_input.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        form.addRow("The file saved as:", self.path_input)
        
        # Size
        self.lbl_size = QLabel(file_data.get('size', 'Unknown'))
        self.lbl_size.setStyleSheet("font-weight: bold;")
        form.addRow("Size:", self.lbl_size)
        
        layout.addLayout(form)
        layout.addSpacing(10)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("Open")
        self.btn_open_with = QPushButton("Open with...")
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_close = QPushButton("Close")
        
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
        
    def on_open(self):
        path = self.file_data.get('path')
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")
            
    def on_open_with(self):
        path = self.file_data.get('path')
        if not path or not os.path.exists(path):
             QMessageBox.warning(self, "Error", "File does not exist.")
             return
             
        # On Linux we can use a generic open with dialog or ask for app
        if os.name == 'nt':
            # On Windows, we can use 'rundll32.exe shell32.dll,OpenAs_RunDLL path'
            subprocess.Popen(['rundll32.exe', 'shell32.dll,OpenAs_RunDLL', path])
        else:
            # On Linux, there isn't a single standard "Open With" command like Windows
            # But we can ask the user for an executable
            app_path, _ = QFileDialog.getOpenFileName(self, "Select Application", "/usr/bin", "Executables (*)")
            if app_path:
                subprocess.Popen([app_path, path])
        self.accept()
            
    def on_open_folder(self):
        path = self.file_data.get('path')
        if path:
            show_in_folder(path)
            self.accept()
