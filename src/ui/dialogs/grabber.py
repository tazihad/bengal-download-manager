"""
Bengal Site Grabber Dialog
==========================
Allows users to crawl websites to a specified depth, filter media and files
by preset categories or custom wildcard masks, and batch-download matching resources.
"""

import os
import urllib.parse
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QApplication, QFrame, QCheckBox, QAbstractItemView,
    QFileDialog, QSpinBox, QMenu
)
from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QFont, QIcon, QDesktopServices, QCursor, QColor

from core.grabber.crawler import GrabberCrawler
from core.utils import format_bytes, get_user_downloads_dir
from core.services.theme_service import get_file_icon, get_category_for_filename


GRABBER_PRESETS = {
    "All Files (*.*)": ["*.*"],
    "Images (*.jpg, *.png, *.webp, *.gif, *.svg)": [
        "*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif", "*.svg", "*.bmp", "*.ico", "*.tif", "*.tiff"
    ],
    "Videos (*.mp4, *.mkv, *.webm, *.avi, *.mov)": [
        "*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv", "*.wmv", "*.m4v", "*.mpg", "*.mpeg"
    ],
    "Audio (*.mp3, *.wav, *.flac, *.ogg, *.m4a)": [
        "*.mp3", "*.wav", "*.flac", "*.ogg", "*.m4a", "*.aac", "*.wma", "*.opus"
    ],
    "Documents (*.pdf, *.epub, *.doc, *.docx, *.txt)": [
        "*.pdf", "*.epub", "*.doc", "*.docx", "*.txt", "*.xlsx", "*.pptx", "*.odt"
    ],
    "Compressed Archives (*.zip, *.rar, *.7z, *.tar, *.gz)": [
        "*.zip", "*.rar", "*.7z", "*.tar", "*.gz", "*.bz2", "*.xz", "*.tgz", "*.zst"
    ],
    "Custom Filters...": []
}


def _apply_tabular_font(widget, point_size: int = 9, bold: bool = False):
    font = QFont(widget.font())
    font.setPointSize(point_size)
    font.setBold(bold)
    font.setFeature(QFont.Tag.fromString("tnum"), 1)
    widget.setFont(font)


class GrabberDialog(QDialog):
    """
    Site Grabber window for exploring URLs and batch harvesting downloadable files.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.crawler: Optional[GrabberCrawler] = None
        self.discovered_items: List[Dict[str, Any]] = []
        self._url_to_row: Dict[str, int] = {}

        self.setWindowTitle(self.tr("Site Grabber — Bengal Download Manager"))
        self.resize(980, 620)
        self.setMinimumSize(820, 520)

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # -----------------------------------------------------------------
        # 1. Configuration Panel (Card)
        # -----------------------------------------------------------------
        config_card = QFrame()
        config_card.setStyleSheet("""
            QFrame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(config_card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        # Row 1: Start URL Input & Action Buttons
        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        lbl_url = QLabel(self.tr("Start URL:"))
        lbl_url.setStyleSheet("font-weight: bold; border: none; background: transparent;")
        url_row.addWidget(lbl_url)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://example.com/gallery or website address to crawl")
        self.txt_url.setClearButtonEnabled(True)
        self.txt_url.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: palette(base);
                color: palette(text);
            }
            QLineEdit:focus {
                border: 1px solid palette(highlight);
            }
        """)
        url_row.addWidget(self.txt_url, 1)

        self.btn_explore = QPushButton(self.tr("Explore Site"))
        self.btn_explore.setStyleSheet("""
            QPushButton {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        self.btn_explore.clicked.connect(self.start_exploration)
        url_row.addWidget(self.btn_explore)

        self.btn_stop = QPushButton(self.tr("Stop"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:disabled {
                background-color: palette(mid);
                color: palette(placeholder-text);
            }
        """)
        self.btn_stop.clicked.connect(self.stop_exploration)
        url_row.addWidget(self.btn_stop)

        card_layout.addLayout(url_row)

        # Row 2: Presets, Depth, and Save Directory
        options_row = QHBoxLayout()
        options_row.setSpacing(12)

        lbl_preset = QLabel(self.tr("File Type:"))
        lbl_preset.setStyleSheet("border: none; background: transparent;")
        options_row.addWidget(lbl_preset)

        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(list(GRABBER_PRESETS.keys()))
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        options_row.addWidget(self.cmb_preset, 1)

        lbl_depth = QLabel(self.tr("Levels to Explore:"))
        lbl_depth.setStyleSheet("border: none; background: transparent;")
        options_row.addWidget(lbl_depth)

        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(1, 5)
        self.spin_depth.setValue(1)
        self.spin_depth.setToolTip(self.tr("1 = Only the start page\n2 = Start page + links on start page\n3+ = Deeper exploration"))
        options_row.addWidget(self.spin_depth)

        lbl_save = QLabel(self.tr("Save To:"))
        lbl_save.setStyleSheet("border: none; background: transparent;")
        options_row.addWidget(lbl_save)

        default_save = get_user_downloads_dir()
        self.txt_save_path = QLineEdit(default_save)
        self.txt_save_path.setReadOnly(True)
        self.txt_save_path.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: palette(base);
                color: palette(text);
            }
        """)
        options_row.addWidget(self.txt_save_path, 1)

        btn_browse = QPushButton(self.tr("Browse..."))
        btn_browse.clicked.connect(self._browse_save_folder)
        options_row.addWidget(btn_browse)

        card_layout.addLayout(options_row)

        # Row 3: Custom mask filter (shown when custom is selected) & Toggles
        filter_row = QHBoxLayout()
        filter_row.setSpacing(14)

        self.lbl_custom_mask = QLabel(self.tr("Custom Wildcards:"))
        self.lbl_custom_mask.setStyleSheet("border: none; background: transparent;")
        self.txt_custom_mask = QLineEdit("*.jpg, *.png, *.mp4")
        self.txt_custom_mask.setPlaceholderText("e.g. *.pdf, *.zip, doc_*")
        self.txt_custom_mask.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: palette(base);
            }
        """)
        self.lbl_custom_mask.setVisible(False)
        self.txt_custom_mask.setVisible(False)
        filter_row.addWidget(self.lbl_custom_mask)
        filter_row.addWidget(self.txt_custom_mask, 1)

        self.chk_same_domain = QCheckBox(self.tr("Stay on same domain"))
        self.chk_same_domain.setChecked(True)
        self.chk_same_domain.setStyleSheet("border: none; background: transparent;")
        filter_row.addWidget(self.chk_same_domain)

        self.chk_hide_dupes = QCheckBox(self.tr("Hide duplicate files"))
        self.chk_hide_dupes.setChecked(True)
        self.chk_hide_dupes.setStyleSheet("border: none; background: transparent;")
        filter_row.addWidget(self.chk_hide_dupes)

        filter_row.addStretch()
        card_layout.addLayout(filter_row)

        main_layout.addWidget(config_card)

        # -----------------------------------------------------------------
        # 2. Results Header Bar (Search & Bulk selection)
        # -----------------------------------------------------------------
        results_ctrl_row = QHBoxLayout()
        results_ctrl_row.setSpacing(8)

        lbl_found_title = QLabel(self.tr("Discovered Files:"))
        lbl_found_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        results_ctrl_row.addWidget(lbl_found_title)

        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText(self.tr("Filter results by name or extension..."))
        self.txt_filter.setClearButtonEnabled(True)
        self.txt_filter.textChanged.connect(self._apply_table_filter)
        self.txt_filter.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: palette(base);
                max-width: 280px;
            }
        """)
        results_ctrl_row.addWidget(self.txt_filter)

        results_ctrl_row.addStretch()

        btn_select_all = QPushButton(self.tr("Select All"))
        btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        results_ctrl_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton(self.tr("Deselect All"))
        btn_deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        results_ctrl_row.addWidget(btn_deselect_all)

        main_layout.addLayout(results_ctrl_row)

        # -----------------------------------------------------------------
        # 3. Results Table
        # -----------------------------------------------------------------
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            self.tr("File Name"),
            self.tr("Type"),
            self.tr("Size"),
            self.tr("URL"),
            self.tr("Source Page")
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemChanged.connect(self._on_table_item_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(4, 200)

        main_layout.addWidget(self.table, 1)

        # -----------------------------------------------------------------
        # 4. Bottom Status & Download Action Row
        # -----------------------------------------------------------------
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate during crawl
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setMaximumWidth(160)

        # Status text
        self.lbl_status = QLabel(self.tr("Ready. Enter a start URL and click 'Explore Site'."))
        self.lbl_status.setStyleSheet("color: palette(window-text); font-size: 11px;")

        # Counter summary badge
        self.lbl_summary = QLabel("0 files (0 B)")
        _apply_tabular_font(self.lbl_summary, point_size=10, bold=True)
        self.lbl_summary.setStyleSheet("""
            QLabel {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)

        bottom_row.addWidget(self.progress_bar)
        bottom_row.addWidget(self.lbl_status, 1)
        bottom_row.addWidget(self.lbl_summary)

        self.btn_download = QPushButton(self.tr("Download Selected"))
        self.btn_download.setEnabled(False)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
            QPushButton:disabled {
                background-color: palette(mid);
                color: palette(placeholder-text);
            }
        """)
        self.btn_download.clicked.connect(self.download_selected)
        bottom_row.addWidget(self.btn_download)

        btn_close = QPushButton(self.tr("Close"))
        btn_close.clicked.connect(self.close)
        bottom_row.addWidget(btn_close)

        main_layout.addLayout(bottom_row)

    # -----------------------------------------------------------------
    # Controller Slots & Handlers
    # -----------------------------------------------------------------
    def _on_preset_changed(self, index: int):
        preset_name = self.cmb_preset.currentText()
        is_custom = "Custom" in preset_name
        self.lbl_custom_mask.setVisible(is_custom)
        self.txt_custom_mask.setVisible(is_custom)

    def _browse_save_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Download Destination Folder"),
            self.txt_save_path.text() or get_user_downloads_dir()
        )
        if folder:
            self.txt_save_path.setText(folder)

    def start_exploration(self):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("Missing URL"), self.tr("Please enter a website start page URL."))
            self.txt_url.setFocus()
            return

        import re
        import ipaddress
        # Extract URL if pasted with leading or trailing words (e.g. "h5ai http://...")
        m = re.search(r"https?://\S+", url)
        if m:
            url = m.group(0)
            self.txt_url.setText(url)
        elif not (url.startswith("http://") or url.startswith("https://")):
            host_candidate = url.split("/")[0].split(":")[0]
            try:
                ipaddress.ip_address(host_candidate)
                url = "http://" + url
            except ValueError:
                if host_candidate.lower() in ("localhost", "127.0.0.1"):
                    url = "http://" + url
                else:
                    url = "https://" + url
            self.txt_url.setText(url)

        # Clear previous exploration results
        self.table.setRowCount(0)
        self.discovered_items.clear()
        self._url_to_row.clear()

        # Collect patterns
        preset_name = self.cmb_preset.currentText()
        if "Custom" in preset_name:
            masks_text = self.txt_custom_mask.text().strip()
            patterns = [m.strip() for m in masks_text.split(",") if m.strip()]
            if not patterns:
                patterns = ["*.*"]
        else:
            patterns = GRABBER_PRESETS.get(preset_name, ["*.*"])

        config = {
            "start_url": url,
            "explore_depth": self.spin_depth.value(),
            "stay_same_domain": self.chk_same_domain.isChecked(),
            "dont_explore_parent_dirs": True,
            "allow_private_hosts": True,
            "hide_duplicates": self.chk_hide_dupes.isChecked(),
            "file_include_patterns": patterns,
            "save_path": self.txt_save_path.text().strip(),
        }

        self.btn_explore.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText(self.tr("Connecting and exploring site..."))

        self.crawler = GrabberCrawler(config, parent=self)
        self.crawler.progress_changed.connect(self._on_progress_changed)
        self.crawler.file_found.connect(self._on_file_found)
        self.crawler.metadata_updated.connect(self._on_metadata_updated)
        self.crawler.crawl_finished.connect(self._on_crawl_finished)
        self.crawler.crawl_failed.connect(self._on_crawl_failed)
        self.crawler.start()

    def stop_exploration(self):
        if self.crawler and self.crawler.isRunning():
            self.crawler.cancel()
            self.lbl_status.setText(self.tr("Stopping exploration..."))
            self.btn_stop.setEnabled(False)

    def _on_progress_changed(self, text: str):
        self.lbl_status.setText(text)

    def _on_file_found(self, item: dict):
        self.discovered_items.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)

        url = item["url"]
        filename = item["filename"]
        self._url_to_row[url] = row

        # Col 0: Filename with checkbox and themed icon
        item_col0 = QTableWidgetItem(filename)
        item_col0.setFlags(item_col0.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item_col0.setCheckState(Qt.CheckState.Checked)
        item_col0.setIcon(get_file_icon(filename))
        item_col0.setToolTip(filename)
        self.table.setItem(row, 0, item_col0)

        # Col 1: Category / Type
        category = get_category_for_filename(filename)
        ext = item.get("extension", "").upper()
        type_str = f"{category} ({ext})" if ext else category
        item_col1 = QTableWidgetItem(type_str)
        self.table.setItem(row, 1, item_col1)

        # Col 2: Size
        size_str = format_bytes(item["size"]) if item["size"] > 0 else self.tr("Probing...")
        item_col2 = QTableWidgetItem(size_str)
        _apply_tabular_font(item_col2, point_size=9)
        self.table.setItem(row, 2, item_col2)

        # Col 3: URL
        item_col3 = QTableWidgetItem(url)
        item_col3.setToolTip(url)
        self.table.setItem(row, 3, item_col3)

        # Col 4: Source Page
        source = item.get("source_page", "")
        item_col4 = QTableWidgetItem(source)
        item_col4.setToolTip(source)
        self.table.setItem(row, 4, item_col4)

        self._update_summary()

    def _on_metadata_updated(self, url: str, size_bytes: int):
        for idx, itm in enumerate(self.discovered_items):
            if itm["url"] == url:
                itm["size"] = size_bytes
                break

        row = self._url_to_row.get(url)
        if row is not None and row < self.table.rowCount():
            item_size = self.table.item(row, 2)
            if item_size:
                item_size.setText(format_bytes(size_bytes))
        self._update_summary()

    def _on_crawl_finished(self, results: list):
        self.progress_bar.setVisible(False)
        self.btn_explore.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.crawler = None
        self._update_summary()

    def _on_crawl_failed(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_explore.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"Exploration error: {error_msg}")
        QMessageBox.warning(self, self.tr("Exploration Notice"), error_msg)
        self.crawler = None

    def _update_summary(self):
        total_files = self.table.rowCount()
        checked_files = 0
        total_bytes = 0

        for r in range(total_files):
            col0 = self.table.item(r, 0)
            if col0 and col0.checkState() == Qt.CheckState.Checked:
                checked_files += 1
                if r < len(self.discovered_items):
                    sz = self.discovered_items[r].get("size", 0)
                    if sz > 0:
                        total_bytes += sz

        self.lbl_summary.setText(f"Selected: {checked_files} / {total_files} files ({format_bytes(total_bytes)})")
        self.btn_download.setEnabled(checked_files > 0)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item and item.column() == 0:
            row = item.row()
            if 0 <= row < len(self.discovered_items):
                self.discovered_items[row]["checked"] = (item.checkState() == Qt.CheckState.Checked)
            self._update_summary()

    def _set_all_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                item = self.table.item(r, 0)
                if item:
                    item.setCheckState(state)
                if r < len(self.discovered_items):
                    self.discovered_items[r]["checked"] = checked
        self.table.blockSignals(False)
        self._update_summary()

    def _apply_table_filter(self, query: str):
        q = query.strip().lower()
        for r in range(self.table.rowCount()):
            if not q:
                self.table.setRowHidden(r, False)
                continue
            name_item = self.table.item(r, 0)
            url_item = self.table.item(r, 3)
            name_text = name_item.text().lower() if name_item else ""
            url_text = url_item.text().lower() if url_item else ""
            matches = (q in name_text) or (q in url_text)
            self.table.setRowHidden(r, not matches)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        act_check = menu.addAction(self.tr("Check Selected"))
        act_uncheck = menu.addAction(self.tr("Uncheck Selected"))
        menu.addSeparator()
        act_copy = menu.addAction(self.tr("Copy Download URL"))
        act_open_browser = menu.addAction(self.tr("Open URL in Browser"))
        menu.addSeparator()
        act_select_all = menu.addAction(self.tr("Select All"))
        act_deselect_all = menu.addAction(self.tr("Deselect All"))

        action = menu.exec(self.table.mapToGlobal(pos))
        selected_rows = set(item.row() for item in self.table.selectedItems())

        if action == act_check:
            for r in selected_rows:
                it = self.table.item(r, 0)
                if it:
                    it.setCheckState(Qt.CheckState.Checked)
            self._update_summary()
        elif action == act_uncheck:
            for r in selected_rows:
                it = self.table.item(r, 0)
                if it:
                    it.setCheckState(Qt.CheckState.Unchecked)
            self._update_summary()
        elif action == act_copy:
            for r in selected_rows:
                it = self.table.item(r, 3)
                if it:
                    QApplication.clipboard().setText(it.text())
                    break
        elif action == act_open_browser:
            for r in selected_rows:
                it = self.table.item(r, 3)
                if it:
                    QDesktopServices.openUrl(QUrl(it.text()))
                    break
        elif action == act_select_all:
            self._set_all_checked(True)
        elif action == act_deselect_all:
            self._set_all_checked(False)

    def download_selected(self):
        """Dispatches all checked files to Bengal Download Manager's download queue."""
        selected_items = []
        for r in range(self.table.rowCount()):
            item0 = self.table.item(r, 0)
            if item0 and item0.checkState() == Qt.CheckState.Checked:
                if r < len(self.discovered_items):
                    selected_items.append(self.discovered_items[r])

        if not selected_items:
            QMessageBox.information(self, self.tr("No Files Selected"), self.tr("Please check one or more files to download."))
            return

        save_dir = self.txt_save_path.text().strip() or get_user_downloads_dir()
        added_count = 0

        if self.main_window and hasattr(self.main_window, "start_download"):
            for item in selected_items:
                try:
                    self.main_window.start_download(
                        url=item["url"],
                        custom_filename=item.get("filename"),
                        custom_save_dir=save_dir,
                        start_paused=False,
                        show_dialog=False,
                        referer=item.get("source_page")
                    )
                    added_count += 1
                except Exception:
                    pass

        QMessageBox.information(
            self,
            self.tr("Downloads Added"),
            self.tr(f"Successfully added {added_count} file{'s' if added_count != 1 else ''} to the download queue.")
        )
        self.accept()

    def closeEvent(self, event):
        self.stop_exploration()
        if self.crawler and self.crawler.isRunning():
            self.crawler.wait(500)
        super().closeEvent(event)
