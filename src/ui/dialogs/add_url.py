import os
from urllib.parse import urlparse
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QWidget, QSizePolicy
)
from PyQt6.QtGui import QIcon, QColor, QPalette, QFont, QFontMetrics, QKeySequence
from PyQt6.QtCore import Qt, QEvent, QObject, QTimer, pyqtSignal

from ui.icons import get_monochrome_icon, get_colorful_icon
from core.memory_guard import MemoryGuard
from core.utils import (
    resolve_filename, is_media_downloader_url, get_file_type_description,
    get_user_downloads_dir
)
from core.config import load_category_config, DEFAULT_CATEGORIES
from core.workers.fetcher import FileInfoFetcherWorker


def get_add_url_button_icon(icon_name: str, size: int = 16) -> QIcon:
    """
    Creates an icon for AddUrlDialog buttons adapting cleanly to dark/light palettes.
    """
    app = QApplication.instance()
    is_dark = True
    if app:
        pal = app.palette()
        bg_val = pal.color(QPalette.ColorRole.Window).value()
        fg_val = pal.color(QPalette.ColorRole.WindowText).value()
        if bg_val >= 128 and fg_val <= 128:
            is_dark = False

    normal_color = QColor("#ffffff") if is_dark else QColor("#232629")
    pressed_color = QColor("#ffffff") if is_dark else QColor("#000000")

    return get_monochrome_icon(
        icon_name,
        color=normal_color,
        selected_color=pressed_color,
        active_color=pressed_color,
        size=size
    )


class AddUrlButtonPressFilter(QObject):
    """
    Event filter for buttons in AddUrlDialog to ensure responsive icon color on mouse press.
    """
    def __init__(self, icon_name: str, size: int = 16, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.size = size

    def _get_is_dark(self) -> bool:
        app = QApplication.instance()
        if app:
            pal = app.palette()
            bg_val = pal.color(QPalette.ColorRole.Window).value()
            fg_val = pal.color(QPalette.ColorRole.WindowText).value()
            if bg_val >= 128 and fg_val <= 128:
                return False
        return True

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and obj.isEnabled():
            if event.type() == QEvent.Type.MouseButtonPress:
                is_dark = self._get_is_dark()
                click_color = QColor("#ffffff") if is_dark else QColor("#000000")
                obj.setIcon(get_monochrome_icon(self.icon_name, color=click_color, selected_color=click_color, active_color=click_color, size=self.size))
            elif event.type() == QEvent.Type.MouseButtonRelease:
                obj.setIcon(get_add_url_button_icon(self.icon_name, size=self.size))
        return super().eventFilter(obj, event)


class MicroInspectorCard(QFrame):
    """
    Essential Streamline Micro-Inspector Card:
    Displays real-time resolved metadata (file category icon, real filename,
    pure tabular download file size, and target directory) with ZERO speed/time clutter.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MicroInspectorCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Style frame cleanly based on system palette
        self._apply_frame_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # 1. Left: Dynamic Category / Extension Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(36, 36)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setStyleSheet("""
            background: rgba(59, 130, 246, 0.12);
            border-radius: 8px;
            padding: 4px;
        """)
        self.lbl_icon.setPixmap(get_monochrome_icon("all_downloads", size=22).pixmap(22, 22))
        layout.addWidget(self.lbl_icon)

        # 2. Center: Filename & Subline Metadata
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(3)

        self.lbl_filename = QLabel("Enter or paste download address")
        font_fn = QFont(self.lbl_filename.font())
        font_fn.setPointSize(font_fn.pointSize() if font_fn.pointSize() > 0 else 10)
        font_fn.setBold(True)
        self.lbl_filename.setFont(font_fn)
        self.lbl_filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.lbl_filename)

        subline_layout = QHBoxLayout()
        subline_layout.setContentsMargins(0, 0, 0, 0)
        subline_layout.setSpacing(6)

        self.lbl_size = QLabel("0 B")
        font_size = QFont(self.lbl_size.font())
        font_size.setBold(True)
        font_size.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.lbl_size.setFont(font_size)
        self.lbl_size.setStyleSheet("color: #3b82f6; font-weight: bold;")

        self.lbl_separator = QLabel("•")
        self.lbl_separator.setStyleSheet("color: gray;")

        self.lbl_category = QLabel("Awaiting URL")
        self.lbl_category.setStyleSheet("color: gray;")

        self.lbl_separator2 = QLabel("•")
        self.lbl_separator2.setStyleSheet("color: gray;")

        self.lbl_destination = QLabel("📁 ~/Downloads")
        self.lbl_destination.setStyleSheet("color: gray;")

        subline_layout.addWidget(self.lbl_size)
        subline_layout.addWidget(self.lbl_separator)
        subline_layout.addWidget(self.lbl_category)
        subline_layout.addWidget(self.lbl_separator2)
        subline_layout.addWidget(self.lbl_destination)
        subline_layout.addStretch()

        details_layout.addLayout(subline_layout)
        layout.addLayout(details_layout)

    def _apply_frame_style(self):
        self.setStyleSheet("""
            QFrame#MicroInspectorCard {
                border: 1px solid palette(mid);
                border-radius: 8px;
                background-color: palette(base);
            }
        """)

    def set_probing(self, url: str):
        """Puts inspector into probing state with initial URL heuristic."""
        initial_fn = resolve_filename(url, {}) or "Resolving filename..."
        self.lbl_filename.setText(initial_fn)
        self.lbl_size.setText("Calculating size...")
        self.lbl_size.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.lbl_category.setText("Probing server...")
        self.lbl_destination.setText("📁 ~/Downloads")
        self.lbl_icon.setPixmap(get_monochrome_icon("download", size=22).pixmap(22, 22))

    def set_resolved(self, filename: str, size_str: str, category: str, save_path: str, icon_name: str = "all_downloads"):
        """Displays fully resolved pre-flight file metadata."""
        self.lbl_filename.setText(filename or "Unknown File")
        self.lbl_size.setText(size_str or "Size Unknown")
        self.lbl_size.setStyleSheet("color: #10b981; font-weight: bold;")
        self.lbl_category.setText(category or "General")

        # Compact destination path display with ~ for home
        home = os.path.expanduser("~")
        dest_display = save_path
        if save_path.startswith(home):
            dest_display = "~" + save_path[len(home):]
        self.lbl_destination.setText(f"📁 {dest_display}")

        self.lbl_icon.setPixmap(get_monochrome_icon(icon_name, size=22).pixmap(22, 22))

    def set_error(self, err_msg: str, fallback_fn: str):
        """Displays non-blocking pre-flight error warning."""
        self.lbl_filename.setText(fallback_fn or "Target File")
        self.lbl_size.setText("Size Unknown")
        self.lbl_size.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.lbl_category.setText(err_msg or "Server error")
        self.lbl_icon.setPixmap(get_monochrome_icon("unfinished", size=22).pixmap(22, 22))

    def reset_clean(self):
        """Resets inspector to clean idle state."""
        self.lbl_filename.setText("Enter or paste download address")
        self.lbl_size.setText("0 B")
        self.lbl_size.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.lbl_category.setText("Awaiting URL")
        self.lbl_destination.setText("📁 ~/Downloads")
        self.lbl_icon.setPixmap(get_monochrome_icon("all_downloads", size=22).pixmap(22, 22))


class AddUrlLineEdit(QLineEdit):
    """
    Custom QLineEdit for Add URL dialog ensuring cursor resets to start (index 0)
    and deselects text whenever content is pasted.
    """
    def paste(self):
        super().paste()
        self.setCursorPosition(0)
        self.deselect()
        QTimer.singleShot(0, lambda: (self.setCursorPosition(0), self.deselect()))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            super().keyPressEvent(event)
            self.setCursorPosition(0)
            self.deselect()
            QTimer.singleShot(0, lambda: (self.setCursorPosition(0), self.deselect()))
            return
        super().keyPressEvent(event)


class AddUrlDialog(QDialog):
    """
    Modern Essential Streamline Add URL Dialog.
    Features:
    - Clean hero URL input bar with clipboard paste
    - Micro-Inspector card with real-time pre-flight metadata (filename, size, folder, icon)
    - Lightweight background HTTP HEAD auto-prefetch with 250ms debouncer
    - Smart detection badges for media streams & batch downloads
    - Pure pre-flight responsibility (never downloads in this dialog)
    """
    def __init__(self, parent=None, paste_clipboard=False):
        super().__init__(parent)
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Enter new address to download")
        self.setWindowIcon(QApplication.windowIcon())
        
        self.setMinimumWidth(720)
        self.resize(720, 190)

        self._active_fetcher = None
        self._prefetched_info = None

        # Category configuration
        self.cat_config = load_category_config()
        self.default_downloads = get_user_downloads_dir()

        self.ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz", ".7z"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"],
            "Programs": [".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"]
        }

        # 150ms Debouncer for pre-flight probing
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(150)
        self._debounce_timer.timeout.connect(self._start_background_prefetch)

        # Layout Setup
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # 1. Address Label
        lbl_addr = QLabel("Address:")
        font_lbl = QFont(lbl_addr.font())
        font_lbl.setBold(True)
        lbl_addr.setFont(font_lbl)
        layout.addWidget(lbl_addr)

        # 2. Hero URL Input Bar
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.url_input = AddUrlLineEdit()
        self.url_input.setPlaceholderText("https://")
        self.url_input.setFixedHeight(32)
        self.url_input.setToolTip("Enter or paste the download URL address (HTTP, HTTPS, FTP, or Magnet link)")
        input_layout.addWidget(self.url_input)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setIcon(get_add_url_button_icon("documents", size=16))
        self._paste_filter = AddUrlButtonPressFilter("documents", size=16, parent=self)
        self.btn_paste.installEventFilter(self._paste_filter)
        self.btn_paste.setFixedWidth(84)
        self.btn_paste.setFixedHeight(32)
        self.btn_paste.setToolTip("Paste link from clipboard")
        self.btn_paste.clicked.connect(self.paste_url)
        input_layout.addWidget(self.btn_paste)

        layout.addLayout(input_layout)

        # 3. Micro-Inspector Card
        self.micro_inspector = MicroInspectorCard(self)
        layout.addWidget(self.micro_inspector)

        # 4. Mode flags
        self.is_media_mode = False
        self.is_batch_mode = False
        self.is_batch_list_mode = False
        self.batch_urls = []

        # 5. Bottom Action Row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        # Detection Status Labels & Action Buttons
        self.lbl_media_status = QLabel("Media Stream detected (go to Media Downloader)")
        self.lbl_media_status.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 11px;")
        self.lbl_media_status.hide()

        self.btn_send_media = QPushButton("Download Media")
        self.btn_send_media.setFixedHeight(30)
        self.btn_send_media.setIcon(get_add_url_button_icon("media_downloader", size=16))
        self._media_filter = AddUrlButtonPressFilter("media_downloader", size=16, parent=self)
        self.btn_send_media.installEventFilter(self._media_filter)
        self.btn_send_media.clicked.connect(self._on_send_media_clicked)
        self.btn_send_media.hide()

        self.lbl_batch_status = QLabel("Batch pattern detected (go to Batch Downloader)")
        self.lbl_batch_status.setStyleSheet("color: #3498db; font-weight: bold; font-size: 11px;")
        self.lbl_batch_status.hide()

        self.btn_send_batch = QPushButton("Batch Download")
        self.btn_send_batch.setFixedHeight(30)
        self.btn_send_batch.setIcon(get_add_url_button_icon("add_url", size=16))
        self._batch_filter = AddUrlButtonPressFilter("add_url", size=16, parent=self)
        self.btn_send_batch.installEventFilter(self._batch_filter)
        self.btn_send_batch.clicked.connect(self._on_send_batch_clicked)
        self.btn_send_batch.hide()

        btn_layout.addWidget(self.btn_send_media)
        btn_layout.addWidget(self.lbl_media_status)
        btn_layout.addWidget(self.btn_send_batch)
        btn_layout.addWidget(self.lbl_batch_status)
        btn_layout.addStretch()

        self.btn_download = QPushButton("Add URL")
        self.btn_download.setDefault(True)
        self.btn_download.setFixedWidth(90)
        self.btn_download.setFixedHeight(30)
        self.btn_download.setToolTip("Add download URL")
        self.btn_download.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip("Cancel and close dialog")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Hook text changes
        self.url_input.textChanged.connect(self._on_url_text_changed)

        # Paste from clipboard only if explicitly requested (e.g. from 'Paste URL' action)
        if paste_clipboard:
            clipboard_text = QApplication.clipboard().text().strip()
            if clipboard_text:
                self.url_input.setText(clipboard_text)
                self.url_input.setCursorPosition(0)
                self.url_input.deselect()
                QTimer.singleShot(0, lambda: (self.url_input.setCursorPosition(0), self.url_input.deselect()))
                if clipboard_text.startswith(("http://", "https://", "ftp://")) and not "*" in clipboard_text and len(clipboard_text.split("\n")) == 1:
                    self._start_background_prefetch()

        self._check_url_type()

    def _on_url_text_changed(self):
        """Triggered on every keystroke in URL box."""
        # Cancel any previous active prefetch
        self._cancel_active_prefetch()
        self._check_url_type()

        url = self.get_url()
        if not url:
            self.micro_inspector.reset_clean()
            return

        # Start debounce timer for probing
        if url.startswith(("http://", "https://", "ftp://")) and not "*" in url and len(url.split("\n")) == 1:
            self.micro_inspector.set_probing(url)
            self._debounce_timer.start()
        elif url.startswith("magnet:"):
            # Instant magnet handling
            self.micro_inspector.set_resolved("BitTorrent Magnet Link", "Torrent Swarm", "Torrent / P2P", self.default_downloads, "all_downloads")
        else:
            # Batch / wildcard / custom
            self._update_inspector_heuristic(url)

    def _start_background_prefetch(self):
        """Initiates lightweight HTTP pre-flight probing in background."""
        url = self.get_url()
        if not url or not url.startswith(("http://", "https://", "ftp://")):
            return

        # Cancel any existing worker
        self._cancel_active_prefetch()

        self._active_fetcher = FileInfoFetcherWorker(url)
        self._active_fetcher.finished_signal.connect(self._on_prefetch_complete)
        self._active_fetcher.start()

    def _on_prefetch_complete(self, result: dict):
        """Callback when pre-flight background probing returns."""
        if not result:
            return

        current_url = self.get_url()
        if result.get("original_url") != current_url and result.get("url") != current_url:
            return

        self._prefetched_info = result
        error = result.get("error")
        filename = result.get("filename") or resolve_filename(result.get("url", ""), {})
        size_str = result.get("size_str") or "Unknown"

        category, icon_name, save_path = self._detect_category_and_path(filename, result.get("content_type"))

        if error:
            self.micro_inspector.set_error(error, filename)
        else:
            self.micro_inspector.set_resolved(filename, size_str, category, save_path, icon_name)

    def _update_inspector_heuristic(self, url: str):
        """Updates inspector with local heuristics when offline or batch."""
        lines = [line.strip() for line in url.split("\n") if line.strip()]
        if len(lines) > 1:
            self.micro_inspector.set_resolved(f"{len(lines)} Batch Download Links", f"{len(lines)} URLs", "Batch Queue", self.default_downloads, "all_downloads")
        elif "*" in url:
            self.micro_inspector.set_resolved("Wildcard Download Pattern", "Sequential Batch", "Batch Sequence", self.default_downloads, "all_downloads")
        elif is_media_downloader_url(url):
            self.micro_inspector.set_resolved("Media Stream Link", "Stream Format", "Video / Audio", os.path.join(self.default_downloads, "Video"), "video")
        else:
            fn = resolve_filename(url, {})
            cat, icon, path = self._detect_category_and_path(fn)
            self.micro_inspector.set_resolved(fn, "Size Awaiting", cat, path, icon)

    def _detect_category_and_path(self, filename: str, content_type: str = None) -> tuple:
        """Determines category, icon, and target directory based on filename & MIME type."""
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        detected_category = "General"

        for cat, ext_list in self.ext_map.items():
            if ext in ext_list:
                detected_category = cat
                break

        # Fallback to content-type if extension was missing
        if detected_category == "General" and content_type:
            if "video" in content_type:
                detected_category = "Video"
            elif "audio" in content_type:
                detected_category = "Music"
            elif "pdf" in content_type or "document" in content_type or "text" in content_type:
                detected_category = "Documents"
            elif "zip" in content_type or "compressed" in content_type or "tar" in content_type or "gzip" in content_type:
                detected_category = "Compressed"

        icon_map = {
            "Compressed": "compressed",
            "Documents": "documents",
            "Music": "music",
            "Programs": "programs",
            "Video": "video",
            "General": "all_downloads"
        }
        icon_name = icon_map.get(detected_category, "all_downloads")

        cat_cfg = self.cat_config.get(detected_category, DEFAULT_CATEGORIES.get(detected_category, {}))
        save_path = cat_cfg.get("path") if isinstance(cat_cfg, dict) else self.default_downloads
        if not save_path:
            save_path = self.default_downloads

        return detected_category, icon_name, save_path

    def _cancel_active_prefetch(self):
        """Safely stops any ongoing background prefetch thread."""
        if self._active_fetcher:
            try:
                self._active_fetcher.cancel()
                if self._active_fetcher.isRunning():
                    self._active_fetcher.quit()
                    self._active_fetcher.wait(50)
            except Exception:
                pass
            self._active_fetcher = None

    def _check_url_type(self):
        """Checks URL type for media streams, wildcards, and batch link lists."""
        url = self.get_url()
        lines = [line.strip() for line in url.split("\n") if line.strip().startswith(("http://", "https://", "ftp://", "magnet:"))]
        
        if len(lines) > 1:
            self.batch_urls = lines
            self.lbl_batch_status.setText(f"{len(lines)} URLs detected (open in Batch Review)")
            self.lbl_batch_status.show()
            self.btn_send_batch.setText("Review Batch")
            self.btn_send_batch.show()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()
        elif "*" in url and url.startswith(("http://", "https://", "ftp://")):
            self.lbl_batch_status.setText("Wildcard pattern detected (open in Batch Downloader)")
            self.lbl_batch_status.show()
            self.btn_send_batch.setText("Batch Download")
            self.btn_send_batch.show()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()
        elif is_media_downloader_url(url):
            self.lbl_batch_status.hide()
            self.btn_send_batch.hide()
            self.lbl_media_status.show()
            self.btn_send_media.show()
        else:
            self.lbl_batch_status.hide()
            self.btn_send_batch.hide()
            self.lbl_media_status.hide()
            self.btn_send_media.hide()

    def _on_send_media_clicked(self):
        self.is_media_mode = True
        self.accept()

    def _on_send_batch_clicked(self):
        url = self.get_url()
        lines = [line.strip() for line in url.split("\n") if line.strip().startswith(("http://", "https://", "ftp://", "magnet:"))]
        if len(lines) > 1:
            self.is_batch_list_mode = True
            self.batch_urls = lines
        else:
            self.is_batch_mode = True
        self.accept()

    def paste_url(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        self.url_input.setText(text)
        self.url_input.setCursorPosition(0)
        self.url_input.deselect()
        QTimer.singleShot(0, lambda: (self.url_input.setCursorPosition(0), self.url_input.deselect()))
        if text.startswith(("http://", "https://", "ftp://")) and not "*" in text and len(text.split("\n")) == 1:
            self._start_background_prefetch()

    def get_url(self):
        return self.url_input.text().strip()

    def get_prefetched_info(self) -> dict:
        """Returns pre-flight metadata if available."""
        return self._prefetched_info

    def showEvent(self, event):
        """Ensures cursor is at the beginning of the text when shown."""
        super().showEvent(event)
        if self.url_input.text():
            self.url_input.setCursorPosition(0)
            self.url_input.deselect()
            QTimer.singleShot(0, lambda: (self.url_input.setCursorPosition(0), self.url_input.deselect()))

    def reject(self):
        """Gracefully aborts background worker when dialog is cancelled or Esc is pressed."""
        self._cancel_active_prefetch()
        super().reject()

    def closeEvent(self, event):
        """Gracefully aborts background worker when dialog is closed."""
        self._cancel_active_prefetch()
        super().closeEvent(event)
