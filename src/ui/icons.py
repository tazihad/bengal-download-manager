"""
Monochromatic Minimalist Vector Stroke Icons for Bengal Download Manager.
Provides high-DPI resolution-independent vector icons that automatically adapt to light/dark themes.
"""

import math
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath, QPalette
from PyQt6.QtCore import Qt, QSize, QPointF, QRectF


def draw_icon_path(painter: QPainter, name: str, size: int):
    s = float(size)
    
    if name in ("add_url", "add"):
        # Hexagon + Plus
        cx, cy, r = s / 2.0, s / 2.0, s * 0.38
        poly = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0: poly.moveTo(x, y)
            else: poly.lineTo(x, y)
        poly.closeSubpath()
        painter.drawPath(poly)
        # Plus inside
        arm = s * 0.14
        painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
        painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))

    elif name == "resume":
        # Play Triangle
        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.22)
        path.lineTo(s * 0.76, s * 0.50)
        path.lineTo(s * 0.32, s * 0.78)
        path.closeSubpath()
        painter.drawPath(path)

    elif name in ("stop", "pause"):
        # Rounded Square Stop
        rect = QRectF(s * 0.26, s * 0.26, s * 0.48, s * 0.48)
        painter.drawRoundedRect(rect, 3, 3)

    elif name == "stop_all":
        # Double Square Stop
        r1 = QRectF(s * 0.20, s * 0.20, s * 0.38, s * 0.38)
        r2 = QRectF(s * 0.42, s * 0.42, s * 0.38, s * 0.38)
        painter.drawRoundedRect(r1, 2, 2)
        painter.drawRoundedRect(r2, 2, 2)

    elif name in ("delete", "trash"):
        # Trash Can
        # Lid
        painter.drawLine(QPointF(s * 0.20, s * 0.30), QPointF(s * 0.80, s * 0.30))
        painter.drawLine(QPointF(s * 0.40, s * 0.30), QPointF(s * 0.40, s * 0.22))
        painter.drawLine(QPointF(s * 0.40, s * 0.22), QPointF(s * 0.60, s * 0.22))
        painter.drawLine(QPointF(s * 0.60, s * 0.22), QPointF(s * 0.60, s * 0.30))
        # Body
        body = QPainterPath()
        body.moveTo(s * 0.26, s * 0.30)
        body.lineTo(s * 0.30, s * 0.78)
        body.lineTo(s * 0.70, s * 0.78)
        body.lineTo(s * 0.74, s * 0.30)
        painter.drawPath(body)
        # Inner vertical lines
        painter.drawLine(QPointF(s * 0.42, s * 0.40), QPointF(s * 0.42, s * 0.68))
        painter.drawLine(QPointF(s * 0.58, s * 0.40), QPointF(s * 0.58, s * 0.68))

    elif name in ("clear", "clear_completed"):
        # Circle + Checkmark
        painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        chk = QPainterPath()
        chk.moveTo(s * 0.32, s * 0.50)
        chk.lineTo(s * 0.44, s * 0.62)
        chk.lineTo(s * 0.68, s * 0.38)
        painter.drawPath(chk)

    elif name in ("options", "settings", "configure"):
        # Gear Cog
        cx, cy, r_out, r_in = s / 2.0, s / 2.0, s * 0.36, s * 0.24
        gear = QPainterPath()
        teeth = 8
        for i in range(teeth * 2):
            angle = math.radians(i * (360 / (teeth * 2)))
            r = r_out if i % 2 == 0 else r_in
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0: gear.moveTo(x, y)
            else: gear.lineTo(x, y)
        gear.closeSubpath()
        painter.drawPath(gear)
        painter.drawEllipse(QRectF(cx - s * 0.12, cy - s * 0.12, s * 0.24, s * 0.24))

    elif name in ("open_folder", "folder", "folder_download"):
        # Folder Outline
        f = QPainterPath()
        f.moveTo(s * 0.18, s * 0.30)
        f.lineTo(s * 0.40, s * 0.30)
        f.lineTo(s * 0.48, s * 0.38)
        f.lineTo(s * 0.82, s * 0.38)
        f.lineTo(s * 0.82, s * 0.74)
        f.lineTo(s * 0.18, s * 0.74)
        f.closeSubpath()
        painter.drawPath(f)

    elif name == "all_downloads":
        # Inbox Tray + Arrow
        t = QPainterPath()
        t.moveTo(s * 0.18, s * 0.40)
        t.lineTo(s * 0.18, s * 0.74)
        t.lineTo(s * 0.82, s * 0.74)
        t.lineTo(s * 0.82, s * 0.40)
        painter.drawPath(t)
        painter.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.50, s * 0.54))
        arr = QPainterPath()
        arr.moveTo(s * 0.38, s * 0.44)
        arr.lineTo(s * 0.50, s * 0.56)
        arr.lineTo(s * 0.62, s * 0.44)
        painter.drawPath(arr)

    elif name == "compressed":
        # Zip Box
        r = QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56)
        painter.drawRoundedRect(r, 4, 4)
        painter.drawLine(QPointF(s * 0.36, s * 0.36), QPointF(s * 0.64, s * 0.36))
        painter.drawLine(QPointF(s * 0.36, s * 0.50), QPointF(s * 0.64, s * 0.50))
        painter.drawLine(QPointF(s * 0.36, s * 0.64), QPointF(s * 0.64, s * 0.64))

    elif name == "documents":
        # Document Page
        doc = QPainterPath()
        doc.moveTo(s * 0.24, s * 0.20)
        doc.lineTo(s * 0.58, s * 0.20)
        doc.lineTo(s * 0.76, s * 0.38)
        doc.lineTo(s * 0.76, s * 0.80)
        doc.lineTo(s * 0.24, s * 0.80)
        doc.closeSubpath()
        painter.drawPath(doc)
        # Folded corner
        fold = QPainterPath()
        fold.moveTo(s * 0.58, s * 0.20)
        fold.lineTo(s * 0.58, s * 0.38)
        fold.lineTo(s * 0.76, s * 0.38)
        painter.drawPath(fold)

    elif name == "music":
        # Musical Note
        painter.drawEllipse(QRectF(s * 0.24, s * 0.58, s * 0.24, s * 0.20))
        painter.drawLine(QPointF(s * 0.48, s * 0.68), QPointF(s * 0.48, s * 0.24))
        painter.drawLine(QPointF(s * 0.48, s * 0.24), QPointF(s * 0.72, s * 0.32))
        painter.drawLine(QPointF(s * 0.72, s * 0.32), QPointF(s * 0.72, s * 0.50))

    elif name == "programs":
        # App Window
        w = QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.52)
        painter.drawRoundedRect(w, 3, 3)
        painter.drawLine(QPointF(s * 0.20, s * 0.40), QPointF(s * 0.80, s * 0.40))
        painter.drawEllipse(QRectF(s * 0.28, s * 0.30, s * 0.04, s * 0.04))
        painter.drawEllipse(QRectF(s * 0.36, s * 0.30, s * 0.04, s * 0.04))

    elif name == "video":
        # Video Play Box
        v = QRectF(s * 0.18, s * 0.26, s * 0.64, s * 0.48)
        painter.drawRoundedRect(v, 4, 4)
        vp = QPainterPath()
        vp.moveTo(s * 0.42, s * 0.38)
        vp.lineTo(s * 0.60, s * 0.50)
        vp.lineTo(s * 0.42, s * 0.62)
        vp.closeSubpath()
        painter.drawPath(vp)

    elif name == "unfinished":
        # Clock Circle + Hands
        painter.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        painter.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.50, s * 0.32))
        painter.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.64, s * 0.50))

    elif name == "finished":
        # Checkmark Badge
        painter.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        chk = QPainterPath()
        chk.moveTo(s * 0.34, s * 0.50)
        chk.lineTo(s * 0.46, s * 0.62)
        chk.lineTo(s * 0.66, s * 0.38)
        painter.drawPath(chk)

    elif name in ("exit", "quit"):
        # Power Button
        painter.drawArc(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), 45 * 16, 270 * 16)
        painter.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.50, s * 0.48))

    elif name in ("show_hide", "window_toggle"):
        # Window Layout Toggle
        r = QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60)
        painter.drawRoundedRect(r, 3, 3)
        painter.drawLine(QPointF(s * 0.20, s * 0.38), QPointF(s * 0.80, s * 0.38))

    elif name == "github":
        # GitHub icon
        painter.drawEllipse(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60))
        cat = QPainterPath()
        cat.moveTo(s * 0.35, s * 0.45)
        cat.lineTo(s * 0.42, s * 0.68)
        cat.lineTo(s * 0.58, s * 0.68)
        cat.lineTo(s * 0.65, s * 0.45)
        painter.drawPath(cat)

    elif name == "firefox":
        # Firefox icon
        painter.drawEllipse(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60))
        painter.drawArc(QRectF(s * 0.15, s * 0.35, s * 0.70, s * 0.30), 0, 360 * 16)
        painter.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.50, s * 0.80))

    elif name == "chrome":
        # Chrome icon
        painter.drawEllipse(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60))
        painter.drawEllipse(QRectF(s * 0.36, s * 0.36, s * 0.28, s * 0.28))
        painter.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.65, s * 0.40))
        painter.drawLine(QPointF(s * 0.65, s * 0.58), QPointF(s * 0.38, s * 0.72))
        painter.drawLine(QPointF(s * 0.35, s * 0.40), QPointF(s * 0.20, s * 0.58))

    else:
        # Generic stroke circle dot fallback
        painter.drawEllipse(QRectF(s * 0.25, s * 0.25, s * 0.50, s * 0.50))


def get_monochrome_icon(name: str, color: QColor = None, size: int = 24) -> QIcon:
    """
    Renders a clean, high-DPI vector stroke icon for the given symbol name.
    If color is None, dynamically extracts QApplication.palette().color(QPalette.ColorRole.WindowText).
    """
    if color is None:
        app = QApplication.instance()
        if app:
            color = app.palette().color(QPalette.ColorRole.WindowText)
        else:
            color = QColor("#333333")

    pixmap = QPixmap(size * 2, size * 2) # Render 2x for high-DPI sharpness
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    
    pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    
    draw_icon_path(painter, name, size * 2)
    painter.end()

    icon = QIcon()
    icon.addPixmap(pixmap)
    return icon
