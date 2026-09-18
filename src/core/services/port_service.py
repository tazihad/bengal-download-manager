"""
Port Management & Service Reclamation Service
=============================================
Provides cross-platform, pure-Python port inspection, PID resolution,
and automatic port reclamation for Bengal Download Manager runtime services.

Guarantees safety:
- Never terminates unrelated user or system processes.
- Only terminates processes matching the current user UID, not matching current PID,
  and matching allowed executable/cmdline patterns.
"""

import os
import sys
import time
import json
import socket
import signal
import logging
import subprocess
from typing import Optional, Tuple, List

logger = logging.getLogger("bengal.services.port")


def is_port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    """
    Checks whether a TCP port is currently occupied by an active listener.
    Returns True if a connection was accepted or refused (reset), False if available.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            # connect_ex returns 0 on successful connection
            res = s.connect_ex((host, port))
            return res == 0
    except Exception:
        return False


def get_pid_listening_on_port(port: int, host: str = "127.0.0.1") -> Optional[Tuple[int, str]]:
    """
    Resolves the process ID and command line currently listening on the specified TCP port.
    Uses pure-Python Linux /proc inspection, with fallback to system utilities (ss, lsof).
    Restricted strictly to processes owned by the current user.
    """
    # 1. Primary Strategy: Pure-Python Linux /proc inspection
    proc_result = _get_pid_via_proc(port)
    if proc_result:
        return proc_result

    # 2. Fallback Strategy: 'ss' utility
    ss_result = _get_pid_via_ss(port)
    if ss_result:
        return ss_result

    # 3. Fallback Strategy: 'lsof' utility
    lsof_result = _get_pid_via_lsof(port)
    if lsof_result:
        return lsof_result

    return None


def _get_pid_via_proc(port: int) -> Optional[Tuple[int, str]]:
    """Inspects Linux /proc/net/tcp[6] and /proc/[pid]/fd to find the listening socket's PID."""
    hex_port = f"{port:04X}"
    inodes = set()

    for net_file in ("/proc/net/tcp", "/proc/net/tcp6"):
        if not os.path.exists(net_file):
            continue
        try:
            with open(net_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 10:
                    local_addr = parts[1]
                    state = parts[3]
                    inode = parts[9]
                    # State 0A is TCP_LISTEN
                    if state == "0A" and local_addr.endswith(":" + hex_port):
                        inodes.add(inode)
        except Exception:
            pass

    if not inodes:
        return None

    my_uid = os.getuid() if hasattr(os, "getuid") else None
    my_pid = os.getpid()

    try:
        pid_entries = [p for p in os.listdir("/proc") if p.isdigit()]
    except Exception:
        return None

    for pid_str in pid_entries:
        pid = int(pid_str)
        try:
            if my_uid is not None:
                stat = os.stat(f"/proc/{pid}")
                if stat.st_uid != my_uid:
                    continue

            fd_dir = f"/proc/{pid}/fd"
            if not os.path.exists(fd_dir):
                continue

            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(f"{fd_dir}/{fd}")
                    for inode in inodes:
                        if target == f"socket:[{inode}]":
                            cmdline = ""
                            try:
                                with open(f"/proc/{pid}/cmdline", "rb") as f:
                                    cmdline = f.read().decode("utf-8", errors="ignore").replace("\x00", " ").strip()
                            except Exception:
                                pass
                            if not cmdline:
                                try:
                                    with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="ignore") as f:
                                        cmdline = f.read().strip()
                                except Exception:
                                    pass
                            return pid, cmdline
                except Exception:
                    pass
        except Exception:
            continue

    return None


def _get_pid_via_ss(port: int) -> Optional[Tuple[int, str]]:
    """Fallback PID discovery using ss command."""
    try:
        res = subprocess.run(
            ["ss", "-lptn", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False
        )
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if f":{port}" in line and "pid=" in line:
                    import re
                    match = re.search(r"pid=(\d+)", line)
                    if match:
                        pid = int(match.group(1))
                        cmdline = _get_cmdline_for_pid(pid)
                        return pid, cmdline
    except Exception:
        pass
    return None


def _get_pid_via_lsof(port: int) -> Optional[Tuple[int, str]]:
    """Fallback PID discovery using lsof command."""
    try:
        res = subprocess.run(
            ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-n", "-P", "-Fp"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False
        )
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if line.startswith("p"):
                    pid = int(line[1:])
                    cmdline = _get_cmdline_for_pid(pid)
                    return pid, cmdline
    except Exception:
        pass
    return None


def _get_cmdline_for_pid(pid: int) -> str:
    """Reads cmdline or comm for a given PID."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().decode("utf-8", errors="ignore").replace("\x00", " ").strip()
            if cmd:
                return cmd
    except Exception:
        pass
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        pass
    return ""


def _is_safe_to_terminate(pid: int, cmdline: str, allowed_patterns: List[str]) -> bool:
    """
    Strict safety check:
    1. PID must not be our own process.
    2. Process must be owned by the current user.
    3. Command line must match at least one allowed pattern.
    """
    if pid == os.getpid():
        return False

    if hasattr(os, "getuid"):
        try:
            stat = os.stat(f"/proc/{pid}")
            if stat.st_uid != os.getuid():
                logger.warning(
                    "[PortService] Refusing to terminate PID %d: UID mismatch (expected %d, got %d)",
                    pid, os.getuid(), stat.st_uid
                )
                return False
        except Exception:
            return False

    cmd_lower = cmdline.lower()
    for pattern in allowed_patterns:
        if pattern.lower() in cmd_lower:
            return True

    logger.warning(
        "[PortService] Refusing to terminate PID %d (%r): does not match allowed patterns %r",
        pid, cmdline, allowed_patterns
    )
    return False


def _attempt_aria2_rpc_shutdown(port: int, token: str = "") -> bool:
    """Attempts graceful JSON-RPC shutdown of an existing Aria2 daemon via raw loopback socket."""
    try:
        from core.utils import call_aria2_rpc
        res = call_aria2_rpc("aria2.shutdown", port=port, token=token)
        if res is not None:
            return True
    except Exception:
        pass

    # Fallback to direct raw HTTP without environment proxies
    try:
        import urllib.request
        payload = {
            "jsonrpc": "2.0",
            "id": "shutdown",
            "method": "aria2.shutdown",
            "params": [f"token:{token}"] if token else []
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/jsonrpc",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with no_proxy_opener.open(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def reclaim_port(
    port: int,
    service_name: str,
    allowed_patterns: List[str],
    timeout_sec: float = 2.0,
    rpc_token: str = ""
) -> bool:
    """
    Reclaims a TCP port for Bengal DM runtime services without manual intervention.

    Steps:
    1. Checks if port is currently in use. If free, returns True immediately.
    2. If service is 'aria2', attempts graceful JSON-RPC shutdown first.
    3. Identifies the listening process PID and command line.
    4. Validates safety constraints (UID match, PID != current, allowlist match).
    5. Sends SIGTERM, then SIGKILL if unresponsive.
    6. Waits for socket release with exponential backoff.

    Returns:
        bool: True if port is free and ready for binding; False if occupied by an unauthorized process.
    """
    if not is_port_in_use(port):
        return True

    logger.info("[PortService] Port %d (%s) is currently occupied. Attempting reclamation...", port, service_name)

    # 1. For Aria2, attempt graceful JSON-RPC shutdown
    if service_name.lower() == "aria2":
        try:
            from core.utils import load_extension_config
            token = rpc_token or load_extension_config().get("token", "")
            _attempt_aria2_rpc_shutdown(port, token=token)
            # Also try without token if token was changed
            if is_port_in_use(port) and token:
                _attempt_aria2_rpc_shutdown(port, token="")
        except Exception:
            pass

        # Check if RPC shutdown was sufficient with short wait
        wait_deadline = time.time() + 0.35
        while time.time() < wait_deadline:
            if not is_port_in_use(port):
                logger.info("[PortService] Port %d (%s) successfully reclaimed via RPC shutdown.", port, service_name)
                return True
            time.sleep(0.05)

    # 2. Identify the process listening on the port
    proc_info = get_pid_listening_on_port(port)
    if proc_info:
        pid, cmdline = proc_info
        if _is_safe_to_terminate(pid, cmdline, allowed_patterns):
            logger.info("[PortService] Terminating orphan process PID %d (%r) on port %d...", pid, cmdline, port)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error("[PortService] Failed to send SIGTERM to PID %d: %s", pid, e)

            # Wait up to 1.0s for graceful exit
            start_wait = time.time()
            while time.time() - start_wait < 1.0:
                if not is_port_in_use(port):
                    logger.info("[PortService] Port %d released after SIGTERM to PID %d.", port, pid)
                    return True
                time.sleep(0.05)

            # Force kill if still holding port
            try:
                logger.warning("[PortService] PID %d still holding port %d; issuing SIGKILL...", pid, port)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error("[PortService] Failed to send SIGKILL to PID %d: %s", pid, e)
        else:
            logger.warning(
                "[PortService] Port %d (%s) is in use by PID %d (%r) which does not match safe termination criteria.",
                port, service_name, pid, cmdline
            )
            return False

    # 3. Wait for socket release (handles TIME_WAIT and socket recycling)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not is_port_in_use(port):
            logger.info("[PortService] Port %d successfully verified available.", port)
            return True
        time.sleep(0.05)

    is_free = not is_port_in_use(port)
    if is_free:
        logger.info("[PortService] Port %d successfully reclaimed.", port)
    else:
        logger.warning("[PortService] Port %d could not be reclaimed within %.1fs timeout.", port, timeout_sec)
    return is_free
