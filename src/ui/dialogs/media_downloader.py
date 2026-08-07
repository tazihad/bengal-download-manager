"""
Media Downloader Dialog for Bengal Download Manager.
Provides link input, media link parsing, dependency status bar (yt-dlp, ffmpeg, ffprobe, deno, AtomicParsley),
quality chooser, codec filters, format table sorting, and playlist batch selection.
"""

import sys
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QApplication, QFrame, QCheckBox,
    QAbstractItemView, QToolButton, QToolTip
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from core.media_downloader import YtDlpManager, MediaExtractorWorker, DependencyManagerWorker


class MediaDownloaderDialog(QDialog):
    """
    Top-level Media Downloader Window.
    Initialized with parent=None and Qt.WindowType.Window flag to render as an independent window
    in window manager taskbar panels while sharing the application's WM_CLASS.
    """

    def __init__(self, main_window=None, parent=None):
        super().__init__(None)
        self._main_window = main_window or parent
        self.setWindowTitle("Media Downloader")
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(820, 640)
        self.setMinimumSize(660, 500)

        # Standalone top-level window flag
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

        self._worker = None
        self._dep_worker = None
        self._current_video_data = None
        self._current_playlist_data = None

        self.setStyleSheet("""
            QPushButton:disabled {
                color: palette(disabled, button-text);
                background-color: palette(disabled, window);
                border: 1px solid palette(disabled, mid);
                opacity: 0.45;
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

        # 0. Dependency Engines & Status Section (Above Enter URL)
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

        input_layout.addWidget(self.txt_url)
        input_layout.addWidget(self.btn_paste)
        input_layout.addWidget(self.btn_analyze)
        main_layout.addLayout(input_layout)

        # 3. Status Bar & Progress
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: gray;")
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
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

        self.lbl_video_title = QLabel("Video Title")
        font_title = QFont()
        font_title.setPointSize(11)
        font_title.setBold(True)
        self.lbl_video_title.setFont(font_title)
        self.lbl_video_title.setWordWrap(True)
        layout.addWidget(self.lbl_video_title)

        self.lbl_video_meta = QLabel("Uploader: Unknown | Duration: 0s")
        self.lbl_video_meta.setStyleSheet("color: gray;")
        layout.addWidget(self.lbl_video_meta)

        # Row 1: Media Quality Preset + Video Format Dropdown + Audio Format Dropdown
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)

        lbl_preset = QLabel("Quality Preset:")
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
            "Audio Only (MP3)"
        ])
        self.cmb_quality_preset.currentIndexChanged.connect(self._on_preset_changed)

        lbl_vfmt = QLabel("Video:")
        self.cmb_video_format = QComboBox()
        self.cmb_video_format.setFixedHeight(30)
        self.cmb_video_format.setToolTip("Filter video container / codec")
        self.cmb_video_format.addItems([
            "All Formats",
            "MP4 (H.264 / AVC)",
            "WEBM (VP9 / AV1)",
            "AV1 Codec",
            "VP9 Codec",
            "H.264 Codec"
        ])
        self.cmb_video_format.currentIndexChanged.connect(self._on_preset_changed)

        lbl_afmt = QLabel("Audio:")
        self.cmb_audio_format = QComboBox()
        self.cmb_audio_format.setFixedHeight(30)
        self.cmb_audio_format.setToolTip("Filter audio container / codec")
        self.cmb_audio_format.addItems([
            "All Formats",
            "MP3 Audio",
            "M4A / AAC Audio",
            "OPUS Audio"
        ])
        self.cmb_audio_format.currentIndexChanged.connect(self._on_preset_changed)

        preset_layout.addWidget(lbl_preset)
        preset_layout.addWidget(self.cmb_quality_preset, stretch=2)
        preset_layout.addWidget(lbl_vfmt)
        preset_layout.addWidget(self.cmb_video_format, stretch=2)
        preset_layout.addWidget(lbl_afmt)
        preset_layout.addWidget(self.cmb_audio_format, stretch=2)
        layout.addLayout(preset_layout)

        # Row 2: Checkboxes for Manual Selection Mode & Preferences Persistence
        chk_layout = QHBoxLayout()
        chk_layout.setSpacing(15)

        self.chk_manual_selection = QCheckBox("Use Manual Format Selection from Table below")
        self.chk_manual_selection.setToolTip("Check to manually pick a stream row from the table below; uncheck to use preset controls")
        self.chk_manual_selection.toggled.connect(self._on_manual_selection_toggled)

        self.chk_save_defaults = QCheckBox("Save Default Preferences")
        self.chk_save_defaults.setToolTip("Persist currently selected quality, formats, and selection mode for future downloads")
        self.chk_save_defaults.toggled.connect(self._save_preferences_if_enabled)

        chk_layout.addWidget(self.chk_manual_selection)
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
        
        font_tbl = self.tbl_formats.font()
        font_tbl.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.tbl_formats.setFont(font_tbl)

        layout.addWidget(self.tbl_formats, stretch=1)

    def _setup_playlist_page(self):
        layout = QVBoxLayout(self.page_playlist)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.lbl_playlist_title = QLabel("Playlist Title")
        font_pl = QFont()
        font_pl.setPointSize(11)
        font_pl.setBold(True)
        self.lbl_playlist_title.setFont(font_pl)
        layout.addWidget(self.lbl_playlist_title)

        ctrl_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setFixedWidth(90)
        self.btn_select_all.clicked.connect(lambda: self._set_all_playlist_checked(True))

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setFixedWidth(90)
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_playlist_checked(False))

        self.lbl_select_count = QLabel("0 of 0 items selected")
        self.lbl_select_count.setStyleSheet("font-weight: bold;")

        ctrl_layout.addWidget(self.btn_select_all)
        ctrl_layout.addWidget(self.btn_deselect_all)
        ctrl_layout.addWidget(self.lbl_select_count)
        ctrl_layout.addStretch()

        layout.addLayout(ctrl_layout)

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
            "Audio Only (MP3)"
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
                lbl_name.setStyleSheet("color: #e5a50a; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name}: ({ver_text})")
            elif status_color == "green":
                lbl_name.setStyleSheet("color: #2ec27e; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name} Version: {ver_text}")
            else:
                lbl_name.setStyleSheet("color: gray; font-weight: bold;")
                btn_info.setToolTip(f"{tool_name}: Not Installed")

    def _on_ctrl_v_paste(self):
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            return
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.txt_url.setText(text)
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
                    self._worker.requestInterruption()
                    self._worker.quit()
                    self._worker.wait(1000)
                    if self._worker.isRunning():
                        self._worker.terminate()
                        self._worker.wait(1000)
                except Exception:
                    pass
        self._finish_loading()
        self.lbl_status.setText("Analysis cancelled.")

    def start_analysis(self):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter or paste a media link.")
            return

        self.txt_url.setEnabled(False)
        self.btn_paste.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.btn_analyze.setText("Stop")
        self.btn_analyze.setToolTip("Stop ongoing link analysis")
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("Analyzing link...")

        self._worker = MediaExtractorWorker(url)
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

        self.lbl_video_title.setText(data.get("title", "Untitled Media"))
        dur_sec = int(data.get("duration") or 0)
        dur_str = f"{dur_sec // 60}m {dur_sec % 60:02d}s" if dur_sec else "Unknown"
        self.lbl_video_meta.setText(f"Uploader: {data.get('uploader')} | Duration: {dur_str}")

        formats = data.get("formats", [])
        self.tbl_formats.setRowCount(0)

        for row_idx, fmt in enumerate(formats):
            self.tbl_formats.insertRow(row_idx)
            self.tbl_formats.setItem(row_idx, 0, QTableWidgetItem(str(fmt["format_id"])))
            self.tbl_formats.setItem(row_idx, 1, QTableWidgetItem(str(fmt["res_label"])))
            self.tbl_formats.setItem(row_idx, 2, QTableWidgetItem(str(fmt["ext"])))
            
            codec_info = fmt["vcodec"] if fmt["vcodec"] != "none" else fmt["acodec"]
            self.tbl_formats.setItem(row_idx, 3, QTableWidgetItem(str(codec_info)))
            
            tbr_str = f"{int(fmt['tbr'])} kbps" if fmt["tbr"] else "-"
            self.tbl_formats.setItem(row_idx, 4, QTableWidgetItem(tbr_str))
            
            size_mb = f"{fmt['filesize'] / (1024*1024):.1f} MB" if fmt["filesize"] else "-"
            self.tbl_formats.setItem(row_idx, 5, QTableWidgetItem(size_mb))

        if formats:
            self.tbl_formats.selectRow(0)

        self._update_preset_availability(data)
        self.stack.setCurrentWidget(self.page_video)
        self.btn_download.setText("Download Media")
        self.btn_download.setEnabled(True)

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
            ("Audio Only (MP3)", has_audio)
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

    def _reset_preset_labels(self):
        preset_items = [
            "Best Quality (Video + Audio merged)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "360p Low Quality",
            "Audio Only (MP3)"
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

        self.stack.setCurrentWidget(self.page_playlist)
        self.btn_download.setEnabled(True)

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
        self.lbl_status.setText("Analysis failed.")
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
            target_row = self._find_format_row_by_height(target_height)

        self.tbl_formats.selectRow(target_row)

    def _on_manual_selection_toggled(self, checked: bool):
        self.cmb_quality_preset.setEnabled(not checked)
        self.cmb_video_format.setEnabled(not checked)
        self.cmb_audio_format.setEnabled(not checked)
        self._save_preferences_if_enabled()

    def _on_format_table_selection_changed(self):
        if self.chk_manual_selection.isChecked():
            self._save_preferences_if_enabled()

    def _find_format_row_by_height(self, target_height: int) -> int:
        formats = self._current_video_data.get("formats", [])
        for i, fmt in enumerate(formats):
            if fmt.get("height") == target_height:
                return i
        return 0

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

        self.chk_manual_selection.setChecked(use_manual)
        self.chk_save_defaults.setChecked(save_defaults)

        self.cmb_quality_preset.setEnabled(not use_manual)
        self.cmb_video_format.setEnabled(not use_manual)
        self.cmb_audio_format.setEnabled(not use_manual)

        self.cmb_quality_preset.blockSignals(False)
        self.cmb_video_format.blockSignals(False)
        self.cmb_audio_format.blockSignals(False)
        self.chk_manual_selection.blockSignals(False)
        self.chk_save_defaults.blockSignals(False)

    def _save_preferences_if_enabled(self):
        if hasattr(self, "chk_save_defaults") and self.chk_save_defaults.isChecked():
            from core.config import load_category_config, save_category_config
            config = load_category_config()
            config["media_downloader_defaults"] = {
                "preset_idx": self.cmb_quality_preset.currentIndex(),
                "video_format_idx": self.cmb_video_format.currentIndex(),
                "audio_format_idx": self.cmb_audio_format.currentIndex(),
                "use_manual_selection": self.chk_manual_selection.isChecked(),
                "save_defaults": True
            }
            save_category_config(config)

    def _get_single_video_format_spec(self) -> tuple[str, bool]:
        """
        Returns tuple (format_spec, is_audio_only).
        If Manual Selection is checked, uses selected format ID from table.
        Otherwise builds format_spec using quality preset, video format filter, and audio format filter.
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
        vfmt_idx = self.cmb_video_format.currentIndex()
        afmt_idx = self.cmb_audio_format.currentIndex()

        # Audio-only preset
        if preset_idx == 7:
            if afmt_idx == 1:
                return ("bestaudio[ext=mp3]/bestaudio/best", True)
            elif afmt_idx == 2:
                return ("bestaudio[ext=m4a]/bestaudio/best", True)
            elif afmt_idx == 3:
                return ("bestaudio[acodec^=opus]/bestaudio/best", True)
            return ("bestaudio/best", True)

        height_limit = None
        if preset_idx == 1: height_limit = 2160     # 4K
        elif preset_idx == 2: height_limit = 1440   # 2K
        elif preset_idx == 3: height_limit = 1080   # 1080p
        elif preset_idx == 4: height_limit = 720    # 720p
        elif preset_idx == 5: height_limit = 480    # 480p
        elif preset_idx == 6: height_limit = 360    # 360p

        vfilter = ""
        if vfmt_idx == 1: vfilter = "[ext=mp4]"
        elif vfmt_idx == 2: vfilter = "[ext=webm]"
        elif vfmt_idx == 3: vfilter = "[vcodec^=av01]"
        elif vfmt_idx == 4: vfilter = "[vcodec^=vp9]"
        elif vfmt_idx == 5: vfilter = "[vcodec^=avc]"

        afilter = ""
        if afmt_idx == 1: afilter = "[ext=mp3]"
        elif afmt_idx == 2: afilter = "[ext=m4a]"
        elif afmt_idx == 3: afilter = "[acodec^=opus]"

        if height_limit:
            v_spec = f"bestvideo[height<={height_limit}]{vfilter}"
            a_spec = f"bestaudio{afilter}"
            format_spec = f"{v_spec}+{a_spec}/{v_spec}/best[height<={height_limit}]/best"
        else:
            v_spec = f"bestvideo{vfilter}"
            a_spec = f"bestaudio{afilter}"
            format_spec = f"{v_spec}+{a_spec}/{v_spec}/best"

        return (format_spec, False)

    def _get_playlist_format_spec(self) -> tuple[str, bool]:
        """Returns format spec for playlist items based on global playlist quality dropdown."""
        idx = self.cmb_playlist_quality.currentIndex()
        if idx == 0:
            return ("bestvideo+bestaudio/best", False)
        elif idx == 1:
            return ("bestvideo[height<=2160]+bestaudio/best[height<=2160]/best", False)
        elif idx == 2:
            return ("bestvideo[height<=1440]+bestaudio/best[height<=1440]/best", False)
        elif idx == 3:
            return ("bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", False)
        elif idx == 4:
            return ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", False)
        elif idx == 5:
            return ("bestvideo[height<=480]+bestaudio/best[height<=480]/best", False)
        elif idx == 6:
            return ("bestaudio/best", True)

        return ("bestvideo+bestaudio/best", False)

    def _on_download_clicked(self):
        self._save_preferences_if_enabled()
        mw = self.main_win
        if not mw:
            QMessageBox.warning(self, "Main Window Missing", "Cannot locate main application window.")
            return

        if self.stack.currentWidget() == self.page_video and self._current_video_data:
            title = self._current_video_data.get("title", "video")
            webpage_url = self._current_video_data.get("webpage_url") or self.txt_url.text().strip()
            format_spec, is_audio_only = self._get_single_video_format_spec()
            
            clean_title = re.sub(r'[\\/*?:"<>|]', "_", title)
            ext = ".mp3" if is_audio_only else ".mp4"
            filename = f"{clean_title}{ext}"

            if hasattr(mw, "start_media_download"):
                mw.start_media_download(
                    url=webpage_url,
                    filename=filename,
                    format_spec=format_spec,
                    is_audio_only=is_audio_only
                )
            else:
                mw.process_incoming_url(webpage_url)
            
            self.accept()

        elif self.stack.currentWidget() == self.page_playlist and self._current_playlist_data:
            entries = self._current_playlist_data.get("entries", [])
            format_spec, is_audio_only = self._get_playlist_format_spec()
            enqueued = 0

            for r in range(self.tbl_playlist.rowCount()):
                item = self.tbl_playlist.item(r, 0)
                if item and item.checkState() == Qt.CheckState.Checked and r < len(entries):
                    entry = entries[r]
                    item_url = entry["url"]
                    item_title = entry.get("title", f"video_{r+1}")
                    clean_title = re.sub(r'[\\/*?:"<>|]', "_", item_title)
                    ext = ".mp3" if is_audio_only else ".mp4"
                    filename = f"{clean_title}{ext}"

                    if hasattr(mw, "start_media_download"):
                        mw.start_media_download(
                            url=item_url,
                            filename=filename,
                            format_spec=format_spec,
                            is_audio_only=is_audio_only
                        )
                    else:
                        mw.process_incoming_url(item_url)
                    enqueued += 1

            self.accept()

    def closeEvent(self, event):
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            try:
                self._worker.requestInterruption()
                self._worker.quit()
                self._worker.wait(1000)
                if self._worker.isRunning():
                    self._worker.terminate()
                    self._worker.wait(1000)
            except Exception:
                pass
        if hasattr(self, "_dep_worker") and self._dep_worker and self._dep_worker.isRunning():
            try:
                self._dep_worker.requestInterruption()
                self._dep_worker.quit()
                self._dep_worker.wait(1000)
            except Exception:
                pass
        super().closeEvent(event)
