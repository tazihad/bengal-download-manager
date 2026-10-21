#!/usr/bin/env python3
"""
Generates high-resolution branding posters for Bengal Download Manager.
Outputs 1920x1080 (16:9 full HD) artwork into assets/posters/.
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import (
    QImage, QPainter, QPixmap, QColor, QFont, QLinearGradient, 
    QRadialGradient, QPen, QBrush, QPainterPath
)
from PyQt6.QtCore import Qt, QRectF, QPointF

# Initialize offscreen Qt application
app = QApplication.instance() or QApplication(["-platform", "offscreen"])

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
POSTERS_DIR = os.path.join(ASSETS_DIR, "posters")
SCREENSHOTS_DIR = os.path.join(ASSETS_DIR, "screenshots")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

os.makedirs(POSTERS_DIR, exist_ok=True)


def get_screenshot_path(base_name: str) -> str:
    """Finds screenshot path supporting numbered prefixes and extensions."""
    if os.path.exists(SCREENSHOTS_DIR):
        for fname in sorted(os.listdir(SCREENSHOTS_DIR)):
            clean = fname.lower()
            if base_name in clean:
                return os.path.join(SCREENSHOTS_DIR, fname)
            if base_name == "extension" and "extension" in clean:
                return os.path.join(SCREENSHOTS_DIR, fname)
    return os.path.join(SCREENSHOTS_DIR, f"{base_name}.webp")


def draw_pill(painter, x, y, text, icon_text="⚡", bg_color=QColor(255, 140, 0, 40), border_color=QColor(255, 140, 0, 160), text_color=QColor(255, 180, 50)):
    font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13)
    font.setBold(True)
    painter.setFont(font)
    full_text = f"{icon_text}  {text}"
    metrics = painter.fontMetrics()
    w = metrics.horizontalAdvance(full_text) + 36
    h = 36
    
    rect = QRectF(x, y, w, h)
    path = QPainterPath()
    path.addRoundedRect(rect, 18, 18)
    
    painter.fillPath(path, bg_color)
    painter.setPen(QPen(border_color, 1.5))
    painter.drawPath(path)
    
    painter.setPen(text_color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, full_text)
    return w


def draw_framed_screenshot(painter, pixmap, dest_rect, radius=18):
    """Draws screenshot with soft drop shadow and sleek dark border frame."""
    # Outer drop shadow
    for i in range(16, 0, -2):
        s_rect = dest_rect.adjusted(-i, -i + 6, i, i + 12)
        s_path = QPainterPath()
        s_path.addRoundedRect(s_rect, radius + i // 2, radius + i // 2)
        alpha = int(18 * (1.0 - i / 16.0))
        painter.fillPath(s_path, QColor(0, 0, 0, alpha))
        
    # Clip and draw image
    clip_path = QPainterPath()
    clip_path.addRoundedRect(dest_rect, radius, radius)
    
    painter.save()
    painter.setClipPath(clip_path)
    scaled = pixmap.scaled(
        int(dest_rect.width()), int(dest_rect.height()),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation
    )
    painter.drawPixmap(int(dest_rect.x()), int(dest_rect.y()), scaled)
    painter.restore()
    
    # Outer stroke
    painter.setPen(QPen(QColor(255, 255, 255, 45), 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(clip_path)


def generate_speed_poster():
    """Poster 1: Extreme Speed & Multi-threaded Aria2 Acceleration."""
    out_path = os.path.join(POSTERS_DIR, "poster_speed_acceleration.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(10, 14, 26))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Dynamic background glow
    glow1 = QRadialGradient(400, 300, 700)
    glow1.setColorAt(0.0, QColor(255, 100, 20, 50))
    glow1.setColorAt(0.5, QColor(180, 40, 10, 15))
    glow1.setColorAt(1.0, QColor(10, 14, 26, 0))
    p.fillRect(0, 0, 1920, 1080, glow1)
    
    glow2 = QRadialGradient(1500, 800, 800)
    glow2.setColorAt(0.0, QColor(30, 100, 255, 40))
    glow2.setColorAt(1.0, QColor(10, 14, 26, 0))
    p.fillRect(0, 0, 1920, 1080, glow2)
    
    # Logo
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(100, 95, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    brand_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 24)
    brand_font.setBold(True)
    p.setFont(brand_font)
    p.drawText(180, 140, "Bengal Download Manager")
    
    # Badge Pill
    draw_pill(p, 100, 200, "High Performance Engine", "⚡", QColor(255, 120, 0, 40), QColor(255, 120, 0, 180), QColor(255, 170, 50))
    
    # Hero Title
    title_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 46)
    title_font.setBold(True)
    p.setFont(title_font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(100, 310, "Unleash Maximum")
    
    # Accent colored text
    grad_text = QLinearGradient(100, 0, 700, 0)
    grad_text.setColorAt(0.0, QColor(255, 130, 20))
    grad_text.setColorAt(1.0, QColor(255, 200, 80))
    p.setPen(QPen(QBrush(grad_text), 1))
    p.drawText(100, 375, "Download Speeds")
    
    # Subtitle
    sub_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17)
    p.setFont(sub_font)
    p.setPen(QColor(160, 175, 205))
    p.drawText(100, 435, "Engineered with native 32-connection chunk segmentation,")
    p.drawText(100, 465, "Aria2 RPC daemon integration, and smart bandwidth optimization.")
    
    # Feature checklist items
    features = [
        ("Multi-Threaded Acceleration", "Up to 32 concurrent connection segments per task"),
        ("Smart Auto-Resume", "Seamless recovery from network cuts & broken streams"),
        ("Resource Lightweight", "Built with modern Qt6 for minimal CPU & RAM usage")
    ]
    
    cur_y = 540
    for title, desc in features:
        # Checkmark bullet
        check_path = QPainterPath()
        check_path.addRoundedRect(QRectF(100, cur_y - 22, 34, 34), 8, 8)
        p.fillPath(check_path, QColor(255, 130, 20, 40))
        p.setPen(QPen(QColor(255, 140, 30), 1.5))
        p.drawPath(check_path)
        
        p.setPen(QColor(255, 160, 50))
        p.setFont(QFont("sans-serif", 15, QFont.Weight.Bold))
        p.drawText(QRectF(100, cur_y - 22, 34, 34), Qt.AlignmentFlag.AlignCenter, "✓")
        
        f_title_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold)
        p.setFont(f_title_font)
        p.setPen(QColor(245, 248, 255))
        p.drawText(150, cur_y, title)
        
        f_desc_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13)
        p.setFont(f_desc_font)
        p.setPen(QColor(140, 155, 185))
        p.drawText(150, cur_y + 24, desc)
        
        cur_y += 75
        
    # App screenshot hero showcase on right
    main_sc = get_screenshot_path("main-app")
    if os.path.exists(main_sc):
        pm = QPixmap(main_sc)
        draw_framed_screenshot(p, pm, QRectF(920, 180, 920, 560), radius=16)
        
    # Download progress popup overlapping in foreground
    prog_sc = get_screenshot_path("download-progress")
    if os.path.exists(prog_sc):
        pm_prog = QPixmap(prog_sc)
        draw_framed_screenshot(p, pm_prog, QRectF(1120, 480, 680, 460), radius=14)
        
    # Footer tag
    foot_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13)
    p.setFont(foot_font)
    p.setPen(QColor(100, 115, 145))
    p.drawText(100, 1000, "Free & Open Source  •  Native Linux & Windows  •  Built with PyQt6 & Aria2")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


def generate_ecosystem_poster():
    """Poster 2: Complete Desktop & Browser Ecosystem Integration."""
    out_path = os.path.join(POSTERS_DIR, "poster_ecosystem_integration.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(11, 15, 25))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Ambient Lighting
    glow = QRadialGradient(960, 400, 900)
    glow.setColorAt(0.0, QColor(0, 180, 216, 45))
    glow.setColorAt(0.6, QColor(10, 80, 160, 15))
    glow.setColorAt(1.0, QColor(11, 15, 25, 0))
    p.fillRect(0, 0, 1920, 1080, glow)
    
    # Top centered banner
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(720, 70, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 26, QFont.Weight.Bold))
    p.drawText(795, 112, "Bengal Download Manager")
    
    draw_pill(p, 830, 155, "Cross-Browser Integration", "🌐", QColor(0, 180, 216, 40), QColor(0, 180, 216, 180), QColor(90, 225, 255))
    
    # Title
    t_font = QFont("Inter, Noto Sans, Ubuntu, sans-serif", 40, QFont.Weight.Bold)
    p.setFont(t_font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, 210, 1920, 60), Qt.AlignmentFlag.AlignCenter, "Seamless Browser & Media Downloader")
    
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 16))
    p.setPen(QColor(150, 170, 200))
    p.drawText(QRectF(0, 275, 1920, 40), Qt.AlignmentFlag.AlignCenter, "Capture 4K videos, live streams, and files effortlessly with Chrome, Firefox, Brave, and Edge extensions.")
    
    # 3-Card Showcase Layout
    # Card 1: Media Downloader
    media_sc = get_screenshot_path("media-downloader")
    if os.path.exists(media_sc):
        draw_framed_screenshot(p, QPixmap(media_sc), QRectF(100, 360, 530, 400), radius=16)
        
    # Card 2: Main Application
    main_sc = get_screenshot_path("main-app")
    if os.path.exists(main_sc):
        draw_framed_screenshot(p, QPixmap(main_sc), QRectF(695, 330, 530, 440), radius=18)
        
    # Card 3: Browser Extension Popup
    ext_sc = get_screenshot_path("extension")
    if os.path.exists(ext_sc):
        draw_framed_screenshot(p, QPixmap(ext_sc), QRectF(1290, 360, 530, 400), radius=16)
        
    # Feature 3 Columns Below Cards
    col_data = [
        ("🎬 Built-in Media Sniffer", "Auto-sniffs streaming video qualities and streams from YouTube, Vimeo, and web players.", 100),
        ("⚡ High-Speed Multi-Connection", "Accelerates large files with Aria2 chunk workers and smart queue prioritization.", 695),
        ("🧩 One-Click Extension Bridge", "Zero-friction link interception with native TCP IPC bridge for Chromium & Firefox.", 1290)
    ]
    
    for title, desc, col_x in col_data:
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold))
        p.drawText(col_x, 830, title)
        
        p.setPen(QColor(140, 160, 190))
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
        p.drawText(QRectF(col_x, 850, 530, 60), Qt.TextFlag.TextWordWrap, desc)
        
    p.setPen(QColor(90, 110, 140))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
    p.drawText(QRectF(0, 990, 1920, 40), Qt.AlignmentFlag.AlignCenter, "Open Source  •  No Ads  •  No Tracking  •  Linux Flatpak, Snap, AppImage & Windows")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


def generate_theme_poster():
    """Poster 3: Adaptive Themes & Elegant UI Polish."""
    out_path = os.path.join(POSTERS_DIR, "poster_adaptive_themes.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(14, 18, 30))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Purple/Cyan gradient background
    bg_grad = QRadialGradient(500, 540, 800)
    bg_grad.setColorAt(0.0, QColor(140, 40, 240, 35))
    bg_grad.setColorAt(0.5, QColor(40, 120, 220, 15))
    bg_grad.setColorAt(1.0, QColor(14, 18, 30, 0))
    p.fillRect(0, 0, 1920, 1080, bg_grad)
    
    # Header
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(100, 95, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 24, QFont.Weight.Bold))
    p.drawText(180, 140, "Bengal Download Manager")
    
    draw_pill(p, 100, 200, "Designed for Modern Desktops", "🎨", QColor(140, 40, 240, 40), QColor(180, 80, 255, 180), QColor(210, 140, 255))
    
    # Hero Title
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 46, QFont.Weight.Bold))
    p.setPen(QColor(255, 255, 255))
    p.drawText(100, 310, "Crafted for Every")
    
    grad_text = QLinearGradient(100, 0, 600, 0)
    grad_text.setColorAt(0.0, QColor(180, 90, 255))
    grad_text.setColorAt(1.0, QColor(60, 190, 255))
    p.setPen(QPen(QBrush(grad_text), 1))
    p.drawText(100, 375, "Desktop Aesthetic")
    
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17))
    p.setPen(QColor(165, 180, 210))
    p.drawText(100, 435, "Full adaptive theme support including Dark, Light, Chroma,")
    p.drawText(100, 465, "and Stellar styles with native Wayland title bar integration.")
    
    # Badges
    badges = [
        ("🌙 Dark & Light Modes", "Adaptive system color schemes and custom palette overrides"),
        ("🌐 16+ Languages", "Native AI translation support for global accessibility"),
        ("⚡ Wayland & CSD Ready", "Crisp high-DPI font rendering and modern window decoration")
    ]
    cur_y = 540
    for title, desc in badges:
        dot_path = QPainterPath()
        dot_path.addRoundedRect(QRectF(100, cur_y - 20, 32, 32), 8, 8)
        p.fillPath(dot_path, QColor(160, 80, 255, 40))
        p.setPen(QPen(QColor(180, 100, 255), 1.5))
        p.drawPath(dot_path)
        
        p.setPen(QColor(210, 150, 255))
        p.setFont(QFont("sans-serif", 14, QFont.Weight.Bold))
        p.drawText(QRectF(100, cur_y - 20, 32, 32), Qt.AlignmentFlag.AlignCenter, "★")
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold))
        p.setPen(QColor(245, 248, 255))
        p.drawText(150, cur_y, title)
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
        p.setPen(QColor(140, 155, 185))
        p.drawText(150, cur_y + 24, desc)
        cur_y += 75
        
    # Side-by-side Dark, Theme, and Light screenshot trio
    dark_sc = get_screenshot_path("01-main-app")
    theme_sc = get_screenshot_path("03-main-app-different-theme")
    light_sc = get_screenshot_path("02-main-app-light-mode")
    
    if os.path.exists(dark_sc):
        draw_framed_screenshot(p, QPixmap(dark_sc), QRectF(860, 150, 740, 450), radius=16)
        
    if os.path.exists(theme_sc):
        draw_framed_screenshot(p, QPixmap(theme_sc), QRectF(1080, 320, 720, 440), radius=16)
        
    if os.path.exists(light_sc):
        draw_framed_screenshot(p, QPixmap(light_sc), QRectF(920, 520, 740, 450), radius=16)
        
    p.setPen(QColor(100, 115, 145))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
    p.drawText(100, 1000, "Clean OpenType Tabular Figures  •  System Accent Colors  •  Adaptive QPalette")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


def generate_power_tools_poster():
    """Poster 4: Batch Site Grabber & Smart Automation Suite."""
    out_path = os.path.join(POSTERS_DIR, "poster_power_tools.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(13, 19, 31))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Emerald / Cyan ambient glow
    glow = QRadialGradient(450, 420, 800)
    glow.setColorAt(0.0, QColor(16, 185, 129, 45))
    glow.setColorAt(0.5, QColor(6, 95, 70, 15))
    glow.setColorAt(1.0, QColor(13, 19, 31, 0))
    p.fillRect(0, 0, 1920, 1080, glow)
    
    # Header Logo
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(100, 95, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 24, QFont.Weight.Bold))
    p.drawText(180, 140, "Bengal Download Manager")
    
    # Badge Pill
    draw_pill(p, 100, 200, "Automation & Batch Suite", "🛠️", QColor(16, 185, 129, 40), QColor(16, 185, 129, 180), QColor(52, 211, 153))
    
    # Title
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 46, QFont.Weight.Bold))
    p.setPen(QColor(255, 255, 255))
    p.drawText(100, 310, "Automate & Conquer")
    
    grad_text = QLinearGradient(100, 0, 650, 0)
    grad_text.setColorAt(0.0, QColor(52, 211, 153))
    grad_text.setColorAt(1.0, QColor(56, 189, 248))
    p.setPen(QPen(QBrush(grad_text), 1))
    p.drawText(100, 375, "Batch Downloads")
    
    # Subtitle
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17))
    p.setPen(QColor(160, 180, 205))
    p.drawText(100, 435, "Crawl entire websites with the Site Grabber, schedule off-peak")
    p.drawText(100, 465, "downloads automatically, and manage queues with pinpoint accuracy.")
    
    # Features
    tools = [
        ("🌐 Deep Site Crawler", "Scrapes links, images, docs, and media across configurable crawl depths"),
        ("⏱️ Automated Task Scheduler", "Starts, pauses, and schedules downloads during off-peak network hours"),
        ("📊 Data Usage & Quota Tracker", "Monitors daily/monthly bandwidth consumption to prevent ISP overages")
    ]
    cur_y = 540
    for title, desc in tools:
        dot_path = QPainterPath()
        dot_path.addRoundedRect(QRectF(100, cur_y - 20, 32, 32), 8, 8)
        p.fillPath(dot_path, QColor(16, 185, 129, 40))
        p.setPen(QPen(QColor(16, 185, 129), 1.5))
        p.drawPath(dot_path)
        
        p.setPen(QColor(52, 211, 153))
        p.setFont(QFont("sans-serif", 14, QFont.Weight.Bold))
        p.drawText(QRectF(100, cur_y - 20, 32, 32), Qt.AlignmentFlag.AlignCenter, "★")
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold))
        p.setPen(QColor(245, 248, 255))
        p.drawText(150, cur_y, title)
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
        p.setPen(QColor(140, 160, 185))
        p.drawText(150, cur_y + 24, desc)
        cur_y += 75
        
    # Showcase Cards on Right
    grabber_sc = get_screenshot_path("site-grabber")
    sched_sc = get_screenshot_path("scheduler")
    
    if os.path.exists(grabber_sc):
        draw_framed_screenshot(p, QPixmap(grabber_sc), QRectF(880, 160, 920, 560), radius=16)
        
    if os.path.exists(sched_sc):
        draw_framed_screenshot(p, QPixmap(sched_sc), QRectF(1100, 470, 720, 480), radius=14)
        
    p.setPen(QColor(100, 120, 145))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
    p.drawText(100, 1000, "Native Linux & Windows  •  No Ads  •  Open Source  •  Built with PyQt6 & Aria2")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


def generate_media_downloader_poster():
    """Poster 5: 4K Stream Grabber & Media Sniffer."""
    out_path = os.path.join(POSTERS_DIR, "poster_media_downloader.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(18, 14, 26))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Rose / Crimson ambient glow
    glow = QRadialGradient(450, 420, 800)
    glow.setColorAt(0.0, QColor(244, 63, 94, 50))
    glow.setColorAt(0.5, QColor(225, 29, 72, 15))
    glow.setColorAt(1.0, QColor(18, 14, 26, 0))
    p.fillRect(0, 0, 1920, 1080, glow)
    
    # Header Logo
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(100, 95, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 24, QFont.Weight.Bold))
    p.drawText(180, 140, "Bengal Download Manager")
    
    # Badge Pill
    draw_pill(p, 100, 200, "High-Res Stream Sniffer", "🎬", QColor(244, 63, 94, 40), QColor(244, 63, 94, 180), QColor(251, 113, 133))
    
    # Title
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 46, QFont.Weight.Bold))
    p.setPen(QColor(255, 255, 255))
    p.drawText(100, 310, "4K Video & Audio")
    
    grad_text = QLinearGradient(100, 0, 650, 0)
    grad_text.setColorAt(0.0, QColor(251, 113, 133))
    grad_text.setColorAt(1.0, QColor(251, 146, 60))
    p.setPen(QPen(QBrush(grad_text), 1))
    p.drawText(100, 375, "Stream Grabber")
    
    # Subtitle
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17))
    p.setPen(QColor(175, 170, 195))
    p.drawText(100, 435, "Effortlessly capture video streams, playlists, and audio tracks")
    p.drawText(100, 465, "with built-in format extraction and Aria2 chunk acceleration.")
    
    # Features
    media_features = [
        ("🎥 Multi-Resolution Sniffer", "Download in 4K, 1440p, 1080p, 60fps, or extract clean audio-only MP3/M4A"),
        ("⚡ 32-Stream Segmentation", "Split video chunks dynamically across worker threads for maximum line speed"),
        ("🧩 Browser One-Click Bridge", "Catch video download prompts instantly in Chrome, Firefox, Edge, and Brave")
    ]
    cur_y = 540
    for title, desc in media_features:
        dot_path = QPainterPath()
        dot_path.addRoundedRect(QRectF(100, cur_y - 20, 32, 32), 8, 8)
        p.fillPath(dot_path, QColor(244, 63, 94, 40))
        p.setPen(QPen(QColor(244, 63, 94), 1.5))
        p.drawPath(dot_path)
        
        p.setPen(QColor(251, 113, 133))
        p.setFont(QFont("sans-serif", 14, QFont.Weight.Bold))
        p.drawText(QRectF(100, cur_y - 20, 32, 32), Qt.AlignmentFlag.AlignCenter, "★")
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold))
        p.setPen(QColor(245, 248, 255))
        p.drawText(150, cur_y, title)
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
        p.setPen(QColor(155, 150, 175))
        p.drawText(150, cur_y + 24, desc)
        cur_y += 75
        
    # Showcase Cards on Right
    media_sc = get_screenshot_path("04-media-downloader")
    prog_sc = get_screenshot_path("05-download-progress")
    
    if os.path.exists(media_sc):
        draw_framed_screenshot(p, QPixmap(media_sc), QRectF(900, 170, 900, 560), radius=16)
        
    if os.path.exists(prog_sc):
        draw_framed_screenshot(p, QPixmap(prog_sc), QRectF(1120, 480, 680, 470), radius=14)
        
    p.setPen(QColor(120, 110, 135))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
    p.drawText(100, 1000, "Aria2 Powered  •  YouTube, Vimeo & Direct MP4 Streams  •  No Ads  •  100% Free")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


def generate_network_analytics_poster():
    """Poster 6: Bandwidth Analytics & Connection Diagnostics."""
    out_path = os.path.join(POSTERS_DIR, "poster_network_analytics.jpg")
    print(f"[*] Generating: {out_path}")
    
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    img.fill(QColor(10, 17, 32))
    
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Cyan / Azure ambient glow
    glow = QRadialGradient(450, 420, 800)
    glow.setColorAt(0.0, QColor(6, 182, 212, 50))
    glow.setColorAt(0.5, QColor(14, 116, 144, 15))
    glow.setColorAt(1.0, QColor(10, 17, 32, 0))
    p.fillRect(0, 0, 1920, 1080, glow)
    
    # Header Logo
    if os.path.exists(LOGO_PATH):
        logo_pm = QPixmap(LOGO_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(100, 95, logo_pm)
        
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 24, QFont.Weight.Bold))
    p.drawText(180, 140, "Bengal Download Manager")
    
    # Badge Pill
    draw_pill(p, 100, 200, "Bandwidth & Security Management", "📊", QColor(6, 182, 212, 40), QColor(6, 182, 212, 180), QColor(103, 232, 249))
    
    # Title
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 46, QFont.Weight.Bold))
    p.setPen(QColor(255, 255, 255))
    p.drawText(100, 310, "Monitor & Control")
    
    grad_text = QLinearGradient(100, 0, 650, 0)
    grad_text.setColorAt(0.0, QColor(103, 232, 249))
    grad_text.setColorAt(1.0, QColor(125, 211, 252))
    p.setPen(QPen(QBrush(grad_text), 1))
    p.drawText(100, 375, "Data & Bandwidth")
    
    # Subtitle
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17))
    p.setPen(QColor(160, 180, 210))
    p.drawText(100, 435, "Maintain full visibility over data consumption with daily limits,")
    p.drawText(100, 465, "secure proxy tunnels (HTTP/SOCKS5), and instant speed throttling.")
    
    # Features
    net_features = [
        ("📈 Real-Time Data Usage Summary", "Accurate daily, monthly, and per-session transfer consumption metrics"),
        ("🛡️ SOCKS5 & HTTP Proxy Bridge", "Tunnel traffic through authenticated proxies with automatic connectivity check"),
        ("🎛️ Live Bandwidth Speed Limiter", "Cap download rates instantly to keep browsing and streaming latency low")
    ]
    cur_y = 540
    for title, desc in net_features:
        dot_path = QPainterPath()
        dot_path.addRoundedRect(QRectF(100, cur_y - 20, 32, 32), 8, 8)
        p.fillPath(dot_path, QColor(6, 182, 212, 40))
        p.setPen(QPen(QColor(6, 182, 212), 1.5))
        p.drawPath(dot_path)
        
        p.setPen(QColor(103, 232, 249))
        p.setFont(QFont("sans-serif", 14, QFont.Weight.Bold))
        p.drawText(QRectF(100, cur_y - 20, 32, 32), Qt.AlignmentFlag.AlignCenter, "★")
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 17, QFont.Weight.Bold))
        p.setPen(QColor(245, 248, 255))
        p.drawText(150, cur_y, title)
        
        p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
        p.setPen(QColor(140, 160, 185))
        p.drawText(150, cur_y + 24, desc)
        cur_y += 75
        
    # Showcase Cards on Right
    usage_sc = get_screenshot_path("data-usage-summary")
    ext_sc = get_screenshot_path("06-extension-options")
    
    if os.path.exists(usage_sc):
        draw_framed_screenshot(p, QPixmap(usage_sc), QRectF(900, 170, 900, 560), radius=16)
        
    if os.path.exists(ext_sc):
        draw_framed_screenshot(p, QPixmap(ext_sc), QRectF(1120, 480, 680, 470), radius=14)
        
    p.setPen(QColor(100, 120, 145))
    p.setFont(QFont("Inter, Noto Sans, Ubuntu, sans-serif", 13))
    p.drawText(100, 1000, "Privacy First  •  Local Processing  •  Zero Telemetry  •  Free & Open Source")
    
    p.end()
    img.save(out_path, "JPEG", 94)
    print(f"[✓] Created: {out_path}")


if __name__ == "__main__":
    generate_ecosystem_poster()
    generate_theme_poster()
    generate_power_tools_poster()
    print("\n[✓] Active branding posters generated successfully in assets/posters/")
