"""
Bengal Download Manager - Core Services Package
===============================================
Application and infrastructure service layer.
"""

from core.services.ipc_service import (
    DM_CONNECTOR_PORT,
    SignalEmitter,
    IPCEmitter,
    IPCRequestHandler,
    TcpListenerThread,
    IPCListenerThread,
    get_single_instance_key,
    SingleInstanceServer,
    check_single_instance,
)

__all__ = [
    "DM_CONNECTOR_PORT",
    "SignalEmitter",
    "IPCEmitter",
    "IPCRequestHandler",
    "TcpListenerThread",
    "IPCListenerThread",
    "get_single_instance_key",
    "SingleInstanceServer",
    "check_single_instance",
]
