"""
Media Downloader Core Engine for Bengal Download Manager (Adapter Facade).
==========================================================================
Re-exports modularized media components from core.media package for 100%
backwards compatibility across legacy callers and UI dialogs.
"""

import subprocess
from core.config import load_category_config
from core.utils import get_clean_env, get_cache_dir, get_data_dir

from core.media import (
    APP_DATA_DIR,
    BIN_DIR,
    YT_DLP_BIN,
    DEPENDENCY_TOOLS,
    get_local_tool_path,
    get_tool_path,
    get_tool_version,
    DependencyManagerWorker,
    YtDlpManager,
    MediaExtractorWorker,
    _keep_thread_alive,
    create_temp_netscape_cookie_file,
    YtDlpDownloadWorker,
    parse_size_str_to_bytes,
)

__all__ = [
    "APP_DATA_DIR",
    "BIN_DIR",
    "YT_DLP_BIN",
    "DEPENDENCY_TOOLS",
    "get_local_tool_path",
    "get_tool_path",
    "get_tool_version",
    "DependencyManagerWorker",
    "YtDlpManager",
    "MediaExtractorWorker",
    "_keep_thread_alive",
    "create_temp_netscape_cookie_file",
    "YtDlpDownloadWorker",
    "parse_size_str_to_bytes",
    "subprocess",
    "load_category_config",
    "get_clean_env",
]
