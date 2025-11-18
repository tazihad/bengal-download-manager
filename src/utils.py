import os
import sys

def get_unique_filepath(filepath):
    """
    Ensures a filename is unique by appending (1), (2), etc. if it already exists.
    """
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"

def get_data_dir():
    """
    Returns the XDG Data Home directory for the application.
    Defaults to ~/.local/share/bengal-download-manager on Linux/Unix.
    """
    home = os.path.expanduser("~")
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
    path = os.path.join(base, 'bengal-download-manager')
    os.makedirs(path, exist_ok=True)
    return path

def get_config_dir():
    """
    Returns the XDG Config Home directory for the application.
    Defaults to ~/.config/bengal-download-manager on Linux/Unix.
    """
    home = os.path.expanduser("~")
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    path = os.path.join(base, 'bengal-download-manager')
    os.makedirs(path, exist_ok=True)
    return path