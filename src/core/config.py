import os
import json
from .utils import get_config_dir

DEFAULT_CATEGORIES = {
    "General": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads"),
        "extensions": ""
    },
    "Compressed": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Compressed"),
        "extensions": "zip rar 7z tar gz iso"
    },
    "Documents": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Documents"),
        "extensions": "pdf doc docx txt ppt pptx xls xlsx"
    },
    "Music": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Music"),
        "extensions": "mp3 wav aac flac ogg"
    },
    "Programs": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Programs"),
        "extensions": "exe msi sh bin deb bat"
    },
    "Video": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Video"),
        "extensions": "mp4 mkv avi mov wmv flv"
    }
}

def load_category_config():
    path = os.path.join(get_config_dir(), "categories.json")
    data = {"categories": DEFAULT_CATEGORIES, "temp_dir": os.path.join(os.path.expanduser("~"), ".cache", "bengal-dm")}
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
