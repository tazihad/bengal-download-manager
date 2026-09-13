"""
Data Usage & Storage Widget
===========================
Clean, compact data usage and download storage summary card for Bengal DM sidebar.
Features:
- Today's data usage button-card that opens a monthly Android 17-style line graph dialog
- Today's downloaded files counter
- Real-time active downloads and current speed
- Download storage space meter
"""

import os
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.utils import format_bytes, get_user_downloads_dir
from core.services.theme_service import parse_size_to_bytes
from core.database import record_daily_usage, get_month_daily_usage


def _apply_tabular_font(widget, point_size: int = 9, bold: bool = False):
    """Applies OpenType tabular numbers font feature and formatting to widget."""
    font = QFont(widget.font())
    if point_size > 0:
        font.setPointSize(point_size)
    font.setBold(bold)
    font.setFeature(QFont.Tag.fromString("tnum"), 1)
    widget.setFont(font)


class ClickableCardFrame(QFrame):
    """QFrame subclass that acts like a button and emits a clicked signal on mouse press."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class DataUsageWidget(QFrame):
    """
    Compact card positioned at the bottom of the left sidebar displaying:
    - Today's data usage (interactive button opening the monthly graph dialog)
    - Key metrics (Today's completed files, Active downloads, Current speed)
    - Download storage meter (Used vs Free disk space)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dataUsageCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._build_ui()
        self.setStyleSheet("""
            QFrame#dataUsageCard {
                background-color: palette(window);
                border-top: 1px solid palette(mid);
                padding: 6px 8px 6px 8px;
            }
            QFrame#todayUsageCard {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 6px 8px;
            }
            QFrame#todayUsageCard:hover {
                border-color: palette(highlight);
                background-color: palette(alternate-base);
            }
            QLabel.sectionHeader {
                font-weight: bold;
                font-size: 11px;
                color: palette(highlight);
            }
            QLabel.secondaryLabel {
                font-size: 10px;
                color: palette(placeholder-text);
            }
            QFrame.statBadge {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 3px 2px;
            }
            QProgressBar#storageProgressBar {
                border: none;
                border-radius: 2px;
                background-color: palette(base);
                height: 5px;
                max-height: 5px;
            }
            QProgressBar#storageProgressBar::chunk {
                background-color: palette(highlight);
                border-radius: 2px;
            }
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # -------------------------------------------------------------
        # 1. Clickable Today's Data Usage Button Card
        # -------------------------------------------------------------
        self.today_card = ClickableCardFrame(self)
        self.today_card.setObjectName("todayUsageCard")
        self.today_card.setToolTip("Click to view current month data usage and graph")
        self.today_card.clicked.connect(self._open_data_usage_dialog)

        card_layout = QVBoxLayout(self.today_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(3)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        self.lbl_header = QLabel("Today's data usage")
        self.lbl_header.setProperty("class", "sectionHeader")
        self.lbl_header.setToolTip("Click to view current month data usage and graph")
        header_row.addWidget(self.lbl_header)
        header_row.addStretch()

        card_layout.addLayout(header_row)

        # Main Stat: Big Downloaded Size + "downloaded today"
        stat_row = QHBoxLayout()
        stat_row.setContentsMargins(0, 0, 0, 0)
        stat_row.setSpacing(6)
        stat_row.setAlignment(Qt.AlignmentFlag.AlignBaseline)

        self.lbl_downloaded_val = QLabel("0 B")
        self.lbl_downloaded_val.setToolTip("Data completed today (click to view graph)")
        _apply_tabular_font(self.lbl_downloaded_val, point_size=15, bold=True)
        stat_row.addWidget(self.lbl_downloaded_val)

        self.lbl_downloaded_desc = QLabel("downloaded today")
        self.lbl_downloaded_desc.setProperty("class", "secondaryLabel")
        self.lbl_downloaded_desc.setToolTip("Data completed today (click to view graph)")
        stat_row.addWidget(self.lbl_downloaded_desc)
        stat_row.addStretch()

        card_layout.addLayout(stat_row)
        main_layout.addWidget(self.today_card)

        # -------------------------------------------------------------
        # 2. Badges Row: [ Files (Today) ]  [ Active ]  [ Speed ]
        # -------------------------------------------------------------
        badges_layout = QHBoxLayout()
        badges_layout.setContentsMargins(0, 1, 0, 1)
        badges_layout.setSpacing(4)

        def make_badge(title: str, tooltip: str = ""):
            frame = QFrame()
            frame.setProperty("class", "statBadge")
            if tooltip:
                frame.setToolTip(tooltip)
            f_layout = QVBoxLayout(frame)
            f_layout.setContentsMargins(2, 2, 2, 2)
            f_layout.setSpacing(1)

            t_lbl = QLabel(title)
            t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t_lbl.setStyleSheet("font-size: 8px; font-weight: bold; color: palette(placeholder-text);")
            if tooltip:
                t_lbl.setToolTip(tooltip)

            v_lbl = QLabel("0")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _apply_tabular_font(v_lbl, point_size=10, bold=True)
            if tooltip:
                v_lbl.setToolTip(tooltip)

            f_layout.addWidget(t_lbl)
            f_layout.addWidget(v_lbl)
            return frame, v_lbl

        self.badge_files, self.lbl_files_val = make_badge("Files", "Files downloaded today")
        self.badge_active, self.lbl_active_val = make_badge("Active", "Currently active downloads")
        self.badge_speed, self.lbl_speed_val = make_badge("Speed", "Current download transfer rate")

        badges_layout.addWidget(self.badge_files, 1)
        badges_layout.addWidget(self.badge_active, 1)
        badges_layout.addWidget(self.badge_speed, 1)

        main_layout.addLayout(badges_layout)

        # -------------------------------------------------------------
        # 3. Storage Section: Storage + Bar + Free Info
        # -------------------------------------------------------------
        storage_header_row = QHBoxLayout()
        storage_header_row.setContentsMargins(0, 2, 0, 0)
        storage_header_row.setSpacing(4)

        self.lbl_storage_title = QLabel("Storage")
        self.lbl_storage_title.setStyleSheet("font-size: 9px; font-weight: bold; color: palette(placeholder-text);")
        self.lbl_storage_title.setToolTip("Disk storage usage of downloads directory")
        storage_header_row.addWidget(self.lbl_storage_title)
        storage_header_row.addStretch()

        self.lbl_storage_val = QLabel("-- / --")
        _apply_tabular_font(self.lbl_storage_val, point_size=9, bold=False)
        self.lbl_storage_val.setStyleSheet("color: palette(window-text);")
        self.lbl_storage_val.setToolTip("Used disk space of total capacity")
        storage_header_row.addWidget(self.lbl_storage_val)

        main_layout.addLayout(storage_header_row)

        # Progress bar
        self.storage_progress = QProgressBar()
        self.storage_progress.setObjectName("storageProgressBar")
        self.storage_progress.setRange(0, 100)
        self.storage_progress.setValue(0)
        self.storage_progress.setTextVisible(False)
        self.storage_progress.setToolTip("Downloads directory disk usage")
        main_layout.addWidget(self.storage_progress)

        # Storage subtext: "X% used" (left) ... "Y free" (right)
        storage_sub_row = QHBoxLayout()
        storage_sub_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_storage_used = QLabel("0% used")
        self.lbl_storage_used.setProperty("class", "secondaryLabel")
        self.lbl_storage_used.setToolTip("Percentage of disk space used")
        _apply_tabular_font(self.lbl_storage_used, point_size=8)
        storage_sub_row.addWidget(self.lbl_storage_used)

        storage_sub_row.addStretch()

        self.lbl_storage_free = QLabel("0 B free")
        self.lbl_storage_free.setProperty("class", "secondaryLabel")
        self.lbl_storage_free.setToolTip("Free disk space remaining")
        _apply_tabular_font(self.lbl_storage_free, point_size=8)
        storage_sub_row.addWidget(self.lbl_storage_free)

        main_layout.addLayout(storage_sub_row)

    def _open_data_usage_dialog(self):
        """Opens the Android 17-style current month data usage line graph dialog."""
        from ui.dialogs import DataUsageDialog
        dlg = DataUsageDialog(parent=self.window())
        dlg.exec()

    def refresh_stats(self, main_window):
        """Calculates and updates metrics from MainWindow state, database, and disk storage."""
        if not main_window:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Start with today's usage from database (persists even if user clears completed downloads)
        month_str = datetime.now().strftime("%Y-%m")
        try:
            db_usage = get_month_daily_usage(month_str).get(today_str, {"bytes": 0, "files": 0})
            today_completed_bytes = db_usage.get("bytes", 0)
            today_files_count = db_usage.get("files", 0)
        except Exception:
            today_completed_bytes = 0
            today_files_count = 0

        # Also inspect current table rows in case new downloads finished
        table_bytes = 0
        table_files = 0
        if hasattr(main_window, "download_table"):
            table = main_window.download_table
            total_rows = table.rowCount()
            for r in range(total_rows):
                status_item = table.item(r, 2)
                status_text = status_item.text() if status_item else ""
                logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
                item_0 = table.item(r, 0)
                is_comp = (
                    logic_status in ["Complete", "Finished"] or
                    status_text in ["Complete", "Finished"] or
                    (item_0 and item_0.data(Qt.ItemDataRole.UserRole + 11) == "Complete")
                )
                if is_comp and item_0:
                    # Determine date of completion / addition
                    last_try_ts = item_0.data(Qt.ItemDataRole.UserRole + 2)
                    date_added_ts = item_0.data(Qt.ItemDataRole.UserRole + 3)
                    file_path = item_0.data(Qt.ItemDataRole.UserRole + 1) or ""

                    is_today = False
                    for ts in (last_try_ts, date_added_ts):
                        if ts:
                            try:
                                if datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d") == today_str:
                                    is_today = True
                                    break
                            except Exception:
                                pass

                    if not is_today and file_path and os.path.exists(file_path):
                        try:
                            if datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d") == today_str:
                                is_today = True
                        except Exception:
                            pass

                    if is_today:
                        table_files += 1
                        file_sz = 0
                        if file_path and os.path.exists(file_path):
                            try:
                                file_sz = os.path.getsize(file_path)
                            except Exception:
                                pass
                        if file_sz == 0:
                            size_item = table.item(r, 1)
                            if size_item:
                                file_sz = int(parse_size_to_bytes(size_item.text()))
                        table_bytes += file_sz

        # If table has higher count/bytes (e.g. newly completed items), update database and state
        if table_bytes > today_completed_bytes or table_files > today_files_count:
            today_completed_bytes = max(today_completed_bytes, table_bytes)
            today_files_count = max(today_files_count, table_files)
            try:
                record_daily_usage(today_str, today_completed_bytes, today_files_count)
            except Exception:
                pass

        active_count = len(getattr(main_window, "active_downloads", {})) or len(getattr(main_window, "active_speeds", {}))
        active_speeds = getattr(main_window, "active_speeds", {})
        current_speed = sum(active_speeds.values()) if active_speeds else 0.0

        # Update labels and dynamic tooltips
        files_tip = f"{today_files_count} file{'s' if today_files_count != 1 else ''} downloaded today"
        downloaded_tip = f"{format_bytes(today_completed_bytes)} completed today (click to view calendar graph)"

        self.lbl_downloaded_val.setText(format_bytes(today_completed_bytes))
        self.lbl_downloaded_val.setToolTip(downloaded_tip)
        self.lbl_downloaded_desc.setToolTip(downloaded_tip)
        self.lbl_header.setToolTip(downloaded_tip)
        self.today_card.setToolTip(downloaded_tip)

        self.lbl_files_val.setText(str(today_files_count))
        self.lbl_files_val.setToolTip(files_tip)
        self.badge_files.setToolTip(files_tip)

        self.update_live_speed(current_speed, active_count)

    def update_live_speed(self, current_speed: float = 0.0, active_count: int = 0):
        """Immediately updates the speed and active downloads badge in sync with download status updates."""
        speed_str = format_bytes(current_speed) + "/s" if current_speed > 0 else "0 B/s"
        if self.lbl_speed_val.text() != speed_str:
            self.lbl_speed_val.setText(speed_str)
            speed_tip = f"Current transfer rate: {speed_str}"
            self.lbl_speed_val.setToolTip(speed_tip)
            self.badge_speed.setToolTip(speed_tip)

        active_str = str(active_count)
        if self.lbl_active_val.text() != active_str:
            self.lbl_active_val.setText(active_str)
            active_tip = f"{active_count} active download{'s' if active_count != 1 else ''} in progress"
            self.lbl_active_val.setToolTip(active_tip)
            self.badge_active.setToolTip(active_tip)

        # 2. Download Storage Meter
        try:
            dl_dir = get_user_downloads_dir()
            usage = shutil.disk_usage(dl_dir)
            total = usage.total
            used = usage.used
            free = usage.free
            pct = int((used / total) * 100) if total > 0 else 0

            storage_tip = f"Downloads storage: {format_bytes(used)} used of {format_bytes(total)} ({pct}%), {format_bytes(free)} free"
            self.lbl_storage_val.setText(f"{format_bytes(used)} of {format_bytes(total)}")
            self.lbl_storage_val.setToolTip(storage_tip)
            self.storage_progress.setValue(min(100, max(0, pct)))
            self.storage_progress.setToolTip(storage_tip)
            self.lbl_storage_used.setText(f"{pct}% used")
            self.lbl_storage_used.setToolTip(f"{pct}% of disk space used")
            self.lbl_storage_free.setText(f"{format_bytes(free)} free")
            self.lbl_storage_free.setToolTip(f"{format_bytes(free)} free disk space remaining")
        except Exception:
            pass
