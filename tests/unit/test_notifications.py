"""Unit tests for core.notifications."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from core.notifications import (
    _is_running_in_flatpak,
    _resolve_notification_icon,
    _send_freedesktop_notification,
    _send_gdbus_cli,
    _send_portal_notification,
    _send_notify_send_cli,
    send_system_notification,
)


class TestNotifications:
    def test_is_running_in_flatpak(self):
        with patch("os.path.exists", return_value=True):
            assert _is_running_in_flatpak() is True
        with patch("os.path.exists", return_value=False):
            assert _is_running_in_flatpak() is False

    def test_resolve_notification_icon_with_existing_absolute_path(self, tmp_path):
        dummy_icon = tmp_path / "custom_icon.png"
        dummy_icon.write_bytes(b"dummy_bytes")
        resolved = _resolve_notification_icon(str(dummy_icon))
        assert resolved == str(dummy_icon)

    def test_resolve_notification_icon_fallback_bundled(self):
        resolved = _resolve_notification_icon("nonexistent_theme_icon_xyz")
        assert resolved is not None
        assert isinstance(resolved, str)
        # Should either resolve to a local bundled path or a fallback theme name
        assert len(resolved) > 0

    def test_send_freedesktop_notification_success(self):
        with patch("PyQt6.QtDBus.QDBusConnection.sessionBus") as mock_bus_func:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = True
            mock_reply = MagicMock()
            from PyQt6.QtDBus import QDBusMessage
            mock_reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
            mock_bus.call.return_value = mock_reply
            mock_bus_func.return_value = mock_bus

            result = _send_freedesktop_notification(
                title="Test",
                message="Message",
                app_name="Bengal Download Manager",
                icon_str="download"
            )
            assert result is True
            assert mock_bus.call.called

    def test_send_freedesktop_notification_not_connected(self):
        with patch("PyQt6.QtDBus.QDBusConnection.sessionBus") as mock_bus_func:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = False
            mock_bus_func.return_value = mock_bus

            result = _send_freedesktop_notification("Test", "Message")
            assert result is False

    def test_send_freedesktop_notification_error_reply(self):
        with patch("PyQt6.QtDBus.QDBusConnection.sessionBus") as mock_bus_func:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = True
            mock_reply = MagicMock()
            from PyQt6.QtDBus import QDBusMessage
            mock_reply.type.return_value = QDBusMessage.MessageType.ErrorMessage
            mock_bus.call.return_value = mock_reply
            mock_bus_func.return_value = mock_bus

            result = _send_freedesktop_notification("Test", "Message")
            assert result is False

    def test_send_gdbus_cli_not_installed(self):
        with patch("shutil.which", return_value=None):
            assert _send_gdbus_cli("Test", "Message") is False

    def test_send_gdbus_cli_success(self):
        with patch("shutil.which", return_value="/usr/bin/gdbus"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert _send_gdbus_cli("Test", "Message") is True
            assert mock_run.called

    def test_send_notify_send_cli_not_installed(self):
        with patch("shutil.which", return_value=None):
            assert _send_notify_send_cli("Test", "Message") is False

    def test_send_notify_send_cli_success(self):
        with patch("shutil.which", return_value="/usr/bin/notify-send"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert _send_notify_send_cli("Test", "Message") is True
            assert mock_run.called

    def test_send_portal_notification_success(self):
        with patch("PyQt6.QtDBus.QDBusConnection.sessionBus") as mock_bus_func, \
             patch("PyQt6.QtDBus.QDBusInterface") as mock_iface_cls:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = True
            mock_bus_func.return_value = mock_bus

            mock_portal = MagicMock()
            mock_portal.isValid.return_value = True
            mock_reply = MagicMock()
            from PyQt6.QtDBus import QDBusMessage
            mock_reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
            mock_portal.call.return_value = mock_reply
            mock_iface_cls.return_value = mock_portal

            result = _send_portal_notification("Test", "Message", "download")
            assert result is True

    def test_send_system_notification_calls_freedesktop_on_host(self):
        with patch("core.notifications._is_running_in_flatpak", return_value=False), \
             patch("core.notifications._send_freedesktop_notification", return_value=True) as mock_fdo:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_fdo.called

    def test_send_system_notification_calls_portal_in_flatpak(self):
        with patch("core.notifications._is_running_in_flatpak", return_value=True), \
             patch("core.notifications._send_portal_notification", return_value=True) as mock_portal:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_portal.called
