"""
Bengal Media Downloader Subsystem
=================================
Cohesive domain package for external tool dependency resolution,
stream probing and metadata extraction, and media downloading/muxing.
"""

from core.media.dependencies import (
    APP_DATA_DIR,
    BIN_DIR,
    YT_DLP_BIN,
    DEPENDENCY_TOOLS,
    get_local_tool_path,
    get_tool_path,
    get_tool_version,
    get_ytdlp_channel,
    set_ytdlp_channel,
    get_tool_url,
    DependencyManagerWorker,
    YtDlpManager,
)
from core.media.extractor import (
    MediaExtractorWorker,
    MediaInfoFetcherWorker,
    get_format_size_bytes,
    get_selected_download_size,
    probe_media_sizes,
    _keep_thread_alive,
)
from core.media.worker import (
    create_temp_netscape_cookie_file,
    YtDlpDownloadWorker,
)
from core.media.pot_provider import (
    check_pot_provider_status,
    is_pot_provider_available,
    get_pot_extractor_args,
    DEFAULT_POT_PROVIDER_URL,
)
import re

def parse_size_str_to_bytes(size_str: str) -> float:
    """Helper to convert sizes like '12.50MiB', '1.5GB' or '500KiB' to bytes."""
    if not size_str or not isinstance(size_str, str):
        return 0.0
    s = size_str.strip().lstrip("~").strip().upper()
    units = {
        "KIB": 1024, "KB": 1000,
        "MIB": 1024**2, "MB": 1000**2,
        "GIB": 1024**3, "GB": 1000**3,
        "B": 1
    }
    for u, factor in units.items():
        if s.endswith(u):
            try:
                num = float(s[:-len(u)].strip())
                return float(num * factor)
            except ValueError:
                pass
    try:
        clean = re.sub(r"[^\d.]", "", s)
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0


__all__ = [
    "APP_DATA_DIR",
    "BIN_DIR",
    "YT_DLP_BIN",
    "DEPENDENCY_TOOLS",
    "get_local_tool_path",
    "get_tool_path",
    "get_tool_version",
    "get_ytdlp_channel",
    "set_ytdlp_channel",
    "get_tool_url",
    "DependencyManagerWorker",
    "YtDlpManager",
    "MediaExtractorWorker",
    "MediaInfoFetcherWorker",
    "get_format_size_bytes",
    "get_selected_download_size",
    "probe_media_sizes",
    "_keep_thread_alive",
    "create_temp_netscape_cookie_file",
    "YtDlpDownloadWorker",
    "parse_size_str_to_bytes",
    "check_pot_provider_status",
    "is_pot_provider_available",
    "get_pot_extractor_args",
    "DEFAULT_POT_PROVIDER_URL",
]
