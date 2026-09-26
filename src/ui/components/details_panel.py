"""
Bottom Details Panel Component
==============================
Provides a collapsible details panel underneath the main download table,
featuring General, Progress, and Connections tabs similar to Free Download Manager.

Tabs:
- General: Large file type icon, name, progress bar, file size, date added, destination folder, URL.
- Progress: Detailed metrics (percentage, bytes, speed, ETA, segments stats), discrete block visualizer
  with color-coded segments (downloaded, active remaining, failed), and legend.
- Connections: Table listing Host, Port, Connection Count, and Proxy status (Direct or Proxied).
"""

import os
from urllib.parse import urlparse
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileIconProvider, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QFileInfo, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush

from core.utils import format_bytes, show_in_folder, load_proxy_config, open_file_generic


def apply_tnum_font(widget, point_size: int = 0, bold: bool = False):
    """Applies OpenType tabular numbers font feature to a widget."""
    font = QFont(widget.font())
    if point_size > 0:
        font.setPointSize(point_size)
    if bold:
        font.setBold(True)
    font.setFeature(QFont.Tag.fromString("tnum"), 1)
    widget.setFont(font)


class SegmentGridWidget(QWidget):
    """
    Renders connection segments as a grid of discrete blocks.
    Matches FDM / Fasto style:
    Row index (e.g. 01, 02...), series of block cells, and completion percentage.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # List of dicts: [{"percent": 0.0, "status": "Pending...", "downloaded": 0, "total": 0}]
        self._segments = []
        self._num_segments = 8
        self._num_blocks_per_row = 60

        apply_tnum_font(self, point_size=8)

    def set_segment_data(self, segments_data, total_segments=8):
        """
        Updates segment progress.
        segments_data: list of dicts with keys: 'percent' (0-100), 'status', 'downloaded', 'total'
        """
        self._num_segments = max(1, total_segments)
        self._segments = segments_data or []
        self.update()

    def set_fallback_progress(self, overall_percent: float, num_segments: int = 8, is_complete: bool = False):
        """Generates synthetic segment progress from overall download percentage when workers are inactive."""
        self._num_segments = max(1, num_segments)
        segments = []
        if is_complete or overall_percent >= 100.0:
            for _ in range(self._num_segments):
                segments.append({"percent": 100.0, "status": "Complete", "failed": False})
        elif overall_percent <= 0.0:
            for _ in range(self._num_segments):
                segments.append({"percent": 0.0, "status": "Pending", "failed": False})
        else:
            # Distribute overall percent across segments realistically
            remaining_total = overall_percent * self._num_segments
            for i in range(self._num_segments):
                seg_p = min(100.0, max(0.0, remaining_total))
                remaining_total -= seg_p
                status = "Complete" if seg_p >= 100.0 else ("Downloading" if seg_p > 0 else "Pending")
                segments.append({"percent": seg_p, "status": status, "failed": False})
        self._segments = segments
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w = self.width()
        h = self.height()
        if w < 100 or h < 30:
            return

        num_segs = max(1, min(16, self._num_segments))
        row_height = max(6, int((h - 2) / num_segs))
        block_h = max(4, min(8, row_height - 2))

        grid_start_x = 0
        grid_width = max(50, w - 2)

        # Colors
        downloaded_color = QColor("#a855f7")  # Purple
        active_remaining_color = QColor("#784b28")  # Orange-brown tint for active remaining
        empty_block_color = QColor(60, 50, 45)  # Dim base block
        failed_color = QColor("#ef4444")  # Red

        # Calculate number of blocks that fit
        block_w = 6
        block_gap = 2
        num_blocks = max(10, int(grid_width / (block_w + block_gap)))

        for i in range(num_segs):
            y = i * row_height + int((row_height - block_h) / 2)
            if y + block_h > h:
                break

            seg_info = self._segments[i] if i < len(self._segments) else {"percent": 0.0, "status": "Pending"}
            seg_percent = float(seg_info.get("percent", 0.0))
            is_failed = seg_info.get("failed", False) or seg_info.get("status") == "Error"
            is_active = seg_info.get("status") in ["Receiving data...", "Downloading", "Active"]

            # Number of downloaded blocks
            filled_blocks = int(round((seg_percent / 100.0) * num_blocks))

            # Draw discrete blocks
            for b in range(num_blocks):
                bx = grid_start_x + b * (block_w + block_gap)
                rect = QRectF(bx, y, block_w, block_h)

                if is_failed:
                    color = failed_color
                elif b < filled_blocks:
                    color = downloaded_color
                elif is_active:
                    color = active_remaining_color
                else:
                    color = empty_block_color

                painter.fillRect(rect, color)


class DetailsPanel(QFrame):
    """
    Bottom collapsible details panel for Bengal Download Manager.
    Displays General, Progress, and Connections information for the selected download.
    """
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailsPanel")
        self.setMinimumHeight(210)
        self.current_download_data = {}
        self.current_worker = None

        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QFrame#detailsPanel {
                background-color: palette(window);
                border-top: 1px solid palette(mid);
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 6, 10, 8)
        main_layout.setSpacing(6)

        # --- Top Tab Bar Header ---
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.tab_buttons = []
        tab_names = ["General", "Progress", "Connections"]
        for idx, name in enumerate(tab_names):
            btn = QPushButton(name, self)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid transparent;
                    color: palette(window-text);
                    font-size: 11px;
                    font-weight: 500;
                    padding: 4px 12px;
                    border-radius: 0px;
                }
                QPushButton:hover {
                    color: palette(highlight);
                }
                QPushButton:checked {
                    color: palette(highlight);
                    border-bottom: 2px solid palette(highlight);
                    font-weight: 700;
                }
            """)
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            header_layout.addWidget(btn)
            self.tab_buttons.append(btn)

        self.tab_buttons[0].setChecked(True)

        header_layout.addStretch(1)

        # Close button (✕) on the far right
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Close details panel")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: palette(window-text);
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: palette(mid);
                color: palette(highlighted-text);
            }
        """)
        self.btn_close.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.btn_close)

        main_layout.addLayout(header_layout)

        # --- Stacked Widget for Tab Pages ---
        self.stacked_widget = QStackedWidget(self)

        self.page_general = self._create_general_tab()
        self.page_progress = self._create_progress_tab()
        self.page_connections = self._create_connections_tab()

        self.stacked_widget.addWidget(self.page_general)
        self.stacked_widget.addWidget(self.page_progress)
        self.stacked_widget.addWidget(self.page_connections)

        main_layout.addWidget(self.stacked_widget, 1)

    def switch_tab(self, index: int):
        self.stacked_widget.setCurrentIndex(index)
        for i, btn in enumerate(self.tab_buttons):
            btn.setChecked(i == index)

    # -------------------------------------------------------------
    # TAB 1: GENERAL
    # -------------------------------------------------------------
    def _create_general_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(14)

        # Left: Large file type icon
        self.gen_icon_label = QLabel(self)
        self.gen_icon_label.setFixedSize(64, 64)
        self.gen_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gen_icon_label.setStyleSheet("""
            QLabel {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.gen_icon_label, 0, Qt.AlignmentFlag.AlignTop)

        # Right: Metadata details
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)

        # Filename
        self.gen_filename_label = QLabel("No download selected", self)
        self.gen_filename_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f = QFont(self.gen_filename_label.font())
        f.setPointSize(12)
        f.setBold(True)
        self.gen_filename_label.setFont(f)
        info_layout.addWidget(self.gen_filename_label)

        # Progress bar + status
        pbar_row = QHBoxLayout()
        pbar_row.setSpacing(8)
        self.gen_progress_bar = QProgressBar(self)
        self.gen_progress_bar.setFixedHeight(8)
        self.gen_progress_bar.setTextVisible(False)
        self.gen_progress_bar.setRange(0, 1000)
        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: palette(highlight);
                border-radius: 3px;
            }
        """)
        pbar_row.addWidget(self.gen_progress_bar, 1)

        self.gen_status_label = QLabel("0% Idle", self)
        apply_tnum_font(self.gen_status_label, point_size=9, bold=True)
        pbar_row.addWidget(self.gen_status_label, 0)
        info_layout.addLayout(pbar_row)

        # Downloaded size & Added date row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(20)
        self.gen_size_label = QLabel("Downloaded: 0 B of 0 B", self)
        apply_tnum_font(self.gen_size_label, point_size=9)
        meta_row.addWidget(self.gen_size_label)

        self.gen_added_label = QLabel("Added at: --", self)
        apply_tnum_font(self.gen_added_label, point_size=9)
        meta_row.addWidget(self.gen_added_label)
        meta_row.addStretch(1)
        info_layout.addLayout(meta_row)

        # Destination Folder row
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        lbl_f_icon = QLabel("📁", self)
        lbl_f_icon.setFixedWidth(16)
        folder_row.addWidget(lbl_f_icon)

        self.gen_folder_btn = QPushButton("--", self)
        self.gen_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gen_folder_btn.setToolTip("Click to open containing folder")
        self.gen_folder_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: palette(highlight);
                text-align: left;
                font-size: 11px;
                padding: 0px;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.gen_folder_btn.clicked.connect(self._on_open_folder_clicked)
        folder_row.addWidget(self.gen_folder_btn, 1)
        info_layout.addLayout(folder_row)

        # File URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        lbl_u_icon = QLabel("🔗", self)
        lbl_u_icon.setFixedWidth(16)
        url_row.addWidget(lbl_u_icon)

        self.gen_url_label = QLabel("--", self)
        self.gen_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.gen_url_label.setStyleSheet("color: palette(window-text); font-size: 11px;")
        url_row.addWidget(self.gen_url_label, 1)
        info_layout.addLayout(url_row)

        info_layout.addStretch(1)
        layout.addLayout(info_layout, 1)

        return widget

    def _on_open_folder_clicked(self):
        filepath = self.current_download_data.get("filepath", "")
        if filepath:
            show_in_folder(filepath)

    # -------------------------------------------------------------
    # TAB 2: PROGRESS
    # -------------------------------------------------------------
    def _create_progress_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        # Top metrics row (Percent, Downloaded/Total, Speed, ETA)
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(16)

        self.prog_percent_label = QLabel("0.0%", self)
        apply_tnum_font(self.prog_percent_label, point_size=13, bold=True)
        metrics_row.addWidget(self.prog_percent_label)

        self.prog_bytes_label = QLabel("0 B / 0 B", self)
        apply_tnum_font(self.prog_bytes_label, point_size=10)
        metrics_row.addWidget(self.prog_bytes_label)

        metrics_row.addStretch(1)

        self.prog_speed_label = QLabel("0 B/s", self)
        apply_tnum_font(self.prog_speed_label, point_size=10, bold=True)
        metrics_row.addWidget(self.prog_speed_label)

        self.prog_eta_label = QLabel("ETA --", self)
        apply_tnum_font(self.prog_eta_label, point_size=10)
        metrics_row.addWidget(self.prog_eta_label)

        layout.addLayout(metrics_row)

        # Segments stats row (Segments count, Active, Failed, Live blocks)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        self.prog_segments_stat = QLabel("Segments: 0 / 8", self)
        apply_tnum_font(self.prog_segments_stat, point_size=9, bold=True)
        stats_row.addWidget(self.prog_segments_stat)

        self.prog_active_stat = QLabel("Active: 0", self)
        apply_tnum_font(self.prog_active_stat, point_size=9)
        stats_row.addWidget(self.prog_active_stat)

        self.prog_failed_stat = QLabel("Failed: 0", self)
        apply_tnum_font(self.prog_failed_stat, point_size=9)
        stats_row.addWidget(self.prog_failed_stat)

        self.prog_blocks_stat = QLabel("Live blocks: 480", self)
        apply_tnum_font(self.prog_blocks_stat, point_size=9)
        stats_row.addWidget(self.prog_blocks_stat)

        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        # Discrete Segment Block Visualizer
        self.segment_grid = SegmentGridWidget(self)
        layout.addWidget(self.segment_grid, 1)

        # Legend container at bottom with fixed height to prevent overlap
        legend_container = QWidget(self)
        legend_container.setFixedHeight(20)
        legend_row = QHBoxLayout(legend_container)
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(16)

        def make_legend_item(color_hex, label_text):
            item_box = QHBoxLayout()
            item_box.setSpacing(4)
            sq = QLabel(legend_container)
            sq.setFixedSize(9, 9)
            sq.setStyleSheet(f"background-color: {color_hex}; border-radius: 1px;")
            lbl = QLabel(label_text, legend_container)
            lbl.setStyleSheet("font-size: 10px; color: palette(placeholder-text);")
            item_box.addWidget(sq)
            item_box.addWidget(lbl)
            return item_box

        legend_row.addLayout(make_legend_item("#a855f7", "Purple = downloaded bytes"))
        legend_row.addLayout(make_legend_item("#f97316", "Orange = active remaining bytes"))
        legend_row.addLayout(make_legend_item("#ef4444", "Red = failed"))
        legend_row.addStretch(1)

        layout.addWidget(legend_container, 0)

        return widget

    # -------------------------------------------------------------
    # TAB 3: CONNECTIONS
    # -------------------------------------------------------------
    def _create_connections_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.conn_table = QTableWidget(self)
        apply_tnum_font(self.conn_table, point_size=9)
        self.conn_table.setColumnCount(4)
        headers = ["Host", "Port", "Connection count", "Proxy"]
        self.conn_table.setHorizontalHeaderLabels(headers)
        self.conn_table.verticalHeader().setVisible(False)
        self.conn_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conn_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.conn_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.conn_table.setShowGrid(False)

        header = self.conn_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.conn_table.setStyleSheet("""
            QTableWidget {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: palette(window);
                color: palette(window-text);
                font-weight: bold;
                border: none;
                border-bottom: 1px solid palette(mid);
                padding: 4px 8px;
            }
            QTableWidget::item {
                padding: 3px 8px;
            }
        """)

        layout.addWidget(self.conn_table)
        return widget

    # -------------------------------------------------------------
    # DATA UPDATE METHODS
    # -------------------------------------------------------------
    def set_download_data(self, data: dict, worker=None):
        """
        Populates all three tabs with the details of the given download.
        data dict keys:
          - filename: str
          - url: str
          - filepath: str
          - total_bytes: int / float
          - downloaded_bytes: int / float
          - status: str (e.g. "Downloading", "Paused", "Complete")
          - percent: float (0.0 to 100.0)
          - speed: str (e.g. "2.16 MB/s")
          - time_left: str (e.g. "2h 36m")
          - date_added: str
          - num_connections: int (default 8)
        """
        self.current_download_data = data or {}
        self.current_worker = worker

        filename = data.get("filename", "") or "No download selected"
        url = data.get("url", "")
        filepath = data.get("filepath", "")
        total_bytes = data.get("total_bytes", 0) or 0
        downloaded_bytes = data.get("downloaded_bytes", 0) or 0
        status = data.get("status", "") or "Idle"
        percent = float(data.get("percent", 0.0) or 0.0)
        speed = data.get("speed", "0 B/s") or "0 B/s"
        time_left = data.get("time_left", "--") or "--"
        date_added = data.get("date_added", "--") or "--"
        num_connections = data.get("num_connections", 8) or 8
        is_complete = status == "Complete" or percent >= 100.0

        # --- 1. Update General Tab ---
        self.gen_filename_label.setText(filename)
        self.gen_progress_bar.setValue(int(percent * 10))
        self.gen_status_label.setText(f"{int(percent)}% {status}")

        total_str = format_bytes(total_bytes, precision=2) if total_bytes > 0 else "Unknown"
        dl_str = format_bytes(downloaded_bytes, precision=2)
        self.gen_size_label.setText(f"Downloaded: {dl_str} of {total_str}")
        self.gen_added_label.setText(f"Added at: {date_added}")

        folder_path = os.path.dirname(filepath) if filepath else "--"
        self.gen_folder_btn.setText(folder_path or "--")
        self.gen_url_label.setText(url or "--")

        # Icon
        if filepath and os.path.exists(filepath):
            icon = QFileIconProvider().icon(QFileInfo(filepath))
            pix = icon.pixmap(48, 48)
            self.gen_icon_label.setPixmap(pix)
        else:
            # Fallback file icon
            icon = QFileIconProvider().icon(QFileIconProvider.IconType.File)
            pix = icon.pixmap(48, 48)
            self.gen_icon_label.setPixmap(pix)

        # --- 2. Update Progress Tab ---
        self.prog_percent_label.setText(f"{percent:.2f}%")
        self.prog_bytes_label.setText(f"{dl_str} / {total_str}")
        self.prog_speed_label.setText(speed)
        self.prog_eta_label.setText(f"ETA {time_left}")

        active_count = num_connections if (status in ["Downloading", "Receiving data..."] and not is_complete) else 0
        comp_count = num_connections if is_complete else int(round((percent / 100.0) * num_connections))
        self.prog_segments_stat.setText(f"Segments: {comp_count} / {num_connections}")
        self.prog_active_stat.setText(f"Active: {active_count}")
        self.prog_failed_stat.setText("Failed: 0")

        # Extract worker segment information if active
        segment_items = []
        if worker and hasattr(worker, "segments") and worker.segments:
            for s in worker.segments:
                s_tot = getattr(s, "total_size", 0)
                s_dl = getattr(s, "downloaded", 0)
                s_pct = (s_dl / s_tot * 100.0) if s_tot > 0 else (100.0 if is_complete else 0.0)
                s_status = "Complete" if s_pct >= 100.0 else ("Downloading" if getattr(s, "is_running", False) else "Pending")
                segment_items.append({"percent": s_pct, "status": s_status, "downloaded": s_dl, "total": s_tot})
            self.segment_grid.set_segment_data(segment_items, total_segments=len(worker.segments))
        else:
            self.segment_grid.set_fallback_progress(percent, num_segments=num_connections, is_complete=is_complete)

        # --- 3. Update Connections Tab ---
        self._update_connections_table(url, num_connections, active_count, is_complete)

    def _update_connections_table(self, url: str, num_connections: int, active_count: int, is_complete: bool):
        self.conn_table.setRowCount(0)
        if not url:
            return

        try:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
        except Exception:
            host = "Unknown"
            port = "443"

        # Determine Proxy configuration
        proxy_cfg = load_proxy_config()
        mode = proxy_cfg.get("mode", "no_proxy")
        if mode == "manual" and proxy_cfg.get("host"):
            p_type = proxy_cfg.get("type", "http").upper()
            proxy_str = f"{p_type} {proxy_cfg.get('host')}:{proxy_cfg.get('port', 8080)}"
        else:
            proxy_str = "Direct"

        conn_count_str = str(active_count if active_count > 0 else (num_connections if not is_complete else num_connections))

        self.conn_table.setRowCount(1)
        it_host = QTableWidgetItem(host)
        it_port = QTableWidgetItem(port)
        it_count = QTableWidgetItem(conn_count_str)
        it_proxy = QTableWidgetItem(proxy_str)

        apply_tnum_font(it_port)
        apply_tnum_font(it_count)

        self.conn_table.setItem(0, 0, it_host)
        self.conn_table.setItem(0, 1, it_port)
        self.conn_table.setItem(0, 2, it_count)
        self.conn_table.setItem(0, 3, it_proxy)


class DetailsToggleButton(QWidget):
    """
    Status bar button positioned at the bottom right.
    Displays the current/selected download filename with an arrow icon (▲ / ▼)
    that toggles the bottom details panel open and closed.
    """
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Toggle download details panel")
        self._is_open = False
        self._raw_filename = "No selection"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(6)

        self.lbl_name = QLabel(self._raw_filename, self)
        apply_tnum_font(self.lbl_name, point_size=9)
        self.lbl_name.setStyleSheet("color: palette(window-text);")
        layout.addWidget(self.lbl_name)

        # Arrow icon: ▲ (closed) / ▼ (open)
        self.lbl_arrow = QLabel("▲", self)
        self.lbl_arrow.setStyleSheet("""
            QLabel {
                color: #00a2ff;
                font-size: 10px;
                font-weight: bold;
                padding-bottom: 1px;
            }
        """)
        layout.addWidget(self.lbl_arrow)

        self.setStyleSheet("""
            DetailsToggleButton {
                background: transparent;
                border-radius: 3px;
            }
            DetailsToggleButton:hover {
                background-color: palette(mid);
            }
        """)

    def set_filename(self, filename: str):
        self._raw_filename = filename or "No selection"
        # Elide if excessively long
        metrics = self.lbl_name.fontMetrics()
        elided = metrics.elidedText(self._raw_filename, Qt.TextElideMode.ElideMiddle, 280)
        self.lbl_name.setText(elided)
        self.setToolTip(f"Toggle details panel for: {self._raw_filename}")

    def set_open(self, is_open: bool):
        self._is_open = is_open
        if is_open:
            self.lbl_arrow.setText("▼")
        else:
            self.lbl_arrow.setText("▲")

    def is_open(self) -> bool:
        return self._is_open

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

