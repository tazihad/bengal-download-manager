"""
Media Downloader Dialog for Bengal Download Manager.
Provides link input, media link parsing, quality chooser, and playlist batch selection.
"""

import sys
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QApplication, QFrame, QCheckBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon
from core.media_downloader import YtDlpManager, MediaExtractorWorker


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
        self.resize(740, 560)
        self.setMinimumSize(600, 450)

        # Standalone top-level window flag
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

        self._worker = None
        self._current_video_data = None
        self._current_playlist_data = None

        self._setup_ui()

    @property
    def main_win(self):
        return getattr(self, "_main_window", None) or self.parent()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # 1. Header Area: "Enter URL"
        lbl_header = QLabel("Enter URL")
        header_font = QFont()
        header_font.setPointSize(13)
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
        self.txt_url.setToolTip("Enter direct video URL or playlist link to analyze")

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedHeight(34)
        self.btn_paste.setFixedWidth(75)
        self.btn_paste.setToolTip("Paste URL from clipboard")
        self.btn_paste.clicked.connect(self._paste_clipboard)

        self.btn_analyze = QPushButton("Analyze Link")
        self.btn_analyze.setFixedHeight(34)
        self.btn_analyze.setFixedWidth(110)
        self.btn_analyze.setDefault(True)
        self.btn_analyze.setToolTip("Parse media formats or playlist items using yt-dlp")
        self.btn_analyze.clicked.connect(self.start_analysis)

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
        lbl_empty = QLabel("Enter a video or playlist link above and click 'Analyze Link' to view download options.")
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
        self.btn_download.setToolTip("Start download for selected format (merges video + audio) or playlist items")
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

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Media Quality Preset:"))
        
        self.cmb_quality_preset = QComboBox()
        self.cmb_quality_preset.setFixedHeight(30)
        self.cmb_quality_preset.setToolTip("Select quality preset (auto-merges Video + Audio)")
        self.cmb_quality_preset.addItems([
            "Best Quality (Video + Audio merged)",
            "1080p Full HD (Video + Audio)",
            "720p HD (Video + Audio)",
            "480p SD (Video + Audio)",
            "360p Low Quality",
            "Audio Only (MP3)"
        ])
        self.cmb_quality_preset.currentIndexChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.cmb_quality_preset, stretch=1)
        layout.addLayout(preset_layout)

        lbl_streams = QLabel("Available Formats & Streams:")
        layout.addWidget(lbl_streams)

        self.tbl_formats = QTableWidget()
        self.tbl_formats.setColumnCount(6)
        self.tbl_formats.setHorizontalHeaderLabels(["Format ID", "Resolution", "Extension", "Codec", "Bitrate", "Size Est."])
        self.tbl_formats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_formats.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_formats.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_formats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
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

    def _paste_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.txt_url.setText(text)
            self.start_analysis()

    def start_analysis(self):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter or paste a media link.")
            return

        self.btn_analyze.setEnabled(False)
        self.txt_url.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("Analyzing link...")
        self.btn_download.setEnabled(False)

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

        self.stack.setCurrentWidget(self.page_video)
        self.btn_download.setText("Download Media")
        self.btn_download.setEnabled(True)

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

    def _on_analysis_failed(self, error_msg: str):
        self._finish_loading()
        self.lbl_status.setText("Analysis failed.")
        QMessageBox.critical(self, "Extraction Error", f"Failed to analyze URL:\n{error_msg}")

    def _finish_loading(self):
        self.btn_analyze.setEnabled(True)
        self.txt_url.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Analysis finished.")

    def _on_preset_changed(self, idx: int):
        if not self._current_video_data:
            return
        formats = self._current_video_data.get("formats", [])
        if not formats:
            return

        target_row = 0
        if idx == 0:
            target_row = 0
        elif idx == 1:
            target_row = self._find_format_row_by_height(1080)
        elif idx == 2:
            target_row = self._find_format_row_by_height(720)
        elif idx == 3:
            target_row = self._find_format_row_by_height(480)
        elif idx == 4:
            target_row = self._find_format_row_by_height(360)
        elif idx == 5:
            target_row = self._find_audio_only_row()

        self.tbl_formats.selectRow(target_row)

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

    def _get_single_video_format_spec(self) -> tuple[str, bool]:
        """Returns tuple (format_spec, is_audio_only) based on preset or format selection."""
        idx = self.cmb_quality_preset.currentIndex()
        if idx == 0:
            return ("bestvideo+bestaudio/best", False)
        elif idx == 1:
            return ("bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", False)
        elif idx == 2:
            return ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", False)
        elif idx == 3:
            return ("bestvideo[height<=480]+bestaudio/best[height<=480]/best", False)
        elif idx == 4:
            return ("bestvideo[height<=360]+bestaudio/best[height<=360]/best", False)
        elif idx == 5:
            return ("bestaudio/best", True)

        # Fallback to selected row format
        sel_rows = self.tbl_formats.selectionModel().selectedRows()
        if sel_rows and self._current_video_data:
            row_idx = sel_rows[0].row()
            formats = self._current_video_data.get("formats", [])
            if row_idx < len(formats):
                fmt = formats[row_idx]
                if fmt.get("is_video") and not fmt.get("is_audio"):
                    return (f"{fmt['format_id']}+bestaudio/best", False)
                elif fmt.get("is_audio") and not fmt.get("is_video"):
                    return (f"{fmt['format_id']}", True)
                else:
                    return (fmt["format_id"], False)

        return ("bestvideo+bestaudio/best", False)

    def _get_playlist_format_spec(self) -> tuple[str, bool]:
        """Returns format spec for playlist items based on global playlist quality dropdown."""
        idx = self.cmb_playlist_quality.currentIndex()
        if idx == 0:
            return ("bestvideo+bestaudio/best", False)
        elif idx == 1:
            return ("bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", False)
        elif idx == 2:
            return ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", False)
        elif idx == 3:
            return ("bestvideo[height<=480]+bestaudio/best[height<=480]/best", False)
        elif idx == 4:
            return ("bestaudio/best", True)

        return ("bestvideo+bestaudio/best", False)

    def _on_download_clicked(self):
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
