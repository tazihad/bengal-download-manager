"""
Category Sidebar Component & Item Delegate
==========================================
Sidebar category tree delegate ensuring crisp black selection text & headers.
"""

from PyQt6.QtWidgets import (
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QApplication,
)
from PyQt6.QtGui import (
    QColor,
    QPalette,
    QIcon,
    QPixmap,
    QImage,
)
from PyQt6.QtCore import (
    Qt,
    QSize,
)


class SidebarItemDelegate(QStyledItemDelegate):
    """
    Delegate for the left panel category tree that guarantees the selected and hovered item's
    icon and text render in pure black (#000000) over the accent highlight in both light and dark modes.
    Formats non-selectable section headers with small font and muted text color.
    """
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(Qt.ItemDataRole.UserRole) == "header":
            option.state &= ~QStyle.StateFlag.State_MouseOver
            option.state &= ~QStyle.StateFlag.State_Selected
            option.font.setPointSize(8)
            option.font.setBold(True)
            app = QApplication.instance()
            if app:
                pal = app.palette()
                placeholder_color = pal.color(QPalette.ColorRole.PlaceholderText)
                option.palette.setColor(QPalette.ColorRole.Text, placeholder_color)
                option.palette.setColor(QPalette.ColorRole.WindowText, placeholder_color)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.data(Qt.ItemDataRole.UserRole) == "header":
            return QSize(size.width(), 20)
        return QSize(size.width(), 26)

    def paint(self, painter, option, index):
        if index.data(Qt.ItemDataRole.UserRole) == "header":
            super().paint(painter, option, index)
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if is_selected or is_hovered:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)

            from core.services.theme_service import is_monochrome_icon_theme
            if is_monochrome_icon_theme():
                # Left panel selected/hovered icon for BDM monochrome stroke icons MUST be pure black
                icon = index.data(Qt.ItemDataRole.DecorationRole)
                if isinstance(icon, QIcon) and not icon.isNull():
                    dec_size = opt.decorationSize if opt.decorationSize.isValid() and not opt.decorationSize.isEmpty() else QSize(18, 18)
                    src_pm = icon.pixmap(dec_size, QIcon.Mode.Normal)
                    if not src_pm.isNull() and src_pm.width() > 0 and src_pm.height() > 0:
                        img = src_pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
                        for y in range(img.height()):
                            for x in range(img.width()):
                                c = img.pixelColor(x, y)
                                if c.alpha() > 0:
                                    img.setPixelColor(x, y, QColor(0, 0, 0, c.alpha()))
                        black_pm = QPixmap.fromImage(img)
                        black_ic = QIcon()
                        black_ic.addPixmap(black_pm, QIcon.Mode.Normal)
                        black_ic.addPixmap(black_pm, QIcon.Mode.Selected)
                        black_ic.addPixmap(black_pm, QIcon.Mode.Active)
                        opt.icon = black_ic

            opt.palette.setColor(QPalette.ColorRole.Text, QColor("#000000"))
            opt.palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
            opt.palette.setColor(QPalette.ColorRole.WindowText, QColor("#000000"))

            widget = option.widget
            style = widget.style() if widget else QApplication.style()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        else:
            super().paint(painter, option, index)
