"""
IPC & Single-Instance Services
==============================
Manages local TCP listener for browser extensions and QLocalServer
single-instance inter-process communication for Bengal Download Manager.
"""

import os
import sys
import json
import logging
import threading
import getpass
from http.server import HTTPServer, BaseHTTPRequestHandler

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.utils import load_extension_config, is_debug_mode

logger = logging.getLogger("bengal.ipc")

# Default TCP port for browser extension communication
DM_CONNECTOR_PORT = 56900


class SignalEmitter(QObject):
    """Utility to emit signals safely to the GUI thread."""
    new_download_signal = pyqtSignal(str)


# Alias for compatibility
IPCEmitter = SignalEmitter


class IPCRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP API requests from browser extension (GET config, POST new download)."""

    def do_OPTIONS(self):
        if is_debug_mode():
            logger.debug("[IPC] CORS preflight OPTIONS request from %s for %s", self.client_address[0], self.path)
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if is_debug_mode():
            logger.debug("[IPC] Extension ping / GET request from %s on %s", self.client_address[0], self.path)
        ext_data = load_extension_config()
        try:
            from core.version import VERSION
            app_version = VERSION
        except Exception:
            app_version = "0.1"

        config_json = json.dumps({
            "status": "Bengal DM is running",
            "version": app_version,
            "aria2": {
                "port": ext_data.get("port", 56800),
                "token": ext_data.get("token", "")
            }
        })
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(config_json.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        
        # Guard: Only explicit user download submissions on root '/' or '/download' should trigger downloads
        clean_path = self.path.split("?")[0].rstrip("/")
        if is_debug_mode():
            logger.debug("[IPC] POST request from %s on %s (bytes=%d)", self.client_address[0], self.path, content_length)

        if clean_path not in ("", "/download"):
            # Background sniffing or status notification (e.g. /media, /tab-update)
            # Acknowledge with 200 OK without emitting new_download_signal
            if is_debug_mode():
                logger.debug("[IPC] Acknowledged background notification on %s", clean_path)
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "acknowledged"}')
            return
        
        url = ""
        user_agent = ""
        cookies = ""
        referrer = ""
        is_media = False
        title = ""
        quality = ""
        size_bytes = 0
        size_str = ""
        
        try:
            payload = json.loads(body)
            url = payload.get("url", "")
            user_agent = payload.get("userAgent", "")
            cookies = payload.get("cookies", "")
            referrer = payload.get("referrer", "")
            is_media = bool(payload.get("isMedia", False))
            title = str(payload.get("title", "") or payload.get("filename", "")).strip()
            quality = str(payload.get("quality", "")).strip()
            size_bytes = int(payload.get("sizeBytes", 0) or 0)
            size_str = str(payload.get("sizeStr", "") or "").strip()
            if is_debug_mode():
                logger.debug("[IPC] Parsed JSON payload from extension: url=%s, title=%r, quality=%r, isMedia=%s, size=%s",
                             url, title, quality, is_media, size_str or size_bytes)
        except json.JSONDecodeError:
            url = body.strip()
            if is_debug_mode():
                logger.debug("[IPC] Received raw string URL from extension: %s", url)
            
        if url and url.startswith("http"):
            media_flag = "1" if is_media else "0"
            raw_msg = f"{url}|{user_agent}|{cookies}|{referrer}|{media_flag}|{quality}|{title}|{size_bytes}|{size_str}"
            if is_debug_mode():
                logger.debug("[IPC] Emitting new_download_signal: %s", raw_msg[:300])
            # self.server.emitter is passed when initializing the server
            self.server.emitter.new_download_signal.emit(raw_msg)
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            if is_debug_mode():
                logger.warning("[IPC] Rejected POST: missing or invalid HTTP URL: %s", url[:100])
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
    def log_message(self, format, *args):
        if is_debug_mode():
            logger.debug("[IPC HTTP] %s - %s", self.client_address[0], format % args)


class TcpListenerThread(QThread):
    """Background TCP HTTP server listening for browser extension downloads."""

    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.server = None

    def run(self):
        try:
            if is_debug_mode():
                logger.debug("[IPC] Starting extension TCP listener thread on 127.0.0.1:%s", self.port)
            self.server = HTTPServer(('127.0.0.1', self.port), IPCRequestHandler)
            # Attach emitter to server so handler can access it
            self.server.emitter = self.emitter 
            if is_debug_mode():
                logger.debug("[IPC] Extension TCP listener bound and active on port %s", self.port)
            self.server.serve_forever()
        except Exception as e:
            logger.error("[IPC] Failed to run TCP listener on port %s: %s", self.port, e)

    def stop(self):
        if self.server:
            if is_debug_mode():
                logger.debug("[IPC] Stopping extension TCP listener on port %s", self.port)
            # shutdown() must be called from another thread
            def cleanup():
                try:
                    self.server.shutdown()
                    self.server.server_close()
                except Exception:
                    pass
            threading.Thread(target=cleanup, daemon=True).start()


# Alias for compatibility
IPCListenerThread = TcpListenerThread


def get_single_instance_key() -> str:
    """Generates user-scoped unique IPC socket key for single instance enforcement."""
    user_identifier = str(os.getuid()) if hasattr(os, 'getuid') else getpass.getuser()
    return f"bengal-download-manager-single-instance-{user_identifier}"


class SingleInstanceServer(QObject):
    """Local IPC server enforcing single application instance and forwarding invocations."""
    messageReceived = pyqtSignal(dict)

    def __init__(self, key=None, parent=None):
        super().__init__(parent)
        self.key = key or get_single_instance_key()
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_new_connection)

    def start(self):
        QLocalServer.removeServer(self.key)
        if not self.server.listen(self.key):
            logger.warning("[SingleInstance] Could not listen on key %r: %s", self.key, self.server.errorString())
        elif is_debug_mode():
            logger.debug("[SingleInstance] Listening for companion processes on key %r", self.key)

    def stop(self):
        if self.server and self.server.isListening():
            if is_debug_mode():
                logger.debug("[SingleInstance] Closing server on key %r", self.key)
            self.server.close()
            QLocalServer.removeServer(self.key)

    def _on_new_connection(self):
        client = self.server.nextPendingConnection()
        if client:
            if is_debug_mode():
                logger.debug("[SingleInstance] Inbound connection established")
            client.readyRead.connect(lambda c=client: self._read_client(c))

    def _read_client(self, client):
        try:
            data = client.readAll().data()
            if data:
                payload = json.loads(data.decode('utf-8'))
                if is_debug_mode():
                    logger.debug("[SingleInstance] Received forwarded command payload: %s", payload)
                self.messageReceived.emit(payload)
        except Exception as e:
            logger.error("[SingleInstance] Error parsing client message: %s", e)
        finally:
            client.deleteLater()


def check_single_instance(key=None, timeout_ms=500) -> bool:
    """
    Attempts to connect to an existing running instance of Bengal Download Manager.
    If connected, sends invocation arguments to the primary instance and returns True.
    Otherwise returns False.
    """
    target_key = key or get_single_instance_key()
    socket = QLocalSocket()
    socket.connectToServer(target_key)
    if socket.waitForConnected(timeout_ms):
        msg_payload = {
            "command": "show",
            "args": sys.argv[1:]
        }
        data = json.dumps(msg_payload).encode('utf-8')
        socket.write(data)
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        if is_debug_mode():
            logger.debug("[SingleInstance] Successfully forwarded args to primary instance: %s", sys.argv[1:])
        return True
    return False
