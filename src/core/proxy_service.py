"""
Proxy Service Facade
====================
Provides backward-compatible re-exports for the core proxy detection service.
"""

from core.services.proxy_service import (
    ProxyDetectionResult,
    country_code_to_flag,
    detect_proxy_status,
    ProxyDetectorWorker,
)

__all__ = [
    "ProxyDetectionResult",
    "country_code_to_flag",
    "detect_proxy_status",
    "ProxyDetectorWorker",
]
