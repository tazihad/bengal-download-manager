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
import time
import getpass
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.utils import load_extension_config, is_debug_mode, is_verbose_mode

logger = logging.getLogger("bengal.ipc")

# Default TCP port for browser extension communication
DM_CONNECTOR_PORT = 56900


def get_ipc_port() -> int:
    """Retrieve configured IPC port for extension communication, fallback to default."""
    ext_data = load_extension_config()
    try:
        return int(ext_data.get("ipc_port", DM_CONNECTOR_PORT))
    except (ValueError, TypeError):
        return DM_CONNECTOR_PORT


class SignalEmitter(QObject):
    """Utility to emit signals safely to the GUI thread."""
    new_download_signal = pyqtSignal(str)
    batch_download_signal = pyqtSignal(list)


# Alias for compatibility
IPCEmitter = SignalEmitter


class IPCRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP API requests from browser extension (GET config, POST new download)."""

    _heartbeat_lock = threading.Lock()
    _last_heartbeat_time = 0.0
    _heartbeat_count = 0
    _last_heartbeat_client = None
    _HEARTBEAT_SUMMARY_INTERVAL = 300.0  # Log summary once every 5 minutes in --debug

    def do_OPTIONS(self):
        # Handle CORS preflight from extensions or web integrations
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With, Authorization')
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        is_heartbeat = clean_path in ("", "/")
        self._is_routine_heartbeat = is_heartbeat
        client_ip = self.client_address[0] if (hasattr(self, "client_address") and self.client_address) else "127.0.0.1"

        is_verbose = is_verbose_mode() or os.environ.get("BENGAL_VERBOSE_IPC") == "1"
        if is_debug_mode() or is_verbose:
            if is_verbose:
                logger.debug("[IPC] Extension ping / GET request from %s on %s", client_ip, self.path)
            elif is_heartbeat:
                now = time.time()
                with self._heartbeat_lock:
                    IPCRequestHandler._heartbeat_count += 1
                    # Log initial connection or client change immediately
                    if IPCRequestHandler._last_heartbeat_client != client_ip:
                        IPCRequestHandler._last_heartbeat_client = client_ip
                        IPCRequestHandler._last_heartbeat_time = now
                        IPCRequestHandler._heartbeat_count = 1
                        logger.debug("[IPC] Extension heartbeat connected from %s", client_ip)
                    elif now - IPCRequestHandler._last_heartbeat_time >= self._HEARTBEAT_SUMMARY_INTERVAL:
                        elapsed_min = max(1, int((now - IPCRequestHandler._last_heartbeat_time) / 60))
                        logger.debug(
                            "[IPC] Extension heartbeat active from %s (%d pings in last %dm)",
                            client_ip,
                            IPCRequestHandler._heartbeat_count,
                            elapsed_min,
                        )
                        IPCRequestHandler._last_heartbeat_time = now
                        IPCRequestHandler._heartbeat_count = 0
            else:
                logger.debug("[IPC] GET request from %s on %s", client_ip, self.path)
        ext_data = load_extension_config()
        try:
            from core.version import VERSION
            app_version = VERSION
        except Exception:
            app_version = "0.1"

        configured_ipc_port = ext_data.get("ipc_port", DM_CONNECTOR_PORT)
        server_port = self.server.server_address[1] if (hasattr(self, 'server') and hasattr(self.server, 'server_address')) else configured_ipc_port
        is_fallback = bool(server_port != configured_ipc_port)

        try:
            from core.media.sabr import sabr_runtime_available
            sabr_capable = sabr_runtime_available()
        except Exception:
            sabr_capable = False

        config_json = json.dumps({
            "status": "Bengal DM is running",
            "version": app_version,
            "ipc_port": server_port,
            "configured_ipc_port": configured_ipc_port,
            "is_fallback": is_fallback,
            "sabr": sabr_capable,
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
        # A SABR session body carries formats plus a capped protobuf blob; anything
        # beyond a few MiB cannot be a legitimate submission from the extension.
        if content_length > 8 * 1024 * 1024:
            logger.warning("[IPC] Rejected POST body of %d bytes (8 MiB cap)", content_length)
            self.send_response(413)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            return
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        
        clean_path = self.path.split("?")[0].rstrip("/")
        if is_debug_mode():
            logger.debug("[IPC] POST request from %s on %s (bytes=%d)", self.client_address[0], self.path, content_length)

        payload = {}
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            pass

        # Check for batch download submissions
        if clean_path in ("/batch", "/import-links") or (isinstance(payload, dict) and (payload.get("links") or payload.get("urls"))):
            raw_links = payload.get("links") or payload.get("urls") if isinstance(payload, dict) else None
            if isinstance(raw_links, list) and raw_links:
                if is_debug_mode():
                    logger.debug("[IPC] Received batch of %d links", len(raw_links))
                if hasattr(self.server.emitter, "batch_download_signal"):
                    self.server.emitter.batch_download_signal.emit(raw_links)
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "batch_received"}')
                return

        # Resolve stream URLs for Direct downloads. yt-dlp only locates the signed URLs;
        # both tracks are transferred by Aria2 and muxed by the desktop.
        if clean_path == "/resolve-direct":
            page_url = payload.get("url", "") if isinstance(payload, dict) else ""
            if not page_url or not str(page_url).lower().startswith(("http://", "https://")):
                status = 400
                body_out = json.dumps({"success": False, "error": "Missing or invalid URL"})
            else:
                status = 200
                try:
                    from core.media.direct import resolve_media_tracks, resolve_single_file_url

                    video_itag = str(payload.get("videoItag", "") or "") or None
                    audio_itag = str(payload.get("audioItag", "") or "") or None
                    resolution = None
                    if video_itag or audio_itag:
                        resolution = resolve_media_tracks(
                            page_url=str(page_url),
                            cookies=str(payload.get("cookies", "") or ""),
                            user_agent=str(payload.get("userAgent", "") or ""),
                            referrer=str(payload.get("referrer", "") or ""),
                            video_itag=video_itag,
                            audio_itag=audio_itag,
                        )
                    else:
                        resolution = resolve_single_file_url(
                            page_url=str(page_url),
                            cookies=str(payload.get("cookies", "") or ""),
                            user_agent=str(payload.get("userAgent", "") or ""),
                            referrer=str(payload.get("referrer", "") or ""),
                        )
                    resolution = resolution or {}
                    video_url = resolution.get("videoUrl") or resolution.get("url") or ""
                    audio_url = resolution.get("audioUrl") or ""
                    video_ext = resolution.get("videoExt") or resolution.get("ext") or ""
                    audio_ext = resolution.get("audioExt") or ""
                    video_size = int(resolution.get("videoSize") or resolution.get("sizeBytes") or 0)
                    audio_size = int(resolution.get("audioSize") or 0)
                    if not video_url and audio_url:
                        # Audio-only pick.
                        video_ext, audio_ext = "", audio_ext or video_ext or ".m4a"
                    body_out = json.dumps({
                        "success": bool(video_url or audio_url),
                        "resolvedUrl": video_url,
                        "videoUrl": video_url,
                        "audioUrl": audio_url,
                        "ext": video_ext,
                        "videoExt": video_ext,
                        "audioExt": audio_ext,
                        "sizeBytes": video_size + audio_size,
                    })
                    if is_debug_mode():
                        logger.debug("[IPC] Direct URL resolution for %s -> %s", str(page_url)[:120], body_out[:240])
                except Exception as e:
                    if is_debug_mode():
                        logger.warning("[IPC] Direct URL resolution failed: %s", e)
                    body_out = json.dumps({"success": False, "error": str(e)})

            self.send_response(status)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body_out.encode('utf-8'))
            return

        # Check for media sizes / probe requests (used exclusively by browser extension media popup)
        if clean_path in ("/media-sizes", "/probe-media", "/media-info"):
            url = payload.get("url", "") if isinstance(payload, dict) else ""
            if not url:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"success": false, "error": "Missing URL"}')
                return

            try:
                from core.media import probe_media_sizes
                res = probe_media_sizes(
                    url=url,
                    heights=payload.get("heights"),
                    referrer=payload.get("referrer"),
                    user_agent=payload.get("userAgent"),
                    cookies=payload.get("cookies"),
                    cookies_file=payload.get("cookiesFile"),
                    cookies_browser=payload.get("cookiesBrowser"),
                    video_container=payload.get("videoContainer", "auto"),
                    audio_format=payload.get("audioFormat", "auto"),
                )
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                if is_debug_mode():
                    logger.warning("[IPC] Failed to probe media sizes: %s", e)
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
            return

        # Guard: Only explicit user download submissions on root '/' or '/download' should trigger downloads
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
        method = ""
        filename = ""
        ext = ""
        audio_url = ""
        sabr_session = None

        if isinstance(payload, dict) and payload:
            url = payload.get("url", "")
            user_agent = payload.get("userAgent", "")
            cookies = payload.get("cookies", "")
            referrer = payload.get("referrer", "")
            is_media = bool(payload.get("isMedia", False))
            title = str(payload.get("title", "") or payload.get("filename", "")).strip()
            quality = str(payload.get("quality", "")).strip()
            size_bytes = int(payload.get("sizeBytes", 0) or 0)
            size_str = str(payload.get("sizeStr", "") or "").strip()
            method = str(payload.get("method", "") or "").strip()
            filename = str(payload.get("filename", "") or "").strip()
            ext = str(payload.get("ext", "") or "").strip()
            audio_url = str(payload.get("audioUrl", "") or "").strip()
            raw_sabr = payload.get("sabr")
            if isinstance(raw_sabr, dict) and raw_sabr:
                try:
                    from core.media.sabr import validate_sabr_session
                    sabr_session = validate_sabr_session(raw_sabr)
                except Exception:
                    sabr_session = None
                if sabr_session is None:
                    logger.warning("[IPC] Dropped invalid SABR session payload for %s", url[:120])
            if is_debug_mode():
                logger.debug("[IPC] Parsed JSON payload from extension: url=%s, title=%r, quality=%r, isMedia=%s, size=%s, audioUrl=%s, sabr=%s",
                             url, title, quality, is_media, size_str or size_bytes, bool(audio_url), bool(sabr_session))
        else:
            url = body.strip()
            if is_debug_mode():
                logger.debug("[IPC] Received raw string URL from extension: %s", url)
            
        if url and url.startswith("http"):
            payload_data = {
                "url": url,
                "userAgent": user_agent,
                "cookies": cookies,
                "referrer": referrer,
                "isMedia": is_media,
                "quality": quality,
                "title": title,
                "sizeBytes": size_bytes,
                "sizeStr": size_str,
                "method": method,
                "filename": filename,
                "ext": ext,
                "audioUrl": audio_url,
            }
            if sabr_session:
                payload_data["sabr"] = sabr_session
            raw_msg = json.dumps(payload_data)
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
        is_verbose = is_verbose_mode() or os.environ.get("BENGAL_VERBOSE_IPC") == "1"
        if is_debug_mode() or is_verbose:
            msg = format % args
            # Suppress routine successful heartbeat GET / pings unless verbose mode is active
            if not is_verbose:
                if getattr(self, "_is_routine_heartbeat", False) and ' 200 ' in msg:
                    return
                if ('"GET / HTTP/' in msg or '"GET /? ' in msg or '"GET / ' in msg) and ' 200 ' in msg:
                    return
            client_ip = self.client_address[0] if (hasattr(self, "client_address") and self.client_address) else "127.0.0.1"
            logger.debug("[IPC HTTP] %s - %s", client_ip, msg)


class ReusableHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class TcpListenerThread(QThread):
    """Background TCP HTTP server listening for browser extension downloads."""

    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.server = None

    def run(self):
        from core.utils import set_linux_process_name
        set_linux_process_name("bengal-ipc")
        try:
            if is_debug_mode():
                logger.debug("[IPC] Starting extension TCP listener thread on 127.0.0.1:%s", self.port)

            # Auto-reclaim port if held by an orphaned instance or prior crash
            try:
                from core.services.port_service import reclaim_port
                reclaim_port(self.port, "ipc", ["python", "python3", "bengal", "bengal-download-manager"])
            except Exception as pe:
                if is_debug_mode():
                    logger.debug("[IPC] Pre-bind port reclamation check: %s", pe)

            # Try binding to configured port from options first; if occupied by an external
            # socket (e.g. browser TCP self-connect), gracefully activate safe fallback port.
            ports_to_try = [self.port]
            for fallback in (26900, 26901, 26902):
                if fallback not in ports_to_try:
                    ports_to_try.append(fallback)

            server = None
            bound_port = self.port
            for candidate_port in ports_to_try:
                try:
                    reclaim_port(candidate_port, "ipc", ["python", "python3", "bengal", "bengal-download-manager"], timeout_sec=0.2)
                except Exception:
                    pass

                for attempt in range(3):
                    try:
                        server = ReusableHTTPServer(('127.0.0.1', candidate_port), IPCRequestHandler)
                        bound_port = candidate_port
                        break
                    except OSError as oe:
                        if attempt < 2 and (getattr(oe, 'errno', None) == 98 or 'Address already in use' in str(oe)):
                            time.sleep(0.15)
                            continue
                        break
                if server is not None:
                    break

            if server is None:
                raise OSError(98, f"Address already in use on ports {ports_to_try}")

            if bound_port != self.port:
                logger.warning(
                    "[IPC] Configured port %s is occupied by an external process/connection. "
                    "Activated safe fallback listener on port %s.",
                    self.port, bound_port
                )
            self.port = bound_port
            self.server = server
            # Attach emitter to server so handler can access it
            self.server.emitter = self.emitter 
            if is_debug_mode():
                logger.debug("[IPC] Extension TCP listener bound and active on port %s", self.port)
            self.server.serve_forever()
        except OSError as e:
            if getattr(e, 'errno', None) == 98 or 'Address already in use' in str(e):
                logger.error(
                    "[IPC] Failed to run TCP listener on port %s: [Errno 98] Address already in use. "
                    "Another instance or service is occupying this port. "
                    "You can change the IPC Port in Tools -> Options -> Extension tab.",
                    self.port
                )
            else:
                logger.error("[IPC] Failed to run TCP listener on port %s: %s", self.port, e)
        except Exception as e:
            logger.error("[IPC] Failed to run TCP listener on port %s: %s", self.port, e)

    def stop(self, timeout_ms=2000):
        srv = self.server
        self.server = None
        if srv:
            if is_debug_mode():
                logger.debug("[IPC] Stopping extension TCP listener on port %s", self.port)
            def _cleanup():
                try:
                    srv.shutdown()
                except Exception:
                    pass
                try:
                    srv.server_close()
                except Exception:
                    pass
                try:
                    if hasattr(srv, "socket") and srv.socket:
                        srv.socket.close()
                except Exception:
                    pass
            t = threading.Thread(target=_cleanup, daemon=True)
            t.start()
            t.join(timeout=(timeout_ms / 1000.0 if timeout_ms else 2.0))
        try:
            self.quit()
            self.wait(timeout_ms or 2000)
        except Exception:
            pass


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
