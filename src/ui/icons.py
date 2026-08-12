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

    elif name in ("media_downloader", "media", "video"):
        # Display Screen + Play Triangle
        rect = QRectF(s * 0.18, s * 0.22, s * 0.64, s * 0.44)
        painter.drawRoundedRect(rect, 3, 3)
        # Stand
        painter.drawLine(QPointF(s * 0.40, s * 0.76), QPointF(s * 0.60, s * 0.76))
        painter.drawLine(QPointF(s * 0.50, s * 0.66), QPointF(s * 0.50, s * 0.76))
        # Play Triangle inside screen
        play = QPainterPath()
        play.moveTo(s * 0.42, s * 0.34)
        play.lineTo(s * 0.62, s * 0.44)
        play.lineTo(s * 0.42, s * 0.54)
        play.closeSubpath()
        painter.drawPath(play)

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

    elif name in ("exe", "msi"):
        # Windows Executable / MSI Installer Icon
        w = QRectF(s * 0.20, s * 0.22, s * 0.60, s * 0.56)
        painter.drawRoundedRect(w, 3, 3)
        painter.drawLine(QPointF(s * 0.20, s * 0.38), QPointF(s * 0.80, s * 0.38))
        # Gear / Run emblem inside
        cx, cy = s * 0.50, s * 0.56
        painter.drawEllipse(QRectF(cx - s * 0.10, cy - s * 0.10, s * 0.20, s * 0.20))
        painter.drawLine(QPointF(cx, cy - s * 0.14), QPointF(cx, cy + s * 0.14))
        painter.drawLine(QPointF(cx - s * 0.14, cy), QPointF(cx + s * 0.14, cy))

    elif name == "appimage":
        # Linux AppImage Package Icon
        b = QRectF(s * 0.20, s * 0.22, s * 0.60, s * 0.56)
        painter.drawRoundedRect(b, 4, 4)
        # Upward diagonal launcher arrow
        arr = QPainterPath()
        arr.moveTo(s * 0.36, s * 0.62)
        arr.lineTo(s * 0.64, s * 0.34)
        arr.moveTo(s * 0.44, s * 0.34)
        arr.lineTo(s * 0.64, s * 0.34)
        arr.lineTo(s * 0.64, s * 0.54)
        painter.drawPath(arr)

    elif name == "flatpak":
        # Flatpak Cube / Box Container Icon
        cube = QPainterPath()
        # Top diamond
        cube.moveTo(s * 0.50, s * 0.20)
        cube.lineTo(s * 0.80, s * 0.35)
        cube.lineTo(s * 0.50, s * 0.50)
        cube.lineTo(s * 0.20, s * 0.35)
        cube.closeSubpath()
        # Vertical sides down
        cube.moveTo(s * 0.20, s * 0.35)
        cube.lineTo(s * 0.20, s * 0.68)
        cube.lineTo(s * 0.50, s * 0.82)
        cube.lineTo(s * 0.80, s * 0.68)
        cube.lineTo(s * 0.80, s * 0.35)
        # Center vertical line
        cube.moveTo(s * 0.50, s * 0.50)
        cube.lineTo(s * 0.50, s * 0.82)
        painter.drawPath(cube)

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

    elif name in ("scheduler", "queues", "alarm"):
        # Alarm Clock / Scheduler
        cx, cy = s * 0.50, s * 0.52
        r = s * 0.28
        # Clock face
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # Bell ears (two small arcs on top)
        painter.drawLine(QPointF(cx - r * 0.70, cy - r * 0.90), QPointF(cx - r * 0.30, cy - r * 1.10))
        painter.drawLine(QPointF(cx + r * 0.70, cy - r * 0.90), QPointF(cx + r * 0.30, cy - r * 1.10))
        # Small knob on top
        painter.drawLine(QPointF(cx - s * 0.03, cy - r - s * 0.04), QPointF(cx + s * 0.03, cy - r - s * 0.04))
        # Hour hand (~10 o'clock position)
        painter.drawLine(QPointF(cx, cy), QPointF(cx - r * 0.40, cy - r * 0.50))
        # Minute hand (~12 o'clock position)
        painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - r * 0.65))
        # Stand legs at bottom
        painter.drawLine(QPointF(cx - r * 0.55, cy + r + s * 0.02), QPointF(cx - r * 0.80, cy + r + s * 0.10))
        painter.drawLine(QPointF(cx + r * 0.55, cy + r + s * 0.02), QPointF(cx + r * 0.80, cy + r + s * 0.10))

    else:
        # Generic stroke circle dot fallback
        painter.drawEllipse(QRectF(s * 0.25, s * 0.25, s * 0.50, s * 0.50))


def get_monochrome_icon(name: str, color: QColor = None, selected_color: QColor = None, size: int = 24, disabled_color: QColor = None) -> QIcon:
    """
    Renders a clean, high-DPI vector stroke icon for the given symbol name.
    Dynamically renders Normal state using WindowText color, Selected state using HighlightedText color,
    and Disabled state using a low-opacity faded pixmap to adapt across Light and Dark system themes.
    """
    app = QApplication.instance()
    if color is None:
        color = app.palette().color(QPalette.ColorRole.WindowText) if app else QColor("#333333")

    if selected_color is None:
        selected_color = app.palette().color(QPalette.ColorRole.HighlightedText) if app else QColor("#ffffff")

    def _render_pixmap(c: QColor) -> QPixmap:
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(c, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        draw_icon_path(painter, name, size * 2)
        painter.end()
        return pixmap

    normal_pixmap = _render_pixmap(color)
    selected_pixmap = _render_pixmap(selected_color)

    if disabled_color is not None:
        disabled_pixmap = _render_pixmap(disabled_color)
    else:
        disabled_pixmap = QPixmap(normal_pixmap.size())
        disabled_pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(disabled_pixmap)
        p.setOpacity(0.35)
        p.drawPixmap(0, 0, normal_pixmap)
        p.end()

    icon = QIcon()
    icon.addPixmap(normal_pixmap, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(normal_pixmap, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(selected_pixmap, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(selected_pixmap, QIcon.Mode.Selected, QIcon.State.On)
    icon.addPixmap(selected_pixmap, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(selected_pixmap, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(disabled_pixmap, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(disabled_pixmap, QIcon.Mode.Disabled, QIcon.State.On)
    return icon

