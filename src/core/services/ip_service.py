"""
Public IP Detection Service
===========================
Fetches the public external IP address and geographic flag asynchronously
using lightweight HTTP endpoints without requiring API keys.
"""

import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal

from core.services.proxy_service import country_code_to_flag

logger = logging.getLogger("bengal.ip")

# Reliable fallback endpoints that only return the raw IP address
RAW_IP_ENDPOINTS = [
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com"
]


@dataclass
class PublicIpInfo:
    """Represents public IP address with associated geographic details."""
    ip: str = ""
    country: str = ""
    country_code: str = ""
    city: str = ""
    flag_emoji: str = "🌐"


def fetch_public_ip_info(timeout: float = 3.5) -> PublicIpInfo:
    """Queries geolocation endpoints first, falling back to raw IP endpoints."""
    # 1. Try ipwho.is (HTTPS, returns emoji directly or country_code)
    try:
        req = urllib.request.Request(
            "https://ipwho.is/",
            headers={"User-Agent": "Bengal-Download-Manager/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
            if data.get("success") is True or "ip" in data:
                ip = str(data.get("ip", "")).strip()
                code = str(data.get("country_code", "")).strip()
                country = str(data.get("country", "")).strip()
                city = str(data.get("city", "")).strip()
                flag_data = data.get("flag", {})
                flag = flag_data.get("emoji") if isinstance(flag_data, dict) else ""
                if not flag:
                    flag = country_code_to_flag(code)
                if ip:
                    return PublicIpInfo(ip=ip, country=country, country_code=code, city=city, flag_emoji=flag or "🌐")
    except Exception as e:
        logger.debug("ipwho.is lookup failed: %s", e)

    # 2. Try ip-api.com (HTTP fallback)
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json",
            headers={"User-Agent": "Bengal-Download-Manager/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
            if data.get("status") == "success":
                ip = str(data.get("query", "")).strip()
                code = str(data.get("countryCode", "")).strip()
                country = str(data.get("country", "")).strip()
                city = str(data.get("city", "")).strip()
                flag = country_code_to_flag(code)
                if ip:
                    return PublicIpInfo(ip=ip, country=country, country_code=code, city=city, flag_emoji=flag or "🌐")
    except Exception as e:
        logger.debug("ip-api.com lookup failed: %s", e)

    # 3. Fall back to raw IP providers
    raw_ip = fetch_public_ip(timeout=timeout)
    if raw_ip:
        return PublicIpInfo(ip=raw_ip, flag_emoji="🌐")

    return PublicIpInfo()


def fetch_public_ip(timeout: float = 3.0) -> Optional[str]:
    """Queries raw public IP endpoints sequentially until a valid IP is returned."""
    for endpoint in RAW_IP_ENDPOINTS:
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
    ip_fetched = pyqtSignal(object)  # Emits PublicIpInfo (or str)

    def run(self):
        info = fetch_public_ip_info()
        self.ip_fetched.emit(info)
