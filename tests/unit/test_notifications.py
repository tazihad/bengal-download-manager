"""Unit tests for core.notifications."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from core.notifications import (
    _is_running_in_flatpak,
    _is_running_in_snap,
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

    def test_is_running_in_snap(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/my-snap/current")
        assert _is_running_in_snap() is True
        monkeypatch.delenv("SNAP", raising=False)
        assert _is_running_in_snap() is False

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

    def test_resolve_notification_icon_appdir_bundle(self, tmp_path, monkeypatch):
        mock_appdir = tmp_path / "appdir"
        icon_dir = mock_appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        icon_dir.mkdir(parents=True)
        mock_icon = icon_dir / "bd.com.zihad.BengalDownloadManager.png"
        mock_icon.write_bytes(b"dummy_png")

        monkeypatch.setenv("APPDIR", str(mock_appdir))
        resolved = _resolve_notification_icon("nonexistent_icon")
        assert resolved == str(mock_icon)

    def test_resolve_notification_icon_pyinstaller_internal(self, tmp_path, monkeypatch):
        mock_meipass = tmp_path / "dist"
        internal_icons = mock_meipass / "_internal" / "assets" / "icons"
        internal_icons.mkdir(parents=True)
        mock_icon = internal_icons / "256x256.png"
        mock_icon.write_bytes(b"dummy_png")

        monkeypatch.delenv("APPDIR", raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(mock_meipass), raising=False)
        resolved = _resolve_notification_icon("nonexistent_icon")
        assert resolved == str(mock_icon)

    def test_has_installed_desktop_entry(self, tmp_path, monkeypatch):
        from core.notifications import _has_installed_desktop_entry
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        fake_apps = tmp_path / "applications"
        fake_apps.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))

        assert _has_installed_desktop_entry("my-app") is False

        (fake_apps / "my-app.desktop").write_text("[Desktop Entry]\nName=App\n", encoding="utf-8")
        assert _has_installed_desktop_entry("my-app") is True

    def test_has_installed_desktop_entry_snap(self, monkeypatch):
        from core.notifications import _has_installed_desktop_entry
        monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
        assert _has_installed_desktop_entry("bengal-download-manager_bengal-download-manager") is True

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
                icon_str="download",
                desktop_entry="bd.com.zihad.BengalDownloadManager"
            )
            assert result is True
            assert mock_bus.call.called
            call_arg = mock_bus.call.call_args[0][0]
            args = call_arg.arguments()
            assert args[0] == "Bengal Download Manager"
            assert args[2] == "download"
            # Hints dict must include desktop-entry for GNOME Shell
            hints = args[6]
            assert "desktop-entry" in hints
            val = hints["desktop-entry"].value() if hasattr(hints["desktop-entry"], "value") else hints["desktop-entry"]
            assert val == "bd.com.zihad.BengalDownloadManager"

    def test_send_freedesktop_notification_formats_file_uri_for_local_path(self, tmp_path):
        dummy_icon = tmp_path / "test_icon.png"
        dummy_icon.write_bytes(b"dummy")
        with patch("PyQt6.QtDBus.QDBusConnection.sessionBus") as mock_bus_func:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = True
            mock_reply = MagicMock()
            from PyQt6.QtDBus import QDBusMessage
            mock_reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
            mock_bus.call.return_value = mock_reply
            mock_bus_func.return_value = mock_bus

            _send_freedesktop_notification("T", "M", icon_str=str(dummy_icon))
            call_arg = mock_bus.call.call_args[0][0]
            args = call_arg.arguments()
            assert args[2] == f"file://{dummy_icon}"
            assert "image-path" in args[6]
            img_val = args[6]["image-path"].value() if hasattr(args[6]["image-path"], "value") else args[6]["image-path"]
            assert img_val == f"file://{dummy_icon}"

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

    def _mock_portal_reply(self, message_type_name="ReplyMessage"):
        """Starts patches for QDBusInterface + sessionBus and returns (mocks, context)."""
        from PyQt6.QtDBus import QDBusMessage
        bus_patch = patch("PyQt6.QtDBus.QDBusConnection.sessionBus")
        iface_patch = patch("PyQt6.QtDBus.QDBusInterface")
        mock_bus_func = bus_patch.start()
        mock_iface_cls = iface_patch.start()
        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = True
        mock_bus_func.return_value = mock_bus
        mock_portal = MagicMock()
        mock_portal.isValid.return_value = True
        mock_reply = MagicMock()
        mock_reply.type.return_value = getattr(QDBusMessage.MessageType, message_type_name)
        mock_portal.call.return_value = mock_reply
        mock_iface_cls.return_value = mock_portal
        return mock_portal, (bus_patch, iface_patch)

    def test_send_portal_notification_marshals_variant_details(self):
        from PyQt6.QtCore import QVariant
        mock_portal, patches = self._mock_portal_reply()
        try:
            result = _send_portal_notification("Title", "Body", "download", "my.app.Id")
        finally:
            for p in patches:
                p.stop()

        assert result is True
        method, notification_id, details = mock_portal.call.call_args[0]
        assert method == "AddNotification"
        assert isinstance(notification_id, str) and notification_id
        assert isinstance(details, dict)
        assert details["title"].value() == "Title"
        assert details["body"].value() == "Body"
        assert details["icon"].value() == "download"
        assert details["priority"].value() == "normal"
        # Values must be wrapped as variants for the a{sv} D-Bus signature
        assert all(isinstance(v, QVariant) for v in details.values())

    def test_send_portal_notification_absolute_icon_falls_back_to_app_id(self, tmp_path):
        icon_path = tmp_path / "logo.png"
        icon_path.write_bytes(b"x")
        mock_portal, patches = self._mock_portal_reply()
        try:
            _send_portal_notification("T", "B", str(icon_path), "my.app.Id")
        finally:
            for p in patches:
                p.stop()

        details = mock_portal.call.call_args[0][2]
        assert details["icon"].value() == "my.app.Id"

    def test_send_portal_notification_error_reply_returns_false(self):
        mock_portal, patches = self._mock_portal_reply(message_type_name="ErrorMessage")
        try:
            result = _send_portal_notification("T", "B", "download")
        finally:
            for p in patches:
                p.stop()
        assert result is False

    def test_send_system_notification_calls_freedesktop_on_host(self):
        with patch("core.notifications._is_running_in_flatpak", return_value=False), \
             patch("core.notifications._has_installed_desktop_entry", return_value=True), \
             patch("core.notifications._send_freedesktop_notification", return_value=True) as mock_fdo:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_fdo.called

    def test_send_system_notification_uninstalled_calls_gdbus(self):
        with patch("core.notifications._is_running_in_flatpak", return_value=False), \
             patch("core.notifications._has_installed_desktop_entry", return_value=False), \
             patch("core.notifications._send_gdbus_cli", return_value=True) as mock_gdbus:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_gdbus.called

    def test_send_system_notification_calls_portal_in_flatpak(self):
        with patch("core.notifications._is_running_in_flatpak", return_value=True), \
             patch("core.notifications._send_portal_notification", return_value=True) as mock_portal:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_portal.called

    def test_send_system_notification_calls_freedesktop_in_snap(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
        monkeypatch.setenv("SNAP_INSTANCE_NAME", "bengal-download-manager")
        monkeypatch.setenv("SNAP_APP_NAME", "bengal-download-manager")
        with patch("core.notifications._is_running_in_flatpak", return_value=False), \
             patch("core.notifications._send_freedesktop_notification", return_value=True) as mock_fdo:
            send_system_notification("Title", "Message")
            import time
            time.sleep(0.1)
            assert mock_fdo.called
            call_kwargs = mock_fdo.call_args[1]
            assert call_kwargs.get("desktop_entry") == "bengal-download-manager_bengal-download-manager"

    def test_should_send_notification_for_item_main_queue(self):
        from PyQt6.QtCore import Qt
        mock_win = MagicMock()
        mock_win.system_notifications = True
        mock_win.settings = {"system_notifications": True}
        from ui.main_window import MainWindow
        mock_win._should_send_notification_for_item = MainWindow._should_send_notification_for_item.__get__(mock_win)
        mock_win._get_queue_config = MainWindow._get_queue_config.__get__(mock_win)

        mock_item = MagicMock()
        # Not a batch item, not a queue run, queue is Main download queue
        mock_item.data.side_effect = lambda role: {
            Qt.ItemDataRole.UserRole + 18: False,
            Qt.ItemDataRole.UserRole + 14: False,
            Qt.ItemDataRole.UserRole + 8: "Main download queue"
        }.get(role, None)

        assert mock_win._should_send_notification_for_item(mock_item) is True

        # When global setting is False
        mock_win.system_notifications = False
        mock_win.settings = {"system_notifications": False}
        assert mock_win._should_send_notification_for_item(mock_item) is False

    def test_should_send_notification_for_custom_queue(self):
        from PyQt6.QtCore import Qt
        mock_win = MagicMock()
        mock_win.system_notifications = True  # Main queue setting should NOT affect custom queue
        mock_win._queues_data = [
            {"name": "Custom Queue", "show_notification": False},
            {"name": "Notified Queue", "show_notification": True}
        ]
        from ui.main_window import MainWindow
        mock_win._should_send_notification_for_item = MainWindow._should_send_notification_for_item.__get__(mock_win)
        mock_win._get_queue_config = MainWindow._get_queue_config.__get__(mock_win)

        mock_item_unmarked = MagicMock()
        mock_item_unmarked.data.side_effect = lambda role: {
            Qt.ItemDataRole.UserRole + 18: False,
            Qt.ItemDataRole.UserRole + 8: "Custom Queue"
        }.get(role, None)

        # Unmarked custom queue should NOT notify
        assert mock_win._should_send_notification_for_item(mock_item_unmarked) is False

        mock_item_marked = MagicMock()
        mock_item_marked.data.side_effect = lambda role: {
            Qt.ItemDataRole.UserRole + 18: False,
            Qt.ItemDataRole.UserRole + 8: "Notified Queue"
        }.get(role, None)

        # Marked custom queue SHOULD notify
        assert mock_win._should_send_notification_for_item(mock_item_marked) is True

    def test_scheduler_dialog_queue_notifications(self, qapp):
        from ui.dialogs.scheduler import SchedulerDialog
        from core.queue_manager import DEFAULT_QUEUES, make_default_queue

        queues = [
            dict(DEFAULT_QUEUES[0]),
            make_default_queue("Custom Queue")
        ]
        dlg = SchedulerDialog(initial_queues=queues)
        # Main queue: checkbox hidden
        dlg._load_queue_to_ui(0)
        assert dlg.chk_show_notification.isHidden() is True

        # Custom queue: checkbox visible, unmarked by default
        dlg._load_queue_to_ui(1)
        assert dlg.chk_show_notification.isHidden() is False
        assert dlg.chk_show_notification.isChecked() is False

        # Mark and save
        dlg.chk_show_notification.setChecked(True)
        dlg._save_ui_to_queue(1)
        assert dlg.queues[1]["show_notification"] is True

    def test_ensure_desktop_integration_skipped_in_dev(self, monkeypatch):
        from core.desktop import ensure_desktop_integration
        monkeypatch.delenv("APPDIR", raising=False)
        monkeypatch.delenv("APPIMAGE", raising=False)
        monkeypatch.delenv("BDM_FORCE_DESKTOP_INTEGRATION", raising=False)
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        # Should cleanly return without error or file creation
        ensure_desktop_integration()

    def test_ensure_desktop_integration_forced_creates_entries(self, tmp_path, monkeypatch):
        from core.desktop import ensure_desktop_integration
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("BDM_FORCE_DESKTOP_INTEGRATION", "1")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.delenv("BDM_TESTING", raising=False)
        monkeypatch.delenv("BDM_SKIP_DESKTOP_INTEGRATION", raising=False)

        ensure_desktop_integration()

        desktop_file = fake_home / ".local" / "share" / "applications" / "bd.com.zihad.BengalDownloadManager.desktop"
        assert desktop_file.exists()
        content = desktop_file.read_text(encoding="utf-8")
        assert "StartupWMClass=bd.com.zihad.BengalDownloadManager" in content
        assert "X-GNOME-UsesNotifications=true" in content
        assert "Icon=bd.com.zihad.BengalDownloadManager" in content

    def test_ensure_desktop_integration_appimage_creates_entries(self, tmp_path, monkeypatch):
        from core.desktop import ensure_desktop_integration
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("APPIMAGE", "/tmp/BengalDownloadManager.AppImage")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.delenv("BDM_TESTING", raising=False)
        monkeypatch.delenv("BDM_SKIP_DESKTOP_INTEGRATION", raising=False)
        # sys.modules has "pytest", so BDM_FORCE_DESKTOP_INTEGRATION ensures test runs
        monkeypatch.setenv("BDM_FORCE_DESKTOP_INTEGRATION", "1")

        ensure_desktop_integration()

        desktop_file = fake_home / ".local" / "share" / "applications" / "bd.com.zihad.BengalDownloadManager.desktop"
        assert desktop_file.exists()
        content = desktop_file.read_text(encoding="utf-8")
        assert "StartupWMClass=bd.com.zihad.BengalDownloadManager" in content
        assert "X-GNOME-UsesNotifications=true" in content
        assert "Icon=bd.com.zihad.BengalDownloadManager" in content
        assert 'Exec="/tmp/BengalDownloadManager.AppImage" %u' in content

    def test_ensure_desktop_integration_appimage_clean_by_default(self, tmp_path, monkeypatch):
        from core.desktop import ensure_desktop_integration
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("APPIMAGE", "/tmp/BengalDownloadManager.AppImage")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.delenv("BDM_TESTING", raising=False)
        monkeypatch.delenv("BDM_SKIP_DESKTOP_INTEGRATION", raising=False)
        monkeypatch.delenv("BDM_FORCE_DESKTOP_INTEGRATION", raising=False)

        ensure_desktop_integration()

        desktop_file = fake_home / ".local" / "share" / "applications" / "bd.com.zihad.BengalDownloadManager.desktop"
        assert not desktop_file.exists()

    def test_is_image_file(self):
        from core.notifications import _is_image_file
        assert _is_image_file("/path/to/image.png") is True
        assert _is_image_file("/path/to/photo.JPG") is True
        assert _is_image_file("/path/to/logo.svg") is True
        assert _is_image_file("/path/to/app.flatpak") is False
        assert _is_image_file("/path/to/archive.zip") is False
        assert _is_image_file("") is False
        assert _is_image_file(None) is False

    def test_appimage_manager_desktop_discovery(self, tmp_path, monkeypatch):
        from core.desktop import get_desktop_file_name
        from core.notifications import _has_installed_desktop_entry

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        apps_dir = tmp_path / "applications"
        apps_dir.mkdir()
        monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        # Before AppImage manager integrates
        assert get_desktop_file_name() == "bd.com.zihad.BengalDownloadManager"
        assert _has_installed_desktop_entry("bd.com.zihad.BengalDownloadManager") is False

        # AppImageLauncher creates appimagekit_<hash>-bd.com.zihad.BengalDownloadManager.desktop
        managed_file = apps_dir / "appimagekit_abc123-bd.com.zihad.BengalDownloadManager.desktop"
        managed_file.write_text("[Desktop Entry]\nName=Bengal Download Manager\nStartupWMClass=bd.com.zihad.BengalDownloadManager\n", encoding="utf-8")

        # After integration, discovered automatically
        assert get_desktop_file_name() == "appimagekit_abc123-bd.com.zihad.BengalDownloadManager"
        assert _has_installed_desktop_entry("bd.com.zihad.BengalDownloadManager") is True




