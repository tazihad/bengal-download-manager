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
    QAbstractItemView, QToolButton, QToolTip, QFileDialog
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QFont, QIcon, QKeySequence, QShortcut, QPixmap, QImage, QPainter,
    QPainterPath, QColor, QPen, QLinearGradient, QPalette
)
from core.media_downloader import YtDlpManager, MediaExtractorWorker, DependencyManagerWorker, _keep_thread_alive
from core.memory_guard import MemoryGuard


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

        # 0. Dependency Engines & Status Section
        dep_frame = QFrame()
        dep_frame.setFrameShape(QFrame.Shape.StyledPanel)
        dep_frame.setStyleSheet("""
            QFrame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
        """)
        dep_layout = QHBoxLayout(dep_frame)
        dep_layout.setContentsMargins(10, 6, 10, 6)
        dep_layout.setSpacing(10)

        lbl_dep_title = QLabel("Engines:")
        font_dep_title = QFont()
        font_dep_title.setBold(True)
        lbl_dep_title.setFont(font_dep_title)
        dep_layout.addWidget(lbl_dep_title)

        self.dep_tools = {}
        tool_names = ["yt-dlp", "ffmpeg", "ffprobe", "deno", "AtomicParsley"]
        for tool in tool_names:
            box = QFrame()
            box.setFrameShape(QFrame.Shape.StyledPanel)
            box.setStyleSheet("""
                QFrame {
                    background-color: palette(base);
                    border: 1px solid palette(mid);
                    border-radius: 6px;
                }
                QLabel {
                    border: none;
                    background: transparent;
                }
            """)
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(8, 4, 8, 4)
            box_layout.setSpacing(6)
            box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_name = QLabel(tool)
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font_name = QFont()
            font_name.setPointSize(9)
            font_name.setBold(True)
            lbl_name.setFont(font_name)
            lbl_name.setStyleSheet("color: gray; font-weight: bold;")

            btn_info = QToolButton()
            btn_info.setText("ⓘ")
            btn_info.setFixedSize(18, 18)
            btn_info.setToolTip(f"{tool}: Checking status...")
            btn_info.setStyleSheet("""
                QToolButton {
                    border-radius: 9px;
                    border: 1px solid palette(mid);
                    background-color: palette(button);
                    color: palette(button-text);
                    font-size: 10px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: palette(highlight);
                    color: palette(highlighted-text);
                }
            """)
            btn_info.clicked.connect(lambda _, t=tool, b=btn_info: QToolTip.showText(b.mapToGlobal(b.rect().center()), b.toolTip(), b))

            box_layout.addWidget(lbl_name)
            box_layout.addWidget(btn_info)

            self.dep_tools[tool] = {
                "name_label": lbl_name,
                "info_btn": btn_info,
                "box": box
            }
            dep_layout.addWidget(box)

        dep_layout.addStretch()

        self.btn_update_deps = QPushButton("Update")
        self.btn_update_deps.setFixedHeight(30)
        self.btn_update_deps.setFixedWidth(80)
        self.btn_update_deps.setToolTip("Check and download latest yt-dlp, ffmpeg, ffprobe, deno, and AtomicParsley engines")
        self.btn_update_deps.clicked.connect(self.update_all_dependencies)
        dep_layout.addWidget(self.btn_update_deps)

        main_layout.addWidget(dep_frame)

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

        self.btn_prefs = QPushButton("🍪 Cookies ▾")
        self.btn_prefs.setFixedHeight(34)
        self.btn_prefs.setFixedWidth(130)
        self.btn_prefs.setCheckable(True)
        self.btn_prefs.setToolTip("Configure Browser Cookies & Authentication (cookies.txt / Auto-Extract)")
        self.btn_prefs.clicked.connect(self._toggle_cookies_prefs)

        input_layout.addWidget(self.txt_url)
        input_layout.addWidget(self.btn_paste)
        input_layout.addWidget(self.btn_analyze)
        input_layout.addWidget(self.btn_prefs)
        main_layout.addLayout(input_layout)

        # 2b. Cookies & Authentication Configuration Panel (Software Engineering UI Standard)
        self.frame_cookies_prefs = QFrame()
        self.frame_cookies_prefs.setObjectName("cookiesPrefsFrame")
        self.frame_cookies_prefs.setFrameShape(QFrame.Shape.NoFrame)
        self.frame_cookies_prefs.setStyleSheet("""
            QFrame#cookiesPrefsFrame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QFrame#cookiesPrefsFrame QLabel {
                background: transparent;
                border: none;
            }
        """)
        self.frame_cookies_prefs.hide()

        cookies_layout = QVBoxLayout(self.frame_cookies_prefs)
        cookies_layout.setContentsMargins(14, 12, 14, 12)
        cookies_layout.setSpacing(10)

        # Header Row with Mode Selector
        auth_header_layout = QHBoxLayout()
        lbl_cookies_header = QLabel("Authentication & Cookie Vault")
        font_c = QFont()
        font_c.setBold(True)
        lbl_cookies_header.setFont(font_c)
        auth_header_layout.addWidget(lbl_cookies_header)
        auth_header_layout.addStretch()

        lbl_mode = QLabel("Auth Source:")
        lbl_mode.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.cmb_cookies_mode = QComboBox()
        self.cmb_cookies_mode.setFixedHeight(28)
        self.cmb_cookies_mode.addItems([
            "Netscape cookies.txt File",
            "Auto-Extract from Browser",
            "None (Direct Public Access)"
        ])
        self.cmb_cookies_mode.currentIndexChanged.connect(self._on_cookies_mode_changed)
        auth_header_layout.addWidget(lbl_mode)
        auth_header_layout.addWidget(self.cmb_cookies_mode)
        cookies_layout.addLayout(auth_header_layout)

        # Stack for Mode Controls
        self.stack_cookies = QStackedWidget()

        # Page 0: Netscape cookies.txt File Mode
        page_file = QWidget()
        page_file_layout = QVBoxLayout(page_file)
        page_file_layout.setContentsMargins(0, 0, 0, 0)
        page_file_layout.setSpacing(6)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        lbl_manual_path = QLabel("File Path:")
        self.txt_cookies_path = QLineEdit()
        self.txt_cookies_path.setPlaceholderText("Select or paste absolute path to cookies.txt...")
        self.txt_cookies_path.setFixedHeight(28)
        self.txt_cookies_path.textChanged.connect(self._on_cookies_text_changed)

        self.btn_browse_cookies = QPushButton("Browse...")
        self.btn_browse_cookies.setFixedHeight(28)
        self.btn_browse_cookies.setToolTip("Select Netscape formatted cookies.txt file from disk")
        self.btn_browse_cookies.clicked.connect(self._on_browse_cookies_clicked)

        self.btn_clear_cookies = QPushButton("Clear")
        self.btn_clear_cookies.setFixedHeight(28)
        self.btn_clear_cookies.setToolTip("Clear selected cookies configuration")
        self.btn_clear_cookies.clicked.connect(self._on_clear_cookies_clicked)

        file_row.addWidget(lbl_manual_path)
        file_row.addWidget(self.txt_cookies_path, stretch=1)
        file_row.addWidget(self.btn_browse_cookies)
        file_row.addWidget(self.btn_clear_cookies)
        page_file_layout.addLayout(file_row)

        self.lbl_cookies_status = QLabel("No cookies file configured.")
        self.lbl_cookies_status.setStyleSheet("font-size: 11px; color: gray;")
        page_file_layout.addWidget(self.lbl_cookies_status)

        self.stack_cookies.addWidget(page_file)

        # Page 1: Browser Extraction Mode
        page_browser = QWidget()
        page_browser_layout = QHBoxLayout(page_browser)
        page_browser_layout.setContentsMargins(0, 0, 0, 0)
        page_browser_layout.setSpacing(8)

        lbl_browser_sel = QLabel("Installed Browser:")
        self.cmb_cookies_browser = QComboBox()
        self.cmb_cookies_browser.setFixedHeight(28)
        self.cmb_cookies_browser.addItems(["Chrome", "Firefox", "Brave", "Edge", "Chromium", "Vivaldi", "Opera", "Safari"])
        self.cmb_cookies_browser.currentIndexChanged.connect(self._save_cookies_path_permanently)

        lbl_browser_hint = QLabel("• Auto-loads session auth cookies via yt-dlp native extraction.")
        lbl_browser_hint.setStyleSheet("font-size: 11px; color: gray;")

        page_browser_layout.addWidget(lbl_browser_sel)
        page_browser_layout.addWidget(self.cmb_cookies_browser)
        page_browser_layout.addWidget(lbl_browser_hint, stretch=1)

        self.stack_cookies.addWidget(page_browser)

        # Page 2: None / Anonymous Mode
        page_none = QWidget()
        page_none_layout = QHBoxLayout(page_none)
        page_none_layout.setContentsMargins(0, 0, 0, 0)
        lbl_none_hint = QLabel("Anonymous access active. Standard public streams will be fetched without cookies.")
        lbl_none_hint.setStyleSheet("font-size: 11px; color: gray; font-style: italic;")
        page_none_layout.addWidget(lbl_none_hint)

        self.stack_cookies.addWidget(page_none)

        cookies_layout.addWidget(self.stack_cookies)

        # Information & Security note
        self.lbl_cookies_info = QLabel(
            '🔒 <b>Local Execution:</b> Cookies are read strictly locally, never shared. • <a href="https://github.com/tazihad/bengal-download-manager/blob/main/docs/COOKIES_GUIDE.md" style="color: palette(highlight); text-decoration: underline;">How to export cookies.txt guide</a>'
        )
        self.lbl_cookies_info.setStyleSheet("font-size: 11px; color: palette(window-text); opacity: 0.85;")
        self.lbl_cookies_info.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_cookies_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.lbl_cookies_info.setOpenExternalLinks(True)
        cookies_layout.addWidget(self.lbl_cookies_info)

        main_layout.addWidget(self.frame_cookies_prefs)

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

        font_pl_tbl = self.tbl_playlist.font()
        font_pl_tbl.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.tbl_playlist.setFont(font_pl_tbl)

        layout.addWidget(self.tbl_playlist, stretch=1)

    def check_all_dependencies(self, force_download: bool = False):
        """Spawns DependencyManagerWorker to verify and install missing engines."""
        if hasattr(self, "_dep_worker") and self._dep_worker and self._dep_worker.isRunning():
            if force_download:
                try:
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

        self._dep_worker = DependencyManagerWorker(force_download=force_download)
        self._dep_worker.tool_status_signal.connect(self._on_dep_status_updated)
        self._dep_worker.all_finished_signal.connect(self._on_all_deps_finished)
        self._dep_worker.start()

    def update_all_dependencies(self):
        """Forces checking and updating of all 5 dependency tools."""
        self.btn_update_deps.setText("Checking...")
        self.btn_update_deps.setEnabled(False)
        for tool, item in self.dep_tools.items():
            item["name_label"].setStyleSheet("color: #e5a50a; font-weight: bold;")
            item["info_btn"].setToolTip(f"{tool}: Checking for updates...")
        self.check_all_dependencies(force_download=True)

    def _on_all_deps_finished(self):
        self.btn_update_deps.setText("Update")
        self.btn_update_deps.setEnabled(True)

    def _on_dep_status_updated(self, tool_name: str, display_text: str, status_color: str):
        if tool_name in self.dep_tools:
            item = self.dep_tools[tool_name]
            lbl_name = item["name_label"]
            btn_info = item["info_btn"]

            ver_text = display_text
            if display_text.startswith(f"{tool_name} (") and display_text.endswith(")"):
                ver_text = display_text[len(tool_name) + 2 : -1]

            if status_color == "yellow":
                dl_label = ver_text if ("Downloading" in ver_text or "Checking" in ver_text) else f"{ver_text} Downloading..."
                lbl_name.setText(f"{tool_name} ({dl_label})")
                lbl_name.setStyleSheet("color: #e5a50a; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name}: ({dl_label})")
            elif status_color == "green":
                lbl_name.setText(tool_name)
                lbl_name.setStyleSheet("color: #2ec27e; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name} Version: {ver_text}")
            else:
                lbl_name.setText(tool_name)
                lbl_name.setStyleSheet("color: gray; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name}: Not Installed")

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

    def _toggle_cookies_prefs(self):
        is_open = self.btn_prefs.isChecked()
        self.frame_cookies_prefs.setVisible(is_open)
        self.btn_prefs.setText("🍪 Cookies ▴" if is_open else "🍪 Cookies ▾")

    def _on_cookies_mode_changed(self, idx: int):
        if hasattr(self, "stack_cookies"):
            self.stack_cookies.setCurrentIndex(idx)
        self._save_cookies_path_permanently()

    def _on_cookies_text_changed(self, text: str):
        self._update_cookies_status_indicator()
        self._save_cookies_path_permanently()

    def _update_cookies_status_indicator(self):
        if not hasattr(self, "lbl_cookies_status") or not hasattr(self, "txt_cookies_path"):
            return
        c_path = self.txt_cookies_path.text().strip()
        if not c_path:
            self.lbl_cookies_status.setText("No cookies file configured.")
            self.lbl_cookies_status.setStyleSheet("font-size: 11px; color: gray;")
            if hasattr(self, "btn_prefs"):
                self.btn_prefs.setToolTip("Configure Browser Cookies & Authentication (cookies.txt / Auto-Extract)")
            return
        if not os.path.exists(c_path):
            self.lbl_cookies_status.setText(f"⚠️ File does not exist: {c_path}")
            self.lbl_cookies_status.setStyleSheet("font-size: 11px; color: #e5a50a;")
            if hasattr(self, "btn_prefs"):
                self.btn_prefs.setToolTip(f"Cookies: ⚠️ File not found ({c_path})")
            return
        try:
            sz = os.path.getsize(c_path)
            sz_str = f"{sz / 1024:.1f} KB" if sz >= 1024 else f"{sz} B"
            self.lbl_cookies_status.setText(f"✓ Valid Netscape Cookie file ({sz_str}) • Ready for yt-dlp authentication")
            self.lbl_cookies_status.setStyleSheet("font-size: 11px; color: #2ec27e; font-weight: bold;")
            if hasattr(self, "btn_prefs"):
                self.btn_prefs.setToolTip(f"Cookies Active: Netscape ({sz_str})")
        except Exception as e:
            self.lbl_cookies_status.setText(f"⚠️ Error accessing file: {e}")
            self.lbl_cookies_status.setStyleSheet("font-size: 11px; color: #e5a50a;")

    def _on_browse_cookies_clicked(self):
        from core.utils import choose_portal_open_file_path, get_user_home_dir

        file_path = choose_portal_open_file_path(title="Select Cookies File", folder=get_user_home_dir())
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Cookies File",
                get_user_home_dir(),
                "Text Files (*.txt);;All Files (*)"
            )
        if file_path:
            self.txt_cookies_path.setText(file_path)
            self._update_cookies_status_indicator()
            self._save_cookies_path_permanently()

    def _on_clear_cookies_clicked(self):
        self.txt_cookies_path.clear()
        self._update_cookies_status_indicator()
        self._save_cookies_path_permanently()

    def _get_cookies_args(self):
        mode_idx = self.cmb_cookies_mode.currentIndex() if hasattr(self, "cmb_cookies_mode") else 0
        if mode_idx == 1:  # Browser Auto-Extract
            browser = self.cmb_cookies_browser.currentText().lower() if hasattr(self, "cmb_cookies_browser") else None
            return browser, None
        elif mode_idx == 2:  # None
            return None, None
        else:  # Netscape File Mode (Index 0 / Default)
            c_path = self.txt_cookies_path.text().strip() if hasattr(self, "txt_cookies_path") else ""
            if c_path and os.path.exists(c_path):
                return None, c_path
            return None, None

    def set_request_context(self, referrer=None, user_agent=None, custom_title=None, cookies=None, estimated_size_bytes=0):
        """Sets incoming HTTP context (referrer, user-agent), cookies, custom title, and estimated size for media analysis and downloads."""
        self._referrer = referrer
        self._user_agent = user_agent
        self._custom_title = custom_title
        self._cookies = cookies
        self._estimated_size_bytes = estimated_size_bytes

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
        self._worker = MediaExtractorWorker(
            url,
            cookies_browser=c_browser,
            cookies_file=c_file,
            referrer=getattr(self, "_referrer", None),
            user_agent=getattr(self, "_user_agent", None),
            cookies=getattr(self, "_cookies", None)
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

        custom_title = getattr(self, "_custom_title", None)
        raw_title = data.get("title", "Untitled Media")
        is_generic = not raw_title or raw_title.lower().strip() in ("master", "index", "video", "untitled media", "playlist", "videoplayback", "media")
        if custom_title and (is_generic or custom_title.lower() != "video stream"):
            display_title = custom_title
        else:
            display_title = raw_title
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

        # Auto-start download execution if requested from browser integration
        if getattr(self, "_auto_start_pending", False):
            self._auto_start_pending = False
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

        curr_v_data = self.cmb_video_format.currentData() or "any"
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

        mode_idx = prefs.get("cookies_mode_idx", 0)
        if hasattr(self, "cmb_cookies_mode"):
            self.cmb_cookies_mode.blockSignals(True)
            self.cmb_cookies_mode.setCurrentIndex(min(max(0, mode_idx), self.cmb_cookies_mode.count() - 1))
            self.cmb_cookies_mode.blockSignals(False)
            if hasattr(self, "stack_cookies"):
                self.stack_cookies.setCurrentIndex(self.cmb_cookies_mode.currentIndex())

        browser_name = config.get("media_downloader_cookies_browser", prefs.get("cookies_browser", "Chrome"))
        if hasattr(self, "cmb_cookies_browser"):
            idx_b = self.cmb_cookies_browser.findText(browser_name, Qt.MatchFlag.MatchFixedString)
            if idx_b >= 0:
                self.cmb_cookies_browser.setCurrentIndex(idx_b)

        c_path = config.get("media_downloader_cookies_path", prefs.get("cookies_path", ""))
        self.txt_cookies_path.blockSignals(True)
        self.txt_cookies_path.setText(c_path)
        self.txt_cookies_path.blockSignals(False)
        self._update_cookies_status_indicator()

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

    def _save_cookies_path_permanently(self):
        """Always save cookies configurations persistently across app restarts."""
        from core.config import load_category_config, save_category_config
        config = load_category_config()
        path = self.txt_cookies_path.text().strip() if hasattr(self, "txt_cookies_path") else ""
        config["media_downloader_cookies_path"] = path
        
        mode_idx = self.cmb_cookies_mode.currentIndex() if hasattr(self, "cmb_cookies_mode") else 0
        browser_name = self.cmb_cookies_browser.currentText() if hasattr(self, "cmb_cookies_browser") else "Chrome"
        config["media_downloader_cookies_browser"] = browser_name

        defaults = config.get("media_downloader_defaults", {})
        defaults["cookies_path"] = path
        defaults["cookies_mode_idx"] = mode_idx
        defaults["cookies_browser"] = browser_name
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
                "cookies_path": self.txt_cookies_path.text().strip() if hasattr(self, "txt_cookies_path") else "",
                "cookies_mode_idx": self.cmb_cookies_mode.currentIndex() if hasattr(self, "cmb_cookies_mode") else 0,
                "cookies_browser": self.cmb_cookies_browser.currentText() if hasattr(self, "cmb_cookies_browser") else "Chrome",
                "auto_start_media": self.chk_auto_start_browser.isChecked() if hasattr(self, "chk_auto_start_browser") else defaults.get("auto_start_media", False)
            })
            config["media_downloader_defaults"] = defaults
            save_category_config(config)

    def _get_single_video_format_spec(self) -> tuple[str, bool]:
        """
        Returns tuple (format_spec, is_audio_only).
        If Manual Selection is checked, uses selected format ID from table.
        Otherwise builds format_spec using quality preset, video format filter, audio format filter, and FPS filter.
        """
        if self.chk_manual_selection.isChecked():
            sel_rows = self.tbl_formats.selectionModel().selectedRows()
            if sel_rows and self._current_video_data:
                row_idx = sel_rows[0].row()
                formats = self._current_video_data.get("formats", [])
                if row_idx < len(formats):
                    fmt = formats[row_idx]
                    if fmt.get("is_video") and not fmt.get("is_audio"):
                        return (f"{fmt['format_id']}+bestaudio/best", False)
                    elif fmt.get("is_audio") and not fmt.get("is_video"):
                        return (fmt["format_id"], True)
                    else:
                        return (fmt["format_id"], False)

        preset_idx = self.cmb_quality_preset.currentIndex()
        v_key = self.cmb_video_format.currentData() or "any"
        a_key = self.cmb_audio_format.currentData() or "any"
        fps_target = self.cmb_fps.currentData() if hasattr(self, "cmb_fps") else 0

        # Audio-only preset
        if preset_idx == 7:
            return ("bestaudio/best", True)

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

        return (format_spec, False)

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
            is_generic = not yt_title or yt_title.lower().strip() in ("master", "index", "video", "untitled media", "playlist", "videoplayback", "media")

            webpage_url = self._current_video_data.get("webpage_url") or self.txt_url.text().strip()
            is_youtube = ("youtube.com" in webpage_url.lower() or "youtu.be" in webpage_url.lower() or
                          self._current_video_data.get("extractor", "").lower() == "youtube" or
                          "youtube" in self._current_video_data.get("extractor_key", "").lower())

            if is_youtube and yt_title and not is_generic:
                title = yt_title
            elif custom_title and (is_generic or custom_title.lower() != "video stream"):
                title = custom_title
            elif not is_generic:
                title = yt_title
            elif custom_title:
                title = custom_title
            else:
                ref = getattr(self, "_referrer", None) or self.txt_url.text().strip()
                m = re.search(r"/(?:v|video|watch)/([A-Za-z0-9_-]+)", ref)
                title = f"video_{m.group(1)}" if m else "video"

            format_spec, is_audio_only = self._get_single_video_format_spec()

            from core.utils import sanitize_media_filename
            ext = ".opus" if is_audio_only else ".mkv"

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

            if is_youtube and video_id:
                clean_title = title.strip()
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
                        cookies=getattr(self, "_cookies", None)
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
                            show_file_info=True
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
                self._dep_worker.requestInterruption()
                self._dep_worker.quit()
                self._dep_worker.wait(2000)
                if self._dep_worker.isRunning():
                    self._dep_worker.terminate()
                    self._dep_worker.wait(2000)
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
