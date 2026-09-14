"""
Public IP Detection Service
===========================
Fetches the public external IP address asynchronously using lightweight HTTP endpoints.
"""

import logging
import urllib.request
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("bengal.ip")

# Reliable, lightweight public IP lookup endpoints with fallback
IP_ENDPOINTS = [
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com"
]


def fetch_public_ip(timeout: float = 3.0) -> Optional[str]:
    """Queries public IP endpoints sequentially until a valid IP is returned."""
    for endpoint in IP_ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "Bengal-Download-Manager/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                ip = response.read().decode("utf-8").strip()
                if ip and len(ip) <= 45 and all(c in "0123456789abcdefABCDEF:." for c in ip):
                    return ip
        except Exception:
            continue
    return None


class PublicIpWorker(QThread):
    """Background worker thread to retrieve external public IP without blocking the GUI."""
    ip_fetched = pyqtSignal(str)

    def run(self):
        ip = fetch_public_ip()
        self.ip_fetched.emit(ip or "")
