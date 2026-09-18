"""
Aria2 Daemon Manager
====================
Deep module encapsulating aria2 RPC daemon supervision, port reclamation,
command-line synthesis, background stderr logging, graceful JSON-RPC shutdown,
and process liveness tracking.

Architecture:
- High depth: Encapsulates complex OS process orchestration and RPC protocols
  behind a concise, signal-driven interface.
- Seam: Positioned cleanly between presentation callers (PyQt6 MainWindow,
  Kirigami QML DownloadBridge, CLI runners) and external aria2c binary processes.
"""

import os
import time
import json
import socket
import logging
import threading
import subprocess
import urllib.request
from typing import Optional, List

from PyQt6.QtCore import QObject, pyqtSignal

from core.utils import (
    load_extension_config,
    ensure_aria2,
    get_clean_env,
    load_proxy_config,
    get_aria2_proxy_url,
    get_upstream_proxy_url,
    is_socks_proxy_config,
    is_debug_mode,
)
from core.services.socks_bridge import SocksBridgeRunner

logger = logging.getLogger("bengal.core.aria2_daemon")


class Aria2DaemonManager(QObject):
    """
    Supervises the internal aria2 RPC daemon process.
    Provides graceful lifecycle controls and liveness monitoring.
    """

    status_changed = pyqtSignal(bool, str)  # (is_running, status_text)
    started = pyqtSignal(int)               # (port)
    stopped = pyqtSignal()
    error_occurred = pyqtSignal(str)        # (error_message)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._process: Optional[subprocess.Popen] = None
        self._port: int = 56800
        self._token: str = ""
        self._socks_bridge_runner: Optional[SocksBridgeRunner] = None
        self._lock = threading.RLock()

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Direct access to the underlying subprocess if active."""
        with self._lock:
            return self._process

    @property
    def pid(self) -> Optional[int]:
        """PID of the managed daemon process if running."""
        with self._lock:
            if self._process and self._process.poll() is None:
                return self._process.pid
        return None

    @property
    def port(self) -> int:
        """Configured RPC port for this daemon."""
        return self._port

    @property
    def token(self) -> str:
        """Configured RPC secret token."""
        return self._token

    @property
    def socks_bridge_runner(self) -> Optional[SocksBridgeRunner]:
        """Active local HTTP-to-SOCKS bridge runner if SOCKS is configured."""
        with self._lock:
            return self._socks_bridge_runner

    def is_running(self) -> bool:
        """
        Determines if the managed aria2 process is currently alive,
        or if an external aria2 RPC listener is responding on the configured port.
        """
        with self._lock:
            if self._process and self._process.poll() is None:
                return True

        # Fallback check: probe TCP port
        return self.is_port_active(timeout=0.15)

    def is_port_active(self, timeout: float = 0.15) -> bool:
        """Directly probes whether the RPC port is accepting TCP connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex(("127.0.0.1", self._port)) == 0
        except Exception:
            return False

    def start(
        self,
        port: Optional[int] = None,
        token: Optional[str] = None,
        max_connections: Optional[int] = None,
    ) -> bool:
        """
        Starts the aria2 daemon process, reclaiming orphaned ports and
        setting up RPC and proxy parameters.
        """
        with self._lock:
            self.stop(timeout_sec=1.5)

            ext_data = load_extension_config()
            self._port = port if port is not None else int(ext_data.get("port", 56800))
            self._token = token if token is not None else str(ext_data.get("token", ""))
            max_conn = str(
                max_connections
                if max_connections is not None
                else ext_data.get("max_connections", 8)
            )

            aria2_bin = ensure_aria2() or "aria2c"

            # Auto-reclaim port if occupied by orphaned instance
            try:
                from core.services.port_service import reclaim_port
                reclaim_port(self._port, "aria2", ["aria2c", "aria2"], rpc_token=self._token)
            except Exception as pe:
                if is_debug_mode():
                    logger.debug("[Aria2DaemonManager] Pre-launch port reclamation check: %s", pe)

            cmd: List[str] = [
                aria2_bin,
                "--enable-rpc=true",
                f"--rpc-listen-port={self._port}",
                "--rpc-listen-all=false",
                "--rpc-allow-origin-all",
                f"--max-connection-per-server={max_conn}",
                "--min-split-size=1M",
                f"--split={max_conn}",
                "--daemon=false",
                "--no-proxy=127.0.0.1,localhost",
            ]
            if self._token:
                cmd.append(f"--rpc-secret={self._token}")

            # Apply system proxy if configured
            proxy_url = self._setup_proxy_for_startup()
            if proxy_url:
                cmd.append(f"--all-proxy={proxy_url}")

            debug_active = is_debug_mode()
            if debug_active:
                logger.debug(
                    "[Aria2DaemonManager] Spawning daemon on port %s: %s",
                    self._port,
                    " ".join(cmd),
                )

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE if debug_active else subprocess.DEVNULL,
                    env=get_clean_env(),
                )
                self._process = proc

                if debug_active and proc and proc.stderr:
                    logger.debug("[Aria2DaemonManager] Process spawned with PID %s", proc.pid)

                    def _stream_stderr(p: subprocess.Popen):
                        try:
                            if p.stderr:
                                for line in p.stderr:
                                    msg = line.decode("utf-8", errors="ignore").strip()
                                    if msg:
                                        logger.debug("[Aria2Daemon] %s", msg)
                        except Exception:
                            pass

                    threading.Thread(target=_stream_stderr, args=(proc,), daemon=True).start()

                time.sleep(0.05)
                if proc.poll() is not None:
                    ret = proc.returncode
                    err_msg = f"aria2 daemon exited immediately with return code {ret}"
                    logger.error("[Aria2DaemonManager] %s", err_msg)
                    self._process = None
                    self.status_changed.emit(False, "Stopped")
                    self.error_occurred.emit(err_msg)
                    return False

                self.status_changed.emit(True, f"Connected (PID {proc.pid})")
                self.started.emit(self._port)
                return True

            except Exception as e:
                err_msg = f"Failed to spawn aria2 daemon: {e}"
                logger.error("[Aria2DaemonManager] %s", err_msg, exc_info=True)
                self._process = None
                self.status_changed.emit(False, "Failed")
                self.error_occurred.emit(err_msg)
                return False

    def _setup_proxy_for_startup(self, proxy_config: Optional[dict] = None) -> str:
        """
        Prepares the effective aria2 --all-proxy URL, automatically starting or
        reconfiguring the local HTTP-to-SOCKS bridge if a SOCKS proxy is specified.
        """
        if proxy_config is None:
            proxy_config = load_proxy_config()

        if is_socks_proxy_config(proxy_config):
            socks_url = get_upstream_proxy_url(proxy_config)
            if (
                not self._socks_bridge_runner
                or self._socks_bridge_runner.proxy_url != socks_url
                or not self._socks_bridge_runner.is_running()
            ):
                if self._socks_bridge_runner:
                    self._socks_bridge_runner.stop()
                self._socks_bridge_runner = SocksBridgeRunner(socks_url)
                self._socks_bridge_runner.start(timeout=5.0)
            return self._socks_bridge_runner.get_http_proxy_url()
        else:
            if self._socks_bridge_runner:
                self._socks_bridge_runner.stop()
                self._socks_bridge_runner = None
            return get_aria2_proxy_url(proxy_config)

    def update_proxy(self, proxy_config: Optional[dict] = None) -> str:
        """
        Dynamically coordinates proxy transitions (Direct, HTTP, SOCKS4/5),
        starting/stopping the local HTTP-to-SOCKS bridge as needed,
        and updating the running Aria2 daemon via JSON-RPC.
        Returns the effective aria2 --all-proxy URL.
        """
        with self._lock:
            effective_url = self._setup_proxy_for_startup(proxy_config)

            if self.is_running():
                from core.utils import call_aria2_rpc
                try:
                    call_aria2_rpc(
                        "aria2.changeGlobalOption",
                        [{"all-proxy": effective_url}],
                        port=self._port,
                        token=self._token,
                    )
                    logger.info("[Aria2DaemonManager] Dynamically updated Aria2 all-proxy to '%s'", effective_url)
                except Exception as e:
                    logger.warning("[Aria2DaemonManager] Failed to apply proxy dynamically via RPC: %s", e)

            return effective_url

    def stop(self, timeout_sec: float = 2.0) -> bool:
        """
        Gracefully terminates the aria2 daemon process via JSON-RPC shutdown,
        falling back to SIGTERM and SIGKILL if unresponsive.
        Also terminates any active local HTTP-to-SOCKS bridge.
        """
        with self._lock:
            if self._socks_bridge_runner:
                try:
                    self._socks_bridge_runner.stop()
                except Exception:
                    pass
                self._socks_bridge_runner = None

            proc = self._process
            self._process = None

            if not proc:
                return True

            # 1. Graceful RPC shutdown
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": "shutdown",
                    "method": "aria2.shutdown",
                    "params": [f"token:{self._token}"] if self._token else [],
                }
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self._port}/jsonrpc",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=min(0.8, timeout_sec))
            except Exception:
                pass

            # 2. Wait for graceful exit
            try:
                proc.wait(timeout=min(1.0, timeout_sec / 2.0))
                self.status_changed.emit(False, "Stopped")
                self.stopped.emit()
                return True
            except Exception:
                pass

            # 3. Escalated termination
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
                self.status_changed.emit(False, "Stopped")
                self.stopped.emit()
                return True
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=0.3)
                except Exception:
                    pass

            self.status_changed.emit(False, "Stopped")
            self.stopped.emit()
            return True

    def restart(
        self,
        port: Optional[int] = None,
        token: Optional[str] = None,
        max_connections: Optional[int] = None,
    ) -> bool:
        """Stops any existing daemon and launches a fresh instance."""
        return self.start(port=port, token=token, max_connections=max_connections)


# Module-level singleton helper
_GLOBAL_ARIA2_DAEMON: Optional[Aria2DaemonManager] = None


def get_aria2_daemon_manager() -> Aria2DaemonManager:
    """Provides a shared application-wide Aria2DaemonManager instance."""
    global _GLOBAL_ARIA2_DAEMON
    if _GLOBAL_ARIA2_DAEMON is None:
        _GLOBAL_ARIA2_DAEMON = Aria2DaemonManager()
    return _GLOBAL_ARIA2_DAEMON
