import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional


def _is_running_in_flatpak() -> bool:
    """Returns True if running inside a Flatpak container sandbox."""
    return os.path.exists("/.flatpak-info")


def _resolve_notification_icon(icon_name: str = "bd.com.zihad.BengalDownloadManager") -> str:
    """
    Resolves the most appropriate icon identifier or file path for desktop notifications.
    FreeDesktop notification servers accept either an icon theme name or an absolute file path.
    """
    # 1. If already an absolute file path that exists, return it
    if icon_name and os.path.isabs(icon_name) and os.path.exists(icon_name):
        return icon_name

    # 2. Check if the specified icon exists in the system icon theme
    try:
        from PyQt6.QtGui import QIcon
        if icon_name and QIcon.hasThemeIcon(icon_name):
            return icon_name
    except Exception:
        pass

    # 3. Check local bundled asset icons (dev, pyinstaller, snap, etc.)
    _meipass = getattr(sys, "_MEIPASS", None)
    _argv0_src = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else None
    _argv0_root = os.path.dirname(_argv0_src) if _argv0_src else None
    _module_dir = os.path.dirname(os.path.abspath(__file__)) if __file__ else None
    _module_root = os.path.dirname(os.path.dirname(_module_dir)) if _module_dir else None

    candidate_locations = [
        *([
            os.path.join(_meipass, "assets", "icons", "256x256.png"),
            os.path.join(_meipass, "assets", "logo.png"),
        ] if _meipass else []),
        "/app/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png",
        "/app/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg",
        "/usr/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png",
        "/usr/share/icons/hicolor/scalable/apps/bd.com.zihad.BengalDownloadManager.svg",
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/bd.com.zihad.BengalDownloadManager.png"),
        *([
            os.path.join(_argv0_root, "assets", "icons", "256x256.png"),
            os.path.join(_argv0_root, "assets", "logo.png"),
        ] if _argv0_root else []),
        *([
            os.path.join(_module_root, "assets", "icons", "256x256.png"),
            os.path.join(_module_root, "assets", "logo.png"),
        ] if _module_root else []),
    ]

    for loc in candidate_locations:
        if loc and os.path.isabs(loc) and os.path.exists(loc):
            return loc

    # 4. Fallback to standard freedesktop theme icons
    try:
        from PyQt6.QtGui import QIcon
        for fallback in ["document-save", "download"]:
            if QIcon.hasThemeIcon(fallback):
                return fallback
    except Exception:
        pass

    return icon_name or "download"


def _send_freedesktop_notification(
    title: str,
    message: str,
    app_name: str = "Bengal Download Manager",
    icon_str: str = "bd.com.zihad.BengalDownloadManager",
    timeout_ms: int = 5000,
    desktop_entry: str = "bd.com.zihad.BengalDownloadManager",
    file_path: Optional[str] = None,
) -> bool:
    """
    Sends notification via standard FreeDesktop Desktop Notifications Specification
    (org.freedesktop.Notifications.Notify) using PyQt6 QtDBus.
    Supported natively by KDE Plasma (plasmashell), GNOME Shell, XFCE, MATE, Cinnamon, Dunst, etc.
    Includes the desktop-entry hint to ensure GNOME Shell correctly maps and displays notifications.
    """
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        from PyQt6.QtCore import QVariant, QMetaType

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False

        msg = QDBusMessage.createMethodCall(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify"
        )
        if not msg:
            return False

        # D-Bus method signature: Notify (susssasa{sv}i) -> u
        # Parameter 2: replaces_id (uint32)
        v_replaces = QVariant(0)
        v_replaces.convert(QMetaType(QMetaType.Type.UInt.value))

        # Parameter 6: actions (array of strings)
        v_actions = QVariant([])
        v_actions.convert(QMetaType(QMetaType.Type.QStringList.value))

        # Format icon parameter:
        # Per specification, app_icon can be an icon theme name or a file:// URI
        if icon_str and os.path.isabs(icon_str) and os.path.exists(icon_str):
            icon_arg = f"file://{icon_str}"
        else:
            icon_arg = icon_str or "bd.com.zihad.BengalDownloadManager"

        # Parameter 7: hints (dict of variant)
        hints = {
            "desktop-entry": QVariant(desktop_entry),
            "urgency": QVariant(1),
        }
        if file_path and os.path.isabs(file_path) and os.path.exists(file_path):
            hints["image-path"] = QVariant(f"file://{file_path}")
        elif icon_str and os.path.isabs(icon_str) and os.path.exists(icon_str):
            hints["image-path"] = QVariant(f"file://{icon_str}")

        msg.setArguments([
            app_name,
            v_replaces,
            icon_arg,
            title,
            message,
            v_actions,
            hints,
            int(timeout_ms)
        ])

        reply = bus.call(msg)
        return reply.type() == QDBusMessage.MessageType.ReplyMessage
    except Exception:
        return False


def _send_gdbus_cli(
    title: str,
    message: str,
    app_name: str = "Bengal Download Manager",
    icon_str: str = "bd.com.zihad.BengalDownloadManager",
    timeout_ms: int = 5000,
    desktop_entry: str = "bd.com.zihad.BengalDownloadManager",
) -> bool:
    """Fallback using standard GLib gdbus CLI calling org.freedesktop.Notifications."""
    if not shutil.which("gdbus"):
        return False
    try:
        icon_arg = f"file://{icon_str}" if (icon_str and os.path.isabs(icon_str)) else icon_str
        hints_arg = f"{{'desktop-entry': <'{desktop_entry}'>}}"
        res = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.freedesktop.Notifications",
                "--object-path", "/org/freedesktop/Notifications",
                "--method", "org.freedesktop.Notifications.Notify",
                app_name, "0", icon_arg, title, message, "[]", hints_arg, str(timeout_ms)
            ],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    except Exception:
        return False


def _send_portal_notification(
    title: str,
    message: str,
    icon_name: str,
    app_id: str = "bd.com.zihad.BengalDownloadManager"
) -> bool:
    """
    Sends notification via XDG Desktop Portal (org.freedesktop.portal.Notification).
    Note: Intended primarily for sandboxed Flatpak containers where the portal associates
    the container's App ID. Unconfined host apps calling this may be silently dropped by the portal.
    """
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

        portal_icon = app_id if (not icon_name or os.path.isabs(icon_name)) else icon_name
        notification_id = f"bengal_dl_{int(time.time() * 1000)}"
        details = {
            "title": title,
            "body": message,
            "icon": portal_icon,
            "priority": "normal"
        }
        reply = portal.call("AddNotification", notification_id, details)
        return reply.type() != reply.MessageType.ErrorMessage
    except Exception:
        return False


def _send_notify_send_cli(
    title: str,
    message: str,
    app_name: str = "Bengal Download Manager",
    icon_name: str = "bd.com.zihad.BengalDownloadManager",
    desktop_entry: str = "bd.com.zihad.BengalDownloadManager",
) -> bool:
    """Fallback using notify-send command line tool if available."""
    if not shutil.which("notify-send"):
        return False
    try:
        res = subprocess.run(
            ["notify-send", "-a", app_name, "-i", icon_name, f"--hint=string:desktop-entry:{desktop_entry}", title, message],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if res.returncode == 0:
            return True
        res2 = subprocess.run(
            ["notify-send", "-a", app_name, "-i", icon_name, title, message],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return res2.returncode == 0
    except Exception:
        return False


def send_system_notification(
    title: str,
    message: str,
    app_name: str = "Bengal Download Manager",
    icon_name: str = "bd.com.zihad.BengalDownloadManager",
    file_path: Optional[str] = None,
    tray_icon = None
) -> None:
    """
    Dispatches an XDG-compliant desktop notification asynchronously.
    Supports native FreeDesktop D-Bus Notifications (KDE, GNOME, etc.),
    XDG Desktop Portal (Flatpak sandbox), gdbus/notify-send CLI tools,
    and QSystemTrayIcon fallbacks.
    """
    resolved_icon = _resolve_notification_icon(icon_name)

    def _worker():
        is_flatpak = _is_running_in_flatpak()

        # In Flatpak container sandbox, XDG Desktop Portal is the primary interface
        if is_flatpak:
            if _send_portal_notification(title, message, resolved_icon, "bd.com.zihad.BengalDownloadManager"):
                return
            if _send_freedesktop_notification(title, message, app_name, resolved_icon, file_path=file_path):
                return
            if _send_notify_send_cli(title, message, app_name, resolved_icon):
                return

        # On host environments (KDE Plasma, GNOME Shell, XFCE, etc.),
        # use the native FreeDesktop Notifications Specification directly
        else:
            # 1. Native FreeDesktop D-Bus Notification (Primary for KDE, GNOME, etc.)
            if _send_freedesktop_notification(title, message, app_name, resolved_icon, file_path=file_path):
                return

            # 2. GLib gdbus CLI fallback
            if _send_gdbus_cli(title, message, app_name, resolved_icon):
                return

            # 3. notify-send CLI fallback
            if _send_notify_send_cli(title, message, app_name, resolved_icon):
                return

            # 4. QSystemTrayIcon if visible
            if tray_icon and hasattr(tray_icon, "showMessage") and hasattr(tray_icon, "isVisible") and tray_icon.isVisible():
                try:
                    from PyQt6.QtWidgets import QSystemTrayIcon
                    tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
                    return
                except Exception:
                    pass

            # 5. XDG Desktop Portal (Last resort fallback for host)
            if _send_portal_notification(title, message, resolved_icon, "bd.com.zihad.BengalDownloadManager"):
                return

    # Run in background daemon thread so UI is never blocked
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

