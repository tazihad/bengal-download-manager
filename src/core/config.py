import os
import re
import json
from .utils import get_config_dir, get_cache_dir, get_user_downloads_dir, get_user_home_dir

def get_default_categories():
    downloads = get_user_downloads_dir()
    return {
        "General": {
            "path": downloads,
            "extensions": "plj"
        },
        "Compressed": {
            "path": os.path.join(downloads, "Compressed"),
            "extensions": "7z ace arj bz2 gz gzip lzh rar sea sit sitx tar zip xz bz bz2 lzma war ear"
        },
        "Documents": {
            "path": os.path.join(downloads, "Documents"),
            "extensions": "pdf pps ppt doc docx xls xlsx pptx odt ods odp rtf csv ppsx dot"
        },
        "Music": {
            "path": os.path.join(downloads, "Music"),
            "extensions": "aac aif m4a mp3 mpa ogg wav wma"
        },
        "Programs": {
            "path": os.path.join(downloads, "Programs"),
            "extensions": "exe msi msu bin deb rpm appimage flatpak snap apk sh bat cmd run dmg pkg jar"
        },
        "Video": {
            "path": os.path.join(downloads, "Video"),
            "extensions": "3gp asf avi m4v mkv mov mp4 mpe mpeg mpg ogv rmvb wmv"
        },
        "Disk Images": {
            "path": os.path.join(downloads, "Images"),
            "extensions": "img iso"
        },
        "Images": {
            "path": os.path.join(downloads, "Pictures"),
            "extensions": "tif tiff"
        }
    }

DEFAULT_CATEGORIES = get_default_categories()

def _normalize_snap_path(path: str) -> str:
    """Normalize snap internal download path to real user download path if running in Snap or migrated."""
    if not path or not isinstance(path, str):
        return path

    snap_user_data = os.environ.get("SNAP_USER_DATA")
    real_home = os.environ.get("SNAP_REAL_HOME")
    if snap_user_data and real_home and path.startswith(snap_user_data):
        rel = os.path.relpath(path, snap_user_data)
        return os.path.normpath(os.path.join(real_home, rel))

    # Pattern for snap user paths: /home/<user>/snap/<snap_name>/<rev>/Downloads...
    m = re.match(r"^/home/[^/]+/snap/[^/]+/[^/]+/Downloads(/.*)?$", path)
    if m:
        downloads_base = get_user_downloads_dir()
        sub = m.group(1) or ""
        sub = sub.lstrip("/")
        return os.path.join(downloads_base, sub) if sub else downloads_base

    return path

def load_category_config():
    path = os.path.join(get_config_dir(), "categories.json")
    defaults = get_default_categories()
    data = {"categories": defaults, "temp_dir": os.path.join(get_cache_dir(), "downloads")}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
                if "categories" not in loaded or not isinstance(loaded["categories"], dict):
                    loaded["categories"] = {}
                for cat, default_val in defaults.items():
                    if cat not in loaded["categories"]:
                        loaded["categories"][cat] = default_val
                    else:
                        cat_path = loaded["categories"][cat].get("path", "")
                        loaded["categories"][cat]["path"] = _normalize_snap_path(cat_path)
                return loaded
        except:
            pass
    return data

def save_category_config(data):
    path = os.path.join(get_config_dir(), "categories.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass
