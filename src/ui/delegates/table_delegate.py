"""
Modern Table Delegate for Bengal Download Manager.
Renders two-line file cells (Title + Category), embedded mini progress bars,
and tabular-aligned figures within the QTableWidget without modifying existing theme.
"""
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QLinearGradient, QBrush, QIcon


CATEGORY_EXTENSIONS = {
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz", ".dmg", ".zst"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt", ".epub"],
    "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus", ".m4b"],
    "Pictures": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".tif"],
    "Programs": [".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".3gp"]
}


def _get_category_for_filename(filename: str) -> str:
    """Infers category name from filename extension."""
    if not filename:
        return "General"
    fn = filename.lower()
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if any(fn.endswith(ext) for ext in exts):
            return cat
    return "General"


class ModernTableDelegate(QStyledItemDelegate):
    """Custom item delegate rendering the Modern card/two-line table view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row_height = 50

    def sizeHint(self, option: QStyleOptionViewItem, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), self.row_height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # 1. Background rendering
        if is_selected:
            bg_color = option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.Highlight)
            painter.fillRect(option.rect, bg_color)
        elif is_hovered:
            hover_color = option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.AlternateBase)
            painter.fillRect(option.rect, hover_color)

        col = index.column()
        rect = option.rect.adjusted(8, 4, -8, -4)

        if col == 0:
            self._paint_name_cell(painter, option, index, rect, is_selected)
        elif col == 2:
            self._paint_status_cell(painter, option, index, rect, is_selected)
        else:
            self._paint_text_cell(painter, option, index, rect, is_selected)

        painter.restore()

    def _paint_name_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect, is_selected: bool):
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        category = _get_category_for_filename(text)

        # Dynamic text colors adapting to selection and theme
        if is_selected:
            primary_color = QColor("#000000")
            sub_color = QColor("#333333")
        else:
            primary_color = option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText)
            sub_color = option.palette.color(option.palette.ColorGroup.Disabled, option.palette.ColorRole.WindowText)
            if not sub_color.isValid() or sub_color == primary_color:
                sub_color = QColor("#888888")

        x_offset = rect.left()
        if icon:
            icon_rect = QRect(x_offset, rect.top() + (rect.height() - 24) // 2, 24, 24)
            if isinstance(icon, QIcon):
                icon.paint(painter, icon_rect)
            x_offset += 30

        # Line 1: Primary Filename (Bold)
        font_primary = QFont(option.font)
        font_primary.setBold(True)
        font_primary.setPointSize(font_primary.pointSize())
        painter.setFont(font_primary)
        painter.setPen(primary_color)

        title_rect = QRect(x_offset, rect.top() + 1, rect.right() - x_offset, (rect.height() // 2))
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)

        # Line 2: Category subtitle
        font_sub = QFont(option.font)
        font_sub.setBold(False)
        font_sub.setPointSize(max(8, font_sub.pointSize() - 2))
        painter.setFont(font_sub)
        painter.setPen(sub_color)

        cat_rect = QRect(x_offset, rect.top() + (rect.height() // 2), rect.right() - x_offset, (rect.height() // 2) - 1)
        painter.drawText(cat_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, category)

    def _paint_status_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect, is_selected: bool):
        status_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        progress_val = index.data(Qt.ItemDataRole.UserRole)
        internal_status = index.data(Qt.ItemDataRole.UserRole + 1)

        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)

        if status_text in ("Complete", "Finished") or internal_status in ("Complete", "Finished") or "100" in str(progress_val):
            painter.setPen(QColor("#2ec27e"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Finished")
            return

        # Extract percentage numeric value
        pct = 0.0
        pct_str = ""
        if "%" in status_text:
            try:
                pct = float(status_text.split("%")[0].strip())
                pct_str = f"{pct:.2f}%"
            except ValueError:
                pct_str = status_text
        elif progress_val and "%" in str(progress_val):
            try:
                pct = float(str(progress_val).replace("%", "").strip())
                pct_str = f"{pct:.2f}%"
            except ValueError:
                pct_str = str(progress_val)

        # Determine state keyword: Paused, Downloading, Connecting, Resuming, Error, etc.
        state_label = ""
        if internal_status:
            clean_status = str(internal_status).replace("...", "").strip()
            if clean_status.lower() in ("pause", "paused"):
                state_label = "Paused"
            elif clean_status.lower() in ("resume", "resuming"):
                state_label = "Resuming"
            elif clean_status.lower() in ("connect", "connecting"):
                state_label = "Connecting"
            elif clean_status.lower() in ("download", "downloading", "receiving data"):
                state_label = "Downloading"
            else:
                state_label = clean_status
        elif "pause" in status_text.lower():
            state_label = "Paused"
        elif "resum" in status_text.lower():
            state_label = "Resuming"
        elif "connect" in status_text.lower():
            state_label = "Connecting"
        elif pct > 0:
            state_label = "Downloading"

        if pct_str:
            if state_label and state_label.lower() not in pct_str.lower():
                display_label = f"{pct_str} {state_label}"
            else:
                display_label = pct_str
        else:
            display_label = status_text if status_text else "Queued"

        text_rect = QRect(rect.left(), rect.top() + 1, rect.width(), (rect.height() // 2))

        if is_selected:
            painter.setPen(QColor("#000000"))
        else:
            if "pause" in display_label.lower():
                painter.setPen(QColor("#f59e0b"))
            elif "error" in display_label.lower():
                painter.setPen(QColor("#ef4444"))
            else:
                painter.setPen(option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, display_label)

        # Mini Progress Bar underneath percentage/download status
        bar_rect = QRect(rect.left(), rect.top() + (rect.height() // 2) + 5, rect.width(), 4)
        painter.setBrush(option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.Mid))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_rect, 2, 2)

        if pct > 0:
            fill_width = int(bar_rect.width() * (min(100.0, pct) / 100.0))
            if fill_width > 0:
                fill_rect = QRect(bar_rect.left(), bar_rect.top(), fill_width, bar_rect.height())
                if "pause" in display_label.lower():
                    painter.setBrush(QColor("#f59e0b"))
                else:
                    grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
                    grad.setColorAt(0.0, QColor("#6366f1"))
                    grad.setColorAt(1.0, QColor("#ec4899"))
                    painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(fill_rect, 2, 2)

    def _paint_text_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect, is_selected: bool):
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        font = QFont(option.font)
        painter.setFont(font)
        if is_selected:
            painter.setPen(QColor("#000000"))
        else:
            painter.setPen(option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText))
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
