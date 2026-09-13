"""
Data Usage Dialog & Android 17-Style Line Graph
===============================================
Displays daily data usage for the current month with a smooth Android 17-style
gradient line graph and day-by-day calendar breakdown.
"""

from datetime import datetime, timedelta
import calendar
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QApplication, QSizePolicy,
    QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient,
    QFont, QFontMetrics, QPalette
)

from core.utils import format_bytes
from core.database import get_month_daily_usage, cleanup_old_data_usage


def _apply_tabular_font(widget, point_size: int = 9, bold: bool = False):
    font = QFont(widget.font())
    if point_size > 0:
        font.setPointSize(point_size)
    font.setBold(bold)
    font.setFeature(QFont.Tag.fromString("tnum"), 1)
    widget.setFont(font)


class Android17LineGraph(QWidget):
    """
    Android 17 / Material You style smooth line graph with gradient fill underneath,
    Y-axis grid lines, date markings, and interactive hover indicator.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.data_points: Dict[int, int] = {}  # day_number (1..days_in_month) -> bytes
        self.data_files: Dict[int, int] = {}   # day_number (1..days_in_month) -> files
        self.days_in_month: int = 30
        self.current_day: int = 1
        self.hovered_day: Optional[int] = None
        self.max_bytes: int = 1

    def set_data(self, daily_bytes: Dict[str, Dict[str, int]], year: int, month: int):
        _, self.days_in_month = calendar.monthrange(year, month)
        now = datetime.now()
        self.current_day = now.day if (now.year == year and now.month == month) else self.days_in_month

        self.data_points = {}
        self.data_files = {}
        for d in range(1, self.days_in_month + 1):
            date_key = f"{year:04d}-{month:02d}-{d:02d}"
            info = daily_bytes.get(date_key, {})
            self.data_points[d] = info.get("bytes", 0)
            self.data_files[d] = info.get("files", 0)

        # Base max on data up to current day (or entire month if past)
        active_vals = [self.data_points.get(d, 0) for d in range(1, self.current_day + 1)]
        self.max_bytes = max(max(active_vals, default=0), 1024 * 1024)
        self.update()

    def mouseMoveEvent(self, event):
        pad_left = 65.0
        pad_right = 20.0
        chart_w = max(1.0, self.width() - pad_left - pad_right)
        x = event.position().x()
        step = chart_w / max(1, self.days_in_month - 1)
        max_x = pad_left + (self.current_day - 1) * step + (step / 2.0)

        if pad_left - (step / 2.0) <= x <= max_x:
            idx = int(round((x - pad_left) / step)) + 1
            idx = max(1, min(self.current_day, idx))
            if self.hovered_day != idx:
                self.hovered_day = idx
                self.update()
        else:
            if self.hovered_day is not None:
                self.hovered_day = None
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_day is not None:
            self.hovered_day = None
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        pad_left = 65.0
        pad_right = 20.0
        pad_top = 25.0
        pad_bottom = 35.0

        chart_w = max(10.0, w - pad_left - pad_right)
        chart_h = max(10.0, h - pad_top - pad_bottom)
        base_y = pad_top + chart_h

        pal = self.palette()
        accent_color = pal.color(QPalette.ColorRole.Highlight)
        if accent_color.value() < 80:
            accent_color = QColor("#0ea5e9")  # Bright cyan-blue fallback if theme highlight is dim
        text_color = pal.color(QPalette.ColorRole.WindowText)
        grid_color = QColor(128, 128, 128, 45)

        # 1. Background Grid & Y-Axis Labels
        tnum_font = QFont(self.font())
        tnum_font.setPointSize(8)
        tnum_font.setFeature(QFont.Tag.fromString("tnum"), 1)
        painter.setFont(tnum_font)

        grid_steps = 4
        for i in range(grid_steps + 1):
            ratio = i / float(grid_steps)
            y = pad_top + chart_h * (1.0 - ratio)
            val_at_y = self.max_bytes * ratio

            # Line
            painter.setPen(QPen(grid_color, 1.0, Qt.PenStyle.DashLine))
            painter.drawLine(int(pad_left), int(y), int(w - pad_right), int(y))

            # Label
            painter.setPen(QPen(QColor(text_color.red(), text_color.green(), text_color.blue(), 160)))
            label_str = format_bytes(val_at_y)
            painter.drawText(QRectF(0, y - 8, pad_left - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label_str)

        # 2. X-Axis Dates
        step_x = chart_w / max(1, self.days_in_month - 1)
        label_days = [1, 5, 10, 15, 20, 25, self.days_in_month]
        if self.days_in_month not in label_days:
            label_days.append(self.days_in_month)

        for d in label_days:
            x = pad_left + (d - 1) * step_x
            painter.setPen(QPen(QColor(text_color.red(), text_color.green(), text_color.blue(), 180)))
            painter.drawText(QRectF(x - 15, h - pad_bottom + 6, 30, 16), Qt.AlignmentFlag.AlignCenter, f"{d}")

        # 3. Build Point Coordinates (plot history up to current_day)
        pts = []
        for d in range(1, self.current_day + 1):
            px = pad_left + (d - 1) * step_x
            val = self.data_points.get(d, 0)
            ratio = val / float(self.max_bytes) if self.max_bytes > 0 else 0.0
            ratio = max(0.0, min(1.0, ratio))
            py = pad_top + chart_h * (1.0 - ratio)
            pts.append(QPointF(px, py))

        # 4. Monotone Cubic Hermite Spline (Fritsch-Carlson)
        n = len(pts)
        if n >= 2:
            dxs = [pts[i + 1].x() - pts[i].x() for i in range(n - 1)]
            dys = [pts[i + 1].y() - pts[i].y() for i in range(n - 1)]
            slopes = [dys[i] / dxs[i] if dxs[i] != 0 else 0.0 for i in range(n - 1)]

            m = [0.0] * n
            m[0] = slopes[0]
            m[-1] = slopes[-1]
            for i in range(1, n - 1):
                if slopes[i - 1] * slopes[i] <= 0:
                    m[i] = 0.0
                else:
                    m[i] = (slopes[i - 1] + slopes[i]) / 2.0

            # Fritsch-Carlson monotonicity condition to prevent dips and overshoots
            for i in range(n - 1):
                if slopes[i] == 0:
                    m[i] = 0.0
                    m[i + 1] = 0.0
                else:
                    alpha = m[i] / slopes[i]
                    beta = m[i + 1] / slopes[i]
                    if alpha < 0:
                        m[i] = 0.0
                    if beta < 0:
                        m[i + 1] = 0.0
                    hypot_sq = alpha * alpha + beta * beta
                    if hypot_sq > 9.0:
                        tau = 3.0 / (hypot_sq ** 0.5)
                        m[i] = tau * alpha * slopes[i]
                        m[i + 1] = tau * beta * slopes[i]

            line_path = QPainterPath()
            line_path.moveTo(pts[0])

            for i in range(n - 1):
                dx = dxs[i]
                c1_x = pts[i].x() + dx / 3.0
                c1_y = pts[i].y() + m[i] * dx / 3.0
                c2_x = pts[i + 1].x() - dx / 3.0
                c2_y = pts[i + 1].y() - m[i + 1] * dx / 3.0

                c1_y = max(pad_top, min(base_y, c1_y))
                c2_y = max(pad_top, min(base_y, c2_y))

                line_path.cubicTo(c1_x, c1_y, c2_x, c2_y, pts[i + 1].x(), pts[i + 1].y())

            # Fill Path under curve
            fill_path = QPainterPath(line_path)
            fill_path.lineTo(pts[-1].x(), base_y)
            fill_path.lineTo(pts[0].x(), base_y)
            fill_path.closeSubpath()

            grad = QLinearGradient(0, pad_top, 0, base_y)
            grad.setColorAt(0.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 110))
            grad.setColorAt(0.7, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 30))
            grad.setColorAt(1.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 0))

            painter.fillPath(fill_path, QBrush(grad))

            # Stroke curve line
            stroke_pen = QPen(accent_color, 2.5)
            stroke_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(line_path, stroke_pen)

        # 5. Points / Dots for Days with Downloads and Today
        for d, pt in enumerate(pts, start=1):
            val = self.data_points.get(d, 0)
            if val > 0 or d == self.current_day:
                painter.setPen(QPen(accent_color, 2.0))
                painter.setBrush(QBrush(pal.color(QPalette.ColorRole.Base)))
                painter.drawEllipse(pt, 3.5, 3.5)

        # 6. Interactive Hover Indicator / Tooltip
        active_day = self.hovered_day or self.current_day
        if 1 <= active_day <= len(pts):
            active_pt = pts[active_day - 1]
            active_val = self.data_points.get(active_day, 0)
            active_files = self.data_files.get(active_day, 0)

            # Vertical guide line
            guide_pen = QPen(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 180), 1.2, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            painter.drawLine(int(active_pt.x()), int(pad_top), int(active_pt.x()), int(base_y))

            # Highlighted Dot
            painter.setPen(QPen(accent_color, 2.5))
            painter.setBrush(QBrush(accent_color))
            painter.drawEllipse(active_pt, 5.0, 5.0)

            # Tooltip pill badge
            files_suffix = f" • {active_files} files" if active_files > 0 else ""
            pill_text = f"Day {active_day}: {format_bytes(active_val)}{files_suffix}"
            pill_font = QFont(self.font())
            pill_font.setPointSize(8)
            pill_font.setBold(True)
            pill_font.setFeature(QFont.Tag.fromString("tnum"), 1)
            painter.setFont(pill_font)

            fm = QFontMetrics(pill_font)
            pw = fm.horizontalAdvance(pill_text) + 16
            ph = 22.0

            px = max(pad_left, min(w - pad_right - pw, active_pt.x() - pw / 2.0))
            py = max(2.0, active_pt.y() - ph - 8.0)

            pill_rect = QRectF(px, py, pw, ph)
            painter.setPen(QPen(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 180), 1.0))
            painter.setBrush(QBrush(QColor(24, 26, 32, 235) if pal.color(QPalette.ColorRole.Window).value() < 128 else QColor(255, 255, 255, 240)))
            painter.drawRoundedRect(pill_rect, 6.0, 6.0)

            painter.setPen(QPen(text_color))
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, pill_text)


class NoFocusDelegate(QStyledItemDelegate):
    """Item delegate that suppresses State_HasFocus to avoid accent focus outlines on table cells."""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


class DataUsageDialog(QDialog):
    """Small window popup showing 30 days data usage with Android 17 style line graph."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Data Usage - Current Month")
        self.setWindowIcon(QApplication.windowIcon())
        self.setMinimumSize(620, 500)
        self.resize(650, 520)

        now = datetime.now()
        self.year = now.year
        self.month = now.month
        self.today_str = now.strftime("%Y-%m-%d")
        self.month_str = now.strftime("%Y-%m")

        # Automatically clean up older months from SQLite database
        cleanup_old_data_usage(self.month_str)

        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header Card
        header_card = QFrame()
        header_card.setStyleSheet("""
            QFrame {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)

        now = datetime.now()
        month_name = now.strftime("%B %Y")
        title_lbl = QLabel(f"Data Usage • {month_name}")
        title_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: palette(highlight);")
        h_layout.addWidget(title_lbl)

        stat_row = QHBoxLayout()
        self.lbl_month_total = QLabel("0 B")
        self.lbl_month_total.setToolTip("Total data downloaded in current month")
        _apply_tabular_font(self.lbl_month_total, point_size=20, bold=True)
        stat_row.addWidget(self.lbl_month_total)
        stat_row.addStretch()

        self.lbl_today_badge = QLabel("Today: 0 B")
        self.lbl_today_badge.setToolTip("Total data downloaded today")
        _apply_tabular_font(self.lbl_today_badge, point_size=10, bold=True)
        self.lbl_today_badge.setStyleSheet("""
            background-color: palette(window);
            border: 1px solid palette(mid);
            border-radius: 6px;
            padding: 4px 10px;
        """)
        stat_row.addWidget(self.lbl_today_badge)

        h_layout.addLayout(stat_row)
        layout.addWidget(header_card)

        # 2. Android 17 Style Line Graph
        graph_card = QFrame()
        graph_card.setStyleSheet("""
            QFrame {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 4px;
            }
        """)
        g_layout = QVBoxLayout(graph_card)
        g_layout.setContentsMargins(4, 4, 4, 4)
        self.graph = Android17LineGraph(graph_card)
        g_layout.addWidget(self.graph)
        layout.addWidget(graph_card)

        # 3. Calendar Daily Breakdown Table
        lbl_breakdown = QLabel("Daily Activity Breakdown")
        lbl_breakdown.setStyleSheet("font-weight: bold; font-size: 11px; color: palette(window-text);")
        layout.addWidget(lbl_breakdown)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Date", "Data Downloaded", "Files"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMaximumHeight(140)
        self.table.setItemDelegate(NoFocusDelegate(self.table))
        self.table.setStyleSheet("""
            QTableWidget {
                outline: none;
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
            QTableWidget::item {
                outline: none;
                border: none;
            }
        """)
        layout.addWidget(self.table)

        # 4. Bottom Row
        btn_row = QHBoxLayout()
        lbl_note = QLabel("Only current month's usage is preserved in database.")
        lbl_note.setStyleSheet("font-size: 10px; color: palette(placeholder-text);")
        btn_row.addWidget(lbl_note)
        btn_row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _load_data(self):
        daily_usage = get_month_daily_usage(self.month_str)
        self.graph.set_data(daily_usage, self.year, self.month)

        total_month_bytes = sum(entry.get("bytes", 0) for entry in daily_usage.values())
        today_bytes = daily_usage.get(self.today_str, {}).get("bytes", 0)
        today_files = daily_usage.get(self.today_str, {}).get("files", 0)

        self.lbl_month_total.setText(format_bytes(total_month_bytes))
        self.lbl_today_badge.setText(f"Today: {format_bytes(today_bytes)} ({today_files} files)")

        # Populate daily breakdown table (sorted descending by date)
        _, days_count = calendar.monthrange(self.year, self.month)
        active_dates = []
        for d in range(days_count, 0, -1):
            dk = f"{self.year:04d}-{self.month:02d}-{d:02d}"
            info = daily_usage.get(dk, {"bytes": 0, "files": 0})
            if info["bytes"] > 0 or dk == self.today_str:
                active_dates.append((dk, info["bytes"], info["files"]))

        self.table.setRowCount(len(active_dates))
        for r, (dk, b, f_cnt) in enumerate(active_dates):
            date_item = QTableWidgetItem(f"{dk} (Today)" if dk == self.today_str else dk)
            bytes_item = QTableWidgetItem(format_bytes(b))
            files_item = QTableWidgetItem(str(f_cnt))

            _apply_tabular_font(date_item, point_size=9, bold=(dk == self.today_str))
            _apply_tabular_font(bytes_item, point_size=9, bold=True)
            _apply_tabular_font(files_item, point_size=9)

            self.table.setItem(r, 0, date_item)
            self.table.setItem(r, 1, bytes_item)
            self.table.setItem(r, 2, files_item)
