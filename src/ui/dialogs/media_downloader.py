"""
Media Downloader Dialog for Bengal Download Manager.
Provides link input, media link parsing, dependency status bar (yt-dlp, ffmpeg, ffprobe, deno, AtomicParsley),
thumbnail preview, quality chooser, codec filters, format table sorting, cookie authentication vault, and playlist batch selection.
"""

import os
import sys
import re
import urllib.request
import ssl
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QApplication, QFrame, QCheckBox,
    QAbstractItemView, QToolButton, QToolTip, QFileDialog, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer, QPoint, QUrl
from PyQt6.QtGui import (
    QFont, QIcon, QKeySequence, QShortcut, QPixmap, QImage, QPainter,
    QPainterPath, QColor, QPen, QLinearGradient, QPalette, QBrush
)
import logging
from core.media_downloader import (
    YtDlpManager, MediaExtractorWorker, DependencyManagerWorker, _keep_thread_alive,
    BIN_DIR, DEPENDENCY_TOOLS
)
from core.memory_guard import MemoryGuard
from core.utils import is_debug_mode
from ui.delegates import CheckableTableItemDelegate

logger = logging.getLogger("bengal.dialog.media_downloader")


def make_rounded_thumbnail(pixmap: QPixmap, width: int = 160, height: int = 90, radius: int = 8) -> QPixmap:
    """Scales pixmap to aspect fill and crops into rounded rectangle with subtle contrast border."""
    if pixmap.isNull() or width <= 0 or height <= 0:
        return pixmap
    scaled = pixmap.scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation
    )
    x_off = max(0, (scaled.width() - width) // 2)
    y_off = max(0, (scaled.height() - height) // 2)
    cropped = scaled.copy(x_off, y_off, width, height)

    out = QPixmap(width, height)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, width, height, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.setClipping(False)

    pen = QPen(QColor(128, 128, 128, 70), 1.0)
    painter.setPen(pen)
    painter.drawRoundedRect(0, 0, width - 1, height - 1, radius, radius)
    painter.end()
    return out


def create_thumbnail_placeholder(width: int = 160, height: int = 90, radius: int = 8, is_playlist: bool = False) -> QPixmap:
    """Generates a sleek placeholder for media thumbnail before loading."""
    out = QPixmap(width, height)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, width, height, radius, radius)
    painter.fillPath(path, QColor(32, 34, 38, 220))
    painter.setPen(QPen(QColor(128, 128, 128, 60), 1.0))
    painter.drawPath(path)

    cx, cy = width // 2, height // 2
    if is_playlist:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 180))
        painter.drawRoundedRect(cx - 18, cy - 12, 36, 4, 2, 2)
        painter.drawRoundedRect(cx - 18, cy - 4, 36, 4, 2, 2)
        painter.drawRoundedRect(cx - 18, cy + 4, 36, 4, 2, 2)
    else:
        triangle = QPainterPath()
        triangle.moveTo(cx - 10, cy - 14)
        triangle.lineTo(cx + 14, cy)
        triangle.lineTo(cx - 10, cy + 14)
        triangle.closeSubpath()
        painter.fillPath(triangle, QColor(255, 255, 255, 190))
    painter.end()
    return out


class ThumbnailLoaderWorker(QThread):
    """Background worker to fetch thumbnail image bytes without freezing Qt GUI."""
    thumbnail_loaded = pyqtSignal(object)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        _keep_thread_alive(self)

    def run(self):
        if not self.url or self.isInterruptionRequested():
            return
        data = None
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0)"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if self.isInterruptionRequested():
                        return
                    data = resp.read()
            except Exception:
                if self.isInterruptionRequested():
                    return
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                    if self.isInterruptionRequested():
                        return
                    data = resp.read()

            if data and not self.isInterruptionRequested():
                img = QImage()
                if img.loadFromData(data) and not img.isNull():
                    self.thumbnail_loaded.emit(img)
        except Exception:
            pass


class AndroidProgressBar(QProgressBar):
    """
    Android 17 / Material 3 Expressive Linear Progress Indicator:
    - Ultra-sleek pill geometry (5px height) with subtle ambient track.
    - Dual organic flowing capsules with vibrant Cyan-to-Neon-Violet gradient.
    - Automatic 60fps frame-paced animation when visible, zero CPU when hidden.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(5)
        self.setTextVisible(False)
        self._anim_pos = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_tick)

    def showEvent(self, event):
        super().showEvent(event)
        if self.minimum() == 0 and self.maximum() == 0:
            self._anim_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._anim_timer.stop()

    def setRange(self, minimum: int, maximum: int):
        super().setRange(minimum, maximum)
        if minimum == 0 and maximum == 0 and self.isVisible():
            self._anim_timer.start()
        else:
            self._anim_timer.stop()
            self.update()

    def _on_tick(self):
        if not self.isVisible():
            self._anim_timer.stop()
            return
        self._anim_pos = (self._anim_pos + 0.015) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0

        # Track background
        track_path = QPainterPath()
        track_path.addRoundedRect(0, 0, w, h, radius, radius)
        
        is_dark = self.palette().color(QPalette.ColorRole.Window).value() < 128
        track_color = QColor(255, 255, 255, 25) if is_dark else QColor(0, 0, 0, 20)
        painter.fillPath(track_path, track_color)

        if self.minimum() == 0 and self.maximum() == 0:
            p = self._anim_pos
            x1 = w * (p * 1.4 - 0.4)
            width1 = max(w * 0.35 * (1.0 - 0.4 * abs(p - 0.5)), 40.0)
            
            p2 = (p + 0.4) % 1.0
            x2 = w * (p2 * 1.4 - 0.4)
            width2 = max(w * 0.18, 20.0)

            grad1 = QLinearGradient(x1, 0, x1 + width1, 0)
            if is_dark:
                grad1.setColorAt(0.0, QColor("#38bdf8"))
                grad1.setColorAt(0.5, QColor("#6366f1"))
                grad1.setColorAt(1.0, QColor("#a855f7"))
            else:
                grad1.setColorAt(0.0, QColor("#0284c7"))
                grad1.setColorAt(0.5, QColor("#4f46e5"))
                grad1.setColorAt(1.0, QColor("#7c3aed"))

            painter.save()
            painter.setClipPath(track_path)

            sec_path = QPainterPath()
            sec_path.addRoundedRect(x2, 0, width2, h, radius, radius)
            sec_color = QColor("#38bdf8" if is_dark else "#0284c7")
            sec_color.setAlpha(140)
            painter.fillPath(sec_path, sec_color)

            prim_path = QPainterPath()
            prim_path.addRoundedRect(x1, 0, width1, h, radius, radius)
            painter.fillPath(prim_path, grad1)

            painter.restore()
        else:
            total = max(1, self.maximum() - self.minimum())
            val = max(0, min(self.value() - self.minimum(), total))
            fill_w = w * (val / total)
            if fill_w > 0:
                fill_path = QPainterPath()
                fill_path.addRoundedRect(0, 0, max(fill_w, radius * 2), h, radius, radius)
                grad = QLinearGradient(0, 0, fill_w, 0)
                grad.setColorAt(0.0, QColor("#38bdf8" if is_dark else "#0284c7"))
                grad.setColorAt(1.0, QColor("#6366f1" if is_dark else "#4f46e5"))
                painter.fillPath(fill_path, grad)

        painter.end()


class ThreeDotsButton(QPushButton):
    """Modern 3-dot options button with integrated status dot for engine pipeline."""
    def __init__(self, parent=None):
        super().__init__("⋮", parent)
        self.setFixedSize(36, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Pipeline Engines & Settings")
        self._status = None  # None (no dot), "yellow" (update/updating), "orange" (missing/attention)
        self.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                border: 1px solid palette(mid);
                border-radius: 6px;
                background-color: palette(button);
                color: palette(button-text);
            }
            QPushButton:hover {
                background-color: palette(alternate-base);
                border-color: palette(highlight);
            }
        """)

    def set_status(self, status: str | None):
        if self._status != status:
            self._status = status
            if status == "yellow":
                self.setToolTip("Pipeline Engines & Settings (Update Available)")
            elif status in ("orange", "red", "gray", "missing"):
                self.setToolTip("Pipeline Engines & Settings (Engines Missing / Attention Needed)")
            else:
                self.setToolTip("Pipeline Engines & Settings")
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Suppress dot when operational or no status
        if not self._status or self._status in ("none", "green", "normal"):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._status == "yellow":
            dot_color = QColor("#e5a50a")
        elif self._status in ("orange", "red", "gray", "missing"):
            dot_color = QColor("#e67e22")
        else:
            dot_color = QColor("#e67e22")
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.width() - 9, 5, 6, 6)
        painter.end()


class EngineRowWidget(QFrame):
    """Individual engine item widget with role, version badge, refresh button, and inline progress bar."""
    def __init__(self, tool_name: str, on_update_clicked, parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self.on_update_clicked = on_update_clicked
        self.tool_info = DEPENDENCY_TOOLS.get(tool_name, {})
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 6, 10, 6)
        vbox.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Icon / Avatar
        icon_str = self.tool_info.get("icon", "⚙️")
        lbl_icon = QLabel(icon_str)
        lbl_icon.setFixedWidth(20)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(lbl_icon)

        # Name + Role
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(0)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.lbl_name = QLabel(self.tool_name)
        font_name = QFont()
        font_name.setBold(True)
        font_name.setPointSize(10)
        self.lbl_name.setFont(font_name)
        name_row.addWidget(self.lbl_name)

        self.lbl_dot = QLabel("●")
        self.lbl_dot.setStyleSheet("color: #888888; font-size: 8px;")
        name_row.addWidget(self.lbl_dot)
        name_row.addStretch()
        info_vbox.addLayout(name_row)

        self.lbl_role = QLabel(self.tool_info.get("role", ""))
        self.lbl_role.setStyleSheet("color: palette(placeholder-text); font-size: 10.5px;")
        self.lbl_role.setToolTip(self.tool_info.get("desc", "") or self.tool_info.get("role", ""))
        info_vbox.addWidget(self.lbl_role)
        top_row.addLayout(info_vbox, stretch=1)

        # Version Pill Badge (initialized synchronously from local cache)
        self.lbl_version = QLabel("Installed")
        font_ver = QFont()
        font_ver.setPointSize(9)
        self.lbl_version.setFont(font_ver)
        from core.media_downloader import get_local_tool_path
        if get_local_tool_path(self.tool_name):
            self.lbl_dot.setStyleSheet("color: #2ec27e; font-size: 8px;")
            self.lbl_version.setText("Installed")
            self.lbl_version.setStyleSheet("""
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 2px 6px;
                color: #2ec27e;
                font-weight: bold;
            """)
        else:
            self.lbl_dot.setStyleSheet("color: #e67e22; font-size: 8px;")
            self.lbl_version.setText("Not Installed")
            self.lbl_version.setStyleSheet("""
                background-color: palette(base);
                border: 1px solid #e67e22;
                border-radius: 4px;
                padding: 2px 6px;
                color: #e67e22;
            """)
        top_row.addWidget(self.lbl_version)

        # Refresh / Update Button
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("↻")
        self.btn_refresh.setFixedSize(24, 24)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setToolTip(f"Check / Update {self.tool_name}")
        self.btn_refresh.setStyleSheet("""
            QToolButton {
                border-radius: 4px;
                border: 1px solid palette(mid);
                background-color: palette(button);
                color: palette(button-text);
                font-size: 12px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        self.btn_refresh.clicked.connect(lambda: self.on_update_clicked(self.tool_name))
        top_row.addWidget(self.btn_refresh)

        vbox.addLayout(top_row)

        # Micro progress bar (hidden by default)
        self.progress_bar = AndroidProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        vbox.addWidget(self.progress_bar)

        self.lbl_progress_meta = QLabel()
        self.lbl_progress_meta.setStyleSheet("font-size: 10px; color: #e5a50a;")
        self.lbl_progress_meta.setVisible(False)
        vbox.addWidget(self.lbl_progress_meta)

    def set_status(self, display_text: str, status_color: str):
        ver_text = display_text
        if display_text.startswith(f"{self.tool_name} (") and display_text.endswith(")"):
            ver_text = display_text[len(self.tool_name) + 2 : -1]

        if status_color == "yellow":
            self.lbl_dot.setStyleSheet("color: #e5a50a; font-size: 8px;")
            if "Update Available" in ver_text or "Update Available" in display_text:
                self.lbl_version.setText("Update Available")
                self.lbl_version.setStyleSheet("background-color: palette(base); border: 1px solid #e5a50a; border-radius: 4px; padding: 2px 6px; color: #e5a50a; font-weight: bold;")
                self.lbl_version.setToolTip(ver_text)
                self.btn_refresh.setEnabled(True)
                self.progress_bar.setVisible(False)
                self.lbl_progress_meta.setVisible(False)
            else:
                self.lbl_version.setText("Updating...")
                self.lbl_version.setStyleSheet("background-color: palette(base); border: 1px solid #e5a50a; border-radius: 4px; padding: 2px 6px; color: #e5a50a; font-weight: bold;")
                self.btn_refresh.setEnabled(False)
                self.progress_bar.setVisible(True)
                self.lbl_progress_meta.setVisible(True)
                self.lbl_progress_meta.setText(ver_text)
                if "MB" in ver_text:
                    m = re.search(r"([\d.]+)\s*MB\s*/\s*([\d.]+)\s*MB", ver_text)
                    if m:
                        dl = float(m.group(1))
                        tot = float(m.group(2))
                        pct = int((dl / tot) * 100) if tot > 0 else 0
                        self.progress_bar.setRange(0, 100)
                        self.progress_bar.setValue(pct)
                    else:
                        self.progress_bar.setRange(0, 0)
                else:
                    self.progress_bar.setRange(0, 0)
        elif status_color == "green":
            self.lbl_dot.setStyleSheet("color: #2ec27e; font-size: 8px;")
            self.lbl_version.setText(ver_text)
            self.lbl_version.setStyleSheet("background-color: palette(base); border: 1px solid palette(mid); border-radius: 4px; padding: 2px 6px; color: #2ec27e; font-weight: bold;")
            self.lbl_version.setToolTip("")
            self.btn_refresh.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_progress_meta.setVisible(False)
        else:
            self.lbl_dot.setStyleSheet("color: #e67e22; font-size: 8px;")
            self.lbl_version.setText(ver_text if ver_text not in ("orange", "red", "gray") else "Not Installed")
            self.lbl_version.setStyleSheet("background-color: palette(base); border: 1px solid #e67e22; border-radius: 4px; padding: 2px 6px; color: #e67e22;")
            self.btn_refresh.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_progress_meta.setVisible(False)


class MediaDownloaderOptionsHub(QFrame):
    """
    Modern popover control center for runtime engines and media pipeline options.
    """
    def __init__(self, dialog, parent=None):
        super().__init__(dialog, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.dialog = dialog
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("optionsHubRoot")
        self.setFixedWidth(480)
        self.setStyleSheet("""
            QFrame#optionsHubRoot {
                background-color: transparent;
                border: none;
            }
            QFrame#optionsHubCard {
                background-color: palette(window);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("optionsHubCard")

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.card.setGraphicsEffect(shadow)

        root_layout.addWidget(self.card)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        lbl_title_icon = QLabel("⚡")
        lbl_title_icon.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(lbl_title_icon)

        lbl_title = QLabel("Pipeline Engines")
        font_t = QFont()
        font_t.setBold(True)
        font_t.setPointSize(11)
        lbl_title.setFont(font_t)
        header_layout.addWidget(lbl_title)

        self.lbl_summary_badge = QLabel("● Checking...")
        self.lbl_summary_badge.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: #2ec27e;
            background-color: palette(alternate-base);
            border: 1px solid palette(mid);
            border-radius: 10px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.lbl_summary_badge)
        header_layout.addStretch()

        self.btn_update_all = QPushButton("Update All")
        self.btn_update_all.setFixedHeight(28)
        self.btn_update_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_all.setStyleSheet("""
            QPushButton {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                font-size: 11px;
                font-weight: bold;
                border-radius: 4px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: palette(highlight);
                opacity: 0.9;
            }
        """)
        self.btn_update_all.clicked.connect(self.dialog.update_all_dependencies)
        header_layout.addWidget(self.btn_update_all)
        layout.addLayout(header_layout)

        self.engine_rows = {}
        for tool in ["yt-dlp", "ffmpeg", "ffprobe", "deno", "AtomicParsley"]:
            row_widget = EngineRowWidget(tool, on_update_clicked=self.dialog.update_single_dependency, parent=self)
            self.engine_rows[tool] = row_widget
            layout.addWidget(row_widget)

        self._refresh_summary()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("border: none; background-color: palette(mid); max-height: 1px;")
        layout.addWidget(sep)

        footer_layout = QHBoxLayout()
        btn_open_folder = QPushButton("📁 Open Binaries Folder")
        btn_open_folder.setFlat(True)
        btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_folder.setStyleSheet("font-size: 11px; color: palette(highlight); text-align: left; padding: 2px;")
        btn_open_folder.clicked.connect(self._open_bin_folder)
        footer_layout.addWidget(btn_open_folder)

        footer_layout.addStretch()

        btn_options = QPushButton("⚙️ Media Options...")
        btn_options.setFlat(True)
        btn_options.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_options.setStyleSheet("font-size: 11px; color: palette(highlight); text-align: right; padding: 2px;")
        btn_options.clicked.connect(self._open_options_dialog)
        footer_layout.addWidget(btn_options)

        layout.addLayout(footer_layout)

    def _open_bin_folder(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BIN_DIR)))

    def _open_options_dialog(self):
        self.hide()
        main_win = self.dialog.main_win
        if main_win and hasattr(main_win, "open_options"):
            main_win.open_options("media")
        else:
            from ui.dialogs import OptionsDialog
            dlg = OptionsDialog(main_window=main_win, parent=self.dialog, initial_tab="media")
            dlg.exec()

    def update_engine(self, tool_name: str, display_text: str, status_color: str):
        if tool_name in self.engine_rows:
            self.engine_rows[tool_name].set_status(display_text, status_color)
        self._refresh_summary()

    def _refresh_summary(self):
        any_updating = False
        any_update_available = False
        all_ready = True
        ready_count = 0
        for r in self.engine_rows.values():
            ver_text = r.lbl_version.text()
            if r.progress_bar.isVisible() or "Updating" in ver_text:
                any_updating = True
            if "Update Available" in ver_text or ("update" in ver_text.lower() and "updating" not in ver_text.lower()):
                any_update_available = True
            if "color: #2ec27e" in r.lbl_version.styleSheet():
                ready_count += 1
            else:
                all_ready = False

        if any_updating:
            self.lbl_summary_badge.setText("↻ Updating...")
            self.lbl_summary_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #e5a50a; background-color: palette(alternate-base); border: 1px solid #e5a50a; border-radius: 10px; padding: 2px 8px;")
            self.dialog.btn_three_dots.set_status("yellow")
        elif any_update_available:
            self.lbl_summary_badge.setText("↻ Update Available")
            self.lbl_summary_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #e5a50a; background-color: palette(alternate-base); border: 1px solid #e5a50a; border-radius: 10px; padding: 2px 8px;")
            self.dialog.btn_three_dots.set_status("yellow")
        elif not all_ready:
            self.lbl_summary_badge.setText(f"● {ready_count}/5 Ready")
            self.lbl_summary_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #e67e22; background-color: palette(alternate-base); border: 1px solid #e67e22; border-radius: 10px; padding: 2px 8px;")
            self.dialog.btn_three_dots.set_status("orange")
        else:
            self.lbl_summary_badge.setText("● 5 Operational")
            self.lbl_summary_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #2ec27e; background-color: palette(alternate-base); border: 1px solid #2ec27e; border-radius: 10px; padding: 2px 8px;")
            self.dialog.btn_three_dots.set_status(None)


class MediaDownloaderDialog(QDialog):
    """
    Top-level Media Downloader Window.
    Initialized with parent=None and Qt.WindowType.Window flag to render as an independent window
    in window manager taskbar panels while sharing the application's WM_CLASS.
    """

    def __init__(self, main_window=None, parent=None):
        super().__init__(None)
        self._main_window = main_window or parent
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Media Downloader")
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(1000, 600)
        self.setMinimumSize(680, 520)

        # Standalone top-level window flag
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

        self._worker = None
        self._dep_worker = None
        self._thumb_worker = None
        self._current_video_data = None
        self._current_playlist_data = None

        self.setStyleSheet("""
            QPushButton, QToolButton {
                color: palette(button-text);
                opacity: 1.0;
            }
            QPushButton:disabled, QToolButton:disabled {
                color: palette(disabled, button-text);
                background-color: palette(disabled, window);
                border: 1px solid palette(disabled, mid);
                opacity: 0.30;
            }
        """)

        self._setup_ui()
        self._load_preferences()
        self.check_all_dependencies(force_download=False)

    @property
    def main_win(self):
        return getattr(self, "_main_window", None) or self.parent()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Area: "Enter URL"
        lbl_header = QLabel("Enter URL")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        lbl_header.setFont(header_font)
        main_layout.addWidget(lbl_header)

        # 2. Input Row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("Paste video or playlist link (e.g. YouTube, Vimeo, Twitch)...")
        self.txt_url.setFixedHeight(34)
        self.txt_url.returnPressed.connect(self.start_analysis)
        self.txt_url.textChanged.connect(self._on_url_text_changed)
        self.txt_url.setToolTip("Enter direct video URL or playlist link to analyze")

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedHeight(34)
        self.btn_paste.setFixedWidth(75)
        self.btn_paste.setToolTip("Paste URL from clipboard (Ctrl+V)")
        self.btn_paste.clicked.connect(self._on_ctrl_v_paste)

        self.shortcut_paste = QShortcut(QKeySequence("Ctrl+V"), self)
        self.shortcut_paste.activated.connect(self._on_ctrl_v_paste)

        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.setFixedHeight(34)
        self.btn_analyze.setFixedWidth(85)
        self.btn_analyze.setDefault(True)
        self.btn_analyze.setToolTip("Parse media formats or playlist items using yt-dlp")
        self.btn_analyze.clicked.connect(self._on_analyze_or_stop_clicked)

        self.btn_three_dots = ThreeDotsButton(self)
        self.btn_three_dots.clicked.connect(self._toggle_options_hub)

        input_layout.addWidget(self.txt_url)
        input_layout.addWidget(self.btn_paste)
        input_layout.addWidget(self.btn_analyze)
        input_layout.addWidget(self.btn_three_dots)
        main_layout.addLayout(input_layout)

        # Popover Options Hub
        self.options_hub = MediaDownloaderOptionsHub(self)
        self.btn_update_deps = self.options_hub.btn_update_all
        self.dep_tools = {
            tool: {
                "name_label": row.lbl_name,
                "info_btn": row.btn_refresh,
                "box": row
            }
            for tool, row in self.options_hub.engine_rows.items()
        }

        # 3. Status Bar & Progress
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: gray;")
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = AndroidProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep)

        # 4. Stacked View Container
        self.stack = QStackedWidget()
        
        page_empty = QWidget()
        empty_layout = QVBoxLayout(page_empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty = QLabel("Enter a video or playlist link above and click 'Analyze' to view download options.")
        lbl_empty.setStyleSheet("color: gray;")
        empty_layout.addWidget(lbl_empty)
        self.stack.addWidget(page_empty)

        self.page_video = QWidget()
        self._setup_single_video_page()
        self.stack.addWidget(self.page_video)

        self.page_playlist = QWidget()
        self._setup_playlist_page()
        self.stack.addWidget(self.page_playlist)

        main_layout.addWidget(self.stack, stretch=1)

        # 5. Bottom Action Buttons
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self.btn_download = QPushButton("Download")
        self.btn_download.setObjectName("btn_download")
        self.btn_download.setFixedHeight(34)
        self.btn_download.setFixedWidth(150)
        self.btn_download.setEnabled(False)
        self.btn_download.setToolTip("Start download for selected format (merges video + audio + thumbnail + subtitles)")
        self.btn_download.clicked.connect(self._on_download_clicked)

        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedHeight(34)
        self.btn_close.setFixedWidth(90)
        self.btn_close.setToolTip("Close Media Downloader window")
        self.btn_close.clicked.connect(self.close)

        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_close)
        main_layout.addLayout(btn_bar)

    def _setup_single_video_page(self):
        layout = QVBoxLayout(self.page_video)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Hero Card: Thumbnail + Title + Metadata Badges
        hero_card = QFrame()
        hero_card.setObjectName("mediaHeroCard")
        hero_card.setStyleSheet("""
            QFrame#mediaHeroCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QFrame#mediaHeroCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(10, 10, 10, 10)
        hero_layout.setSpacing(14)

        self.lbl_thumbnail = QLabel()
        self.lbl_thumbnail.setFixedSize(160, 90)
        self.lbl_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumbnail.setPixmap(create_thumbnail_placeholder(160, 90, radius=8))
        self.lbl_thumbnail.setStyleSheet("border-radius: 8px;")
        hero_layout.addWidget(self.lbl_thumbnail)

        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(6)
        meta_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_video_title = QLabel("Video Title")
        font_title = QFont()
        font_title.setPointSize(11)
        font_title.setBold(True)
        self.lbl_video_title.setFont(font_title)
        self.lbl_video_title.setWordWrap(True)
        self.lbl_video_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_layout.addWidget(self.lbl_video_title)

        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(8)

        self.lbl_video_meta = QLabel("Uploader: Unknown | Duration: 0s")
        self.lbl_video_meta.setStyleSheet("color: palette(window-text); opacity: 0.85; font-size: 11px;")
        chips_layout.addWidget(self.lbl_video_meta)
        chips_layout.addStretch()
        meta_layout.addLayout(chips_layout)

        hero_layout.addLayout(meta_layout, stretch=1)
        layout.addWidget(hero_card)

        # Row 1: Media Quality Preset + Video Format Dropdown + Audio Format Dropdown
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)

        lbl_preset = QLabel("Preset:")
        self.cmb_quality_preset = QComboBox()
        self.cmb_quality_preset.setFixedHeight(30)
        self.cmb_quality_preset.setToolTip("Select quality preset (auto-merges Video + Audio)")
        self.cmb_quality_preset.addItems([
            "Best Quality (Video + Audio merged)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "360p Low Quality",
            "Audio Only (Opus)"
        ])
        self.cmb_quality_preset.currentIndexChanged.connect(self._on_preset_changed)

        lbl_fps = QLabel("FPS:")
        self.cmb_fps = QComboBox()
        self.cmb_fps.setFixedHeight(30)
        self.cmb_fps.setToolTip("Filter video framerate (e.g. 60 fps, 30 fps)")
        self.cmb_fps.addItem("Any FPS", 0)
        self.cmb_fps.currentIndexChanged.connect(self._on_preset_changed)

        lbl_vfmt = QLabel("Video:")
        self.cmb_video_format = QComboBox()
        self.cmb_video_format.setFixedHeight(30)
        self.cmb_video_format.setToolTip("Filter video container / codec")
        for label, key in [
            ("Any Format (Default)", "any"),
            ("MP4 (H.264 / AVC)", "h264"),
            ("WebM (VP9)", "webm"),
            ("AV1 Codec", "av1")
        ]:
            self.cmb_video_format.addItem(label, key)
        self.cmb_video_format.currentIndexChanged.connect(self._on_preset_changed)

        lbl_afmt = QLabel("Audio:")
        self.cmb_audio_format = QComboBox()
        self.cmb_audio_format.setFixedHeight(30)
        self.cmb_audio_format.setToolTip("Filter audio container / codec")
        for label, key in [
            ("Any Format (Default)", "any"),
            ("M4A (AAC Audio)", "m4a"),
            ("Opus (WebM Audio)", "opus"),
            ("MP3 Audio", "mp3")
        ]:
            self.cmb_audio_format.addItem(label, key)
        self.cmb_audio_format.currentIndexChanged.connect(self._on_preset_changed)

        preset_layout.addWidget(lbl_preset)
        preset_layout.addWidget(self.cmb_quality_preset, stretch=3)
        preset_layout.addWidget(lbl_fps)
        preset_layout.addWidget(self.cmb_fps, stretch=2)
        preset_layout.addWidget(lbl_vfmt)
        preset_layout.addWidget(self.cmb_video_format, stretch=2)
        preset_layout.addWidget(lbl_afmt)
        preset_layout.addWidget(self.cmb_audio_format, stretch=2)
        layout.addLayout(preset_layout)

        # Row 2: Checkboxes for Manual Selection Mode & Preferences Persistence
        chk_layout = QHBoxLayout()
        chk_layout.setSpacing(15)

        self.chk_manual_selection = QCheckBox("Enable Manual Stream Selection")
        self.chk_manual_selection.setToolTip("Enable to manually select a specific video/audio format row from the table below")
        self.chk_manual_selection.toggled.connect(self._on_manual_selection_toggled)

        self.chk_auto_start_browser = QCheckBox("Auto-start from extension")
        self.chk_auto_start_browser.setToolTip("Automatically start downloading media links sent from the browser extension using preselected quality")
        self.chk_auto_start_browser.toggled.connect(self._on_auto_start_browser_toggled)

        self.chk_save_defaults = QCheckBox("Remember Preset")
        self.chk_save_defaults.setToolTip("Save current quality preset, format choices, and selection mode for future downloads")
        self.chk_save_defaults.toggled.connect(self._save_preferences_if_enabled)

        chk_layout.addWidget(self.chk_manual_selection)
        chk_layout.addWidget(self.chk_auto_start_browser)
        chk_layout.addWidget(self.chk_save_defaults)
        chk_layout.addStretch()
        layout.addLayout(chk_layout)

        lbl_streams = QLabel("Available Formats & Streams (Sorted High to Low Resolution, Audio-Only at Bottom):")
        layout.addWidget(lbl_streams)

        self.tbl_formats = QTableWidget()
        self.tbl_formats.setColumnCount(6)
        self.tbl_formats.setHorizontalHeaderLabels(["Format ID", "Resolution", "Extension", "Codec", "Bitrate", "Size Est."])
        self.tbl_formats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_formats.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_formats.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_formats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_formats.itemSelectionChanged.connect(self._on_format_table_selection_changed)
        
        self.tbl_formats.setStyleSheet("""
            QTableWidget:disabled {
                background-color: palette(window);
                color: palette(disabled, text);
                border: 1px solid palette(disabled, mid);
            }
            QTableWidget::item:disabled {
                color: palette(disabled, text);
                background: transparent;
            }
            QHeaderView::section:disabled {
                color: palette(disabled, text);
                background-color: palette(window);
            }
        """)

        font_tbl = self.tbl_formats.font()
        font_tbl.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.tbl_formats.setFont(font_tbl)

        layout.addWidget(self.tbl_formats, stretch=1)

    def _setup_playlist_page(self):
        layout = QVBoxLayout(self.page_playlist)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Playlist Hero Card
        pl_hero_card = QFrame()
        pl_hero_card.setObjectName("playlistHeroCard")
        pl_hero_card.setStyleSheet("""
            QFrame#playlistHeroCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QFrame#playlistHeroCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        pl_hero_layout = QHBoxLayout(pl_hero_card)
        pl_hero_layout.setContentsMargins(10, 10, 10, 10)
        pl_hero_layout.setSpacing(14)

        self.lbl_playlist_thumbnail = QLabel()
        self.lbl_playlist_thumbnail.setFixedSize(160, 90)
        self.lbl_playlist_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_playlist_thumbnail.setPixmap(create_thumbnail_placeholder(160, 90, radius=8, is_playlist=True))
        self.lbl_playlist_thumbnail.setStyleSheet("border-radius: 8px;")
        pl_hero_layout.addWidget(self.lbl_playlist_thumbnail)

        pl_meta_layout = QVBoxLayout()
        pl_meta_layout.setSpacing(6)
        pl_meta_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_playlist_title = QLabel("Playlist Title")
        font_pl = QFont()
        font_pl.setPointSize(11)
        font_pl.setBold(True)
        self.lbl_playlist_title.setFont(font_pl)
        self.lbl_playlist_title.setWordWrap(True)
        self.lbl_playlist_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl_meta_layout.addWidget(self.lbl_playlist_title)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setFixedWidth(90)
        self.btn_select_all.clicked.connect(lambda: self._set_all_playlist_checked(True))

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setFixedWidth(90)
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_playlist_checked(False))

        self.lbl_select_count = QLabel("0 of 0 items selected")
        self.lbl_select_count.setStyleSheet("font-weight: bold; color: palette(window-text);")

        ctrl_layout.addWidget(self.btn_select_all)
        ctrl_layout.addWidget(self.btn_deselect_all)
        ctrl_layout.addWidget(self.lbl_select_count)
        ctrl_layout.addStretch()

        pl_meta_layout.addLayout(ctrl_layout)
        pl_hero_layout.addLayout(pl_meta_layout, stretch=1)
        layout.addWidget(pl_hero_card)

        pl_preset_layout = QHBoxLayout()
        pl_preset_layout.addWidget(QLabel("Global Quality Target:"))
        self.cmb_playlist_quality = QComboBox()
        self.cmb_playlist_quality.setFixedHeight(30)
        self.cmb_playlist_quality.addItems([
            "Best Available (Video + Audio)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "Audio Only (Opus)"
        ])
        pl_preset_layout.addWidget(self.cmb_playlist_quality, stretch=1)
        layout.addLayout(pl_preset_layout)

        self.tbl_playlist = QTableWidget()
        self.tbl_playlist.setColumnCount(4)
        self.tbl_playlist.setHorizontalHeaderLabels(["Select", "#", "Title", "Duration"])
        self.tbl_playlist.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_playlist.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_playlist.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_playlist.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_playlist.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_playlist.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._playlist_delegate = CheckableTableItemDelegate(self.tbl_playlist)
        self.tbl_playlist.setItemDelegateForColumn(0, self._playlist_delegate)

        font_pl_tbl = self.tbl_playlist.font()
        font_pl_tbl.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.tbl_playlist.setFont(font_pl_tbl)

        layout.addWidget(self.tbl_playlist, stretch=1)

    def _toggle_options_hub(self):
        if self.options_hub.isVisible():
            self.options_hub.hide()
        else:
            global_pos = self.btn_three_dots.mapToGlobal(QPoint(0, self.btn_three_dots.height() + 4))
            x = global_pos.x() + self.btn_three_dots.width() - self.options_hub.width() + 10
            y = global_pos.y() - 10
            self.options_hub.move(x, y)
            self.options_hub.show()
            self.options_hub.raise_()

    def check_all_dependencies(self, force_download: bool = False, target_tool: str = ""):
        """Spawns DependencyManagerWorker to verify and install missing engines."""
        if "pytest" in sys.modules and not getattr(self, "_force_dep_worker_test", False):
            return
        if hasattr(self, "_dep_worker") and self._dep_worker and self._dep_worker.isRunning():
            if force_download:
                try:
                    self._dep_worker.tool_status_signal.disconnect()
                    self._dep_worker.all_finished_signal.disconnect()
                    self._dep_worker.requestInterruption()
                    self._dep_worker.quit()
                    self._dep_worker.wait(1000)
                    if self._dep_worker.isRunning():
                        self._dep_worker.terminate()
                        self._dep_worker.wait(500)
                except Exception:
                    pass
            else:
                return

        # Reuse running worker from MainWindow if active
        main_worker = getattr(self.main_win, "_media_engine_worker", None)
        if main_worker and main_worker.isRunning() and not target_tool and not force_download:
            self._dep_worker = main_worker
            self._dep_worker.tool_status_signal.connect(self._on_dep_status_updated)
            self._dep_worker.all_finished_signal.connect(self._on_all_deps_finished)
            return

        self._dep_worker = DependencyManagerWorker(force_download=force_download, target_tool=target_tool)
        self._dep_worker.tool_status_signal.connect(self._on_dep_status_updated)
        self._dep_worker.all_finished_signal.connect(self._on_all_deps_finished)
        _keep_thread_alive(self._dep_worker)
        if self.main_win and not target_tool:
            self.main_win._media_engine_worker = self._dep_worker
            try:
                self._dep_worker.tool_status_signal.connect(self.main_win._on_media_engine_status_updated)
                self._dep_worker.all_finished_signal.connect(self.main_win._on_media_engine_finished)
            except Exception:
                pass
        self._dep_worker.start()

    def update_all_dependencies(self):
        """Forces checking and updating of all 5 dependency tools."""
        self.options_hub.btn_update_all.setText("Checking...")
        self.options_hub.btn_update_all.setEnabled(False)
        if hasattr(self.main_win, "_start_media_engine_check"):
            self.main_win._start_media_engine_check(force_download=True)
            main_worker = getattr(self.main_win, "_media_engine_worker", None)
            if main_worker:
                self._dep_worker = main_worker
                self._dep_worker.tool_status_signal.connect(self._on_dep_status_updated)
                self._dep_worker.all_finished_signal.connect(self._on_all_deps_finished)
                return
        self.check_all_dependencies(force_download=True)

    def update_single_dependency(self, tool_name: str):
        """Checks and updates a single dependency tool."""
        self.check_all_dependencies(force_download=True, target_tool=tool_name)

    def _on_all_deps_finished(self):
        self.options_hub.btn_update_all.setText("Update All")
        self.options_hub.btn_update_all.setEnabled(True)
        self.options_hub._refresh_summary()

    def _on_dep_status_updated(self, tool_name: str, display_text: str, status_color: str):
        self.options_hub.update_engine(tool_name, display_text, status_color)

    def _on_ctrl_v_paste(self):
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            return
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            from core.utils import sanitize_media_url
            self.txt_url.setText(sanitize_media_url(text))
            self.start_analysis()

    def _on_analyze_or_stop_clicked(self):
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            self.stop_analysis()
        else:
            self.start_analysis()

    def stop_analysis(self):
        if hasattr(self, "_worker") and self._worker:
            if self._worker.isRunning():
                try:
                    self._worker.stop()
                    self._worker.requestInterruption()
                    self._worker.quit()
                    self._worker.wait(2000)
                    if self._worker.isRunning():
                        self._worker.terminate()
                        self._worker.wait(2000)
                except Exception:
                    pass
        self._finish_loading()
        self.lbl_status.setText("Analysis cancelled.")

    def _get_cookies_args(self):
        """Resolves cookies configuration from caller context or persistent application options."""
        c_path = getattr(self, "_cookies_file", "") or ""
        if c_path and os.path.exists(c_path):
            return None, c_path
        try:
            from core.config import load_category_config
            cfg = load_category_config()
            media_defaults = cfg.get("media_downloader_defaults", {})
            opt_cpath = cfg.get("media_downloader_cookies_path") or media_defaults.get("cookies_path", "")
            opt_cbrowser = cfg.get("media_downloader_cookies_browser") or media_defaults.get("cookies_browser", "")
            if opt_cpath and os.path.exists(opt_cpath):
                return None, opt_cpath
            elif opt_cbrowser and opt_cbrowser.lower() != "none":
                return opt_cbrowser.lower(), None
        except Exception:
            pass
        return None, None

    def set_request_context(self, referrer=None, user_agent=None, custom_title=None, cookies=None, estimated_size_bytes=0, cookies_file=None):
        """Sets incoming HTTP context (referrer, user-agent), cookies, custom title, and estimated size for media analysis and downloads."""
        self._referrer = referrer
        self._user_agent = user_agent
        self._custom_title = custom_title
        self._cookies = cookies
        self._estimated_size_bytes = estimated_size_bytes
        if cookies_file:
            self._cookies_file = cookies_file

    def analyze_and_download(self, url: str, auto_start: bool = False, target_preset: str = ""):
        """Sets URL, applies auto-start flags, and initiates analysis."""
        from core.utils import sanitize_media_url
        clean_url = sanitize_media_url(url)
        self._auto_start_pending = auto_start
        self._auto_start_preset = target_preset or "Best Quality (Video + Audio merged)"
        self.txt_url.setText(clean_url)
        self.start_analysis()

    def start_analysis(self):
        from core.utils import sanitize_media_url
        url = sanitize_media_url(self.txt_url.text().strip())
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter or paste a media link.")
            return

        self.txt_url.setText(url)
        self.txt_url.setEnabled(False)
        self.btn_paste.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.btn_analyze.setText("Stop")
        self.btn_analyze.setToolTip("Stop ongoing link analysis")
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("Analyzing link...")

        c_browser, c_file = self._get_cookies_args()
        effective_cookies = getattr(self, "_cookies", None) if not c_file else None
        if is_debug_mode():
            logger.debug("[MediaDialog] Starting link analysis: url=%s, c_browser=%s, c_file=%s, referrer=%s",
                         url, c_browser, c_file, getattr(self, "_referrer", None))
        self._worker = MediaExtractorWorker(
            url,
            cookies_browser=c_browser,
            cookies_file=c_file,
            referrer=getattr(self, "_referrer", None),
            user_agent=getattr(self, "_user_agent", None),
            cookies=effective_cookies
        )
        self._worker.status_signal.connect(self._on_status_msg)
        self._worker.single_video_analyzed.connect(self._on_single_video_ready)
        self._worker.playlist_analyzed.connect(self._on_playlist_ready)
        self._worker.analysis_failed.connect(self._on_analysis_failed)
        self._worker.start()

    def _on_status_msg(self, msg: str):
        self.lbl_status.setText(msg)

    def _on_single_video_ready(self, data: dict):
        self._finish_loading()
        self._current_video_data = data
        self._current_playlist_data = None

        if is_debug_mode():
            logger.debug("[MediaDialog] Single video ready: id=%s, title=%s, formats=%d, duration=%s",
                         data.get("id"), data.get("title"), len(data.get("formats", [])), data.get("duration"))

        custom_title = getattr(self, "_custom_title", None)
        raw_title = data.get("title", "Untitled Media")
        from core.utils import is_generic_media_title
        is_raw_generic = is_generic_media_title(raw_title)
        is_custom_generic = is_generic_media_title(custom_title)
        if not is_raw_generic:
            display_title = raw_title
        elif not is_custom_generic:
            display_title = custom_title
        else:
            display_title = raw_title or "Media"
        self.lbl_video_title.setText(display_title)
        dur_sec = int(data.get("duration") or 0)
        dur_str = f"{dur_sec // 60}m {dur_sec % 60:02d}s" if dur_sec else "Unknown"
        uploader = data.get("uploader") or "Unknown"
        self.lbl_video_meta.setText(f"👤 {uploader}  •  ⏱️ {dur_str}")

        # Async Thumbnail Acquisition
        if hasattr(self, "lbl_thumbnail"):
            self.lbl_thumbnail.setPixmap(create_thumbnail_placeholder(160, 90, radius=8))
            thumb_url = data.get("thumbnail")
            if thumb_url:
                if hasattr(self, "_thumb_worker") and self._thumb_worker and self._thumb_worker.isRunning():
                    try:
                        self._thumb_worker.requestInterruption()
                        self._thumb_worker.quit()
                        self._thumb_worker.wait(150)
                    except Exception:
                        pass
                self._thumb_worker = ThumbnailLoaderWorker(thumb_url)
                self._thumb_worker.thumbnail_loaded.connect(self._on_thumbnail_loaded)
                self._thumb_worker.start()

        formats = data.get("formats", [])
        self.tbl_formats.setRowCount(0)

        for row_idx, fmt in enumerate(formats):
            self.tbl_formats.insertRow(row_idx)
            self.tbl_formats.setItem(row_idx, 0, QTableWidgetItem(str(fmt["format_id"])))
            
            fps_val = int(fmt.get("fps") or 0)
            res_label = str(fmt.get("res_label") or "")
            if fps_val > 0 and fmt.get("is_video"):
                res_display = f"{res_label} ({fps_val}fps)"
            else:
                res_display = res_label
            self.tbl_formats.setItem(row_idx, 1, QTableWidgetItem(res_display))
            
            self.tbl_formats.setItem(row_idx, 2, QTableWidgetItem(str(fmt.get("ext", "-"))))
            
            vcodec = fmt.get("vcodec", "none")
            acodec = fmt.get("acodec", "none")
            codec_info = vcodec if vcodec != "none" else acodec
            self.tbl_formats.setItem(row_idx, 3, QTableWidgetItem(str(codec_info)))
            
            tbr = fmt.get("tbr")
            tbr_str = f"{int(tbr)} kbps" if tbr else "-"
            self.tbl_formats.setItem(row_idx, 4, QTableWidgetItem(tbr_str))
            
            filesize = fmt.get("filesize")
            size_mb = f"{filesize / (1024*1024):.1f} MB" if filesize else "-"
            self.tbl_formats.setItem(row_idx, 5, QTableWidgetItem(size_mb))

        is_manual = self.chk_manual_selection.isChecked()
        self.tbl_formats.setEnabled(is_manual)
        if formats and is_manual:
            self.tbl_formats.selectRow(0)
        elif not is_manual:
            self.tbl_formats.clearSelection()

        self._update_preset_availability(data)
        self.stack.setCurrentWidget(self.page_video)
        self.btn_download.setText("Download Media")
        self.btn_download.setEnabled(True)

        # Apply target quality preset if specified
        target_preset = getattr(self, "_auto_start_preset", "")
        if target_preset:
            model = self.cmb_quality_preset.model()
            res_match = re.search(r"(\d{3,4}p)", target_preset, re.IGNORECASE)
            is_audio = "audio" in target_preset.lower() or "mp3" in target_preset.lower() or "opus" in target_preset.lower()
            token = res_match.group(1).lower() if res_match else ("audio" if is_audio else target_preset.lower())

            matched_idx = -1
            for i in range(self.cmb_quality_preset.count()):
                item = model.item(i) if model else None
                if item and not item.isEnabled():
                    continue
                item_text = self.cmb_quality_preset.itemText(i).lower()
                if token in item_text or target_preset.lower() in item_text:
                    matched_idx = i
                    break
            if matched_idx != -1:
                self.cmb_quality_preset.setCurrentIndex(matched_idx)

        # Auto-start download execution if requested from browser integration and permitted by options check
        if getattr(self, "_auto_start_pending", False):
            self._auto_start_pending = False
            self._on_download_clicked()

    def _on_thumbnail_loaded(self, image_or_pixmap):
        if hasattr(self, "lbl_thumbnail") and image_or_pixmap:
            if isinstance(image_or_pixmap, QImage):
                if not image_or_pixmap.isNull():
                    pm = QPixmap.fromImage(image_or_pixmap)
                    self.lbl_thumbnail.setPixmap(make_rounded_thumbnail(pm, 160, 90, radius=8))
            elif isinstance(image_or_pixmap, QPixmap):
                if not image_or_pixmap.isNull():
                    self.lbl_thumbnail.setPixmap(make_rounded_thumbnail(image_or_pixmap, 160, 90, radius=8))

    def _update_preset_availability(self, data: dict):
        formats = data.get("formats", [])
        available_heights = {fmt.get("height", 0) for fmt in formats if fmt.get("is_video") and fmt.get("height")}
        has_audio = any(fmt.get("is_audio") for fmt in formats)

        preset_items = [
            ("Best Quality (Video + Audio merged)", True),
            ("4K Ultra HD (2160p)", any(h >= 2160 for h in available_heights)),
            ("2K Quad HD (1440p)", any(h >= 1440 for h in available_heights)),
            ("1080p Full HD", any(h >= 1080 for h in available_heights)),
            ("720p HD", any(h >= 720 for h in available_heights)),
            ("480p SD", any(h >= 480 for h in available_heights)),
            ("360p Low Quality", any(h >= 360 for h in available_heights)),
            ("Audio Only (Opus)", has_audio)
        ]

        curr_idx = self.cmb_quality_preset.currentIndex()
        self.cmb_quality_preset.blockSignals(True)
        self.cmb_quality_preset.clear()

        model = self.cmb_quality_preset.model()
        for idx, (label, is_avail) in enumerate(preset_items):
            display_text = label if is_avail else f"{label} (Not Available)"
            self.cmb_quality_preset.addItem(display_text)
            item = model.item(idx)
            if item:
                item.setEnabled(is_avail)

        valid_idx = min(max(0, curr_idx), len(preset_items) - 1)
        selected_item = model.item(valid_idx)
        if selected_item and not selected_item.isEnabled():
            valid_idx = 0

        self.cmb_quality_preset.setCurrentIndex(valid_idx)
        self.cmb_quality_preset.blockSignals(False)

        # Dynamic FPS Filter based on available video stream framerates
        available_fps = sorted({int(f.get("fps")) for f in formats if f.get("is_video") and f.get("fps") and int(f.get("fps")) > 0}, reverse=True)
        curr_fps = self.cmb_fps.currentData() if hasattr(self, "cmb_fps") else 0
        self.cmb_fps.blockSignals(True)
        self.cmb_fps.clear()
        self.cmb_fps.addItem("Any FPS (Default)", 0)
        fps_to_select = 0
        for fps_val in available_fps:
            self.cmb_fps.addItem(f"{fps_val} fps", fps_val)
            if curr_fps == fps_val:
                fps_to_select = self.cmb_fps.count() - 1

        self.cmb_fps.setCurrentIndex(fps_to_select)
        self.cmb_fps.setEnabled(bool(available_fps) and not self.chk_manual_selection.isChecked())
        self.cmb_fps.blockSignals(False)

        # Dynamic Video Codec Filters based on analyzed video formats
        has_h264 = any("avc" in (f.get("vcodec") or "").lower() or f.get("ext") == "mp4" for f in formats if f.get("is_video"))
        has_webm_vp9 = any("vp9" in (f.get("vcodec") or "").lower() or f.get("ext") == "webm" for f in formats if f.get("is_video"))
        has_av1 = any("av01" in (f.get("vcodec") or "").lower() or "av1" in (f.get("vcodec") or "").lower() for f in formats if f.get("is_video"))

        v_items = [
            ("Any Format (Default)", "any", True),
            ("MP4 (H.264 / AVC)", "h264", has_h264),
            ("WebM (VP9)", "webm", has_webm_vp9),
            ("AV1 Codec", "av1", has_av1),
        ]

        curr_v_data = self.cmb_video_format.currentData()
        if not curr_v_data or curr_v_data == "any":
            try:
                from core.config import load_category_config
                cfg = load_category_config()
                pref_codec = cfg.get("media_downloader_defaults", {}).get("video_codec", "Auto (Default)").lower()
                if "av1" in pref_codec and has_av1:
                    curr_v_data = "av1"
                elif ("h264" in pref_codec or "avc" in pref_codec) and has_h264:
                    curr_v_data = "h264"
                elif "vp9" in pref_codec and has_webm_vp9:
                    curr_v_data = "webm"
                else:
                    curr_v_data = curr_v_data or "any"
            except Exception:
                curr_v_data = "any"

        self.cmb_video_format.blockSignals(True)
        self.cmb_video_format.clear()
        v_model = self.cmb_video_format.model()
        v_idx_to_select = 0
        for idx, (label, key, is_avail) in enumerate(v_items):
            display_text = label if is_avail else f"{label} (Not Available)"
            self.cmb_video_format.addItem(display_text, key)
            item = v_model.item(idx)
            if item:
                item.setEnabled(is_avail)
            if key == curr_v_data and is_avail:
                v_idx_to_select = idx

        self.cmb_video_format.setCurrentIndex(v_idx_to_select)
        self.cmb_video_format.blockSignals(False)

        # Dynamic Audio Codec Filters based on analyzed audio formats
        has_m4a = any("mp4a" in (f.get("acodec") or "").lower() or f.get("ext") == "m4a" for f in formats if f.get("is_audio"))
        has_opus = any("opus" in (f.get("acodec") or "").lower() or "vorbis" in (f.get("acodec") or "").lower() or f.get("ext") == "webm" for f in formats if f.get("is_audio"))
        has_mp3 = any("mp3" in (f.get("acodec") or "").lower() or f.get("ext") == "mp3" for f in formats if f.get("is_audio"))

        a_items = [
            ("Any Format (Default)", "any", True),
            ("M4A (AAC Audio)", "m4a", has_m4a),
            ("Opus (WebM Audio)", "opus", has_opus),
            ("MP3 Audio", "mp3", has_mp3),
        ]

        curr_a_data = self.cmb_audio_format.currentData() or "any"
        self.cmb_audio_format.blockSignals(True)
        self.cmb_audio_format.clear()
        a_model = self.cmb_audio_format.model()
        a_idx_to_select = 0
        for idx, (label, key, is_avail) in enumerate(a_items):
            display_text = label if is_avail else f"{label} (Not Available)"
            self.cmb_audio_format.addItem(display_text, key)
            item = a_model.item(idx)
            if item:
                item.setEnabled(is_avail)
            if key == curr_a_data and is_avail:
                a_idx_to_select = idx

        self.cmb_audio_format.setCurrentIndex(a_idx_to_select)
        self.cmb_audio_format.blockSignals(False)

    def _reset_preset_labels(self):
        preset_items = [
            "Best Quality (Video + Audio merged)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "360p Low Quality",
            "Audio Only (Opus)"
        ]
        curr_idx = self.cmb_quality_preset.currentIndex()
        self.cmb_quality_preset.blockSignals(True)
        self.cmb_quality_preset.clear()

        model = self.cmb_quality_preset.model()
        for idx, label in enumerate(preset_items):
            self.cmb_quality_preset.addItem(label)
            item = model.item(idx)
            if item:
                item.setEnabled(True)

        self.cmb_quality_preset.setCurrentIndex(min(max(0, curr_idx), len(preset_items) - 1))
        self.cmb_quality_preset.blockSignals(False)

        if hasattr(self, "cmb_fps"):
            self.cmb_fps.blockSignals(True)
            self.cmb_fps.clear()
            self.cmb_fps.addItem("Any FPS (Default)", 0)
            self.cmb_fps.blockSignals(False)

        if hasattr(self, "cmb_video_format"):
            v_items = [
                ("Any Format (Default)", "any"),
                ("MP4 (H.264 / AVC)", "h264"),
                ("WebM (VP9)", "webm"),
                ("AV1 Codec", "av1"),
            ]
            curr_v = self.cmb_video_format.currentIndex()
            self.cmb_video_format.blockSignals(True)
            self.cmb_video_format.clear()
            v_model = self.cmb_video_format.model()
            for idx, (label, key) in enumerate(v_items):
                self.cmb_video_format.addItem(label, key)
                item = v_model.item(idx)
                if item:
                    item.setEnabled(True)
            self.cmb_video_format.setCurrentIndex(min(max(0, curr_v), len(v_items) - 1))
            self.cmb_video_format.blockSignals(False)

        if hasattr(self, "cmb_audio_format"):
            a_items = [
                ("Any Format (Default)", "any"),
                ("M4A (AAC Audio)", "m4a"),
                ("Opus (WebM Audio)", "opus"),
                ("MP3 Audio", "mp3"),
            ]
            curr_a = self.cmb_audio_format.currentIndex()
            self.cmb_audio_format.blockSignals(True)
            self.cmb_audio_format.clear()
            a_model = self.cmb_audio_format.model()
            for idx, (label, key) in enumerate(a_items):
                self.cmb_audio_format.addItem(label, key)
                item = a_model.item(idx)
                if item:
                    item.setEnabled(True)
            self.cmb_audio_format.setCurrentIndex(min(max(0, curr_a), len(a_items) - 1))
            self.cmb_audio_format.blockSignals(False)

    def _on_playlist_ready(self, data: dict):
        self._finish_loading()
        self._current_playlist_data = data
        self._current_video_data = None

        if is_debug_mode():
            logger.debug("[MediaDialog] Playlist ready: title=%s, total_items=%s, entries=%d",
                         data.get("title"), data.get("total_items"), len(data.get("entries", [])))

        title = data.get("title", "Playlist")
        total = data.get("total_items", 0)
        self.lbl_playlist_title.setText(f"{title} ({total} items)")

        entries = data.get("entries", [])
        self.tbl_playlist.setRowCount(0)

        for row_idx, entry in enumerate(entries):
            self.tbl_playlist.insertRow(row_idx)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            self.tbl_playlist.setItem(row_idx, 0, chk_item)

            self.tbl_playlist.setItem(row_idx, 1, QTableWidgetItem(str(entry["index"])))
            self.tbl_playlist.setItem(row_idx, 2, QTableWidgetItem(str(entry["title"])))

            dur_sec = int(entry.get("duration") or 0)
            dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "-"
            self.tbl_playlist.setItem(row_idx, 3, QTableWidgetItem(dur_str))

        self.tbl_playlist.itemChanged.connect(self._update_playlist_selection_count)
        self._update_playlist_selection_count()

        # Async Playlist Thumbnail Acquisition
        if hasattr(self, "lbl_playlist_thumbnail"):
            self.lbl_playlist_thumbnail.setPixmap(create_thumbnail_placeholder(160, 90, radius=8, is_playlist=True))
            pl_thumb_url = data.get("thumbnail") or ""
            if not pl_thumb_url and entries:
                pl_thumb_url = entries[0].get("thumbnail") or ""
            if pl_thumb_url:
                if hasattr(self, "_pl_thumb_worker") and self._pl_thumb_worker and self._pl_thumb_worker.isRunning():
                    try:
                        self._pl_thumb_worker.requestInterruption()
                        self._pl_thumb_worker.quit()
                        self._pl_thumb_worker.wait(150)
                    except Exception:
                        pass
                self._pl_thumb_worker = ThumbnailLoaderWorker(pl_thumb_url)
                self._pl_thumb_worker.thumbnail_loaded.connect(self._on_playlist_thumbnail_loaded)
                self._pl_thumb_worker.start()

        self.stack.setCurrentWidget(self.page_playlist)
        self.btn_download.setEnabled(True)

        if getattr(self, "_auto_start_pending", False):
            self._auto_start_pending = False
            target_preset = getattr(self, "_auto_start_preset", "")
            if target_preset:
                for i in range(self.cmb_playlist_quality.count()):
                    if target_preset.lower() in self.cmb_playlist_quality.itemText(i).lower():
                        self.cmb_playlist_quality.setCurrentIndex(i)
                        break
            self._set_all_playlist_checked(True)
            self._on_download_clicked()

    def _on_playlist_thumbnail_loaded(self, image_or_pixmap):
        if hasattr(self, "lbl_playlist_thumbnail") and image_or_pixmap:
            if isinstance(image_or_pixmap, QImage):
                if not image_or_pixmap.isNull():
                    pm = QPixmap.fromImage(image_or_pixmap)
                    self.lbl_playlist_thumbnail.setPixmap(make_rounded_thumbnail(pm, 160, 90, radius=8))
            elif isinstance(image_or_pixmap, QPixmap):
                if not image_or_pixmap.isNull():
                    self.lbl_playlist_thumbnail.setPixmap(make_rounded_thumbnail(image_or_pixmap, 160, 90, radius=8))

    def _on_url_text_changed(self, text: str):
        self._current_video_data = None
        self._current_playlist_data = None
        self.btn_download.setEnabled(False)
        self.btn_download.setText("Download")
        self._reset_preset_labels()
        self.stack.setCurrentIndex(0)

    def _on_analysis_failed(self, error_msg: str):
        if is_debug_mode():
            logger.debug("[MediaDialog] Analysis failed: %s", error_msg)
        self._finish_loading()
        self._current_video_data = None
        self._current_playlist_data = None
        self.btn_download.setEnabled(False)
        self.btn_download.setText("Download")
        self.stack.setCurrentIndex(0)
        self.lbl_status.setText(f"Analysis failed: {error_msg}")
        if self.isVisible():
            QMessageBox.critical(self, "Extraction Error", f"Failed to analyze URL:\n{error_msg}")

    def _finish_loading(self):
        self.btn_analyze.setText("Analyze")
        self.btn_analyze.setToolTip("Parse media formats or playlist items using yt-dlp")
        self.btn_analyze.setEnabled(True)
        self.btn_paste.setEnabled(True)
        self.txt_url.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Analysis finished.")

    def _on_preset_changed(self, idx: int = 0):
        self._save_preferences_if_enabled()
        if not self._current_video_data or self.chk_manual_selection.isChecked():
            return
        formats = self._current_video_data.get("formats", [])
        if not formats:
            return

        preset_idx = self.cmb_quality_preset.currentIndex()
        fps_target = self.cmb_fps.currentData() if hasattr(self, "cmb_fps") else 0
        target_height = 0
        if preset_idx == 1: target_height = 2160
        elif preset_idx == 2: target_height = 1440
        elif preset_idx == 3: target_height = 1080
        elif preset_idx == 4: target_height = 720
        elif preset_idx == 5: target_height = 480
        elif preset_idx == 6: target_height = 360

        target_row = 0
        if preset_idx == 7:
            target_row = self._find_audio_only_row()
        elif target_height > 0:
            target_row = self._find_format_row_by_height(target_height, target_fps=fps_target or 0)

        self.tbl_formats.selectRow(target_row)

    def _on_manual_selection_toggled(self, checked: bool):
        self.cmb_quality_preset.setEnabled(not checked)
        if hasattr(self, "cmb_fps"):
            self.cmb_fps.setEnabled(not checked)
        self.cmb_video_format.setEnabled(not checked)
        self.cmb_audio_format.setEnabled(not checked)
        self.tbl_formats.setEnabled(checked)
        if not checked:
            self.tbl_formats.clearSelection()
        elif self.tbl_formats.rowCount() > 0 and len(self.tbl_formats.selectedItems()) == 0:
            self.tbl_formats.selectRow(0)
        self._save_preferences_if_enabled()

    def _on_format_table_selection_changed(self):
        if self.chk_manual_selection.isChecked():
            self._save_preferences_if_enabled()

    def _find_format_row_by_height(self, target_height: int, target_fps: int = 0) -> int:
        formats = self._current_video_data.get("formats", [])
        best_row = 0
        best_fps = -1
        best_tbr = -1
        found = False
        for i, fmt in enumerate(formats):
            if fmt.get("height") == target_height:
                fps = int(fmt.get("fps") or 0)
                tbr = int(fmt.get("tbr") or 0)
                if target_fps > 0:
                    if fps == target_fps:
                        if not found or tbr > best_tbr:
                            best_fps = fps
                            best_tbr = tbr
                            best_row = i
                            found = True
                    elif not found and (fps > best_fps or (fps == best_fps and tbr > best_tbr)):
                        best_fps = fps
                        best_tbr = tbr
                        best_row = i
                else:
                    if not found or fps > best_fps or (fps == best_fps and tbr > best_tbr):
                        best_fps = fps
                        best_tbr = tbr
                        best_row = i
                        found = True
        return best_row

    def _find_audio_only_row(self) -> int:
        formats = self._current_video_data.get("formats", [])
        for i, fmt in enumerate(formats):
            if fmt.get("is_audio") and not fmt.get("is_video"):
                return i
        return 0

    def _set_all_playlist_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.tbl_playlist.blockSignals(True)
        for r in range(self.tbl_playlist.rowCount()):
            item = self.tbl_playlist.item(r, 0)
            if item:
                item.setCheckState(state)
        self.tbl_playlist.blockSignals(False)
        self._update_playlist_selection_count()

    def _update_playlist_selection_count(self):
        checked_count = 0
        total = self.tbl_playlist.rowCount()
        for r in range(total):
            item = self.tbl_playlist.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked_count += 1

        self.lbl_select_count.setText(f"{checked_count} of {total} items selected")
        self.btn_download.setText(f"Download Selected ({checked_count})")
        self.btn_download.setEnabled(checked_count > 0)

    def _load_preferences(self):
        from core.config import load_category_config
        config = load_category_config()
        prefs = config.get("media_downloader_defaults", {})

        self.cmb_quality_preset.blockSignals(True)
        self.cmb_video_format.blockSignals(True)
        self.cmb_audio_format.blockSignals(True)
        self.chk_manual_selection.blockSignals(True)
        self.chk_save_defaults.blockSignals(True)

        preset_idx = min(max(0, prefs.get("preset_idx", 0)), self.cmb_quality_preset.count() - 1)
        vfmt_idx = min(max(0, prefs.get("video_format_idx", 0)), self.cmb_video_format.count() - 1)
        afmt_idx = min(max(0, prefs.get("audio_format_idx", 0)), self.cmb_audio_format.count() - 1)

        self.cmb_quality_preset.setCurrentIndex(preset_idx)
        self.cmb_video_format.setCurrentIndex(vfmt_idx)
        self.cmb_audio_format.setCurrentIndex(afmt_idx)

        use_manual = bool(prefs.get("use_manual_selection", False))
        save_defaults = bool(prefs.get("save_defaults", False))
        auto_start = bool(prefs.get("auto_start_media", False))

        self.chk_manual_selection.setChecked(use_manual)
        self.chk_save_defaults.setChecked(save_defaults)
        if hasattr(self, "chk_auto_start_browser"):
            self.chk_auto_start_browser.blockSignals(True)
            self.chk_auto_start_browser.setChecked(auto_start)
            self.chk_auto_start_browser.blockSignals(False)

        self.cmb_quality_preset.setEnabled(not use_manual)
        self.cmb_video_format.setEnabled(not use_manual)
        self.cmb_audio_format.setEnabled(not use_manual)
        self.tbl_formats.setEnabled(use_manual)
        if not use_manual:
            self.tbl_formats.clearSelection()

        self.cmb_quality_preset.blockSignals(False)
        self.cmb_video_format.blockSignals(False)
        self.cmb_audio_format.blockSignals(False)
        self.chk_manual_selection.blockSignals(False)
        self.chk_save_defaults.blockSignals(False)

    def _on_auto_start_browser_toggled(self, checked: bool):
        """Immediately update persistent auto-start setting matching the Options Media tab."""
        from core.config import load_category_config, save_category_config
        config = load_category_config()
        defaults = config.get("media_downloader_defaults", {})
        defaults["auto_start_media"] = checked
        config["media_downloader_defaults"] = defaults
        save_category_config(config)

    def _save_preferences_if_enabled(self):
        if hasattr(self, "chk_save_defaults") and self.chk_save_defaults.isChecked():
            from core.config import load_category_config, save_category_config
            config = load_category_config()
            defaults = config.get("media_downloader_defaults", {})
            defaults.update({
                "preset_idx": self.cmb_quality_preset.currentIndex(),
                "video_format_idx": self.cmb_video_format.currentIndex(),
                "audio_format_idx": self.cmb_audio_format.currentIndex(),
                "use_manual_selection": self.chk_manual_selection.isChecked(),
                "save_defaults": True,
                "auto_start_media": self.chk_auto_start_browser.isChecked() if hasattr(self, "chk_auto_start_browser") else defaults.get("auto_start_media", False)
            })
            config["media_downloader_defaults"] = defaults
            save_category_config(config)

    def _get_single_video_format_spec(self) -> tuple[str, bool, str]:
        """
        Returns tuple (format_spec, is_audio_only, output_container).
        If Manual Selection is checked, uses selected format ID from table.
        Otherwise builds format_spec using quality preset, video format filter, audio format filter, and FPS filter.
        output_container is 'mp4', 'webm', or 'mkv' (default).
        """
        if self.chk_manual_selection.isChecked():
            sel_rows = self.tbl_formats.selectionModel().selectedRows()
            if sel_rows and self._current_video_data:
                row_idx = sel_rows[0].row()
                formats = self._current_video_data.get("formats", [])
                if row_idx < len(formats):
                    fmt = formats[row_idx]
                    if fmt.get("is_video") and not fmt.get("is_audio"):
                        return (f"{fmt['format_id']}+bestaudio/best", False, "mkv")
                    elif fmt.get("is_audio") and not fmt.get("is_video"):
                        return (fmt["format_id"], True, "mkv")
                    else:
                        return (fmt["format_id"], False, "mkv")

        preset_idx = self.cmb_quality_preset.currentIndex()
        v_key = self.cmb_video_format.currentData() or "any"
        a_key = self.cmb_audio_format.currentData() or "any"
        fps_target = self.cmb_fps.currentData() if hasattr(self, "cmb_fps") else 0

        # Audio-only preset
        if preset_idx == 7:
            return ("bestaudio/best", True, "mkv")

        height_limit = None
        if preset_idx == 1: height_limit = 2160     # 4K
        elif preset_idx == 2: height_limit = 1440   # 2K
        elif preset_idx == 3: height_limit = 1080   # 1080p
        elif preset_idx == 4: height_limit = 720    # 720p
        elif preset_idx == 5: height_limit = 480    # 480p
        elif preset_idx == 6: height_limit = 360    # 360p

        vfilter = ""
        if v_key == "h264": vfilter = "[vcodec^=avc1]"
        elif v_key == "webm": vfilter = "[vcodec^=vp9]"
        elif v_key == "av1": vfilter = "[vcodec^=av01]"

        # Determine output container based on chosen codec/format
        # h264 → mp4; webm → webm; otherwise fallback to user preference in Options > Media
        if v_key == "h264":
            output_container = "mp4"
        elif v_key == "webm":
            output_container = "webm"
        else:
            try:
                from core.config import load_category_config as _lcfg
                _mdefaults = _lcfg().get("media_downloader_defaults", {})
                _vc_cfg = _mdefaults.get("video_container", "MKV (default)")
                output_container = _vc_cfg.split()[0].lower()
            except Exception:
                output_container = "mkv"

        fps_filter = f"[fps<={fps_target}]" if fps_target and fps_target > 0 else ""

        afilter = ""
        if a_key == "m4a": afilter = "[ext=m4a]"
        elif a_key == "opus": afilter = "[acodec^=opus]"
        elif a_key == "mp3": afilter = "[ext=mp3]"

        if height_limit:
            v_spec = f"bestvideo[height<={height_limit}]{fps_filter}{vfilter}"
            fallback_v = f"bestvideo[height<={height_limit}]"
        else:
            v_spec = f"bestvideo{fps_filter}{vfilter}"
            fallback_v = "bestvideo"

        if afilter:
            a_spec = f"bestaudio{afilter}"
            format_spec = f"{v_spec}+{a_spec}/{v_spec}+bestaudio[ext=m4a]/{v_spec}+bestaudio/{fallback_v}+bestaudio/best"
        else:
            format_spec = f"{v_spec}+bestaudio[ext=m4a]/{v_spec}+bestaudio/{fallback_v}+bestaudio[ext=m4a]/{fallback_v}+bestaudio/best"

        return (format_spec, False, output_container)

    def _get_playlist_format_spec(self) -> tuple[str, bool]:
        """Returns format spec for playlist items based on global playlist quality dropdown."""
        idx = self.cmb_playlist_quality.currentIndex()
        if idx == 0:
            return ("bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best", False)
        elif idx == 1:
            return ("bestvideo[height<=2160]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best", False)
        elif idx == 2:
            return ("bestvideo[height<=1440]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best", False)
        elif idx == 3:
            return ("bestvideo[height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best", False)
        elif idx == 4:
            return ("bestvideo[height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best", False)
        elif idx == 5:
            return ("bestvideo[height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best", False)
        elif idx == 6:
            return ("bestaudio/best", True)

        return ("bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best", False)

    def _on_download_clicked(self):
        self._save_preferences_if_enabled()
        mw = self.main_win
        if not mw:
            QMessageBox.warning(self, "Main Window Missing", "Cannot locate main application window.")
            return

        c_browser, c_file = self._get_cookies_args()

        if self.stack.currentWidget() == self.page_video and self._current_video_data:
            custom_title = getattr(self, "_custom_title", None)
            yt_title = self._current_video_data.get("title", "")
            webpage_url = self._current_video_data.get("webpage_url") or self.txt_url.text().strip()
            is_youtube = ("youtube.com" in webpage_url.lower() or "youtu.be" in webpage_url.lower() or
                          self._current_video_data.get("extractor", "").lower() == "youtube" or
                          "youtube" in self._current_video_data.get("extractor_key", "").lower())
            from core.utils import is_generic_media_title, is_media_downloader_url
            is_popular_platform = is_youtube or bool(is_media_downloader_url(webpage_url))

            is_raw_generic = is_generic_media_title(yt_title)
            is_custom_generic = is_generic_media_title(custom_title)

            if not is_raw_generic:
                title = yt_title
            elif not is_custom_generic:
                title = custom_title
            else:
                ref = getattr(self, "_referrer", None) or webpage_url
                video_id = self._current_video_data.get("id")
                if not video_id:
                    m = re.search(r"/(?:reel|reels|watch|videos?|p|v|status)/([A-Za-z0-9_-]+)", ref)
                    video_id = m.group(1) if m else ""
                title = f"video_{video_id}" if video_id else "video"

            format_spec, is_audio_only, output_container = self._get_single_video_format_spec()

            from core.utils import sanitize_media_filename
            if is_audio_only:
                try:
                    from core.config import load_category_config as _lcfg
                    _mdefaults = _lcfg().get("media_downloader_defaults", {})
                    _af_cfg = _mdefaults.get("audio_format", "Opus (default)")
                    ext = "." + _af_cfg.split()[0].lower()
                except Exception:
                    ext = ".opus"
            else:
                ext = f".{output_container}"

            preset_idx = self.cmb_quality_preset.currentIndex()
            target_height = None
            if preset_idx == 1: target_height = 2160
            elif preset_idx == 2: target_height = 1440
            elif preset_idx == 3: target_height = 1080
            elif preset_idx == 4: target_height = 720
            elif preset_idx == 5: target_height = 480
            elif preset_idx == 6: target_height = 360
            else:
                # Best Quality: check formats for best height
                v_heights = [fmt.get("height") or 0 for fmt in self._current_video_data.get("formats", []) if fmt.get("height") and fmt.get("is_video")]
                if v_heights:
                    target_height = max(v_heights)

            video_id = self._current_video_data.get("id") or ""
            if not video_id:
                m_yt = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", webpage_url)
                if m_yt:
                    video_id = m_yt.group(1)

            is_tiktok = ("tiktok.com" in webpage_url.lower() or
                         self._current_video_data.get("extractor", "").lower() == "tiktok" or
                         "tiktok" in self._current_video_data.get("extractor_key", "").lower())
            is_instagram = ("instagram.com" in webpage_url.lower() or
                            self._current_video_data.get("extractor", "").lower() == "instagram" or
                            "instagram" in self._current_video_data.get("extractor_key", "").lower())
            is_facebook = (any(d in webpage_url.lower() for d in ("facebook.com", "fb.watch", "fb.com")) or
                           self._current_video_data.get("extractor", "").lower() == "facebook" or
                           "facebook" in self._current_video_data.get("extractor_key", "").lower())
            is_twitter_or_x = (any(d in webpage_url.lower() for d in ("twitter.com", "x.com")) or
                               self._current_video_data.get("extractor", "").lower() in ("twitter", "x") or
                               any(k in self._current_video_data.get("extractor_key", "").lower() for k in ("twitter", "x")))

            if is_tiktok:
                v_id = self._current_video_data.get("id") or ""
                u = self._current_video_data.get("uploader_id") or self._current_video_data.get("uploader") or ""
                if not u or u.lower() == "unknown":
                    m_tt = re.search(r"@([^/?#&]+)/(?:video|v)/(\d+)", webpage_url)
                    if m_tt:
                        u = m_tt.group(1)
                        if not v_id: v_id = m_tt.group(2)
                filename = sanitize_media_filename(f"{u}_{v_id}" if (u and v_id) else (v_id or title), ext=ext)
            elif is_instagram:
                v_id = self._current_video_data.get("id") or ""
                u = self._current_video_data.get("channel") or ""
                if not u or u.lower() == "unknown" or " " in u:
                    m_by = re.search(r"(?:video|reel)?\s*by\s+([A-Za-z0-9_.]+)", yt_title, re.I)
                    if m_by:
                        u = m_by.group(1)
                if not u or u.lower() == "unknown":
                    m_ig_u = re.search(r"instagram\.com/([A-Za-z0-9_.]+)/(?:reels?|p|tv)/([A-Za-z0-9_-]+)", webpage_url)
                    if m_ig_u and m_ig_u.group(1).lower() not in ('reels', 'reel', 'p', 'tv', 'explore', 'stories', 'direct', 'accounts'):
                        u = m_ig_u.group(1)
                        if not v_id: v_id = m_ig_u.group(2)
                if not u or u.lower() == "unknown":
                    u = self._current_video_data.get("uploader") or ""
                    if u and " " in u:
                        m_on = re.search(r"(?:^|[\s\-])([A-Za-z0-9_.]+)\s+on\s+instagram", u, re.I)
                        if m_on:
                            u = m_on.group(1)
                        else:
                            u = u.replace(" ", "").lower()
                filename = sanitize_media_filename(f"{u}-{v_id}" if (u and v_id) else (v_id or title), ext=ext)
            elif is_facebook:
                v_id = self._current_video_data.get("id") or ""
                if not v_id:
                    m_fb = re.search(r"(?:facebook\.com|fb\.watch|fb\.com)/(?:reel|reels|videos?|share/[vr])/([A-Za-z0-9_-]+)", webpage_url) or re.search(r"[?&]v=(\d+)", webpage_url)
                    if m_fb: v_id = m_fb.group(1)
                filename = sanitize_media_filename(v_id or title, ext=ext)
            elif is_twitter_or_x:
                v_id = ""
                m_x = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status/(\d+)", webpage_url)
                if m_x and m_x.group(1).lower() not in ("home", "explore", "messages", "i", "notifications", "search"):
                    u = m_x.group(1)
                    v_id = m_x.group(2)
                else:
                    u = self._current_video_data.get("uploader_id") or ""
                    if not u or u.lower() == "unknown":
                        u = self._current_video_data.get("uploader") or ""
                    if m_x and m_x.group(1).lower() == "i":
                        v_id = m_x.group(2)
                    elif not v_id:
                        m_x_id = re.search(r"/status/(\d+)", webpage_url)
                        v_id = m_x_id.group(1) if m_x_id else (self._current_video_data.get("id") or "")
                filename = sanitize_media_filename(f"{u}-{v_id}" if (u and v_id) else (v_id or title), ext=ext)
            elif (is_youtube or is_popular_platform) and video_id:
                clean_title = title.rstrip("-_| ").strip() or title
                if is_audio_only:
                    full_title = f"{clean_title} [{video_id}]"
                else:
                    h_tag = f" [{target_height}p]" if target_height else ""
                    full_title = f"{clean_title} [{video_id}]{h_tag}"
                filename = sanitize_media_filename(full_title, ext=ext)
            else:
                filename = sanitize_media_filename(title, ext=ext)

            total_size_bytes = 0
            estimated_size = int(getattr(self, "_estimated_size_bytes", 0) or 0)
            dur = self._current_video_data.get("duration") or 0

            best_video_size = 0
            best_audio_size = 0
            premerged_size = 0

            for fmt in self._current_video_data.get("formats", []):
                vcodec = fmt.get("vcodec")
                acodec = fmt.get("acodec")
                h = fmt.get("height")
                f_size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
                if not f_size and dur and fmt.get("tbr"):
                    try:
                        f_size = int(float(dur) * float(fmt["tbr"]) * 125)
                    except Exception:
                        f_size = 0
                if not f_size:
                    continue

                is_v_only = bool(vcodec and vcodec != "none" and (not acodec or acodec == "none"))
                is_a_only = bool(acodec and acodec != "none" and (not vcodec or vcodec == "none"))
                is_premerged = bool(vcodec and vcodec != "none" and acodec and acodec != "none")

                if target_height:
                    if h == target_height:
                        if is_v_only and f_size > best_video_size:
                            best_video_size = f_size
                        elif is_premerged and f_size > premerged_size:
                            premerged_size = f_size
                else:
                    if is_v_only and f_size > best_video_size:
                        best_video_size = f_size
                    elif is_premerged and f_size > premerged_size:
                        premerged_size = f_size

                if is_a_only and f_size > best_audio_size:
                    best_audio_size = f_size

            if is_audio_only:
                total_size_bytes = best_audio_size
            else:
                merged_total = best_video_size + best_audio_size
                total_size_bytes = max(merged_total, premerged_size)

            # Prioritize estimated size from extension when preset is Best Quality / Auto,
            # or when format calculation yielded 0 or an underestimate compared to extension's detected tier
            if estimated_size > 0:
                if preset_idx == 0 or total_size_bytes == 0 or (estimated_size > total_size_bytes and not target_height):
                    total_size_bytes = estimated_size

            if hasattr(mw, "start_media_download"):
                if is_debug_mode():
                    logger.debug("[MediaDialog] Triggering start_media_download: filename=%s, format=%s, audio_only=%s, total_size=%s",
                                 filename, format_spec, is_audio_only, total_size_bytes)
                try:
                    mw.start_media_download(
                        url=webpage_url,
                        filename=filename,
                        format_spec=format_spec,
                        is_audio_only=is_audio_only,
                        cookies_browser=c_browser,
                        cookies_file=c_file,
                        total_size_bytes=total_size_bytes,
                        referrer=getattr(self, "_referrer", None),
                        user_agent=getattr(self, "_user_agent", None),
                        show_file_info=True,
                        cookies=getattr(self, "_cookies", None),
                        merge_output_format=output_container
                    )
                except TypeError:
                    try:
                        mw.start_media_download(
                            url=webpage_url,
                            filename=filename,
                            format_spec=format_spec,
                            is_audio_only=is_audio_only,
                            cookies_browser=c_browser,
                            cookies_file=c_file,
                            total_size_bytes=total_size_bytes,
                            referrer=getattr(self, "_referrer", None),
                            user_agent=getattr(self, "_user_agent", None),
                            show_file_info=True,
                            merge_output_format=output_container
                        )
                    except TypeError:
                        mw.start_media_download(
                            url=webpage_url,
                            filename=filename,
                            format_spec=format_spec,
                            is_audio_only=is_audio_only,
                            cookies_browser=c_browser,
                            cookies_file=c_file,
                            total_size_bytes=total_size_bytes,
                            referrer=getattr(self, "_referrer", None),
                            user_agent=getattr(self, "_user_agent", None)
                        )
            else:
                mw.process_incoming_url(webpage_url)

            # Bring main window to front so the user can see the new queue row
            mw.show()
            mw.raise_()
            mw.activateWindow()
            self.close()

        elif self.stack.currentWidget() == self.page_playlist and self._current_playlist_data:
            entries = self._current_playlist_data.get("entries", [])
            format_spec, is_audio_only = self._get_playlist_format_spec()
            from core.utils import sanitize_media_filename
            enqueued = 0

            pl_idx = self.cmb_playlist_quality.currentIndex()
            pl_h = None
            if pl_idx == 1: pl_h = 2160
            elif pl_idx == 2: pl_h = 1440
            elif pl_idx == 3: pl_h = 1080
            elif pl_idx == 4: pl_h = 720
            elif pl_idx == 5: pl_h = 480

            for r in range(self.tbl_playlist.rowCount()):
                chk_item = self.tbl_playlist.item(r, 0)
                if chk_item and chk_item.checkState() == Qt.CheckState.Checked and r < len(entries):
                    entry = entries[r]
                    item_url = entry["url"]
                    item_title = entry.get("title", f"video_{r+1}")
                    item_id = entry.get("id", "")
                    if not item_id:
                        m_yt = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", item_url)
                        if m_yt:
                            item_id = m_yt.group(1)
                    ext = ".opus" if is_audio_only else ".mkv"

                    is_yt_item = ("youtube.com" in item_url.lower() or "youtu.be" in item_url.lower() or
                                  entry.get("extractor", "").lower() == "youtube" or
                                  "youtube" in entry.get("extractor_key", "").lower())

                    if is_yt_item and item_id:
                        if is_audio_only:
                            yt_item_title = f"{item_title} [{item_id}]"
                        else:
                            h_tag = f" [{pl_h}p]" if pl_h else ""
                            yt_item_title = f"{item_title} [{item_id}]{h_tag}"
                        filename = sanitize_media_filename(yt_item_title, ext=ext)
                    else:
                        filename = sanitize_media_filename(item_title, ext=ext)

                    if hasattr(mw, "start_media_download"):
                        if is_debug_mode():
                            logger.debug("[MediaDialog] Enqueueing playlist item [%d/%d]: filename=%s, url=%s",
                                         r + 1, len(entries), filename, item_url)
                        try:
                            mw.start_media_download(
                                url=item_url,
                                filename=filename,
                                format_spec=format_spec,
                                is_audio_only=is_audio_only,
                                cookies_browser=c_browser,
                                cookies_file=c_file,
                                referrer=getattr(self, "_referrer", None),
                                user_agent=getattr(self, "_user_agent", None),
                                cookies=getattr(self, "_cookies", None)
                            )
                        except TypeError:
                            mw.start_media_download(
                                url=item_url,
                                filename=filename,
                                format_spec=format_spec,
                                is_audio_only=is_audio_only,
                                cookies_browser=c_browser,
                                cookies_file=c_file,
                                referrer=getattr(self, "_referrer", None),
                                user_agent=getattr(self, "_user_agent", None)
                            )
                    else:
                        mw.process_incoming_url(item_url)
                    enqueued += 1

            # Bring main window to front
            mw.show()
            mw.raise_()
            mw.activateWindow()
            self.close()

    def closeEvent(self, event):
        if hasattr(self, "options_hub") and self.options_hub:
            try:
                self.options_hub.close()
            except Exception:
                pass
        if hasattr(self, "tbl_playlist"):
            try:
                self.tbl_playlist.setItemDelegateForColumn(0, None)
            except Exception:
                pass
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            try:
                self._worker.stop()
                self._worker.requestInterruption()
                self._worker.quit()
                self._worker.wait(2000)
                if self._worker.isRunning():
                    self._worker.terminate()
                    self._worker.wait(2000)
            except Exception:
                pass
        if hasattr(self, "_dep_worker") and self._dep_worker and self._dep_worker.isRunning():
            try:
                # Do NOT interrupt or terminate _dep_worker; allow media engine downloads to continue in background.
                _keep_thread_alive(self._dep_worker)
                if self.main_win:
                    self.main_win._media_engine_worker = self._dep_worker
                    try:
                        self._dep_worker.tool_status_signal.connect(self.main_win._on_media_engine_status_updated)
                        self._dep_worker.all_finished_signal.connect(self.main_win._on_media_engine_finished)
                    except Exception:
                        pass
                try:
                    self._dep_worker.tool_status_signal.disconnect(self._on_dep_status_updated)
                except Exception:
                    pass
                try:
                    self._dep_worker.all_finished_signal.disconnect(self._on_all_deps_finished)
                except Exception:
                    pass
            except Exception:
                pass
        for attr in ("_thumb_worker", "_pl_thumb_worker"):
            w = getattr(self, attr, None)
            if w and w.isRunning():
                try:
                    w.requestInterruption()
                    w.quit()
                    w.wait(500)
                except Exception:
                    pass
        super().closeEvent(event)
