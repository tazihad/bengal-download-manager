import os
import json
from .utils import get_config_dir, get_cache_dir

DEFAULT_CATEGORIES = {
    "General": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads"),
        "extensions": "plj"
    },
    "Compressed": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Compressed"),
        "extensions": "7z ace arj bz2 gz gzip lzh rar sea sit sitx tar zip xz bz bz2 lzma war ear"
    },
    "Documents": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Documents"),
        "extensions": "pdf pps ppt doc docx xls xlsx pptx odt ods odp rtf csv ppsx"
    },
    "Music": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Music"),
        "extensions": "aac aif m4a mp3 mpa ogg wav wma"
    },
    "Programs": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Programs"),
        "extensions": "exe msi msu bin deb rpm appimage"
    },
    "Video": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Video"),
        "extensions": "3gp asf avi m4v mkv mov mp4 mpe mpeg mpg ogv rmvb wmv"
    },
    "Disk Images": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Images"),
        "extensions": "img iso"
    },
    "Images": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Pictures"),
        "extensions": "tif tiff"
    }
}

def load_category_config():
    path = os.path.join(get_config_dir(), "categories.json")
    data = {"categories": DEFAULT_CATEGORIES, "temp_dir": os.path.join(get_cache_dir(), "downloads")}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
                for cat, defaults in DEFAULT_CATEGORIES.items():
                    if cat not in loaded["categories"]:
                        loaded["categories"][cat] = defaults
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
