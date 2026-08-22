import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QApplication, QFrame
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from core.utils import show_in_folder, open_file_generic
from core.services.theme_service import get_file_icon
from core.memory_guard import MemoryGuard


class DuplicateDownloadDialog(QDialog):
    """
    IDM-style dialog shown when an incoming download URL or filename matches
    an existing entry in Bengal Download Manager.
    """

    def __init__(self, file_data: dict, parent=None):
        super().__init__(parent)
        MemoryGuard.auto_manage_dialog(self)
        
        self.file_data = file_data or {}
        self.action = "cancel"
        
        status = self.file_data.get("status", "Complete")
        self.is_complete = status in ["Complete", "Finished", "Downloaded"]
        
        if self.is_complete:
            self.setWindowTitle("Duplicate Download")
        else:
            self.setWindowTitle("Download Already Exists")
            
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(540)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window)
        
        self._build_ui()
        self.adjustSize()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        
        # Header banner
        header_lbl = QLabel()
        header_lbl.setWordWrap(True)
        font_header = QFont(header_lbl.font())
        font_header.setBold(True)
        header_lbl.setFont(font_header)
        
        if self.is_complete:
            header_lbl.setText("This file has already been downloaded from this URL. What would you like to do?")
        else:
            status_str = self.file_data.get("status", "Incomplete")
            header_lbl.setText(f"This file is already in your download list (Status: {status_str}).")
            
        layout.addWidget(header_lbl)
        
        # Form details
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(6)
        
        # Filename row with icon
        fn_layout = QHBoxLayout()
        fn_layout.setSpacing(6)
        filename = self.file_data.get("filename", "file")
        icon_lbl = QLabel()
        icon = get_file_icon(filename)
        icon_lbl.setPixmap(icon.pixmap(16, 16))
        
        fn_lbl = QLabel(filename)
        fn_font = QFont(fn_lbl.font())
        fn_font.setBold(True)
        fn_lbl.setFont(fn_font)
        fn_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        fn_layout.addWidget(icon_lbl)
        fn_layout.addWidget(fn_lbl)
        fn_layout.addStretch(1)
        form.addRow("File Name:", fn_layout)
        
        # URL
        url_input = QLineEdit(self.file_data.get("url", ""))
        url_input.setReadOnly(True)
        url_input.setCursorPosition(0)
        url_input.setToolTip(self.file_data.get("url", ""))
        form.addRow("URL:", url_input)
        
        # Size
        size_str = self.file_data.get("size", "Unknown")
        lbl_size = QLabel(size_str)
        font_size = QFont(lbl_size.font())
        font_size.setFeature(QFont.Tag.fromString('tnum'), 1)
        lbl_size.setFont(font_size)
        form.addRow("Size:", lbl_size)
        
        # Path
        path_str = self.file_data.get("path", "")
        if path_str:
            path_input = QLineEdit(path_str)
            path_input.setReadOnly(True)
            path_input.setCursorPosition(0)
            path_input.setToolTip(path_str)
            form.addRow("Saved to:", path_input)
            
        layout.addLayout(form)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)
        
        if self.is_complete:
            self.btn_open = QPushButton("Open File")
            self.btn_open.setFixedHeight(30)
            self.btn_open.setToolTip("Open existing downloaded file")
            self.btn_open.clicked.connect(self.on_open)
            btn_layout.addWidget(self.btn_open)
            
            self.btn_folder = QPushButton("Open Folder")
            self.btn_folder.setFixedHeight(30)
            self.btn_folder.setToolTip("Open destination directory and highlight file")
            self.btn_folder.clicked.connect(self.on_open_folder)
            btn_layout.addWidget(self.btn_folder)
            
            self.btn_redownload = QPushButton("Redownload")
            self.btn_redownload.setFixedHeight(30)
            self.btn_redownload.setToolTip("Restart download and overwrite existing file")
            self.btn_redownload.clicked.connect(self.on_redownload)
            btn_layout.addWidget(self.btn_redownload)
        else:
            self.btn_resume = QPushButton("Resume")
            self.btn_resume.setFixedHeight(30)
            self.btn_resume.setDefault(True)
            self.btn_resume.setToolTip("Resume downloading this existing item")
            self.btn_resume.clicked.connect(self.on_resume)
            btn_layout.addWidget(self.btn_resume)
            
            self.btn_restart = QPushButton("Restart")
            self.btn_restart.setFixedHeight(30)
            self.btn_restart.setToolTip("Restart download from beginning (0%)")
            self.btn_restart.clicked.connect(self.on_restart)
            btn_layout.addWidget(self.btn_restart)
            
        self.btn_copy = QPushButton("Download Copy")
        self.btn_copy.setFixedHeight(30)
        self.btn_copy.setToolTip("Save as a new copy with an auto-numbered filename")
        self.btn_copy.clicked.connect(self.on_download_copy)
        btn_layout.addWidget(self.btn_copy)
        
        btn_layout.addStretch(1)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(75)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip("Cancel and discard this request")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)

    def on_open(self):
        path = self.file_data.get("path")
        if path and os.path.exists(path):
            open_file_generic(path)
            self.action = "open"
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The downloaded file was not found at:\n{path}\n\nYou can click 'Redownload' to fetch it again."
            )

    def on_open_folder(self):
        path = self.file_data.get("path")
        if path:
            show_in_folder(path)
            self.action = "open_folder"
            self.accept()

    def on_redownload(self):
        self.action = "redownload"
        self.accept()

    def on_resume(self):
        self.action = "resume"
        self.accept()

    def on_restart(self):
        self.action = "restart"
        self.accept()

    def on_download_copy(self):
        self.action = "download_copy"
        self.accept()

    def get_action(self) -> str:
        return self.action
