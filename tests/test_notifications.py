import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication

from core.notifications import (
    _is_running_in_flatpak,
    _send_portal_notification,
    _send_notify_send_cli,
    send_system_notification
)

# Ensure QApplication instance for tests
app = QApplication.instance() or QApplication(sys.argv)

class TestNotifications(unittest.TestCase):
    def test_is_running_in_flatpak(self):
        with patch("os.path.exists", return_value=True):
            self.assertTrue(_is_running_in_flatpak())
        with patch("os.path.exists", return_value=False):
            self.assertFalse(_is_running_in_flatpak())

    @patch("PyQt6.QtDBus.QDBusConnection.sessionBus")
    @patch("PyQt6.QtDBus.QDBusInterface")
    def test_send_portal_notification_success(self, mock_interface_cls, mock_bus_fn):
        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = True
        mock_bus_fn.return_value = mock_bus

        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True
        mock_reply = MagicMock()
        mock_reply.type.return_value = 2  # Not ErrorMessage
        mock_reply.MessageType.ErrorMessage = 1
        mock_iface.call.return_value = mock_reply
        mock_interface_cls.return_value = mock_iface

        res = _send_portal_notification("Title", "Body", "icon")
        self.assertTrue(res)
        mock_iface.call.assert_called_once()

    @patch("shutil.which", return_value="/usr/bin/notify-send")
    @patch("subprocess.run")
    def test_send_notify_send_cli(self, mock_subproc, mock_which):
        res = _send_notify_send_cli("Title", "Body", "App", "icon")
        self.assertTrue(res)
        mock_subproc.assert_called_once()

    @patch("core.notifications._send_portal_notification", return_value=True)
    def test_send_system_notification_portal(self, mock_portal):
        with patch("threading.Thread", side_effect=lambda target, **kw: MagicMock(start=lambda: target())):
            send_system_notification("Title", "Body")
            mock_portal.assert_called_once()

    def test_options_dialog_notification_checkbox(self):
        from ui.dialogs.options import OptionsDialog
        mock_win = MagicMock()
        mock_win.height.return_value = 600
        mock_win.settings = {"system_notifications": False}
        mock_win.system_notifications = False
        dlg = OptionsDialog(main_window=mock_win)
        
        self.assertTrue(hasattr(dlg, "chk_system_notifications"))
        self.assertFalse(dlg.chk_system_notifications.isChecked())
        
        # Test enabling
        dlg.chk_system_notifications.setChecked(True)
        dlg.save_and_accept()
        self.assertTrue(mock_win.settings.get("system_notifications"))
        self.assertTrue(getattr(mock_win, "system_notifications"))
        dlg.close()

if __name__ == "__main__":
    unittest.main()
