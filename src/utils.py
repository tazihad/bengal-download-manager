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

def ensure_aria2():
    """
    Checks for aria2c. If missing, downloads a static build for the current architecture
    and installs it to ~/.local/share/bengal-download-manager/bin/.
    """
    import shutil
    import platform
    import subprocess
    import urllib.request
    import tarfile
    
    # 1. Check if aria2c is already in PATH
    if shutil.which("aria2c"):
        return "aria2c"
    
    # 2. Check in our local bin
    data_dir = get_data_dir()
    bin_dir = os.path.join(data_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    local_aria2 = os.path.join(bin_dir, "aria2c")
    
    if os.path.exists(local_aria2):
        return local_aria2
    
    # 3. Download if missing
    try:
        arch = platform.machine().lower()
        # Mapping architectures to abcfy2/aria2-static-build release patterns
        if arch in ["x86_64", "amd64"]:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-64bit-build1.tar.bz2"
        elif arch in ["i386", "i686"]:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-32bit-build1.tar.bz2"
        elif "armv7" in arch:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm-el-build1.tar.bz2"
        elif "aarch64" in arch or "arm64" in arch:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm64-build1.tar.bz2"
        else:
            return None # Unsupported arch
            
        temp_file = os.path.join(data_dir, "aria2.tar.bz2")
        urllib.request.urlretrieve(url, temp_file)
        
        # Extract
        with tarfile.open(temp_file, "r:bz2") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/aria2c"):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, bin_dir)
                    break
        
        os.remove(temp_file)
        os.chmod(local_aria2, 0o755)
        
        # Symlink to ~/.local/bin/
        local_bin = os.path.expanduser("~/.local/bin")
        os.makedirs(local_bin, exist_ok=True)
        symlink_path = os.path.join(local_bin, "aria2c")
        if not os.path.exists(symlink_path):
            try:
                os.symlink(local_aria2, symlink_path)
            except:
                pass
                    
        return local_aria2
    except Exception:
        return None