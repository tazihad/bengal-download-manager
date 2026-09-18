"""
UI tests for Proxy Status Bar item and Options Dialog Proxy Tab.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from core.services.proxy_service import ProxyDetectionResult


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_proxy_detector():
    with patch("core.services.proxy_service.ProxyDetectorWorker.start"):
        yield


def test_options_dialog_proxy_tab_components(qapp):
    from ui.dialogs.options import OptionsDialog

    with patch("core.services.proxy_service.ProxyDetectorWorker.start"), \
         patch("ui.dialogs.options.load_proxy_config", return_value={
             "mode": "manual", "type": "socks5", "host": "127.0.0.1", "port": 1080, "auth": False
         }), \
         patch("ui.dialogs.options.load_extension_config", return_value={}):
        dlg = OptionsDialog(initial_tab="Proxy / Socks")
        
        # Verify UI components exist
        assert hasattr(dlg, "proxy_status_frame")
        assert hasattr(dlg, "lbl_proxy_flag")
        assert hasattr(dlg, "lbl_proxy_status")
        assert hasattr(dlg, "lbl_proxy_ip")
        assert hasattr(dlg, "btn_test_proxy")
        assert hasattr(dlg, "_proxy_debounce_timer")

        # Test successful detection callback
        res_ok = ProxyDetectionResult(
            is_working=True,
            ip="203.0.113.195",
            country="United Kingdom",
            country_code="GB",
            city="London",
            flag_emoji="🇬🇧",
            proxy_type="socks5"
        )
        dlg._on_proxy_detection_finished(res_ok)

        # Country flag must display emoji and tooltip must name the country
        assert dlg.lbl_proxy_flag.text() == "🇬🇧"
        assert "United Kingdom" in dlg.lbl_proxy_flag.toolTip()
        # Status must explicitly state "Proxy is working"
        assert dlg.lbl_proxy_status.text() == "Proxy is working"
        assert "203.0.113.195" in dlg.lbl_proxy_ip.text()

        # Test failure detection callback
        res_fail = ProxyDetectionResult(
            is_working=False,
            error_message="Connection refused",
            proxy_type="socks5"
        )
        dlg._on_proxy_detection_finished(res_fail)
        assert dlg.lbl_proxy_flag.text() == "⚠️"
        assert "Connection failed" in dlg.lbl_proxy_status.text()
        assert dlg.lbl_proxy_ip.text() == ""

        # Test debounce timer trigger on input change
        dlg.txt_host.setText("192.168.1.100")
        assert dlg._proxy_debounce_timer.isActive()
        dlg._proxy_debounce_timer.stop()
        dlg.close()


def test_main_window_proxy_status_bar(qapp):
    from ui.main_window import MainWindow

    win = MainWindow(start_ipc=False)
    win.hide()

    try:
        # Verify proxy status bar components
        assert hasattr(win, "status_proxy_label")
        assert hasattr(win, "sep_proxy")
        assert hasattr(win, "action_sb_proxy")

        # Verify action exists in menu
        assert win.action_sb_proxy in win.status_bar_menu.actions()

        # Toggling visibility
        win.action_sb_proxy.setChecked(False)
        win._update_status_bar_visibility()
        assert win.status_proxy_label.isHidden()

        win.action_sb_proxy.setChecked(True)
        win._update_status_bar_visibility()
        assert not win.status_proxy_label.isHidden()

        # Render working proxy
        res_ok = ProxyDetectionResult(
            is_working=True,
            ip="198.51.100.22",
            country="Germany",
            country_code="DE",
            city="Berlin",
            flag_emoji="🇩🇪"
        )
        win._render_proxy_status(res_ok)
        assert "🇩🇪" in win.status_proxy_label.text()
        assert "198.51.100.22" in win.status_proxy_label.text()
        assert "Proxy is working" in win.status_proxy_label.toolTip()
        assert "Germany" in win.status_proxy_label.toolTip()

        # Click handler calls open_options with Proxy / Socks
        with patch.object(win, "open_options") as mock_open_opts:
            win._on_proxy_status_clicked(None)
            mock_open_opts.assert_called_once_with(target_tab="Proxy / Socks")
    finally:
        win.close()


def test_options_dialog_cleanup_proxy_worker(qapp):
    from ui.dialogs.options import OptionsDialog

    with patch("core.services.proxy_service.ProxyDetectorWorker.start"), \
         patch("ui.dialogs.options.load_proxy_config", return_value={"mode": "manual", "type": "http", "host": "1.2.3.4", "port": 8080}), \
         patch("ui.dialogs.options.load_extension_config", return_value={}):
        dlg = OptionsDialog(initial_tab="Proxy / Socks")
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        dlg._proxy_worker = mock_worker

        dlg._cleanup_proxy_worker()

        mock_worker.stop.assert_called_once()
        mock_worker.wait.assert_called_once()
        assert dlg._proxy_worker is None

