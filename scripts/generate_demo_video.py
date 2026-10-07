"""
Bengal Download Manager — High-Definition Demo Video Generator
==============================================================
Generates a professional 1080p 30fps application showcase video
demonstrating Bengal Download Manager's core features, UI, multi-segmented
turbo downloads, media grabber, theme switching, and options.

Outputs: assets/demo/bengal_demo.mp4
"""

import sys
import os
import math
import subprocess
import tempfile
import time
from pathlib import Path

# Add src to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QProgressBar, QDialog, QLineEdit,
    QPushButton, QFrame, QHeaderView, QAbstractItemView, QComboBox
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QFontDatabase, QBrush,
    QLinearGradient, QRadialGradient, QPen, QPainterPath, QIcon, QImage, QPolygonF
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, QSize

# Load application modules
from core.services.theme_service import apply_app_theme, init_app_font, get_file_icon
from ui.main_window import MainWindow
from ui.dialogs.file_info import DownloadFileInfoDialog
from ui.dialogs.progress import DownloadProgressDialog
from ui.dialogs.media_downloader import MediaDownloaderDialog
from ui.dialogs.options import OptionsDialog
from ui.dialogs.complete import DownloadCompleteDialog


WIDTH = 1920
HEIGHT = 1080
FPS = 30
OUTPUT_VIDEO = str(repo_root / "assets" / "demo" / "bengal_demo.mp4")
OUTPUT_PREVIEW_GIF = str(repo_root / "assets" / "demo" / "bengal_demo_preview.gif")


def ease_in_out(t: float) -> float:
    """Smooth cubic ease-in-out curve."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def point_lerp(p1: QPointF, p2: QPointF, t: float) -> QPointF:
    return QPointF(lerp(p1.x(), p2.x(), t), lerp(p1.y(), p2.y(), t))


class MockWorker:
    """Mock worker to simulate multi-threaded turbo download for the demo."""
    def __init__(self, filename="ubuntu-24.04-desktop-amd64.iso", total_bytes=6411517952):
        from PyQt6.QtCore import QObject, pyqtSignal
        class WorkerEmitter(QObject):
            log_signal = pyqtSignal(str)
            main_bar_signal = pyqtSignal(float)
            main_progress_signal = pyqtSignal(int, int, float, str, str)
            finished_signal = pyqtSignal(int, str, str, float)
            init_segments_signal = pyqtSignal(int)
            segment_update_signal = pyqtSignal(int, int, int)

        self.emitter = WorkerEmitter()
        self.log_signal = self.emitter.log_signal
        self.main_bar_signal = self.emitter.main_bar_signal
        self.main_progress_signal = self.emitter.main_progress_signal
        self.finished_signal = self.emitter.finished_signal
        self.init_segments_signal = self.emitter.init_segments_signal
        self.segment_update_signal = self.emitter.segment_update_signal

        self.filename = filename
        self.url = f"https://releases.ubuntu.com/24.04/{filename}"
        self.save_path = f"/home/user/Downloads/{filename}"
        self.total_bytes = total_bytes
        self.current_bytes = 0
        self.speed = 0.0
        self.status = "Downloading"
        self.num_connections = 16
        self.category = "Compressed"

    def isRunning(self):
        return True

    def start(self):
        pass

    def stop(self):
        pass

    def pause(self):
        pass

    def set_global_speed_limit(self, limit):
        pass

    def format_bytes(self, num_bytes, precision=2, pad=False):
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024**2:
            return f"{num_bytes/1024:.{precision}f} KB"
        elif num_bytes < 1024**3:
            return f"{num_bytes/(1024**2):.{precision}f} MB"
        else:
            return f"{num_bytes/(1024**3):.{precision}f} GB"


class DemoVideoRenderer:
    def __init__(self):
        # Initialize QApplication
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication(sys.argv)

        # Initialize fonts and theme
        init_app_font()
        apply_app_theme("Dark")

        # Load Logo
        logo_path = repo_root / "assets" / "logo.png"
        self.logo_pixmap = QPixmap(str(logo_path)) if logo_path.exists() else None

        # Build Main Window
        self.main_window = MainWindow(start_ipc=False)
        self.main_window.resize(1340, 790)
        self.populate_demo_data()

        # Build Dialogs
        self.mock_worker = MockWorker()
        self.progress_dialog = DownloadProgressDialog(self.mock_worker)
        self.progress_dialog.init_segment_table(16)
        self.progress_dialog.toggle_details(True)

        # File Info Dialog
        file_info_sample = {
            "url": "https://releases.ubuntu.com/noble/ubuntu-24.04-desktop-amd64.iso",
            "filename": "ubuntu-24.04-desktop-amd64.iso",
            "size": "5.97 GB (6,411,517,952 bytes)",
            "file_size": 6411517952,
            "category": "Compressed",
            "save_path": "/home/user/Downloads/ubuntu-24.04-desktop-amd64.iso"
        }
        self.file_info_dialog = DownloadFileInfoDialog(file_info_sample, parent=self.main_window)
        self.file_info_dialog.resize(580, 290)

        # Media Downloader Dialog
        self.media_dialog = MediaDownloaderDialog(self.main_window)
        self.media_dialog.txt_url.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.media_dialog.resize(760, 520)
        self.populate_media_dialog()

        # Options Dialog
        self.options_dialog = OptionsDialog(self.main_window)
        self.options_dialog.resize(660, 480)

        # Video dimensions and FFmpeg pipe
        self.width = WIDTH
        self.height = HEIGHT
        self.fps = FPS

    def populate_demo_data(self):
        """Populate realistic sample downloads in the main window."""
        self.main_window.download_table.setRowCount(0)
        self.demo_rows_data = [
            ("ubuntu-24.04-desktop-amd64.iso", "5.97 GB", "60.00%", "00:00:30", "84.25 MB/s", "Today 07:15", "Compressed"),
            ("blender-4.2.0-linux-x64.tar.xz", "330.00 MB", "Complete", "--:--:--", "--", "Today 06:50", "Compressed"),
            ("linux-6.12.tar.xz", "141.00 MB", "Complete", "--:--:--", "--", "Today 06:30", "Compressed"),
            ("nature_documentary_4k_hdr.mkv", "4.00 GB", "50.00%", "00:01:15", "--", "Today 05:40", "Video"),
            ("soundtrack_flac_lossless.zip", "850.00 MB", "Complete", "--:--:--", "--", "Today 04:10", "Music"),
            ("python-3.13.0-docs-pdf-a4.tar.bz2", "18.00 MB", "Complete", "--:--:--", "--", "Today 03:22", "Documents"),
        ]
        for row, (fn, sz, st, eta, speed, date_str, cat) in enumerate(self.demo_rows_data):
            self.main_window.download_table.insertRow(row)
            item_name = QTableWidgetItem(fn)
            item_name.setIcon(get_file_icon(fn))
            self.main_window.download_table.setItem(row, 0, item_name)
            self.main_window.download_table.setItem(row, 1, QTableWidgetItem(sz))
            self.main_window.download_table.setItem(row, 2, QTableWidgetItem(st))
            self.main_window.download_table.setItem(row, 3, QTableWidgetItem(eta))
            self.main_window.download_table.setItem(row, 4, QTableWidgetItem(speed))
            self.main_window.download_table.setItem(row, 5, QTableWidgetItem(date_str))
            self.main_window.download_table.setItem(row, 6, QTableWidgetItem(cat))

    def update_demo_progress(self, pct: float, speed_mbs: float):
        """Update live download progress in the first row."""
        if self.main_window.download_table.rowCount() > 0:
            item_status = self.main_window.download_table.item(0, 2)
            if item_status:
                item_status.setText(f"{pct:.2f}%")
            item_speed = self.main_window.download_table.item(0, 4)
            if item_speed:
                item_speed.setText(f"{speed_mbs:.2f} MB/s")

    def populate_media_dialog(self):
        """Populate media downloader with mock detected formats."""
        try:
            if hasattr(self.media_dialog, "stack") and hasattr(self.media_dialog, "page_video"):
                self.media_dialog.stack.setCurrentWidget(self.media_dialog.page_video)
            if hasattr(self.media_dialog, "lbl_video_title"):
                self.media_dialog.lbl_video_title.setText("4K Tech Showcase - Open Source Linux Demo (60 FPS)")
            if hasattr(self.media_dialog, "lbl_video_meta"):
                self.media_dialog.lbl_video_meta.setText("Uploader: OpenTech Media • Duration: 12:45 • Views: 1.2M • Codec: AV1 / Opus")
            if hasattr(self.media_dialog, "cmb_quality_preset"):
                self.media_dialog.cmb_quality_preset.setCurrentText("4K Ultra HD (2160p)")
            if hasattr(self.media_dialog, "btn_download"):
                self.media_dialog.btn_download.setEnabled(True)
        except Exception as e:
            print("Notice: Media dialog populate helper:", e)

    def render_background(self, painter: QPainter):
        """Render a stylish dark desktop wallpaper with subtle radial glow."""
        bg_grad = QRadialGradient(self.width / 2, self.height / 2, self.width * 0.7)
        bg_grad.setColorAt(0.0, QColor("#161b26"))
        bg_grad.setColorAt(0.5, QColor("#0e121a"))
        bg_grad.setColorAt(1.0, QColor("#07090d"))
        painter.fillRect(0, 0, self.width, self.height, bg_grad)

        painter.setPen(Qt.PenStyle.NoPen)
        glow_grad1 = QRadialGradient(320, 220, 420)
        glow_grad1.setColorAt(0.0, QColor(41, 128, 185, 25))
        glow_grad1.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad1)
        painter.drawEllipse(QPointF(320, 220), 420, 420)

        glow_grad2 = QRadialGradient(self.width - 320, self.height - 220, 500)
        glow_grad2.setColorAt(0.0, QColor(230, 126, 34, 20))
        glow_grad2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad2)
        painter.drawEllipse(QPointF(self.width - 320, self.height - 220), 500, 500)

    def draw_banner_pill(self, painter: QPainter, text: str, subtext: str = "", icon_text: str = "⚡"):
        """Draw top feature callout badge."""
        painter.save()
        pill_w = 740
        pill_h = 58
        pill_x = (self.width - pill_w) / 2
        pill_y = 32

        path = QPainterPath()
        path.addRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 29, 29)

        pill_grad = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y + pill_h)
        pill_grad.setColorAt(0.0, QColor(28, 35, 48, 240))
        pill_grad.setColorAt(1.0, QColor(18, 22, 32, 240))
        painter.fillPath(path, pill_grad)

        painter.setPen(QPen(QColor(52, 152, 219, 130), 1.5))
        painter.drawPath(path)

        icon_rect = QRectF(pill_x + 10, pill_y + 9, 40, 40)
        painter.setBrush(QColor(52, 152, 219, 40))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(icon_rect)

        painter.setPen(QColor("#3498db"))
        painter.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, icon_text)

        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Inter", 13, QFont.Weight.DemiBold))
        painter.drawText(int(pill_x + 62), int(pill_y + 25), text)

        if subtext:
            painter.setPen(QColor("#95a5a6"))
            painter.setFont(QFont("Inter", 10, QFont.Weight.Normal))
            painter.drawText(int(pill_x + 62), int(pill_y + 46), subtext)

        if self.logo_pixmap:
            scaled_logo = self.logo_pixmap.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(50, 42, scaled_logo)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        painter.drawText(98, 58, "Bengal Download Manager")
        painter.setPen(QColor("#7f8c8d"))
        painter.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        painter.drawText(98, 75, "v0.2.72 • Open Source")

        painter.restore()

    def draw_window_frame(self, painter: QPainter, widget: QWidget, x: int, y: int, custom_shadow=True):
        """Render a widget onto the painter canvas with a drop shadow."""
        painter.save()
        w = widget.width()
        h = widget.height()

        if custom_shadow:
            for i in range(5, 0, -1):
                shadow_alpha = int(12 * (6 - i))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, shadow_alpha))
                offset_y = i * 4
                blur_rad = i * 6
                painter.drawRoundedRect(
                    QRectF(x - blur_rad, y - blur_rad + offset_y, w + blur_rad * 2, h + blur_rad * 2),
                    14, 14
                )

        widget.render(painter, QPoint(int(x), int(y)))

        border_path = QPainterPath()
        border_path.addRoundedRect(QRectF(x, y, w, h), 8, 8)
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)

        painter.restore()

    def draw_mouse_cursor(self, painter: QPainter, pos: QPointF, clicking=False, click_progress=0.0):
        """Draw mouse cursor with click ripples."""
        painter.save()
        cx = pos.x()
        cy = pos.y()

        if clicking and click_progress > 0:
            ripple_rad = 10 + click_progress * 35
            ripple_alpha = int((1.0 - click_progress) * 180)
            painter.setPen(QPen(QColor(52, 152, 219, ripple_alpha), 2.5))
            painter.setBrush(QColor(52, 152, 219, int(ripple_alpha * 0.3)))
            painter.drawEllipse(QPointF(cx, cy), ripple_rad, ripple_rad)

        cursor_poly = QPolygonF([
            QPointF(cx, cy),
            QPointF(cx, cy + 18),
            QPointF(cx + 4.5, cy + 14),
            QPointF(cx + 8.5, cy + 22),
            QPointF(cx + 12.5, cy + 20),
            QPointF(cx + 8.5, cy + 12.5),
            QPointF(cx + 14, cy + 12.5),
        ])

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 100))
        shadow_poly = QPolygonF([QPointF(p.x() + 2, p.y() + 2) for p in cursor_poly])
        painter.drawPolygon(shadow_poly)

        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#111111"), 1.5))
        painter.drawPolygon(cursor_poly)

        painter.restore()

    def generate_video(self):
        """Main rendering loop: generate scenes and encode directly to MP4 via ffmpeg."""
        os.makedirs(os.path.dirname(OUTPUT_VIDEO), exist_ok=True)

        print(f"🎬 Initializing Bengal Demo Video Generator ({self.width}x{self.height} @ {self.fps}fps)...")

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.width}x{self.height}",
            "-pix_fmt", "rgb24",
            "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "18",
            OUTPUT_VIDEO
        ]

        ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        total_scenes_duration_sec = 42
        total_frames = total_scenes_duration_sec * self.fps
        print(f"🎥 Rendering {total_frames} frames ({total_scenes_duration_sec} seconds)...")

        frame_idx = 0

        # =========================================================================
        # SCENE 1: TITLE & LOGO INTRO (0s - 4.5s -> 135 frames)
        # =========================================================================
        scene_1_frames = int(4.5 * self.fps)
        for i in range(scene_1_frames):
            t = i / float(scene_1_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            self.render_background(painter)

            scale = lerp(0.85, 1.0, ease_in_out(min(1.0, t * 1.5)))
            alpha = min(255, int(ease_in_out(min(1.0, t * 2.0)) * 255))

            painter.save()
            center_x = self.width / 2
            center_y = self.height / 2 - 40

            if self.logo_pixmap:
                logo_size = int(140 * scale)
                scaled_logo = self.logo_pixmap.scaled(
                    logo_size, logo_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(int(center_x - logo_size / 2), int(center_y - 120), scaled_logo)

            painter.setPen(QColor(255, 255, 255, alpha))
            painter.setFont(QFont("Inter", 32, QFont.Weight.Bold))
            painter.drawText(QRectF(0, center_y + 40, self.width, 60), Qt.AlignmentFlag.AlignCenter, "Bengal Download Manager")

            painter.setPen(QColor(52, 152, 219, alpha))
            painter.setFont(QFont("Inter", 16, QFont.Weight.DemiBold))
            painter.drawText(QRectF(0, center_y + 105, self.width, 40), Qt.AlignmentFlag.AlignCenter, "Ultra-Fast Multi-Threaded Download Accelerator for Linux & Desktop")

            pills = [
                ("⚡ 32x Multi-Segment Turbo Engine", QColor("#e67e22")),
                ("🎨 Dark & Light Native Theming", QColor("#3498db")),
                ("🎬 Smart Media Grabber", QColor("#9b59b6")),
                ("🚀 High-Speed Aria2 RPC Core", QColor("#2ecc71")),
            ]
            pill_y = center_y + 175
            start_x = (self.width - (len(pills) * 260 + 60)) / 2
            for idx, (pill_txt, pill_col) in enumerate(pills):
                px = start_x + idx * 280
                pill_rect = QRectF(px, pill_y, 260, 42)
                p_path = QPainterPath()
                p_path.addRoundedRect(pill_rect, 21, 21)
                painter.fillPath(p_path, QColor(25, 32, 45, int(alpha * 0.9)))
                painter.setPen(QPen(QColor(pill_col.red(), pill_col.green(), pill_col.blue(), int(alpha * 0.8)), 1.5))
                painter.drawPath(p_path)

                painter.setPen(QColor(255, 255, 255, alpha))
                painter.setFont(QFont("Inter", 10, QFont.Weight.Medium))
                painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, pill_txt)

            painter.restore()
            painter.end()

            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 2: MAIN DASHBOARD & CATEGORIES (4.5s - 10s -> 165 frames)
        # =========================================================================
        scene_2_frames = int(5.5 * self.fps)
        win_x = int((self.width - 1340) / 2)
        win_y = 115

        pos_start = QPointF(win_x + 100, win_y + 80)
        pos_compressed = QPointF(win_x + 80, win_y + 240)
        pos_videos = QPointF(win_x + 80, win_y + 270)
        pos_search = QPointF(win_x + 850, win_y + 40)

        for i in range(scene_2_frames):
            t = i / float(scene_2_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                "Intelligent Download Dashboard & Category Organization",
                "Real-time bandwidth monitoring, tabular metrics, and category filtering",
                "📊"
            )

            if t < 0.35:
                sub_t = ease_in_out(t / 0.35)
                cur_pos = point_lerp(pos_start, pos_compressed, sub_t)
                clicking = 0.30 <= t <= 0.35
                click_p = (t - 0.30) / 0.05 if clicking else 0.0
                if hasattr(self.main_window, "all_downloads_header") and self.main_window.all_downloads_header.childCount() > 0:
                    self.main_window.category_tree.setCurrentItem(self.main_window.all_downloads_header.child(0))
            elif t < 0.70:
                sub_t = ease_in_out((t - 0.35) / 0.35)
                cur_pos = point_lerp(pos_compressed, pos_videos, sub_t)
                clicking = 0.65 <= t <= 0.70
                click_p = (t - 0.65) / 0.05 if clicking else 0.0
                if hasattr(self.main_window, "all_downloads_header") and self.main_window.all_downloads_header.childCount() > 4:
                    self.main_window.category_tree.setCurrentItem(self.main_window.all_downloads_header.child(4))
            else:
                sub_t = ease_in_out((t - 0.70) / 0.30)
                cur_pos = point_lerp(pos_videos, pos_search, sub_t)
                clicking = False
                click_p = 0.0
                if hasattr(self.main_window, "all_downloads_header"):
                    self.main_window.category_tree.setCurrentItem(self.main_window.all_downloads_header)

            self.draw_window_frame(painter, self.main_window, win_x, win_y)
            self.draw_mouse_cursor(painter, cur_pos, clicking=clicking, click_progress=click_p)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 3: ADD DOWNLOAD & PRE-FETCH METADATA (10s - 16s -> 180 frames)
        # =========================================================================
        scene_3_frames = int(6.0 * self.fps)
        pos_add_btn = QPointF(win_x + 35, win_y + 40)
        pos_dlg_conn = QPointF(self.width / 2 + 120, self.height / 2 + 20)
        pos_dlg_download = QPointF(self.width / 2 + 180, self.height / 2 + 85)

        dlg_x = int((self.width - self.file_info_dialog.width()) / 2)
        dlg_y = int((self.height - self.file_info_dialog.height()) / 2)

        for i in range(scene_3_frames):
            t = i / float(scene_3_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                "Smart URL Sniffing & Pre-Fetch Engine",
                "Instant filename parsing, size discovery, and multi-connection optimization",
                "⚡"
            )

            self.draw_window_frame(painter, self.main_window, win_x, win_y)

            if t > 0.15:
                overlay_alpha = int(min(140, (t - 0.15) / 0.15 * 140))
                painter.fillRect(0, 0, self.width, self.height, QColor(0, 0, 0, overlay_alpha))
                self.draw_window_frame(painter, self.file_info_dialog, dlg_x, dlg_y)

            if t < 0.20:
                sub_t = ease_in_out(t / 0.20)
                cur_pos = point_lerp(pos_search, pos_add_btn, sub_t)
                clicking = 0.16 <= t <= 0.20
                click_p = (t - 0.16) / 0.04 if clicking else 0.0
            elif t < 0.60:
                sub_t = ease_in_out((t - 0.20) / 0.40)
                cur_pos = point_lerp(pos_add_btn, pos_dlg_conn, sub_t)
                clicking = 0.55 <= t <= 0.60
                click_p = (t - 0.55) / 0.05 if clicking else 0.0
            else:
                sub_t = ease_in_out((t - 0.60) / 0.40)
                cur_pos = point_lerp(pos_dlg_conn, pos_dlg_download, sub_t)
                clicking = 0.92 <= t <= 0.98
                click_p = (t - 0.92) / 0.06 if clicking else 0.0

            self.draw_mouse_cursor(painter, cur_pos, clicking=clicking, click_progress=click_p)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 4: 16x MULTI-SEGMENT TURBO DOWNLOAD (16s - 25s -> 270 frames)
        # =========================================================================
        scene_4_frames = int(9.0 * self.fps)
        prog_w = self.progress_dialog.width()
        prog_h = self.progress_dialog.height()
        prog_x = int((self.width - prog_w) / 2)
        prog_y = int((self.height - prog_h) / 2)

        for i in range(scene_4_frames):
            t = i / float(scene_4_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                "16-Stream Parallel Multi-Segment Turbo Acceleration",
                "High-throughput chunk scheduler maximizing network bandwidth with Aria2 & Python engines",
                "🚀"
            )

            pct = min(100.0, lerp(15.0, 98.5, ease_in_out(t)))
            curr_b = int(self.mock_worker.total_bytes * (pct / 100.0))
            speed_mb = lerp(48.5, 94.8, math.sin(t * math.pi))
            speed_bytes = speed_mb * (1024 * 1024)

            # Update progress dialog labels
            if hasattr(self.progress_dialog, "pbar"):
                self.progress_dialog.pbar.setValue(int(pct))
            if hasattr(self.progress_dialog, "lbl_downloaded"):
                self.progress_dialog.lbl_downloaded.setText(self.mock_worker.format_bytes(curr_b))
            if hasattr(self.progress_dialog, "lbl_speed"):
                self.progress_dialog.lbl_speed.setText(f"{speed_mb:.2f} MB/s")
            if hasattr(self.progress_dialog, "lbl_time"):
                rem_sec = max(1, int((self.mock_worker.total_bytes - curr_b) / max(1.0, speed_bytes)))
                self.progress_dialog.lbl_time.setText(f"00:00:{rem_sec:02d}")

            # Update segment table rows
            if hasattr(self.progress_dialog, "seg_table"):
                tbl = self.progress_dialog.seg_table
                for seg_idx in range(tbl.rowCount()):
                    seg_pct = min(100.0, pct + math.sin(t * 8 + seg_idx * 0.7) * 8.0)
                    seg_down = int((self.mock_worker.total_bytes / 16) * (seg_pct / 100.0))
                    seg_speed = speed_mb / 16.0
                    item_dl = tbl.item(seg_idx, 1)
                    if item_dl: item_dl.setText(self.mock_worker.format_bytes(seg_down))
                    item_sp = tbl.item(seg_idx, 2)
                    if item_sp: item_sp.setText(f"{seg_speed:.2f} MB/s")
                    item_st = tbl.item(seg_idx, 3)
                    if item_st: item_st.setText(f"Receiving data ({seg_pct:.0f}%)")

            # Update segment progress bars in container
            if hasattr(self.progress_dialog, "segment_bars"):
                for seg_idx, pbar in enumerate(self.progress_dialog.segment_bars):
                    seg_pct = min(100.0, pct + math.sin(t * 8 + seg_idx * 0.7) * 8.0)
                    if hasattr(pbar, "setValue"):
                        pbar.setValue(int(seg_pct))

            self.update_demo_progress(pct, speed_mb)

            self.draw_window_frame(painter, self.main_window, win_x, win_y)

            painter.fillRect(0, 0, self.width, self.height, QColor(0, 0, 0, 120))
            self.draw_window_frame(painter, self.progress_dialog, prog_x, prog_y)

            cur_pos = QPointF(prog_x + prog_w - 60, prog_y + prog_h - 30)
            self.draw_mouse_cursor(painter, cur_pos, clicking=False)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 5: MEDIA DOWNLOADER & VIDEO SNIFFER (25s - 31s -> 180 frames)
        # =========================================================================
        scene_5_frames = int(6.0 * self.fps)
        media_x = int((self.width - self.media_dialog.width()) / 2)
        media_y = int((self.height - self.media_dialog.height()) / 2)
        pos_media_btn = QPointF(win_x + 190, win_y + 40)
        pos_media_sel = QPointF(media_x + 200, media_y + 220)
        pos_media_dl = QPointF(media_x + self.media_dialog.width() - 80, media_y + self.media_dialog.height() - 35)

        for i in range(scene_5_frames):
            t = i / float(scene_5_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                "Integrated Media Grabber & Stream Sniffer",
                "Download 4K UHD, Full HD 60fps streams, and extract high-bitrate MP3 audio",
                "🎬"
            )

            self.draw_window_frame(painter, self.main_window, win_x, win_y)

            painter.fillRect(0, 0, self.width, self.height, QColor(0, 0, 0, 130))
            self.draw_window_frame(painter, self.media_dialog, media_x, media_y)

            if t < 0.5:
                sub_t = ease_in_out(t / 0.5)
                cur_pos = point_lerp(pos_media_btn, pos_media_sel, sub_t)
                clicking = 0.45 <= t <= 0.50
                click_p = (t - 0.45) / 0.05 if clicking else 0.0
            else:
                sub_t = ease_in_out((t - 0.5) / 0.5)
                cur_pos = point_lerp(pos_media_sel, pos_media_dl, sub_t)
                clicking = 0.90 <= t <= 0.96
                click_p = (t - 0.90) / 0.06 if clicking else 0.0

            self.draw_mouse_cursor(painter, cur_pos, clicking=clicking, click_progress=click_p)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 6: DYNAMIC THEME SWITCHING (31s - 36.5s -> 165 frames)
        # =========================================================================
        scene_6_frames = int(5.5 * self.fps)
        pos_theme_toggle = QPointF(win_x + 1200, win_y + 40)

        for i in range(scene_6_frames):
            t = i / float(scene_6_frames)

            if 0.30 <= t < 0.75:
                apply_app_theme("Light")
                current_theme_name = "Modern Light Theme"
                pill_icon = "☀️"
            else:
                apply_app_theme("Dark")
                current_theme_name = "Sleek Dark Theme"
                pill_icon = "🌙"

            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                f"Dynamic Theme Adaptation ({current_theme_name})",
                "Full palette awareness with OpenType tabular figures (tnum) and system sync",
                pill_icon
            )

            self.draw_window_frame(painter, self.main_window, win_x, win_y)

            cur_pos = pos_theme_toggle
            clicking = (0.28 <= t <= 0.32) or (0.73 <= t <= 0.77)
            click_p = 0.5 if clicking else 0.0
            self.draw_mouse_cursor(painter, cur_pos, clicking=clicking, click_progress=click_p)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # Reset theme to Dark
        apply_app_theme("Dark")

        # =========================================================================
        # SCENE 7: OPTIONS & ARIA2 CONFIGURATION (36.5s - 40s -> 105 frames)
        # =========================================================================
        scene_7_frames = int(3.5 * self.fps)
        opt_x = int((self.width - self.options_dialog.width()) / 2)
        opt_y = int((self.height - self.options_dialog.height()) / 2)

        for i in range(scene_7_frames):
            t = i / float(scene_7_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            self.render_background(painter)
            self.draw_banner_pill(
                painter,
                "Advanced Engine & Network Preferences",
                "Dual-Engine (Python & Aria2 RPC), connection pooling, proxies, and scheduler",
                "⚙️"
            )

            self.draw_window_frame(painter, self.main_window, win_x, win_y)
            painter.fillRect(0, 0, self.width, self.height, QColor(0, 0, 0, 130))
            self.draw_window_frame(painter, self.options_dialog, opt_x, opt_y)

            cur_pos = QPointF(opt_x + 200, opt_y + 120)
            self.draw_mouse_cursor(painter, cur_pos, clicking=False)

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # =========================================================================
        # SCENE 8: OUTRO & CALL TO ACTION (40s - 44s -> 120 frames)
        # =========================================================================
        scene_8_frames = int(4.0 * self.fps)
        for i in range(scene_8_frames):
            t = i / float(scene_8_frames)
            img = QImage(self.width, self.height, QImage.Format.Format_RGB888)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            self.render_background(painter)

            center_x = self.width / 2
            center_y = self.height / 2 - 30

            if self.logo_pixmap:
                logo_size = 130
                scaled_logo = self.logo_pixmap.scaled(
                    logo_size, logo_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(int(center_x - logo_size / 2), int(center_y - 120), scaled_logo)

            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Inter", 30, QFont.Weight.Bold))
            painter.drawText(QRectF(0, center_y + 35, self.width, 50), Qt.AlignmentFlag.AlignCenter, "Bengal Download Manager")

            painter.setPen(QColor("#3498db"))
            painter.setFont(QFont("Inter", 15, QFont.Weight.Medium))
            painter.drawText(QRectF(0, center_y + 90, self.width, 35), Qt.AlignmentFlag.AlignCenter, "Open Source • Cross-Platform • Fast & Reliable")

            painter.setPen(QColor("#bdc3c7"))
            painter.setFont(QFont("Inter", 12, QFont.Weight.Normal))
            painter.drawText(QRectF(0, center_y + 135, self.width, 30), Qt.AlignmentFlag.AlignCenter, "📦 Available as Flatpak, AppImage, Snap & Native Linux Packages")

            url_box = QRectF(center_x - 240, center_y + 185, 480, 48)
            u_path = QPainterPath()
            u_path.addRoundedRect(url_box, 24, 24)
            painter.fillPath(u_path, QColor(30, 39, 54, 230))
            painter.setPen(QPen(QColor(52, 152, 219, 180), 1.5))
            painter.drawPath(u_path)

            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Inter", 13, QFont.Weight.DemiBold))
            painter.drawText(url_box, Qt.AlignmentFlag.AlignCenter, "⭐ github.com/tazihad/bengal-download-manager")

            painter.end()
            rgb_data = img.bits().asstring(self.width * self.height * 3)
            ffmpeg_proc.stdin.write(rgb_data)
            frame_idx += 1

        # Close ffmpeg input stream
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()

        print(f"✅ Full HD Demo Video successfully rendered and saved to: {OUTPUT_VIDEO}")

        try:
            print("🎞️ Generating animated GIF preview...")
            gif_cmd = [
                "ffmpeg",
                "-y",
                "-i", OUTPUT_VIDEO,
                "-vf", "fps=10,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
                "-ss", "4",
                "-t", "20",
                OUTPUT_PREVIEW_GIF
            ]
            subprocess.run(gif_cmd, check=True)
            print(f"✅ GIF Preview generated: {OUTPUT_PREVIEW_GIF}")
        except Exception as e:
            print(f"Notice: GIF generation skipped or had warning: {e}")


if __name__ == "__main__":
    renderer = DemoVideoRenderer()
    renderer.generate_video()
