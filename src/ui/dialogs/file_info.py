import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QFormLayout
)
from core.utils import get_unique_filepath
from core.config import load_category_config

class DownloadFileInfoDialog(QDialog):
    def __init__(self, file_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download File Info")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(520)
        self.file_info = file_info
        self.config = load_category_config()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)
        
        # Determine category automatically
        self.ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
            "Programs": [".exe", ".msi", ".sh", ".bin", ".deb", ".bat"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }
        
        form_layout = QFormLayout()
        
        self.url_input = QLineEdit(file_info.get("url", ""))
        self.url_input.setReadOnly(True)
        self.url_input.setCursorPosition(0)
        form_layout.addRow("URL:", self.url_input)
        
        self.category_combo = QComboBox()
        categories = ["General", "Compressed", "Documents", "Music", "Programs", "Video"]
        self.category_combo.addItems(categories)
        form_layout.addRow("Category:", self.category_combo)
        
        save_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.clicked.connect(self.browse_save_path)
        save_layout.addWidget(self.save_input)
        save_layout.addWidget(self.btn_browse)
        form_layout.addRow("Save As:", save_layout)
        
        self.lbl_size = QLabel(file_info.get("size_str", "Unknown"))
        self.lbl_size.setStyleSheet("font-weight: bold;")
        form_layout.addRow("File Size:", self.lbl_size)
        
        self.layout.addLayout(form_layout)
        
        self.auto_detect_category()
        self.update_save_path()
        self.category_combo.currentTextChanged.connect(self.update_save_path)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_later = QPushButton("Download Later")
        self.btn_later.setFixedWidth(110)
        self.btn_later.setFixedHeight(30)
        
        self.btn_start = QPushButton("Start Download")
        self.btn_start.setFixedWidth(110)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setDefault(True)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        
        self.btn_start.clicked.connect(self.on_start)
        self.btn_later.clicked.connect(self.on_later)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_later)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(btn_layout)
        
        self.action_result = None 
        
    def auto_detect_category(self):
        filename = self.file_info.get("filename", "").lower()
        detected = "General"
        for cat, exts in self.ext_map.items():
            if any(filename.endswith(ext) for ext in exts):
                detected = cat
                break
        self.category_combo.setCurrentText(detected)
        
    def update_save_path(self):
        cat = self.category_combo.currentText()
        categories = self.config.get("categories", {})
        
        if cat in categories:
            base_dir = categories[cat]["path"]
        else:
            base_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        
        try: os.makedirs(base_dir, exist_ok=True)
        except: pass
        
        target_path = os.path.join(base_dir, self.file_info.get("filename", "file"))
        target_path = get_unique_filepath(target_path)
        self.save_input.setText(target_path)
        
    def browse_save_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File As", self.save_input.text())
        if path:
            self.save_input.setText(path)
            
    def get_results(self):
        return {
            "action": self.action_result,
            "save_path": self.save_input.text(),
            "category": self.category_combo.currentText(),
            "filename": os.path.basename(self.save_input.text()),
            "size_str": self.file_info.get("size_str", "Unknown"),
            "size_bytes": self.file_info.get("size_bytes", 0)
        }
        
    def on_start(self):
        self.action_result = 'start'
        self.accept()
        
    def on_later(self):
        self.action_result = 'later'
        self.accept()
