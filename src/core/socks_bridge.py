"""
Socks Proxy Bridge Facade
Re-exports SocksHttpBridge and SocksBridgeRunner from core.services.socks_bridge.
"""

from core.services.socks_bridge import (
    SocksHttpBridge,
    SocksBridgeRunner,
    parse_host_port,
    MAX_HEADER_SIZE,
    DEFAULT_TIMEOUT,
)

__all__ = [
    "SocksHttpBridge",
    "SocksBridgeRunner",
    "parse_host_port",
    "MAX_HEADER_SIZE",
    "DEFAULT_TIMEOUT",
]
