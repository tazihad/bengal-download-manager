"""
Modern Table Delegate for Bengal Download Manager.
Renders two-line file cells (Title + Category), embedded mini progress bars,
and tabular-aligned figures within the QTableWidget without modifying existing theme.
"""
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QLinearGradient, QBrush, QIcon


def _get_category_for_filename(filename: str) -> str:
    """Infers category name from filename extension if not explicitly stored."""
    if not filename:
        return "General"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "dmg"):
        return "Compressed"
    elif ext in ("exe", "msi", "deb", "rpm", "pkg", "apk", "appimage", "bin"):
        return "Programs"
    elif ext in ("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v"):
        return "Video"
    elif ext in ("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"):
        return "Music"
    elif ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico"):
        return "Pictures"
    elif ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub"):
        return "Documents"
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
        stored_category = index.data(Qt.ItemDataRole.UserRole + 3)
        category = stored_category if stored_category else _get_category_for_filename(text)

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

        text_rect = QRect(rect.left(), rect.top() + 1, rect.width(), (rect.height() // 2))
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)

        if status_text in ("Complete", "Finished"):
            painter.setPen(QColor("#2ec27e"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Finished")
            return

        if is_selected:
            painter.setPen(QColor("#000000"))
        else:
            painter.setPen(option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status_text)

        # Mini Progress Bar underneath percentage/download status
        pct = 0.0
        if progress_val:
            try:
                pct = float(str(progress_val).replace("%", "").strip())
            except ValueError:
                pct = 0.0
        elif "%" in status_text:
            try:
                pct = float(status_text.split("%")[0].strip())
            except ValueError:
                pct = 0.0

        bar_rect = QRect(rect.left(), rect.top() + (rect.height() // 2) + 5, rect.width(), 4)
        painter.setBrush(option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.Mid))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_rect, 2, 2)

        if pct > 0:
            fill_width = int(bar_rect.width() * (min(100.0, pct) / 100.0))
            if fill_width > 0:
                fill_rect = QRect(bar_rect.left(), bar_rect.top(), fill_width, bar_rect.height())
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
