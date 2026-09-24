import os
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QApplication, QCheckBox, QFrame,
    QFileIconProvider, QSizePolicy
)
from PyQt6.QtGui import (
    QDesktopServices, QFont, QDrag, QPixmap, QPainter, QColor,
    QIcon, QPainterPath
)
from PyQt6.QtCore import Qt, QUrl, QPoint, QMimeData, QFileInfo
from core.utils import show_in_folder, open_with, open_file_generic
from core.memory_guard import MemoryGuard


class FileDragButton(QPushButton):
    """
    Draggable button allowing users to click and drag the completed download file
    directly to any destination (file manager, desktop, browser, chat app, etc.)
    using standard freedesktop / XDG URI list specifications.
    """
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._drag_start_pos = None
        self.setText("  Drag File")
        self.setToolTip("Click and drag this file directly to any folder, desktop, file manager, or application")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedHeight(30)

        # Resolve file icon
        icon = None
        if file_path and os.path.exists(file_path):
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(file_path))
        if not icon or icon.isNull():
            icon = QIcon.fromTheme("document-save", QIcon.fromTheme("text-x-generic"))
        if icon and not icon.isNull():
            self.setIcon(icon)

        self.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border: 1px dashed palette(highlight);
                border-radius: 6px;
                background-color: palette(base);
                color: palette(highlight);
            }
            QPushButton:hover {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border-style: solid;
            }
            QPushButton:pressed {
                background-color: palette(mid);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._drag_start_pos:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        if not self.file_path or not os.path.exists(self.file_path):
            return

        abs_path = os.path.abspath(os.path.expanduser(self.file_path))

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(abs_path)])
        mime_data.setText(abs_path)
        drag.setMimeData(mime_data)

        # Render clean drag badge preview
        filename = os.path.basename(abs_path)
        pixmap_w = min(320, max(160, len(filename) * 8 + 40))
        pixmap = QPixmap(pixmap_w, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background pill badge
        painter.setBrush(QColor(46, 194, 126, 230))
        painter.setPen(QColor(39, 174, 96))
        painter.drawRoundedRect(pixmap.rect().adjusted(1, 1, -1, -1), 6, 6)

        if self.icon() and not self.icon().isNull():
            self.icon().paint(painter, 6, 6, 20, 20)

        painter.setPen(QColor("#ffffff"))
        f = painter.font()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(pixmap.rect().adjusted(30, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, filename)
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_pos = None


class DownloadCompleteDialog(QDialog):
    def __init__(self, file_data, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window or (parent if hasattr(parent, "settings") else None)
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Download Completed")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(540)
        
        # Ensure it behaves like a separate top-level window in the OS taskbar while sharing WM_CLASS
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window)
        
        self.file_data = file_data
        file_path = file_data.get('path', '')
        filename = os.path.basename(file_path) if file_path else "file"
        save_folder = os.path.dirname(file_path) if file_path else ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header Banner: Checkmark + "Download Completed" in green
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        lbl_check_badge = QLabel("✔")
        lbl_check_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_check_badge.setFixedSize(28, 28)
        lbl_check_badge.setStyleSheet("""
            QLabel {
                background-color: #2ec27e;
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                border-radius: 14px;
            }
        """)
        header_layout.addWidget(lbl_check_badge)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(1)

        lbl_title = QLabel("Download Completed")
        font_title = QFont()
        font_title.setPointSize(12)
        font_title.setBold(True)
        lbl_title.setFont(font_title)
        lbl_title.setStyleSheet("color: #2ec27e; font-weight: bold;")
        header_text_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel("Your file has been downloaded successfully and is ready to use.")
        lbl_subtitle.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        header_text_layout.addWidget(lbl_subtitle)

        header_layout.addLayout(header_text_layout, stretch=1)
        layout.addLayout(header_layout)

        # 2. File Information Card
        card_frame = QFrame()
        card_frame.setFrameShape(QFrame.Shape.StyledPanel)
        card_frame.setStyleSheet("""
            QFrame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        # File Name + Drag Button Row
        name_drag_row = QHBoxLayout()
        name_drag_row.setSpacing(8)

        file_icon_label = QLabel()
        file_icon_label.setFixedSize(20, 20)
        provider = QFileIconProvider()
        f_icon = provider.icon(QFileInfo(file_path)) if file_path and os.path.exists(file_path) else QIcon.fromTheme("document-save")
        if f_icon and not f_icon.isNull():
            file_icon_label.setPixmap(f_icon.pixmap(20, 20))
        name_drag_row.addWidget(file_icon_label)

        self.lbl_filename = QLabel(filename)
        font_fn = QFont()
        font_fn.setPointSize(10)
        font_fn.setBold(True)
        self.lbl_filename.setFont(font_fn)
        self.lbl_filename.setToolTip(file_path)
        name_drag_row.addWidget(self.lbl_filename, stretch=1)

        # Drag handle button
        self.btn_drag = FileDragButton(file_path)
        name_drag_row.addWidget(self.btn_drag)
        card_layout.addLayout(name_drag_row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("border-top: 1px solid palette(mid); background: transparent;")
        card_layout.addWidget(line)

        # Details Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        # Saved as / Location
        self.path_input = QLineEdit(file_path)
        self.path_input.setReadOnly(True)
        self.path_input.setCursorPosition(0)
        self.path_input.setToolTip(file_path)
        self.path_input.setStyleSheet("background: transparent; border: none; color: palette(text); font-size: 11px;")
        form.addRow("Saved to:", self.path_input)

        # Size
        self.lbl_size = QLabel(file_data.get('size', 'Unknown'))
        font_size = QFont(self.lbl_size.font())
        font_size.setBold(True)
        font_size.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.lbl_size.setFont(font_size)
        self.lbl_size.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.lbl_size.setToolTip(f"Downloaded file size: {file_data.get('size', 'Unknown')}")
        form.addRow("Size:", self.lbl_size)

        # Address / URL
        self.url_input = QLineEdit(file_data.get('url', ''))
        self.url_input.setReadOnly(True)
        self.url_input.setCursorPosition(0)
        self.url_input.setToolTip(file_data.get('url', ''))
        self.url_input.setStyleSheet("background: transparent; border: none; color: palette(placeholder-text); font-size: 11px;")
        form.addRow("Source URL:", self.url_input)

        card_layout.addLayout(form)
        layout.addWidget(card_frame)

        # 3. Checkbox ("Don't show this dialog again")
        self.chk_dont_show = QCheckBox("Don't show this dialog again")
        self.chk_dont_show.setToolTip("Disable completion dialog popup for future downloads")
        self.chk_dont_show.setStyleSheet("font-size: 11px;")
        self.chk_dont_show.toggled.connect(self._on_dont_show_toggled)
        layout.addWidget(self.chk_dont_show)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        self.btn_open = QPushButton("Open")
        self.btn_open.setDefault(True)
        self.btn_open.setToolTip("Open downloaded file with default application")

        self.btn_open_with = QPushButton("Open with...")
        self.btn_open_with.setToolTip("Choose application to open this file")

        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setToolTip("Show file in its containing folder")

        self.btn_close = QPushButton("Close")
        self.btn_close.setToolTip("Close completion dialog")

        for btn in [self.btn_open, self.btn_open_with, self.btn_open_folder, self.btn_close]:
            btn.setFixedHeight(30)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

        # Connect signals
        self.btn_open.clicked.connect(self.on_open)
        self.btn_open_with.clicked.connect(self.on_open_with)
        self.btn_open_folder.clicked.connect(self.on_open_folder)
        self.btn_close.clicked.connect(self.accept)

        self.adjustSize()

    def _on_dont_show_toggled(self, checked: bool):
        target = self.main_window or self.parent()
        if target and hasattr(target, "settings") and isinstance(target.settings, dict):
            target.settings["show_complete_dialog"] = not checked
            if hasattr(target, "save_settings") and callable(target.save_settings):
                target.save_settings()

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
