"""
IPC & Single-Instance Services
==============================
Manages local TCP listener for browser extensions and QLocalServer
single-instance inter-process communication for Bengal Download Manager.
"""

import os
import sys
import json
import threading
import getpass
from http.server import HTTPServer, BaseHTTPRequestHandler

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.utils import load_extension_config

# Default TCP port for browser extension communication
DM_CONNECTOR_PORT = 9000


class SignalEmitter(QObject):
    """Utility to emit signals safely to the GUI thread."""
    new_download_signal = pyqtSignal(str)


# Alias for compatibility
IPCEmitter = SignalEmitter


class IPCRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP API requests from browser extension (GET config, POST new download)."""

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
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
        body = self.rfile.read(content_length).decode('utf-8')
        
        url = ""
        user_agent = ""
        cookies = ""
        
        try:
            payload = json.loads(body)
            url = payload.get("url", "")
            user_agent = payload.get("userAgent", "")
            cookies = payload.get("cookies", "")
        except json.JSONDecodeError:
            url = body
            
        if url and url.startswith("http"):
            # self.server.emitter is passed when initializing the server
            self.server.emitter.new_download_signal.emit(f"{url}|{user_agent}|{cookies}")
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
    def log_message(self, format, *args):
        pass  # Suppress default logging to stderr


class TcpListenerThread(QThread):
    """Background TCP HTTP server listening for browser extension downloads."""

    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.server = None

    def run(self):
        try:
            self.server = HTTPServer(('127.0.0.1', self.port), IPCRequestHandler)
            # Attach emitter to server so handler can access it
            self.server.emitter = self.emitter 
            self.server.serve_forever()
        except Exception:
            pass

    def stop(self):
        if self.server:
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
            print(f"Warning: SingleInstanceServer could not listen on key '{self.key}': {self.server.errorString()}")

    def stop(self):
        if self.server and self.server.isListening():
            self.server.close()
            QLocalServer.removeServer(self.key)

    def _on_new_connection(self):
        client = self.server.nextPendingConnection()
        if client:
            client.readyRead.connect(lambda c=client: self._read_client(c))

    def _read_client(self, client):
        try:
            data = client.readAll().data()
            if data:
                payload = json.loads(data.decode('utf-8'))
                self.messageReceived.emit(payload)
        except Exception as e:
            print(f"SingleInstanceServer read error: {e}")
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
        return True
    return False
