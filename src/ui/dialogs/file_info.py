import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFormLayout, QApplication
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal
from core.utils import get_unique_filepath, choose_portal_save_path, get_user_downloads_dir
from core.config import load_category_config
from core.memory_guard import MemoryGuard

class DownloadFileInfoDialog(QDialog):
    size_updated_signal = pyqtSignal(str, int)

    def __init__(self, file_info, parent=None, existing_paths=None, existing_names=None, force_copy=False):
        super().__init__(parent)
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Download File Info")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(520)
        
        # Ensure it behaves like a separate top-level window in the OS taskbar while sharing WM_CLASS
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window)
        
        self.file_info = file_info
        self.existing_paths = set(existing_paths) if existing_paths else set()
        self.existing_names = set(existing_names) if existing_names else set()
        self.force_copy = force_copy
        self.config = load_category_config()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 10, 15, 10)
        self.layout.setSpacing(8)
        
        # Determine category automatically
        self.ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"],
            "Programs": [".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"]
        }
        
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(8)
        
        self.url_input = QLineEdit(file_info.get("url", ""))
        self.url_input.setReadOnly(True)
        self.url_input.setCursorPosition(0)
        self.url_input.setToolTip("Full download source URL")
        form_layout.addRow("URL:", self.url_input)
        
        self.category_combo = QComboBox()
        categories = ["General", "Compressed", "Documents", "Music", "Programs", "Video"]
        self.category_combo.addItems(categories)
        self.category_combo.setToolTip("Category to organize and route the download file")
        form_layout.addRow("Category:", self.category_combo)
        
        save_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.save_input.setToolTip("Destination path and filename for the download")
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.setToolTip("Browse folder to select save location")
        self.btn_browse.clicked.connect(self.browse_save_path)
        save_layout.addWidget(self.save_input)
        save_layout.addWidget(self.btn_browse)
        form_layout.addRow("Save As:", save_layout)
        
        from core.utils import get_file_type_description
        filename = file_info.get("filename", "")
        file_type = get_file_type_description(filename, file_info.get("content_type"))
        init_size_str = file_info.get("size_str", "Unknown")
        display_size = f"{init_size_str}, {file_type}" if file_type and file_type != "Unknown Type" else init_size_str

        self.lbl_size = QLabel(display_size)
        font_size = QFont(self.lbl_size.font())
        font_size.setBold(True)
        font_size.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.lbl_size.setFont(font_size)
        self.lbl_size.setStyleSheet("font-weight: bold;")
        self.lbl_size.setToolTip("Detected content size and file type")
        form_layout.addRow("File Size:", self.lbl_size)
        
        self.layout.addLayout(form_layout)
        
        self.auto_detect_category()
        self.update_save_path()
        self.category_combo.currentTextChanged.connect(self.update_save_path)
        self.save_input.textChanged.connect(self.on_save_input_changed)
        
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_later = QPushButton("Download Later")
        self.btn_later.setFixedWidth(110)
        self.btn_later.setFixedHeight(30)
        self.btn_later.setToolTip("Add download to list in paused state")
        
        self.btn_start = QPushButton("Start Download")
        self.btn_start.setFixedWidth(110)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setDefault(True)
        self.btn_start.setToolTip("Begin downloading this file immediately")
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip("Cancel and discard download request")
        
        self.btn_start.clicked.connect(self.on_start)
        self.btn_later.clicked.connect(self.on_later)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_later)
        btn_layout.addStretch(1) # Push 'Download Later' to left, others to right
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(btn_layout)
        
        self.adjustSize()
        
        self.action_result = None

        # Background size probing if size was initially unknown
        self.size_probe_worker = None
        current_size_bytes = self.file_info.get("size_bytes", 0)
        current_size_str = str(self.file_info.get("size_str", "")).strip()
        if (not current_size_bytes or current_size_bytes <= 0 or current_size_str in ["Unknown", "Calculating...", "?", ""]) and self.file_info.get("url"):
            from core.workers.fetcher import BackgroundSizeProbeWorker
            self.size_probe_worker = BackgroundSizeProbeWorker(
                url=self.file_info.get("url"),
                user_agent=self.file_info.get("user_agent"),
                cookies=self.file_info.get("cookies"),
                referrer=self.file_info.get("referer") or self.file_info.get("referrer")
            )
            self.size_probe_worker.size_found_signal.connect(self.update_file_size)
            self.size_probe_worker.start()
            self.finished.connect(self._cleanup_probe)

    def _refresh_size_label(self):
        from core.utils import get_file_type_description
        filename = self.file_info.get("filename") or os.path.basename(self.save_input.text().strip())
        file_type = get_file_type_description(filename, self.file_info.get("content_type"))
        size_str = self.file_info.get("size_str", "Unknown")
        display_size = f"{size_str}, {file_type}" if file_type and file_type != "Unknown Type" else size_str
        self.lbl_size.setText(display_size)

    def update_file_size(self, size_str, size_bytes):
        self.file_info["size_str"] = size_str
        self.file_info["size_bytes"] = size_bytes
        self._refresh_size_label()
        self.size_updated_signal.emit(size_str, size_bytes)

    def _cleanup_probe(self):
        worker = getattr(self, "size_probe_worker", None)
        if worker is not None:
            self.size_probe_worker = None
            try:
                worker.stop()
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1500)
            except Exception:
                pass

    def closeEvent(self, event):
        self._cleanup_probe()
        super().closeEvent(event)

    def reject(self):
        self._cleanup_probe()
        super().reject()

    def accept(self):
        self._cleanup_probe()
        super().accept() 

    def on_save_input_changed(self, text):
        new_name = os.path.basename(text.strip())
        if new_name:
            self.file_info["filename"] = new_name
            self._refresh_size_label()
        
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
            base_dir = get_user_downloads_dir()
        
        try: os.makedirs(base_dir, exist_ok=True)
        except: pass
        
        filename = self.file_info.get("filename") or os.path.basename(self.save_input.text().strip()) or "file"
        target_path = os.path.join(base_dir, filename)
        target_path = get_unique_filepath(
            target_path,
            existing_paths=self.existing_paths,
            existing_names=self.existing_names,
            force_suffix=self.force_copy
        )
        self.file_info["filename"] = os.path.basename(target_path)
        self.save_input.setText(target_path)
        self.save_input.setCursorPosition(0)
        
    def browse_save_path(self):
        current_text = self.save_input.text().strip()
        folder = os.path.dirname(current_text) if current_text else get_user_downloads_dir()
        filename = os.path.basename(current_text) if current_text else self.file_info.get("filename", "")
        path = choose_portal_save_path("Save File As", filename, folder)
        if path:
            if os.path.isdir(path):
                path = os.path.join(path, filename)
            self.file_info["filename"] = os.path.basename(path)
            self.save_input.setText(path)
            self.save_input.setCursorPosition(0)
            self._refresh_size_label()
            
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
