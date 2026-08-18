import os
import shutil
import subprocess
import threading
import time
from typing import Optional

def _is_running_in_flatpak() -> bool:
    """Returns True if running inside a Flatpak container sandbox."""
    return os.path.exists("/.flatpak-info")

def _send_portal_notification(title: str, message: str, icon_name: str, app_id: str = "io.github.tazihad.bengal-download-manager") -> bool:
    """Sends notification via XDG Desktop Portal (org.freedesktop.portal.Notification)."""
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusInterface
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        
        portal = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Notification",
            bus
        )
        if not portal.isValid():
            return False
        
        notification_id = f"bengal_dl_{int(time.time() * 1000)}"
        details = {
            "title": title,
            "body": message,
            "icon": icon_name,
            "priority": "normal"
        }
        reply = portal.call("AddNotification", notification_id, details)
        return reply.type() != reply.MessageType.ErrorMessage
    except Exception:
        return False

def _send_notify_send_cli(title: str, message: str, app_name: str, icon_name: str) -> bool:
    """Fallback using notify-send command line tool if available."""
    if not shutil.which("notify-send"):
        return False
    try:
        subprocess.run(
            ["notify-send", "-a", app_name, "-i", icon_name, title, message],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False

def send_system_notification(
    title: str,
    message: str,
    app_name: str = "Bengal Download Manager",
    icon_name: str = "io.github.tazihad.bengal-download-manager",
    file_path: Optional[str] = None,
    tray_icon = None
) -> None:
    """
    Dispatches an XDG-compliant desktop notification asynchronously.
    Supports XDG Desktop Portal (Flatpak & modern desktops), Tray showMessage, and notify-send.
    """
    def _worker():
        # 1. Try XDG Desktop Portal (First choice for Flatpak & Modern Desktops)
        if _send_portal_notification(title, message, icon_name, "io.github.tazihad.bengal-download-manager"):
            return
        
        # 2. Try QSystemTrayIcon if available
        if tray_icon and hasattr(tray_icon, "showMessage") and hasattr(tray_icon, "isVisible") and tray_icon.isVisible():
            try:
                from PyQt6.QtWidgets import QSystemTrayIcon
                tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
                return
            except Exception:
                pass
        
        # 3. Try notify-send CLI
        if _send_notify_send_cli(title, message, app_name, icon_name):
            return

    # Run in background daemon thread so UI is never blocked
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
