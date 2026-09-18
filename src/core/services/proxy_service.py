"""
Proxy Detection and Geolocation Service
=======================================
Detects proxy connectivity, external public IP, and country information
asynchronously without requiring API keys or triggering captchas.
Uses standardized endpoints (ip-api.com with ipwho.is HTTPS fallback).
"""

import http.client
import json
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlsplit

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils import get_upstream_proxy_url, is_socks_proxy_config

logger = logging.getLogger("bengal.proxy_service")


def country_code_to_flag(code: str) -> str:
    """
    Converts a 2-letter ISO 3166-1 alpha-2 country code (e.g., 'US', 'DE', 'BD')
    into its corresponding Unicode regional indicator emoji flag.
    Returns '🌐' if code is empty or invalid.
    """
    if not code or len(code) != 2:
        return "🌐"
    code = code.upper()
    if not (code[0].isalpha() and code[1].isalpha()):
        return "🌐"
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))


@dataclass
class ProxyDetectionResult:
    """Represents the outcome of a proxy connectivity & IP/country lookup."""
    is_working: bool
    ip: str = ""
    country: str = ""
    country_code: str = ""
    city: str = ""
    flag_emoji: str = "🌐"
    error_message: str = ""
    proxy_type: str = "direct"

    def summary(self) -> str:
        """Returns a human-readable one-line summary."""
        if self.is_working:
            loc = f"{self.country}" if self.country else "Unknown"
            if self.city:
                loc = f"{self.city}, {loc}"
            return f"Proxy working ({self.flag_emoji} {self.ip} - {loc})"
        return f"Proxy failed ({self.error_message})"


def _parse_ip_api_response(raw_json: bytes, ptype: str) -> ProxyDetectionResult:
    """Parses JSON response from ip-api.com."""
    data = json.loads(raw_json.decode("utf-8", errors="replace"))
    if data.get("status") == "success":
        ip = data.get("query", "").strip()
        country = data.get("country", "").strip()
        code = data.get("countryCode", "").strip()
        city = data.get("city", "").strip()
        flag = country_code_to_flag(code)
        return ProxyDetectionResult(
            is_working=True,
            ip=ip,
            country=country,
            country_code=code,
            city=city,
            flag_emoji=flag,
            proxy_type=ptype
        )
    err = data.get("message", "API returned failure status")
    return ProxyDetectionResult(
        is_working=False,
        error_message=f"Lookup failed: {err}",
        proxy_type=ptype
    )


def _parse_ipwhois_response(raw_json: bytes, ptype: str) -> ProxyDetectionResult:
    """Parses JSON response from ipwho.is."""
    data = json.loads(raw_json.decode("utf-8", errors="replace"))
    if data.get("success") is True or "ip" in data:
        ip = data.get("ip", "").strip()
        country = data.get("country", "").strip()
        code = data.get("country_code", "").strip()
        city = data.get("city", "").strip()
        flag_data = data.get("flag", {})
        flag = flag_data.get("emoji") if isinstance(flag_data, dict) else ""
        if not flag:
            flag = country_code_to_flag(code)
        return ProxyDetectionResult(
            is_working=True,
            ip=ip,
            country=country,
            country_code=code,
            city=city,
            flag_emoji=flag,
            proxy_type=ptype
        )
    err = data.get("message", "API returned failure")
    return ProxyDetectionResult(
        is_working=False,
        error_message=f"Lookup failed: {err}",
        proxy_type=ptype
    )


def _connect_via_proxy(proxy_url: str, dest_host: str, dest_port: int, timeout: float) -> socket.socket:
    """Connects a socket to dest_host:dest_port via the specified proxy URL."""
    from python_socks.sync import Proxy
    proxy = Proxy.from_url(proxy_url)
    return proxy.connect(dest_host, dest_port, timeout=timeout)


def detect_proxy_status(proxy_config: Optional[dict] = None, timeout: float = 6.0) -> ProxyDetectionResult:
    """
    Tests proxy connectivity by connecting to standard geolocation endpoints (ip-api.com, ipwho.is).
    Supports direct connections, HTTP/HTTPS proxies, and SOCKS4/SOCKS5 proxies with or without authentication.
    """
    if not proxy_config or proxy_config.get("mode") != "manual":
        ptype = "direct"
        proxy_url = None
    else:
        ptype = str(proxy_config.get("type", "http")).lower()
        host = proxy_config.get("host", "").strip()
        if not host:
            return ProxyDetectionResult(
                is_working=False,
                error_message="Proxy host is empty",
                proxy_type=ptype
            )
        proxy_url = get_upstream_proxy_url(proxy_config)

    # 1. Primary Attempt: ip-api.com over HTTP (port 80)
    try:
        if proxy_url:
            sock = _connect_via_proxy(proxy_url, "ip-api.com", 80, timeout=timeout)
            conn = http.client.HTTPConnection("ip-api.com", 80, timeout=timeout)
            conn.sock = sock
        else:
            conn = http.client.HTTPConnection("ip-api.com", 80, timeout=timeout)

        conn.request(
            "GET",
            "/json/?fields=status,message,country,countryCode,city,query",
            headers={
                "User-Agent": "Bengal-Download-Manager/1.0",
                "Host": "ip-api.com",
                "Connection": "close"
            }
        )
        resp = conn.getresponse()
        raw_body = resp.read()
        conn.close()

        if resp.status == 200:
            res = _parse_ip_api_response(raw_body, ptype)
            if res.is_working:
                return res
    except Exception as e:
        logger.debug("[ProxyService] ip-api.com lookup failed via %s: %s", ptype, e)
        last_error = e
    else:
        last_error = RuntimeError("ip-api.com returned non-success response")

    # 2. Fallback Attempt: ipwho.is over HTTPS (port 443)
    try:
        if proxy_url:
            raw_sock = _connect_via_proxy(proxy_url, "ipwho.is", 443, timeout=timeout)
            ssl_ctx = ssl.create_default_context()
            ssl_sock = ssl_ctx.wrap_socket(raw_sock, server_hostname="ipwho.is")
            conn = http.client.HTTPSConnection("ipwho.is", 443, timeout=timeout)
            conn.sock = ssl_sock
        else:
            conn = http.client.HTTPSConnection("ipwho.is", 443, timeout=timeout)

        conn.request(
            "GET",
            "/",
            headers={
                "User-Agent": "Bengal-Download-Manager/1.0",
                "Host": "ipwho.is",
                "Connection": "close"
            }
        )
        resp = conn.getresponse()
        raw_body = resp.read()
        conn.close()

        if resp.status == 200:
            res = _parse_ipwhois_response(raw_body, ptype)
            if res.is_working:
                return res
    except Exception as e:
        logger.debug("[ProxyService] ipwho.is fallback lookup failed via %s: %s", ptype, e)
        last_error = e

    # Format user-friendly error message
    err_str = str(last_error) if last_error else "Unknown error"
    err_type = type(last_error).__name__ if last_error else ""
    if "ProxyConnectionError" in err_type or "ConnectionRefused" in err_str:
        user_err = "Cannot connect to proxy server (Connection refused)"
    elif "ProxyTimeoutError" in err_type or "timed out" in err_str.lower():
        user_err = "Proxy connection timed out"
    elif "407" in err_str or "Authentication" in err_str or "ProxyError" in err_type:
        user_err = f"Proxy error: {err_str}"
    else:
        user_err = err_str

    return ProxyDetectionResult(
        is_working=False,
        error_message=user_err,
        proxy_type=ptype
    )


class ProxyDetectorWorker(QThread):
    """
    Asynchronous Qt worker thread to detect proxy status, public IP, and country flag
    without blocking the GUI thread. Runs detached from QObject parent hierarchy.
    """
    detection_finished = pyqtSignal(object)  # Emits ProxyDetectionResult

    def __init__(self, proxy_config: Optional[dict] = None, timeout: float = 4.0, parent=None):
        super().__init__(parent=None)
        self.proxy_config = proxy_config
        self.timeout = timeout
        self._stopped = False

    def stop(self):
        """Signals worker to stop and disregard pending results."""
        self._stopped = True

    def run(self):
        if self._stopped:
            return
        result = detect_proxy_status(self.proxy_config, timeout=self.timeout)
        if not self._stopped:
            try:
                self.detection_finished.emit(result)
            except RuntimeError:
                pass
