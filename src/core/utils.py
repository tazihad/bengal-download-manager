import os
import sys
import json
import socket
import urllib.request
import platform
import shutil
import tarfile
import subprocess
import re
import mimetypes
from urllib.parse import urlparse, unquote

def resolve_filename(url, headers):
    """
    JDownloader-style robust filename resolution:
    1. Content-Disposition (RFC 5987 filename* > filename)
    2. URL path (last segment)
    3. Extension correction (replace .php/.asp etc. with real extension from MIME)
    4. Fallback to 'downloaded_file'
    """
    filename = None
    
    # --- 1. Content-Disposition (Highest Priority for Generic Links) ---
    cd = headers.get("Content-Disposition")
    if cd:
        # RFC 5987 filename*
        cd_match = re.search(r"filename\*=UTF-8''([^\"';]+)", cd, re.IGNORECASE)
        if not cd_match:
            # Standard filename
            cd_match = re.search(r'filename=["\']?([^"\';]+)[\"\']?', cd, re.IGNORECASE)
        
        if cd_match:
            filename = unquote(cd_match.group(1).strip())
            filename = os.path.basename(filename) # Sanitization
            # Filter out UUIDs/Hashes which JD2 also ignores if better name available
            if filename and (
                re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', filename, re.I) or
                re.match(r'^[0-9a-f]{32,64}$', filename, re.I)
            ):
                filename = None

    # --- 2. URL Path Extraction ---
    if not filename:
        try:
            # Check for location header if present (for manual redirect analysis)
            effective_url = headers.get("Location") or url
            parsed = urlparse(effective_url)
            path = unquote(parsed.path)
            # Remove trailing slashes
            path = path.rstrip('/')
            basename = os.path.basename(path)
            
            if basename and basename not in ["", "/", "."] and not (
                re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', basename, re.I) or
                re.match(r'^[0-9a-f]{32,64}$', basename, re.I) or
                basename.isdigit()
            ):
                filename = basename
        except:
            pass

    # --- 3. JDownloader-style Extension Correction ---
    # Determine the "Real" extension from Content-Type
    content_type = headers.get("Content-Type", "").split(';')[0].strip().lower()
    real_extension = None
    if content_type:
        mime_map = {
            'application/x-msdownload': '.exe',
            'application/octet-stream': '.bin',
            'application/x-executable': '.exe',
            'application/x-msdos-program': '.exe',
            'application/x-msi': '.msi',
            'application/zip': '.zip',
            'application/x-7z-compressed': '.7z',
            'application/x-rar-compressed': '.rar',
            'application/pdf': '.pdf',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'video/mp4': '.mp4',
            'audio/mpeg': '.mp3'
        }
        real_extension = mime_map.get(content_type)
        if not real_extension:
            exts = mimetypes.guess_all_extensions(content_type)
            if exts:
                # Preference list
                if '.exe' in exts: real_extension = '.exe'
                elif '.zip' in exts: real_extension = '.zip'
                elif '.jpg' in exts: real_extension = '.jpg'
                else: real_extension = exts[0]

    if not filename:
        filename = "downloaded_file"
        if real_extension:
            filename += real_extension
    else:
        # CORRECTION LOGIC:
        # If we have a filename but its extension is a script (.php, .asp) or missing, 
        # replace/append with the real one.
        script_exts = ['.php', '.asp', '.aspx', '.jsp', '.cfm', '.cgi', '.pl', '.html', '.htm']
        base, current_ext = os.path.splitext(filename)
        current_ext = current_ext.lower()
        
        if real_extension:
            if current_ext in script_exts or not current_ext:
                filename = base + real_extension
            elif current_ext == '.bin' and real_extension != '.bin':
                # .bin is often a generic fallback, prefer specific extensions
                filename = base + real_extension

    return filename

def get_unique_filepath(filepath):
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"

def get_data_dir():
    home = os.path.expanduser("~")
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
    path = os.path.join(base, 'bengal-download-manager')
    os.makedirs(path, exist_ok=True)
    return path

def get_config_dir():
    home = os.path.expanduser("~")
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    path = os.path.join(base, 'bengal-download-manager')
    os.makedirs(path, exist_ok=True)
    return path

def load_proxy_config():
    path = os.path.join(get_config_dir(), "proxy.json")
    default = {
        "mode": "no_proxy",
        "type": "http",
        "host": "",
        "port": 8080,
        "auth": False,
        "user": "",
        "password": ""
    }
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except: pass
    return default

def save_proxy_config(data):
    path = os.path.join(get_config_dir(), "proxy.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except: pass

def load_extension_config():
    path = os.path.join(get_config_dir(), "extension.json")
    default = {
        "protocol": "ws",
        "host": "localhost",
        "port": 56800,
        "token": ""
    }
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except: pass
    return default

def save_extension_config(data):
    path = os.path.join(get_config_dir(), "extension.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except: pass

def get_proxychains_bin():
    return shutil.which("proxychains4") or shutil.which("proxychains")

def generate_proxychains_config():
    proxy = load_proxy_config()
    if proxy.get("mode") != "manual" or not proxy.get("host"):
        return None
    
    config_path = os.path.join(get_config_dir(), "proxychains.conf")
    ptype = proxy.get("type", "http")
    host = proxy.get("host")
    port = proxy.get("port")
    user = proxy.get("user")
    password = proxy.get("password")
    
    # proxychains supports: http, socks4, socks5
    # Format: type host port [user pass]
    
    content = [
        "strict_chain",
        "proxy_dns",
        "quiet_mode",
        "remote_dns_subnet 224",
        "tcp_read_time_out 15000",
        "tcp_connect_time_out 8000",
        "localnet 127.0.0.0",
        "[ProxyList]"
    ]
    
    # proxychains expects 'socks4' or 'socks5' (no 'socks')
    proxy_line = f"{ptype} {host} {port}"
    if proxy.get("auth") and user and password:
        proxy_line += f" {user} {password}"
    
    content.append(proxy_line)
    
    try:
        with open(config_path, "w") as f:
            f.write("\n".join(content))
        return config_path
    except:
        return None

def call_aria2_rpc(method, params=None, port=56800, token=""):
    """
    Ultra-robust raw socket RPC caller. 
    Bypasses ALL high-level proxy handlers (urllib, requests, pysocks) by 
    writing directly to a TCP socket.
    """
    import socket
    import json
    import os

    if params is None: params = []
    rpc_params = [f"token:{token}"] + params if token else params
    
    payload_dict = {
        "jsonrpc": "2.0",
        "id": "bengal-raw",
        "method": method,
        "params": rpc_params
    }
    payload = json.dumps(payload_dict).encode('utf-8')
    
    host = "127.0.0.1"
    request = (
        f"POST /jsonrpc HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode('utf-8') + payload
    
    s = None
    try:
        # Use low-level socket to avoid high-level library proxy logic
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((host, port))
        s.sendall(request)
        
        response = b""
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk: break
                response += chunk
            except socket.timeout:
                break
        
        if not response: return None
        
        resp_str = response.decode('utf-8', errors='ignore')
        if "200 OK" in resp_str:
            body_start = resp_str.find("\r\n\r\n")
            if body_start != -1:
                body = resp_str[body_start+4:].strip()
                if body:
                    # Robust JSON detection
                    j_start = body.find('{')
                    j_end = body.rfind('}')
                    if j_start != -1 and j_end != -1:
                        return json.loads(body[j_start:j_end+1]).get("result")
        return None
    except:
        return None
    finally:
        if s:
            try: s.shutdown(socket.SHUT_RDWR); s.close()
            except: pass

def ensure_aria2():
    if shutil.which("aria2c"):
        return "aria2c"
    
    data_dir = get_data_dir()
    bin_dir = os.path.join(data_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    local_aria2 = os.path.join(bin_dir, "aria2c")
    
    if os.path.exists(local_aria2):
        return local_aria2
    
    try:
        arch = platform.machine().lower()
        if arch in ["x86_64", "amd64"]:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-64bit-build1.tar.bz2"
        elif arch in ["i386", "i686"]:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-32bit-build1.tar.bz2"
        elif "armv7" in arch:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm-el-build1.tar.bz2"
        elif "aarch64" in arch or "arm64" in arch:
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/v1.37.0/aria2-1.37.0-linux-gnu-arm64-build1.tar.bz2"
        else: return None
            
        temp_file = os.path.join(data_dir, "aria2.tar.bz2")
        urllib.request.urlretrieve(url, temp_file)
        
        with tarfile.open(temp_file, "r:bz2") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/aria2c"):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, bin_dir)
                    break
        os.remove(temp_file)
        os.chmod(local_aria2, 0o755)
        
        local_bin = os.path.expanduser("~/.local/bin")
        os.makedirs(local_bin, exist_ok=True)
        symlink_path = os.path.join(local_bin, "aria2c")
        if not os.path.exists(symlink_path):
            try: os.symlink(local_aria2, symlink_path)
            except: pass
        return local_aria2
    except:
        return None

def open_file_generic(path):
    """
    Robustly opens a file or directory using the OS default application.
    On Linux, clears environment variables to ensure child processes use system libraries.
    """
    if not path or not os.path.exists(path):
        return False

    path = os.path.abspath(path)
    
    # --- ENVIRONMENT SANITIZATION ---
    clean_env = os.environ.copy()
    keys_to_clear = [
        "LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
        "PYTHONHOME", "PYTHONPATH"
    ]
    for key in keys_to_clear:
        clean_env.pop(key, None)

    try:
        if platform.system() == 'Windows':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path], env=clean_env)
        else:
            # Linux / Unix: Use xdg-open for system-wide defaults
            subprocess.Popen(['xdg-open', path], env=clean_env)
        return True
    except Exception:
        return False

def open_with(path):
    """
    Shows the OS-native "Open With" dialog for the given path.
    Returns True if a command was successfully launched.
    """
    if not path or not os.path.exists(path):
        return False

    # Windows
    if platform.system() == 'Windows':
        subprocess.Popen(['rundll32.exe', 'shell32.dll,OpenAs_RunDLL', os.path.normpath(path)])
        return True

    # macOS
    if platform.system() == 'Darwin':
        subprocess.Popen(['open', path])
        return True

    # Linux / Unix
    abs_path = os.path.abspath(path)
    from PyQt6.QtCore import QUrl
    # Ensure URI is properly encoded and prefixed
    uri = QUrl.fromLocalFile(abs_path).toString()
    
    # --- XDG DESKTOP PORTAL: The standard for native "Open With" pickers ---
    
    # 1. Try via busctl (user session)
    if shutil.which("busctl"):
        try:
            # Syntax: parent_window uri options(dict)
            cmd = [
                "busctl", "--user", "call", 
                "org.freedesktop.portal.Desktop", 
                "/org/freedesktop/portal/desktop", 
                "org.freedesktop.portal.OpenURI", "OpenURI", 
                "ssa{sv}", "", uri, "1", "ask", "b", "true"
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except: pass

    # 2. Try via gdbus
    if shutil.which("gdbus"):
        try:
            cmd = [
                "gdbus", "call", "--session", 
                "--dest", "org.freedesktop.portal.Desktop", 
                "--object-path", "/org/freedesktop/portal/desktop", 
                "--method", "org.freedesktop.portal.OpenURI.OpenURI", 
                "", uri, "{'ask': <true>}"
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except: pass

    # 3. Try via dbus-send (older but common)
    if shutil.which("dbus-send"):
        try:
            # Note: dict syntax in dbus-send is very limited, 
            # often portals don't like it, but it's worth a shot.
            cmd = [
                "dbus-send", "--session", "--dest=org.freedesktop.portal.Desktop", 
                "/org/freedesktop/portal/desktop", 
                "org.freedesktop.portal.OpenURI.OpenURI", 
                "string:", f"string:{uri}", "dict:string:variant:ask,boolean:true"
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except: pass

    # --- FALLBACKS: If portals are broken or unavailable ---

    # 4. mimeopen -d (Allows choosing app in a terminal/launcher)
    if shutil.which("mimeopen"):
        try:
            # We try to use a terminal so the user can see the options
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("konsole")
            if term:
                subprocess.Popen([term, "-e", f"mimeopen -d '{abs_path}'"])
                return True
            else:
                subprocess.Popen(["mimeopen", "-d", abs_path])
                return True
        except: pass

    return False

def show_in_folder(path):
    """
    If path is a file, opens the folder containing it and selects (highlights) it.
    If path is a directory, just opens the directory.
    Inspired by qBittorrent's implementation.
    """
    if not path: return
    path = os.path.abspath(path)
    if not os.path.exists(path): return

    # --- ENVIRONMENT SANITIZATION ---
    # When running as a bundled app (e.g. PyInstaller), we must clear 
    # LD_LIBRARY_PATH and other Qt variables so child processes (like Dolphin) 
    # use system libraries instead of the ones bundled with this app.
    clean_env = os.environ.copy()
    keys_to_clear = [
        "LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
        "PYTHONHOME", "PYTHONPATH"
    ]
    for key in keys_to_clear:
        clean_env.pop(key, None)

    # If it's a directory, just open it normally
    if os.path.isdir(path):
        if platform.system() == 'Windows':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path], env=clean_env)
        else:
            try:
                subprocess.Popen(['xdg-open', path], env=clean_env)
            except:
                pass
        return

    # If it's a file, try to open parent and select it
    if platform.system() == 'Windows':
        # explorer.exe /select,"C:\path\to\file"
        win_path = os.path.normpath(path)
        subprocess.Popen(['explorer.exe', '/select,', win_path]) # Windows doesn't use LD_LIBRARY_PATH

    elif platform.system() == 'Darwin':
        # macOS: open -R <path>
        subprocess.Popen(['open', '-R', path], env=clean_env)

    else:
        # Linux / Unix
        try:
            # Query default file manager for directories
            proc = subprocess.Popen(['xdg-mime', 'query', 'default', 'inode/directory'], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
            output, _ = proc.communicate()
            output = output.strip().lower()
            
            # Check for known file managers that support selection flags
            if "dolphin" in output:
                subprocess.Popen(['dolphin', '--select', path], env=clean_env)
            elif "nautilus" in output:
                subprocess.Popen(['nautilus', '--no-desktop', path], env=clean_env)
            elif "caja" in output:
                subprocess.Popen(['caja', '--no-desktop', path], env=clean_env)
            elif "nemo" in output:
                subprocess.Popen(['nemo', '--no-desktop', path], env=clean_env)
            elif "konqueror" in output:
                subprocess.Popen(['konqueror', '--select', path], env=clean_env)
            else:
                # Fallback: Open parent folder with xdg-open
                parent = os.path.dirname(path)
                subprocess.Popen(['xdg-open', parent], env=clean_env)
        except Exception:
            # Fallback to xdg-open if xdg-mime or specific FM calls fail
            parent = os.path.dirname(path)
            subprocess.Popen(['xdg-open', parent], env=clean_env)
