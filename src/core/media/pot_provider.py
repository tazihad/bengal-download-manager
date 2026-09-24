"""
YouTube Proof-of-Origin (PO) Token Provider Module
==================================================
Handles automatic integration with bgutil-ytdlp-pot-provider and YouTube Botguard/PO token generation
using the Deno JS runtime from Bengal DM Media Tools or system Node.js.
Bypasses YouTube bot detection, 403 Forbidden errors, and streaming throttling seamlessly.
"""

import os
import shutil
import logging
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Optional, List, Tuple

from core.config import load_category_config

logger = logging.getLogger("bengal.media.pot_provider")

DEFAULT_POT_PROVIDER_URL = "http://127.0.0.1:4416"
_POT_PROVIDER_CACHE = {"url": "", "available": None, "timestamp": 0}
_CACHE_TTL = 30  # Cache availability for 30 seconds


def get_deno_executable_path() -> Optional[str]:
    """
    Returns path to Deno binary from Bengal DM media download tools (BIN_DIR) or system PATH.
    Does NOT bundle Deno statically; uses the Deno tool managed by Bengal DM or system Deno.
    """
    try:
        from core.media.dependencies import get_tool_path
        local_deno = get_tool_path("deno")
        if local_deno and os.path.exists(local_deno) and os.access(local_deno, os.X_OK):
            return str(local_deno)
    except Exception:
        pass
    return shutil.which("deno")


def get_pot_env() -> dict:
    """
    Returns environment variables for yt-dlp subprocesses.
    Injects the DENO executable path so bgutil-ytdlp-pot-provider can find it without PATH dependency.
    """
    env = {}
    deno_path = get_deno_executable_path()
    if deno_path:
        env["DENO"] = str(deno_path)
    return env


def check_pot_provider_status(base_url: str = DEFAULT_POT_PROVIDER_URL, timeout: float = 1.0) -> Tuple[bool, str]:
    """
    Checks if a bgutil-ytdlp-pot-provider HTTP server is reachable and active.
    Returns: (is_available, status_message_or_version)
    """
    if not base_url or not isinstance(base_url, str):
        return False, "Invalid server URL"
    
    clean_url = base_url.strip().rstrip("/")
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"http://{clean_url}"

    ping_url = f"{clean_url}/ping"
    try:
        req = urllib.request.Request(ping_url, headers={"User-Agent": "BengalDownloadManager"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                raw = response.read().decode("utf-8", errors="ignore").strip()
                try:
                    data = json.loads(raw)
                    ver = data.get("version") or data.get("status") or "Active"
                    return True, f"Connected ({ver})"
                except Exception:
                    return True, "Connected (Active)"
    except urllib.error.URLError as e:
        return False, f"Not reachable: {e.reason}"
    except Exception as e:
        return False, f"Not reachable: {e}"

    return False, "Not reachable"


def is_pot_provider_available(base_url: str = DEFAULT_POT_PROVIDER_URL, timeout: float = 0.5) -> bool:
    """Cached check to quickly determine if local POT daemon is running without UI delay."""
    import time
    now = time.time()
    clean_url = base_url.strip().rstrip("/") if base_url else DEFAULT_POT_PROVIDER_URL
    if _POT_PROVIDER_CACHE["url"] == clean_url and now - _POT_PROVIDER_CACHE["timestamp"] < _CACHE_TTL:
        if _POT_PROVIDER_CACHE["available"] is not None:
            return _POT_PROVIDER_CACHE["available"]

    available, _ = check_pot_provider_status(clean_url, timeout=timeout)
    _POT_PROVIDER_CACHE["url"] = clean_url
    _POT_PROVIDER_CACHE["available"] = available
    _POT_PROVIDER_CACHE["timestamp"] = now
    return available


def get_pot_extractor_args(config: Optional[dict] = None) -> List[str]:
    """
    Builds the appropriate yt-dlp --extractor-args for PO token handling.
    Fully automatic:
    - If disabled in settings -> pass 'youtube:fetch_pot=never'.
    - If local bgutil HTTP daemon (127.0.0.1:4416) is active -> injects daemon base_url.
    - If Deno (from Bengal DM media tools or system) or Node is available -> bgutil generates tokens in-process automatically.
    - If NO JS runtime is available -> pass 'youtube:fetch_pot=never' to prevent silent format breakage.
    """
    if config is None:
        try:
            config = load_category_config()
        except Exception:
            config = {}

    media_defaults = config.get("media_downloader_defaults", {}) if isinstance(config, dict) else {}
    pot_enabled = media_defaults.get("youtube_pot_enabled", True)
    if not pot_enabled:
        return ["--extractor-args", "youtube:fetch_pot=never"]

    # 1. Check if local bgutil HTTP daemon is running
    if is_pot_provider_available(DEFAULT_POT_PROVIDER_URL, timeout=0.2):
        return [
            "--extractor-args", f"youtubepot-bgutilhttp:base_url={DEFAULT_POT_PROVIDER_URL}",
            "--extractor-args", f"youtubepot:base_url={DEFAULT_POT_PROVIDER_URL}",
        ]

    # 2. Check if Deno is available from Bengal DM media download tools or system
    deno_path = get_deno_executable_path()
    if deno_path:
        # bgutil plugin generates tokens in-process via Deno; no extra args needed
        return []

    # 3. Check if Node.js is available
    if shutil.which("node"):
        return []

    # 4. If no JS engine is present, disable fetch_pot to prevent format corruption
    return ["--extractor-args", "youtube:fetch_pot=never"]
