"""
Unit tests for Public IP detection with flags, status bar compact spacing,
Downloads menu ordering, and Stop All Queues feature.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.services.ip_service import PublicIpInfo, fetch_public_ip_info, PublicIpWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_fetch_public_ip_info_ipwhois():
    fake_data = json.dumps({
        "success": True,
        "ip": "103.205.180.5",
        "country": "Bangladesh",
        "country_code": "BD",
        "city": "Dhaka",
        "flag": {"emoji": "🇧🇩"}
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        info = fetch_public_ip_info(timeout=1.0)
        assert info.ip == "103.205.180.5"
        assert info.country == "Bangladesh"
        assert info.country_code == "BD"
        assert info.flag_emoji == "🇧🇩"


def test_fetch_public_ip_info_fallback_ip_api():
    # ipwho.is fails, ip-api succeeds
    fake_ip_api = json.dumps({
        "status": "success",
        "query": "194.55.20.10",
        "country": "Germany",
        "countryCode": "DE",
        "city": "Frankfurt"
    }).encode("utf-8")

    call_count = [0]

    def mock_urlopen(req, timeout=3.5):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("ipwho.is unreachable")
        resp = MagicMock()
        resp.read.return_value = fake_api
        resp.__enter__.return_value = resp
        return resp

    fake_api = fake_ip_api
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        info = fetch_public_ip_info(timeout=1.0)
        assert info.ip == "194.55.20.10"
        assert info.country == "Germany"
        assert info.flag_emoji == "🇩🇪"


def test_main_window_public_ip_status_bar(qapp):
    from ui.main_window import MainWindow

    with patch("core.services.proxy_service.ProxyDetectorWorker.start"), \
         patch("core.services.ip_service.PublicIpWorker.start"), \
         patch("ui.main_window.MainWindow.start_aria2_daemon", return_value=None):
        win = MainWindow()
        try:
            info = PublicIpInfo(
                ip="103.205.180.5",
                country="Bangladesh",
                country_code="BD",
                city="Dhaka",
                flag_emoji="🇧🇩"
            )
            win._on_public_ip_fetched(info)
            assert win.status_public_ip_label.text() == "IP: 🇧🇩 103.205.180.5"
            assert "Bangladesh" in win.status_public_ip_label.toolTip()
            assert "103.205.180.5" in win.status_public_ip_label.toolTip()

            # Test string backward compatibility
            win._on_public_ip_fetched("1.1.1.1")
            assert win.status_public_ip_label.text() == "IP: 🌐 1.1.1.1"
        finally:
            win.close()


def test_downloads_menu_options_and_stop_all_queues(qapp):
    from ui.main_window import MainWindow

    with patch("core.services.proxy_service.ProxyDetectorWorker.start"), \
         patch("core.services.ip_service.PublicIpWorker.start"), \
         patch("ui.main_window.MainWindow.start_aria2_daemon", return_value=None):
        win = MainWindow()
        try:
            assert hasattr(win, "action_stop_all_queues")

            # Verify action ordering in Downloads menu
            downloads_menu = None
            for action in win.menuBar().actions():
                menu = action.menu()
                if menu and "Downloads" in action.text():
                    downloads_menu = menu
                    break

            assert downloads_menu is not None
            actions = downloads_menu.actions()
            action_texts = [a.text() for a in actions if not a.isSeparator()]

            # Stop All Queues should follow Stop All
            stop_all_idx = action_texts.index("Stop All")
            stop_all_queues_idx = action_texts.index("Stop All Queues")
            assert stop_all_queues_idx == stop_all_idx + 1

            # Options should be above Scheduler
            options_idx = action_texts.index("Options")
            scheduler_idx = action_texts.index("Scheduler")
            assert options_idx < scheduler_idx

            # Test stop_all_queues execution
            stopped_queues = []
            with patch.object(win, "_queue_action_stop", side_effect=lambda q: stopped_queues.append(q)):
                win._queues_data = [
                    {"name": "Main download queue"},
                    {"name": "Queue A"},
                    {"name": "Synchronization queue"}
                ]
                win.stop_all_queues()

                assert "Main download queue" in stopped_queues
                assert "Queue A" in stopped_queues
                assert "Synchronization queue" not in stopped_queues

            # Test enabled/disabled state of action_stop_all_queues
            win.update_ui_states()
            assert not win.action_stop_all_queues.isEnabled()

            # Add an active/queued download in Main download queue -> Should be enabled
            from PyQt6.QtWidgets import QTableWidgetItem
            win.download_table.setRowCount(1)
            item_name = QTableWidgetItem("file1.zip")
            item_name.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
            status_item = QTableWidgetItem("Queued")
            status_item.setData(Qt.ItemDataRole.UserRole + 1, "Queued")
            win.download_table.setItem(0, 0, item_name)
            win.download_table.setItem(0, 2, status_item)

            win.update_ui_states()
            assert win.action_stop_all_queues.isEnabled()

            # Change to Synchronization queue -> Should be disabled
            item_name.setData(Qt.ItemDataRole.UserRole + 8, "Synchronization queue")
            win.update_ui_states()
            assert not win.action_stop_all_queues.isEnabled()

            # Change to completed -> Should be disabled
            item_name.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")
            status_item.setText("Complete")
            status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            win.update_ui_states()
            assert not win.action_stop_all_queues.isEnabled()
        finally:
            win.close()
