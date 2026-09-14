"""
Bengal Download Manager — Batch Download Review Dialog
======================================================
Review, filter, probe, rename, and queue multiple downloads in one unified interface.
Supports wildcard batch renaming, per-category save routing, queue selection,
and asynchronous file size probing.
"""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QRect, QPoint
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QPen, QBrush, QPainter
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QRadioButton, QButtonGroup, QGroupBox, QComboBox, QFileDialog, QFrame,
    QMessageBox, QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem
)

from core.config import load_category_config
from core.database import get_all_queues
from core.services.theme_service import get_file_icon, get_category_for_filename, get_themed_icon
from core.utils import format_bytes, get_user_downloads_dir, resolve_filename
from core.workers.batch_prober import BatchProberManager
from ui.components import SortableTableWidgetItem


class BatchCheckTableWidgetItem(QTableWidgetItem):
    """Table item for checkbox column supporting sorting by checked state."""
    def __lt__(self, other):
        c1 = 1 if self.checkState() == Qt.CheckState.Checked else 0
        c2 = 1 if (other and other.checkState() == Qt.CheckState.Checked) else 0
        return c1 < c2


def _apply_tabular_font(widget, point_size: int = 9, bold: bool = False):
    font = QFont(widget.font())
    font.setPointSize(point_size)
    font.setBold(bold)
    font.setFeature(QFont.Tag.fromString('tnum'), 1)
    widget.setFont(font)


class BatchCheckBoxDelegate(QStyledItemDelegate):
    """Custom delegate for column 0 to ensure high contrast, visible checkboxes in all themes and selection states."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw cell selection / hover background
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_selected:
            painter.fillRect(option.rect, option.palette.brush(QPalette.ColorRole.Highlight))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, option.palette.brush(QPalette.ColorRole.AlternateBase))

        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        size = 15
        x = option.rect.x() + (option.rect.width() - size) // 2
        y = option.rect.y() + (option.rect.height() - size) // 2
        box_rect = QRect(x, y, size, size)

        is_checked = (check_state in (Qt.CheckState.Checked, 2))
        is_dark = option.palette.color(QPalette.ColorRole.Base).value() < 128

        if is_selected:
            border_color = QColor("#ffffff") if is_dark else QColor("#000000")
            bg_color = QColor(20, 22, 24) if is_dark else QColor("#ffffff")
        else:
            border_color = QColor("#555555") if is_dark else option.palette.color(QPalette.ColorRole.Mid)
            bg_color = option.palette.color(QPalette.ColorRole.Base)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2))
        painter.drawRoundedRect(box_rect, 3.0, 3.0)

        if is_checked:
            check_color = QColor("#ffffff") if is_dark else QColor("#111111")
            pen = QPen(check_color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            p1 = QPoint(x + int(size * 0.22), y + int(size * 0.52))
            p2 = QPoint(x + int(size * 0.45), y + int(size * 0.75))
            p3 = QPoint(x + int(size * 0.80), y + int(size * 0.28))
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.LeftButton:
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                current = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if current in (Qt.CheckState.Checked, 2) else Qt.CheckState.Checked
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
        elif event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space:
                current = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if current in (Qt.CheckState.Checked, 2) else Qt.CheckState.Checked
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
        return super().editorEvent(event, model, option, index)


class BatchItemEditDialog(QDialog):
    """Dialog to customize save path, URL, description, referer, and credentials for a single batch item."""
    def __init__(self, item_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit File"))
        self.setWindowIcon(get_themed_icon("add_url"))
        self.setMinimumWidth(520)
        self.resize(540, 320)

        self.item_data = dict(item_data)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel(self.tr("Edit File Details"))
        _apply_tabular_font(title, point_size=11, bold=True)
        layout.addWidget(title)

        # File Name
        row_fn = QHBoxLayout()
        lbl_fn = QLabel(self.tr("File name:"))
        lbl_fn.setFixedWidth(80)
        self.txt_filename = QLineEdit(self.item_data.get("filename", ""))
        self.txt_filename.setFixedHeight(28)
        row_fn.addWidget(lbl_fn)
        row_fn.addWidget(self.txt_filename)
        layout.addLayout(row_fn)

        # Save Path
        row_sp = QHBoxLayout()
        lbl_sp = QLabel(self.tr("Save to:"))
        lbl_sp.setFixedWidth(80)
        self.txt_save_path = QLineEdit(self.item_data.get("custom_save_dir", ""))
        self.txt_save_path.setFixedHeight(28)
        btn_browse = QPushButton(self.tr("Browse"))
        btn_browse.setFixedHeight(28)
        btn_browse.setMinimumWidth(80)
        btn_browse.clicked.connect(self._browse_save_path)
        row_sp.addWidget(lbl_sp)
        row_sp.addWidget(self.txt_save_path)
        row_sp.addWidget(btn_browse)
        layout.addLayout(row_sp)

        # URL
        row_url = QHBoxLayout()
        lbl_url = QLabel(self.tr("URL:"))
        lbl_url.setFixedWidth(80)
        self.txt_url = QLineEdit(self.item_data.get("url", ""))
        self.txt_url.setFixedHeight(28)
        row_url.addWidget(lbl_url)
        row_url.addWidget(self.txt_url)
        layout.addLayout(row_url)

        # Description
        row_desc = QHBoxLayout()
        lbl_desc = QLabel(self.tr("Description:"))
        lbl_desc.setFixedWidth(80)
        self.txt_desc = QLineEdit(self.item_data.get("description", ""))
        self.txt_desc.setFixedHeight(28)
        row_desc.addWidget(lbl_desc)
        row_desc.addWidget(self.txt_desc)
        layout.addLayout(row_desc)

        # Referer
        row_ref = QHBoxLayout()
        lbl_ref = QLabel(self.tr("Referer:"))
        lbl_ref.setFixedWidth(80)
        self.txt_ref = QLineEdit(self.item_data.get("referer", ""))
        self.txt_ref.setFixedHeight(28)
        row_ref.addWidget(lbl_ref)
        row_ref.addWidget(self.txt_ref)
        layout.addLayout(row_ref)

        # Credentials
        row_cred = QHBoxLayout()
        lbl_user = QLabel(self.tr("Username:"))
        lbl_user.setFixedWidth(80)
        self.txt_user = QLineEdit(self.item_data.get("username", ""))
        self.txt_user.setFixedHeight(28)
        lbl_pass = QLabel(self.tr("Password:"))
        self.txt_pass = QLineEdit(self.item_data.get("password", ""))
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setFixedHeight(28)
        row_cred.addWidget(lbl_user)
        row_cred.addWidget(self.txt_user)
        row_cred.addWidget(lbl_pass)
        row_cred.addWidget(self.txt_pass)
        layout.addLayout(row_cred)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton(self.tr("Cancel"))
        btn_cancel.setFixedHeight(30)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton(self.tr("Save"))
        btn_save.setDefault(True)
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def _browse_save_path(self):
        curr = self.txt_save_path.text().strip() or get_user_downloads_dir()
        d = QFileDialog.getExistingDirectory(self, self.tr("Select Save Directory"), curr)
        if d:
            self.txt_save_path.setText(d)

    def _on_save(self):
        self.item_data["filename"] = self.txt_filename.text().strip()
        self.item_data["custom_save_dir"] = self.txt_save_path.text().strip()
        self.item_data["url"] = self.txt_url.text().strip()
        self.item_data["description"] = self.txt_desc.text().strip()
        self.item_data["referer"] = self.txt_ref.text().strip()
        self.item_data["username"] = self.txt_user.text().strip()
        self.item_data["password"] = self.txt_pass.text()
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return self.item_data


class BatchDownloadDialog(QDialog):
    """
    Main Batch Download Review and Queueing Dialog.
    Displays all items in a batch, supports wildcard renaming, filters,
    asynchronous size probing, category routing, and queue assignment.
    """
    batch_accepted = pyqtSignal(list)

    COL_CHECK = 0
    COL_NAME = 1
    COL_SIZE = 2
    COL_STATUS = 3
    COL_URL = 4
    COL_LINK_TEXT = 5
    COL_SAVETO = 6

    IMAGE_EXTENSIONS = (
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp", ".ico", ".tif", ".tiff"
    )

    def __init__(self, urls_or_items: List[Any], parent=None, main_window=None, is_import: bool = False, auto_probe: bool = True):
        super().__init__(parent)
        self.main_window = main_window
        self.is_import = is_import

        title = self.tr("Import Links to Bengal Download Manager") if is_import else self.tr("Batch Download Review")
        self.setWindowTitle(title)
        self.setWindowIcon(get_themed_icon("add_url"))
        self.setMinimumSize(860, 520)
        self.resize(1040, 700)

        # Raw item list: each is a dict
        self._items: List[Dict[str, Any]] = []
        self._overrides: Dict[int, Dict[str, Any]] = {}
        self._filtered_indices: List[int] = []
        self._idx_to_items: Dict[int, Dict[str, QTableWidgetItem]] = {}

        # Load category directory mappings
        self._cat_config = load_category_config()

        # Asynchronous prober
        self._prober = BatchProberManager(max_concurrent=6, parent=self)
        self._prober.probe_finished.connect(self._on_probe_result)

        self._parse_incoming(urls_or_items)
        self._init_ui()
        self._apply_filters()
        if auto_probe:
            self._start_probing()

    def _parse_incoming(self, raw_list: List[Any]):
        self._items.clear()
        for idx, entry in enumerate(raw_list):
            if isinstance(entry, str):
                url = entry.strip()
                if not url:
                    continue
                name = resolve_filename(url, {})
                self._items.append({
                    "orig_index": idx,
                    "url": url,
                    "base_filename": name,
                    "filename": name,
                    "link_text": "",
                    "description": "",
                    "size_bytes": -1,
                    "size_str": "",
                    "status": "Checking...",
                    "checked": True,
                    "custom_save_dir": "",
                    "referer": "",
                    "username": "",
                    "password": ""
                })
            elif isinstance(entry, dict):
                url = entry.get("url", "").strip()
                if not url:
                    continue
                name = entry.get("filename") or entry.get("name") or resolve_filename(url, {})
                link_text = entry.get("link_text") or entry.get("linkText") or entry.get("text") or ""
                self._items.append({
                    "orig_index": idx,
                    "url": url,
                    "base_filename": name,
                    "filename": name,
                    "link_text": str(link_text),
                    "description": entry.get("description", ""),
                    "size_bytes": entry.get("size_bytes", -1),
                    "size_str": entry.get("size_str", ""),
                    "status": "Found" if entry.get("size_bytes", -1) > 0 else "Checking...",
                    "checked": bool(entry.get("checked", True)),
                    "custom_save_dir": entry.get("save_dir") or entry.get("savePath") or "",
                    "referer": entry.get("referer", ""),
                    "username": entry.get("username", ""),
                    "password": entry.get("password", "")
                })

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # ── Top Header ───────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_title = QLabel(self.windowTitle())
        _apply_tabular_font(header_title, point_size=13, bold=True)
        header_layout.addWidget(header_title)

        header_sub = QLabel(
            self.tr("Check the links you want to download, configure options, and click OK.")
        )
        header_sub.setStyleSheet("opacity: 0.8;")
        header_layout.addWidget(header_sub, 1)

        self.lbl_selected_summary = QLabel("")
        _apply_tabular_font(self.lbl_selected_summary, point_size=9, bold=True)
        self.lbl_selected_summary.setStyleSheet("color: palette(highlight);")
        header_layout.addWidget(self.lbl_selected_summary)

        main_layout.addLayout(header_layout)

        # ── Wildcard Batch Rename Card ───────────────────────────────────────
        rename_frame = QFrame()
        rename_frame.setStyleSheet("""
            QFrame {
                border: 1px solid palette(mid);
                border-radius: 5px;
                background-color: palette(alternate-base);
                padding: 4px;
            }
        """)
        rename_layout = QHBoxLayout(rename_frame)
        rename_layout.setContentsMargins(10, 6, 10, 6)
        rename_layout.setSpacing(8)

        lbl_pat = QLabel(self.tr("Replace filenames with wildcard pattern (*):"))
        _apply_tabular_font(lbl_pat, point_size=9, bold=True)
        rename_layout.addWidget(lbl_pat)

        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText(self.tr("e.g. file*.zip or episode_*.mkv"))
        self.txt_pattern.setFixedHeight(28)
        self.txt_pattern.textChanged.connect(self._on_pattern_changed)
        rename_layout.addWidget(self.txt_pattern, 1)

        main_layout.addWidget(rename_frame)

        # ── Table Widget ─────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "", self.tr("File name"), self.tr("Size"), self.tr("Status"),
            self.tr("Download from"), self.tr("Link Text"), self.tr("Save to")
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.verticalHeader().setMinimumSectionSize(24)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                selection-color: palette(highlighted-text);
                selection-background-color: palette(highlight);
                outline: 0;
            }
            QTableWidget::item:selected, QTableWidget::item:selected:active, QTableWidget::item:selected:!active {
                color: palette(highlighted-text);
                background-color: palette(highlight);
                outline: 0;
                border: none;
            }
            QTableWidget::item:focus {
                border: none;
                outline: 0;
            }
        """)
        # Ensure inactive selection retains active selection colors so highlighted rows don't look unselected on focus loss
        t_palette = self.table.palette()
        t_palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, t_palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight))
        t_palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, t_palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText))
        self.table.setPalette(t_palette)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_CHECK, 36)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(self.COL_NAME, 220)
        header.setSectionResizeMode(self.COL_SIZE, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(self.COL_SIZE, 95)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(self.COL_STATUS, 100)
        header.setSectionResizeMode(self.COL_URL, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(self.COL_URL, 240)
        header.setSectionResizeMode(self.COL_LINK_TEXT, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(self.COL_LINK_TEXT, 140)
        header.setSectionResizeMode(self.COL_SAVETO, QHeaderView.ResizeMode.Stretch)

        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._update_edit_button_state)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.table.setItemDelegateForColumn(self.COL_CHECK, BatchCheckBoxDelegate(self.table))
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        main_layout.addWidget(self.table, 1)

        # ── Bottom Options Split (Save Destination & Filters) ────────────────
        bottom_options_layout = QHBoxLayout()
        bottom_options_layout.setSpacing(12)

        # --- Left Card: Save to Destination ---
        grp_dest = QGroupBox(self.tr("Save to:"))
        grp_dest_layout = QVBoxLayout(grp_dest)
        grp_dest_layout.setContentsMargins(10, 8, 10, 8)
        grp_dest_layout.setSpacing(6)

        self.radio_per_category = QRadioButton(
            self.tr("Every file to directory according to file category")
        )
        self.radio_per_category.setChecked(True)
        self.radio_per_category.toggled.connect(self._on_dest_mode_changed)

        one_cat_layout = QHBoxLayout()
        one_cat_layout.setSpacing(8)
        self.radio_one_category = QRadioButton(self.tr("All files to category:"))
        self.radio_one_category.toggled.connect(self._on_dest_mode_changed)

        self.combo_category = QComboBox()
        self.combo_category.setFixedHeight(28)
        cats = list(self._cat_config.get("categories", {}).keys())
        if not cats:
            cats = ["General", "Programs", "Video", "Documents", "Music", "Compressed"]
        self.combo_category.addItems(cats)
        self.combo_category.currentTextChanged.connect(self._on_dest_mode_changed)
        self.combo_category.setEnabled(False)
        one_cat_layout.addWidget(self.radio_one_category)
        one_cat_layout.addWidget(self.combo_category, 1)

        self.radio_one_dir = QRadioButton(self.tr("All files to one directory:"))
        self.radio_one_dir.toggled.connect(self._on_dest_mode_changed)

        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(6)
        dir_layout.setContentsMargins(18, 0, 0, 0)
        self.txt_save_dir = QLineEdit(get_user_downloads_dir())
        self.txt_save_dir.setFixedHeight(28)
        self.txt_save_dir.setEnabled(False)
        self.txt_save_dir.textChanged.connect(self._on_dest_mode_changed)
        self.btn_browse_dir = QPushButton(self.tr("Browse"))
        self.btn_browse_dir.setFixedHeight(28)
        self.btn_browse_dir.setMinimumWidth(80)
        self.btn_browse_dir.setEnabled(False)
        self.btn_browse_dir.clicked.connect(self._browse_one_directory)
        dir_layout.addWidget(self.txt_save_dir, 1)
        dir_layout.addWidget(self.btn_browse_dir)

        self.dest_btn_group = QButtonGroup(self)
        self.dest_btn_group.addButton(self.radio_per_category)
        self.dest_btn_group.addButton(self.radio_one_category)
        self.dest_btn_group.addButton(self.radio_one_dir)

        grp_dest_layout.addWidget(self.radio_per_category)
        grp_dest_layout.addLayout(one_cat_layout)
        grp_dest_layout.addWidget(self.radio_one_dir)
        grp_dest_layout.addLayout(dir_layout)
        bottom_options_layout.addWidget(grp_dest, 1)

        # --- Right Card: Filters and Selection ---
        grp_filters = QGroupBox(self.tr("Filters and Selection"))
        grp_filters_layout = QVBoxLayout(grp_filters)
        grp_filters_layout.setContentsMargins(10, 8, 10, 8)
        grp_filters_layout.setSpacing(5)

        filter_btn_layout = QHBoxLayout()
        filter_btn_layout.setSpacing(6)
        self.btn_edit = QPushButton(self.tr("Edit File"))
        self.btn_edit.setFixedHeight(28)
        self.btn_edit.setMinimumWidth(80)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_selected_row)
        filter_btn_layout.addWidget(self.btn_edit)

        filter_btn_layout.addStretch()
        self.btn_check_all = QPushButton(self.tr("Check all"))
        self.btn_check_all.setFixedHeight(28)
        self.btn_check_all.setMinimumWidth(85)
        self.btn_check_all.clicked.connect(lambda: self._set_all_checked(True))
        filter_btn_layout.addWidget(self.btn_check_all)

        self.btn_uncheck_all = QPushButton(self.tr("Uncheck all"))
        self.btn_uncheck_all.setFixedHeight(28)
        self.btn_uncheck_all.setMinimumWidth(95)
        self.btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))
        filter_btn_layout.addWidget(self.btn_uncheck_all)
        grp_filters_layout.addLayout(filter_btn_layout)

        self.chk_use_link_text = QCheckBox(self.tr("Use link texts as descriptions"))
        self.chk_use_link_text.setChecked(True)
        grp_filters_layout.addWidget(self.chk_use_link_text)

        self.chk_hide_html = QCheckBox(self.tr("Hide HTML files (*.html, *.htm)"))
        self.chk_hide_html.toggled.connect(self._apply_filters)
        grp_filters_layout.addWidget(self.chk_hide_html)

        self.chk_hide_images = QCheckBox(self.tr("Hide webpage images (*.jpg, *.png, *.webp, *.svg)"))
        self.chk_hide_images.toggled.connect(self._apply_filters)
        grp_filters_layout.addWidget(self.chk_hide_images)

        self.chk_hide_duplicates = QCheckBox(self.tr("Hide repeated files"))
        self.chk_hide_duplicates.toggled.connect(self._apply_filters)
        grp_filters_layout.addWidget(self.chk_hide_duplicates)

        bottom_options_layout.addWidget(grp_filters, 1)
        main_layout.addLayout(bottom_options_layout)

        # ── Queue Assignment & Action Bar ────────────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        lbl_queue = QLabel(self.tr("Add to queue:"))
        _apply_tabular_font(lbl_queue, point_size=9, bold=True)
        bottom_bar.addWidget(lbl_queue)

        self.combo_queue = QComboBox()
        self.combo_queue.setFixedHeight(30)
        self.combo_queue.setMinimumWidth(180)
        queues = get_all_queues() or []
        queue_names = [q.get("name") for q in queues if isinstance(q, dict) and q.get("name")]
        if "Main download queue" not in queue_names:
            queue_names.insert(0, "Main download queue")
        self.combo_queue.addItems(queue_names)
        bottom_bar.addWidget(self.combo_queue)

        self.chk_start_immediate = QCheckBox(self.tr("Start downloading immediately"))
        self.chk_start_immediate.setChecked(True)
        bottom_bar.addWidget(self.chk_start_immediate)

        bottom_bar.addStretch()

        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setFixedWidth(84)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(self.tr("OK"))
        self.btn_ok.setDefault(True)
        self.btn_ok.setFixedHeight(32)
        self.btn_ok.setFixedWidth(84)
        self.btn_ok.clicked.connect(self._on_accept)
        bottom_bar.addWidget(self.btn_ok)

        main_layout.addLayout(bottom_bar)

    def _browse_one_directory(self):
        curr = self.txt_save_dir.text().strip() or get_user_downloads_dir()
        d = QFileDialog.getExistingDirectory(self, self.tr("Select Destination Directory"), curr)
        if d:
            self.txt_save_dir.setText(d)

    def _on_dest_mode_changed(self):
        is_one_cat = self.radio_one_category.isChecked()
        is_one_dir = self.radio_one_dir.isChecked()
        self.combo_category.setEnabled(is_one_cat)
        self.txt_save_dir.setEnabled(is_one_dir)
        self.btn_browse_dir.setEnabled(is_one_dir)
        self._refresh_table_save_paths()

    def _effective_save_dir(self, item: Dict[str, Any]) -> str:
        # Check custom item override
        custom_dir = item.get("custom_save_dir")
        if custom_dir:
            return custom_dir

        if self.radio_one_dir.isChecked():
            return self.txt_save_dir.text().strip() or get_user_downloads_dir()

        if self.radio_one_category.isChecked():
            chosen_cat = self.combo_category.currentText().strip() or "General"
            cats = self._cat_config.get("categories", {})
            return cats.get(chosen_cat, {}).get("path") or get_user_downloads_dir()

        # Default: perCategory
        fn = item.get("filename") or item.get("base_filename", "")
        cat = get_category_for_filename(fn)
        cats = self._cat_config.get("categories", {})
        return cats.get(cat, {}).get("path") or get_user_downloads_dir()

    def _refresh_table_save_paths(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            item_data = self._get_row_data(r)
            if item_data:
                save_path = self._effective_save_dir(item_data)
                saveto_item = self.table.item(r, self.COL_SAVETO)
                if saveto_item:
                    saveto_item.setText(save_path)
                    saveto_item.setToolTip(save_path)
        self.table.blockSignals(False)

    def _apply_pattern_to_name(self, base_name: str) -> str:
        pattern = self.txt_pattern.text().strip()
        if not pattern:
            return base_name
        if "*" not in pattern:
            return pattern
        return pattern.replace("*", base_name, 1)

    def _on_pattern_changed(self):
        for item in self._items:
            base = item.get("base_filename", "")
            item["filename"] = self._apply_pattern_to_name(base)
        self._populate_table()

    def _apply_filters(self):
        filtered: List[int] = []
        seen_urls = set()

        hide_html = self.chk_hide_html.isChecked()
        hide_img = self.chk_hide_images.isChecked()
        hide_dup = self.chk_hide_duplicates.isChecked()

        for idx, item in enumerate(self._items):
            url_lower = item.get("url", "").lower().split("?")[0]

            if hide_html and (url_lower.endswith(".html") or url_lower.endswith(".htm")):
                continue

            if hide_img and any(url_lower.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                continue

            if hide_dup:
                if url_lower in seen_urls:
                    continue
                seen_urls.add(url_lower)

            filtered.append(idx)

        self._filtered_indices = filtered
        self._populate_table()

    def _populate_table(self):
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            self.table.blockSignals(True)
            self.table.setRowCount(len(self._filtered_indices))
            self._idx_to_items.clear()

            checked_count = 0
            total_count = len(self._filtered_indices)

            for row, orig_idx in enumerate(self._filtered_indices):
                item = self._items[orig_idx]

                # Checkbox
                chk_item = BatchCheckTableWidgetItem()
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                chk_item.setCheckState(Qt.CheckState.Checked if item.get("checked", True) else Qt.CheckState.Unchecked)
                chk_item.setData(Qt.ItemDataRole.UserRole, orig_idx)
                self.table.setItem(row, self.COL_CHECK, chk_item)
                if item.get("checked", True):
                    checked_count += 1

                # Filename & Icon
                fn = item.get("filename", "")
                name_item = SortableTableWidgetItem(fn)
                name_item.setIcon(get_file_icon(fn))
                name_item.setToolTip(fn)

                # Size
                size_str = item.get("size_str", "") or ("-" if item.get("status") == "Checking..." else "")
                size_item = SortableTableWidgetItem(size_str)
                sz_bytes = item.get("size_bytes", -1)
                size_item.setData(Qt.ItemDataRole.UserRole, sz_bytes if sz_bytes is not None else -1)
                _apply_tabular_font(size_item, point_size=9)

                # Status
                status_str = item.get("status", "Checking...")
                status_item = SortableTableWidgetItem(status_str)

                # URL
                url_item = SortableTableWidgetItem(item.get("url", ""))
                url_item.setToolTip(item.get("url", ""))

                # Link Text
                lt_item = SortableTableWidgetItem(item.get("link_text", ""))
                lt_item.setToolTip(item.get("link_text", ""))

                # Save To
                save_path = self._effective_save_dir(item)
                saveto_item = SortableTableWidgetItem(save_path)
                saveto_item.setToolTip(save_path)

                row_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                name_item.setFlags(row_flags)
                size_item.setFlags(row_flags)
                status_item.setFlags(row_flags)
                url_item.setFlags(row_flags)
                lt_item.setFlags(row_flags)
                saveto_item.setFlags(row_flags)

                self.table.setItem(row, self.COL_NAME, name_item)
                self.table.setItem(row, self.COL_SIZE, size_item)
                self.table.setItem(row, self.COL_STATUS, status_item)
                self.table.setItem(row, self.COL_URL, url_item)
                self.table.setItem(row, self.COL_LINK_TEXT, lt_item)
                self.table.setItem(row, self.COL_SAVETO, saveto_item)

                self._idx_to_items[orig_idx] = {
                    "name": name_item,
                    "size": size_item,
                    "status": status_item,
                    "url": url_item,
                    "link_text": lt_item,
                    "saveto": saveto_item,
                    "check": chk_item,
                }

            self.table.blockSignals(False)
        finally:
            self.table.setSortingEnabled(was_sorting)
        self._update_summary(checked_count, total_count)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == self.COL_CHECK:
            orig_idx = item.data(Qt.ItemDataRole.UserRole)
            if orig_idx is not None and 0 <= orig_idx < len(self._items):
                is_checked = item.checkState() == Qt.CheckState.Checked
                self._items[orig_idx]["checked"] = is_checked
                checked_count = sum(1 for idx in self._filtered_indices if self._items[idx].get("checked", True))
                self._update_summary(checked_count, len(self._filtered_indices))

    def _set_all_checked(self, checked: bool):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            chk_item = self.table.item(r, self.COL_CHECK)
            if chk_item:
                chk_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                orig_idx = chk_item.data(Qt.ItemDataRole.UserRole)
                if orig_idx is not None and 0 <= orig_idx < len(self._items):
                    self._items[orig_idx]["checked"] = checked
        self.table.blockSignals(False)
        self._update_summary(len(self._filtered_indices) if checked else 0, len(self._filtered_indices))

    def _update_summary(self, checked_count: int, total_count: int):
        self.lbl_selected_summary.setText(
            self.tr(f"{checked_count} of {total_count} file{'s' if total_count != 1 else ''} selected")
        )
        self.btn_ok.setEnabled(checked_count > 0)

    def _start_probing(self):
        """Starts asynchronous probing for all items."""
        self._prober.probe_items(self._items)

    def _on_probe_result(self, orig_idx: int, result: Dict[str, Any]):
        if orig_idx < 0 or orig_idx >= len(self._items):
            return

        item = self._items[orig_idx]
        item["status"] = result.get("status", "Found")
        item["size_bytes"] = result.get("size_bytes", -1)
        item["size_str"] = result.get("size_str", "")

        # If Content-Disposition resolved a better filename and user hasn't typed a pattern
        resolved_name = result.get("filename")
        if resolved_name and not self.txt_pattern.text().strip():
            item["base_filename"] = resolved_name
            item["filename"] = resolved_name

        # Update matching table row if currently visible
        row_items = self._idx_to_items.get(orig_idx)
        if row_items:
            self.table.blockSignals(True)
            size_item = row_items.get("size")
            if size_item:
                size_item.setText(item["size_str"])
                size_item.setData(Qt.ItemDataRole.UserRole, item["size_bytes"])

            status_item = row_items.get("status")
            if status_item:
                status_item.setText(item["status"])

            name_item = row_items.get("name")
            if name_item:
                name_item.setText(item["filename"])
                name_item.setIcon(get_file_icon(item["filename"]))
            self.table.blockSignals(False)
        elif orig_idx in self._filtered_indices:
            row = self._filtered_indices.index(orig_idx)
            if row < self.table.rowCount():
                self.table.blockSignals(True)

                size_item = self.table.item(row, self.COL_SIZE)
                if size_item:
                    size_item.setText(item["size_str"])
                    size_item.setData(Qt.ItemDataRole.UserRole, item["size_bytes"])

                status_item = self.table.item(row, self.COL_STATUS)
                if status_item:
                    status_item.setText(item["status"])

                name_item = self.table.item(row, self.COL_NAME)
                if name_item:
                    name_item.setText(item["filename"])
                    name_item.setIcon(get_file_icon(item["filename"]))

                self.table.blockSignals(False)

    def _get_row_data(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < self.table.rowCount():
            chk_item = self.table.item(row, self.COL_CHECK)
            if chk_item:
                orig_idx = chk_item.data(Qt.ItemDataRole.UserRole)
                if orig_idx is not None and 0 <= orig_idx < len(self._items):
                    return self._items[orig_idx]
        if 0 <= row < len(self._filtered_indices):
            orig_idx = self._filtered_indices[row]
            return self._items[orig_idx]
        return None

    def _update_edit_button_state(self):
        self.btn_edit.setEnabled(len(self.table.selectedItems()) > 0)

    def _on_row_double_clicked(self, item: QTableWidgetItem):
        self._edit_selected_row()

    def _edit_selected_row(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        item_data = self._get_row_data(row)
        if not item_data:
            return

        dlg = BatchItemEditDialog(item_data, parent=self)
        if dlg.exec():
            updated = dlg.get_data()
            chk_item = self.table.item(row, self.COL_CHECK)
            orig_idx = chk_item.data(Qt.ItemDataRole.UserRole) if chk_item else None
            if orig_idx is not None and 0 <= orig_idx < len(self._items):
                self._items[orig_idx].update(updated)
            elif 0 <= row < len(self._filtered_indices):
                self._items[self._filtered_indices[row]].update(updated)
            self._populate_table()

    def _on_accept(self):
        self._prober.stop_all()

        chosen_queue = self.combo_queue.currentText().strip() or "Main download queue"
        start_immediate = self.chk_start_immediate.isChecked()
        use_link_text = self.chk_use_link_text.isChecked()

        accepted_files: List[Dict[str, Any]] = []
        for idx in self._filtered_indices:
            item = self._items[idx]
            if not item.get("checked", True):
                continue

            save_dir = self._effective_save_dir(item)
            desc = item.get("description", "")
            if not desc and use_link_text:
                desc = item.get("link_text", "")

            accepted_files.append({
                "url": item.get("url"),
                "filename": item.get("filename"),
                "save_dir": save_dir,
                "queue_name": chosen_queue,
                "start_paused": not start_immediate,
                "description": desc,
                "referer": item.get("referer"),
                "username": item.get("username"),
                "password": item.get("password")
            })

        if not accepted_files:
            QMessageBox.information(
                self,
                self.tr("No Files Selected"),
                self.tr("Please select at least one file to download.")
            )
            return

        if self.main_window and hasattr(self.main_window, "add_batch_downloads"):
            self.main_window.add_batch_downloads(accepted_files, queue_name=chosen_queue, start_immediate=start_immediate)
        elif self.main_window and hasattr(self.main_window, "start_download"):
            added_count = 0
            for f in accepted_files:
                try:
                    self.main_window.start_download(
                        url=f["url"],
                        custom_filename=f.get("filename"),
                        custom_save_dir=f.get("save_dir"),
                        start_paused=f.get("start_paused", False),
                        show_dialog=False,
                        referer=f.get("referer"),
                        queue_name=f.get("queue_name")
                    )
                    added_count += 1
                except Exception:
                    pass

            QMessageBox.information(
                self,
                self.tr("Batch Added"),
                self.tr(f"Successfully added {added_count} download{'s' if added_count != 1 else ''} to '{chosen_queue}'.")
            )

        self.batch_accepted.emit(accepted_files)
        self.accept()

    def closeEvent(self, event):
        self._prober.stop_all()
        super().closeEvent(event)
