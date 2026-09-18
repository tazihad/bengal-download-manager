"""
Categories Domain Module for Bengal Download Manager.
Handles file categorization based on extensions, parsing byte sizes,
and formatting temporal download indicators.
"""

import os
import time
from typing import Dict, List, Optional


CATEGORY_EXTENSIONS: Dict[str, List[str]] = {
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt"],
    "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"],
    "Programs": [".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"]
}


def get_category_for_filename(filename: str) -> str:
    """Classifies a filename into a standard media category based on file extension."""
    if not filename:
        return "General"
    fn = filename.lower()
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if any(fn.endswith(ext) for ext in exts):
            return cat
    return "General"


def get_all_categories() -> List[str]:
    """Returns all supported category names."""
    return list(CATEGORY_EXTENSIONS.keys())


def parse_size_to_bytes(text: str) -> float:
    """Parses a formatted size string (e.g. '12.5 MB') to a numeric float in bytes."""
    try:
        if not text or text == "...":
            return 0.0
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else ""
        multipliers = {
            'B': 1,
            'K': 1024,
            'KB': 1024,
            'M': 1024**2,
            'MB': 1024**2,
            'G': 1024**3,
            'GB': 1024**3,
        }
        for key, mult in multipliers.items():
            if unit.startswith(key):
                return val * mult
        return val
    except Exception:
        return 0.0


def parse_time_to_sec(text: str) -> float:
    """Parses a duration string (e.g. '01:23:45' or '1 hr 20 min') to total seconds."""
    try:
        if not text or text in ["...", "--", "Unknown", "?"]:
            return 0.0
        text = text.strip()
        if ":" in text:
            colon_parts = text.split(":")
            if len(colon_parts) == 3:
                return float(int(colon_parts[0]) * 3600 + int(colon_parts[1]) * 60 + int(colon_parts[2]))
            elif len(colon_parts) == 2:
                return float(int(colon_parts[0]) * 60 + int(colon_parts[1]))
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].lower() if len(parts) > 1 else ""
        if 'hr' in unit:
            return val * 3600.0
        if 'min' in unit:
            return val * 60.0
        return val 
    except Exception:
        return 0.0


def format_timestamp_relative(timestamp_str: str, max_relative_seconds: int = 30) -> str:
    """
    Renders an epoch timestamp string into a human-friendly format.
    Shows relative time if within max_relative_seconds, otherwise formats as date/time.
    """
    if not timestamp_str or timestamp_str == "...":
        return "..."

    try:
        timestamp_float = float(timestamp_str)
    except ValueError:
        return timestamp_str

    current_time = time.time()
    diff = current_time - timestamp_float

    if diff < 60:
        return "Just now"
    elif diff < max_relative_seconds:
        minutes_ago = int(diff // 60)
        if minutes_ago == 0:
            return "Just now"
        return f"{minutes_ago} min ago"
    else:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_float))
