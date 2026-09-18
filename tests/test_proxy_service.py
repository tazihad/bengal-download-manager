"""
Unit tests for Proxy Detection and Geolocation Service.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from core.services.proxy_service import (
    country_code_to_flag,
    detect_proxy_status,
    ProxyDetectionResult,
    ProxyDetectorWorker,
)


class TestProxyService(unittest.TestCase):
    def test_country_code_to_flag(self):
        # Standard country codes
        self.assertEqual(country_code_to_flag("US"), "🇺🇸")
        self.assertEqual(country_code_to_flag("BD"), "🇧🇩")
        self.assertEqual(country_code_to_flag("DE"), "🇩🇪")
        self.assertEqual(country_code_to_flag("GB"), "🇬🇧")
        self.assertEqual(country_code_to_flag("JP"), "🇯🇵")

        # Lowercase normalization
        self.assertEqual(country_code_to_flag("us"), "🇺🇸")
        self.assertEqual(country_code_to_flag("bd"), "🇧🇩")

        # Edge cases & invalid codes
        self.assertEqual(country_code_to_flag(""), "🌐")
        self.assertEqual(country_code_to_flag(None), "🌐")
        self.assertEqual(country_code_to_flag("A"), "🌐")
        self.assertEqual(country_code_to_flag("USA"), "🌐")
        self.assertEqual(country_code_to_flag("12"), "🌐")
        self.assertEqual(country_code_to_flag("!@"), "🌐")

    def test_detect_proxy_status_empty_host(self):
        cfg = {"mode": "manual", "type": "http", "host": "  ", "port": 8080}
        result = detect_proxy_status(cfg)
        self.assertFalse(result.is_working)
        self.assertIn("empty", result.error_message.lower())

    @patch("http.client.HTTPConnection")
    def test_detect_proxy_status_direct_success(self, mock_conn_cls):
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "status": "success",
            "country": "Germany",
            "countryCode": "DE",
            "city": "Frankfurt",
            "query": "198.51.100.123"
        }).encode("utf-8")
        mock_conn.getresponse.return_value = mock_resp
        mock_conn_cls.return_value = mock_conn

        result = detect_proxy_status({"mode": "no_proxy"})
        self.assertTrue(result.is_working)
        self.assertEqual(result.ip, "198.51.100.123")
        self.assertEqual(result.country, "Germany")
        self.assertEqual(result.country_code, "DE")
        self.assertEqual(result.city, "Frankfurt")
        self.assertEqual(result.flag_emoji, "🇩🇪")
        self.assertIn("🇩🇪", result.summary())

    @patch("core.services.proxy_service._connect_via_proxy")
    @patch("http.client.HTTPConnection")
    def test_detect_proxy_status_socks5_success(self, mock_conn_cls, mock_connect):
        mock_sock = MagicMock()
        mock_connect.return_value = mock_sock

        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "status": "success",
            "country": "United States",
            "countryCode": "US",
            "city": "New York",
            "query": "203.0.113.50"
        }).encode("utf-8")
        mock_conn.getresponse.return_value = mock_resp
        mock_conn_cls.return_value = mock_conn

        cfg = {
            "mode": "manual",
            "type": "socks5",
            "host": "127.0.0.1",
            "port": 1080,
            "auth": True,
            "user": "u",
            "password": "p"
        }
        result = detect_proxy_status(cfg)
        self.assertTrue(result.is_working)
        self.assertEqual(result.ip, "203.0.113.50")
        self.assertEqual(result.country, "United States")
        self.assertEqual(result.flag_emoji, "🇺🇸")
        self.assertEqual(result.proxy_type, "socks5")
        mock_connect.assert_called_once_with("socks5://u:p@127.0.0.1:1080", "ip-api.com", 80, timeout=6.0)

    @patch("core.services.proxy_service._connect_via_proxy")
    def test_detect_proxy_status_connection_error(self, mock_connect):
        from python_socks import ProxyConnectionError
        mock_connect.side_effect = ProxyConnectionError("Connection refused")

        cfg = {
            "mode": "manual",
            "type": "http",
            "host": "127.0.0.1",
            "port": 9999,
        }
        result = detect_proxy_status(cfg)
        self.assertFalse(result.is_working)
        self.assertIn("Cannot connect to proxy server", result.error_message)

    @patch("core.services.proxy_service.detect_proxy_status")
    def test_proxy_detector_worker(self, mock_detect):
        mock_res = ProxyDetectionResult(is_working=True, ip="1.2.3.4", flag_emoji="🌐")
        mock_detect.return_value = mock_res

        worker = ProxyDetectorWorker({"mode": "no_proxy"})
        results = []
        worker.detection_finished.connect(results.append)
        worker.run()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].ip, "1.2.3.4")
