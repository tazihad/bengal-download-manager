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

def get_cache_dir():
    home = os.path.expanduser("~")
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(home, '.cache')
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
        "token": "",
        "max_connections": 8
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

def get_system_arch():
    """Returns normalized architecture name: x86_64, aarch64, etc."""
    raw = platform.machine().lower()
    if raw in ["x86_64", "amd64"]:
        return "x86_64"
    elif raw in ["aarch64", "arm64"]:
        return "aarch64"
    elif raw in ["i386", "i686"]:
        return "i686"
    return raw

def find_aria2():
    """
    Non-blocking check for aria2c binary.
    Prioritizes bundled embedded binaries, Flatpak sandbox paths, and local assets before falling back to system PATH.
    """
    arch = get_system_arch()
    
    # 1. PyInstaller bundled location (sys._MEIPASS)
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        for candidate in [
            os.path.join(meipass, "assets", "bin", arch, "aria2c"),
            os.path.join(meipass, "assets", "bin", "aria2c"),
            os.path.join(meipass, "bin", "aria2c")
        ]:
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate

    # 2. Flatpak sandbox location
    for candidate in [
        "/app/bin/aria2c",
        f"/app/share/bengal-download-manager/assets/bin/{arch}/aria2c"
    ]:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # 3. Source repository / local asset directory
    # __file__ is src/core/utils.py -> root_dir is repo root
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(src_dir)
    for candidate in [
        os.path.join(root_dir, "assets", "bin", arch, "aria2c"),
        os.path.join(root_dir, "assets", "bin", "aria2c"),
        os.path.join(src_dir, "assets", "bin", arch, "aria2c")
    ]:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # 4. System PATH
    system_aria2 = shutil.which("aria2c")
    if system_aria2:
        return system_aria2

    # 5. Application data directory / local user bin
    data_dir = get_data_dir()
    for candidate in [
        os.path.join(data_dir, "bin", "aria2c"),
        os.path.expanduser("~/.local/bin/aria2c")
    ]:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None

def ensure_aria2():
    found = find_aria2()
    if found:
        return found
    
    data_dir = get_data_dir()
    bin_dir = os.path.join(data_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    local_aria2 = os.path.join(bin_dir, "aria2c")
    
    try:
        arch = get_system_arch()
        if arch == "x86_64":
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-linux-musl_static.zip"
        elif arch == "aarch64":
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-aarch64-linux-musl_static.zip"
        elif arch == "i686":
            url = "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-i686-linux-musl_static.zip"
        else: return None
            
        temp_file = os.path.join(data_dir, "aria2.zip")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            with open(temp_file, "wb") as out:
                out.write(resp.read())
        
        import zipfile
        with zipfile.ZipFile(temp_file, "r") as z:
            for name in z.namelist():
                if name.endswith("aria2c"):
                    data = z.read(name)
                    with open(local_aria2, "wb") as out:
                        out.write(data)
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
    except Exception:
        return None

def get_clean_env():
    """
    Returns a copy of the environment with Qt-specific paths removed.
    Prevents child processes from using bundled libraries.
    """
    clean_env = os.environ.copy()
    keys_to_clear = [
        "LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
        "PYTHONHOME", "PYTHONPATH"
    ]
    for key in keys_to_clear:
        clean_env.pop(key, None)
    return clean_env

def open_file_generic(path):
    """
    Robustly opens a file or directory using the OS default application.
    On Linux, clears environment variables to ensure child processes use system libraries.
    """
    if not path or not os.path.exists(path):
        return False

    path = os.path.abspath(path)
    clean_env = get_clean_env()

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
    Uses XDG Desktop Portal OpenFile method via gdbus with stdin file descriptor redirection
    to force the modern native XDG Desktop Portal App Picker dialog.
    """
    if not path or not os.path.exists(path):
        return False

    path = os.path.abspath(path)
    clean_env = get_clean_env()

    # Windows
    if platform.system() == 'Windows':
        subprocess.Popen(['rundll32.exe', 'shell32.dll,OpenAs_RunDLL', os.path.normpath(path)])
        return True

    # macOS
    if platform.system() == 'Darwin':
        subprocess.Popen(['open', path], env=clean_env)
        return True

    # Linux / Unix
    # 1. Primary Method: XDG Desktop Portal OpenFile via gdbus with stdin file descriptor redirection (forces native XDG portal file picker)
    if shutil.which("gdbus"):
        try:
            cmd = [
                "gdbus", "call", "--session", 
                "--dest", "org.freedesktop.portal.Desktop", 
                "--object-path", "/org/freedesktop/portal/desktop", 
                "--method", "org.freedesktop.portal.OpenURI.OpenFile", 
                "", "0", '{"ask": <true>}'
            ]
            with open(path, "rb") as f:
                res = subprocess.run(cmd, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
                if res.returncode == 0:
                    return True
        except Exception:
            pass

    # 2. Fallback: XDG Desktop Portal OpenURI via gdbus
    from PyQt6.QtCore import QUrl
    uri = QUrl.fromLocalFile(path).toString()
    if shutil.which("gdbus"):
        try:
            cmd = [
                "gdbus", "call", "--session", 
                "--dest", "org.freedesktop.portal.Desktop", 
                "--object-path", "/org/freedesktop/portal/desktop", 
                "--method", "org.freedesktop.portal.OpenURI.OpenURI", 
                "", uri, "{'ask': <true>}"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 2. Try XDG Desktop Portal via dbus-send fallback
    if shutil.which("dbus-send"):
        try:
            cmd = [
                "dbus-send", "--session", "--print-reply",
                "--dest=org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.OpenURI.OpenURI",
                "string:", f"string:{uri}", "dict:string:variant:ask,boolean:true"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 3. Try xdg-open / mimeopen fallback
    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(['xdg-open', path], env=clean_env)
            return True
        except Exception:
            pass

    if shutil.which("mimeopen"):
        try:
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("konsole")
            if term:
                subprocess.Popen([term, "-e", f"mimeopen -d '{path}'"], env=clean_env)
            else:
                subprocess.Popen(["mimeopen", "-d", path], env=clean_env)
            return True
        except Exception:
            pass

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

    clean_env = get_clean_env()

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
        win_path = os.path.normpath(path)
        subprocess.Popen(['explorer.exe', '/select,', win_path]) 

    elif platform.system() == 'Darwin':
        subprocess.Popen(['open', '-R', path], env=clean_env)

    else:
        # Linux / Unix
        try:
            proc = subprocess.Popen(['xdg-mime', 'query', 'default', 'inode/directory'], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
            output, _ = proc.communicate()
            output = output.strip().lower()
            
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
                parent = os.path.dirname(path)
                subprocess.Popen(['xdg-open', parent], env=clean_env)
        except Exception:
            parent = os.path.dirname(path)
            subprocess.Popen(['xdg-open', parent], env=clean_env)

def choose_portal_save_path(title="Save File As", filename="file", folder=""):
    """
    Triggers XDG Desktop Portal FileChooser.SaveFile via DBus to open the native XDG Portal File Picker.
    Returns the chosen destination file path string, "" if user cancelled, or None if portal unavailable.
    """
    # 1. Primary Method: Native QtDBus (QDBusConnection)
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        from PyQt6.QtCore import QByteArray, QEventLoop, QObject, pyqtSlot

        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            msg = QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.FileChooser",
                "SaveFile"
            )

            options = {"current_name": filename}
            if folder and os.path.exists(folder):
                abs_folder = os.path.abspath(folder)
                options["current_folder"] = QByteArray(abs_folder.encode('utf-8'))

            msg.setArguments(["", title, options])
            reply = bus.call(msg)

            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                request_handle = reply.arguments()[0]
                chosen_path = ""
                loop = QEventLoop()

                class PortalReceiver(QObject):
                    @pyqtSlot(QDBusMessage)
                    def on_response(self, response_msg):
                        nonlocal chosen_path
                        args = response_msg.arguments()
                        if len(args) >= 2 and args[0] == 0:
                            results = args[1]
                            if isinstance(results, dict) and "uris" in results:
                                uris = results["uris"]
                                if uris:
                                    target_uri = uris[0]
                                    chosen_path = unquote(urlparse(target_uri).path)
                        loop.quit()

                receiver = PortalReceiver()
                connected = bus.connect(
                    "org.freedesktop.portal.Desktop",
                    request_handle,
                    "org.freedesktop.portal.Request",
                    "Response",
                    receiver.on_response
                )
                if connected:
                    loop.exec()
                    bus.disconnect(
                        "org.freedesktop.portal.Desktop",
                        request_handle,
                        "org.freedesktop.portal.Request",
                        "Response",
                        receiver.on_response
                    )
                    return chosen_path
    except Exception:
        pass

    # 2. Fallback: gdbus command-line tool
    if not shutil.which("gdbus"):
        return None

    clean_env = get_clean_env()

    options = f'{{"current_name": <"{filename}">}}'
    if folder and os.path.exists(folder):
        abs_folder = os.path.abspath(folder)
        options = f'{{"current_name": <"{filename}">, "current_folder": <@ay b"{abs_folder}\\0">}}'

    cmd = [
        'gdbus', 'call', '--session',
        '--dest', 'org.freedesktop.portal.Desktop',
        '--object-path', '/org/freedesktop/portal/desktop',
        '--method', 'org.freedesktop.portal.FileChooser.SaveFile',
        '', title, options
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
        match = re.search(r"'/org/freedesktop/portal/desktop/request/[^']+'", res.stdout)
        if not match:
            return None
        req_path = match.group(0).strip("'")
    except Exception:
        return None

    try:
        monitor_cmd = ['gdbus', 'monitor', '--session', '--dest', 'org.freedesktop.portal.Desktop', '--object-path', req_path]
        if shutil.which("stdbuf"):
            monitor_cmd = ['stdbuf', '-oL'] + monitor_cmd

        monitor = subprocess.Popen(
            monitor_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=clean_env
        )

        chosen_path = ""
        start_time = time.time()
        accumulated = ""
        reading_response = False

        while time.time() - start_time < 300: # Wait up to 5 minutes
            line = monitor.stdout.readline()
            if not line:
                break
            if "Response" in line or reading_response:
                reading_response = True
                accumulated += " " + line.strip()
                if "file://" in accumulated:
                    uri_match = re.search(r"file://[^\s'\">\]]+", accumulated)
                    if uri_match:
                        raw_uri = uri_match.group(0)
                        chosen_path = unquote(urlparse(raw_uri).path)
                    break
                if ")" in line and "Response" not in line:
                    break

        try:
            monitor.kill()
        except Exception:
            pass

        return chosen_path
    except Exception:
        return None

def choose_portal_folder_path(title="Select Directory", folder=""):
    """
    Triggers XDG Desktop Portal FileChooser.OpenFile with directory=true via DBus to open native XDG Portal Directory Picker.
    Returns the chosen folder path string, "" if user cancelled, or None if portal unavailable.
    """
    # 1. Primary Method: Native QtDBus (QDBusConnection)
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        from PyQt6.QtCore import QByteArray, QEventLoop, QObject, pyqtSlot

        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            msg = QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.FileChooser",
                "OpenFile"
            )

            options = {"directory": True}
            if folder and os.path.exists(folder):
                abs_folder = os.path.abspath(folder)
                options["current_folder"] = QByteArray(abs_folder.encode('utf-8'))

            msg.setArguments(["", title, options])
            reply = bus.call(msg)

            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                request_handle = reply.arguments()[0]
                chosen_path = ""
                loop = QEventLoop()

                class PortalReceiver(QObject):
                    @pyqtSlot(QDBusMessage)
                    def on_response(self, response_msg):
                        nonlocal chosen_path
                        args = response_msg.arguments()
                        if len(args) >= 2 and args[0] == 0:
                            results = args[1]
                            if isinstance(results, dict) and "uris" in results:
                                uris = results["uris"]
                                if uris:
                                    target_uri = uris[0]
                                    chosen_path = unquote(urlparse(target_uri).path)
                        loop.quit()

                receiver = PortalReceiver()
                connected = bus.connect(
                    "org.freedesktop.portal.Desktop",
                    request_handle,
                    "org.freedesktop.portal.Request",
                    "Response",
                    receiver.on_response
                )
                if connected:
                    loop.exec()
                    bus.disconnect(
                        "org.freedesktop.portal.Desktop",
                        request_handle,
                        "org.freedesktop.portal.Request",
                        "Response",
                        receiver.on_response
                    )
                    return chosen_path
    except Exception:
        pass

    # 2. Fallback: gdbus command-line tool
    if not shutil.which("gdbus"):
        return None

    clean_env = get_clean_env()

    options = '{"directory": <true>}'
    if folder and os.path.exists(folder):
        abs_folder = os.path.abspath(folder)
        options = f'{{"directory": <true>, "current_folder": <@ay b"{abs_folder}\\0">}}'

    cmd = [
        'gdbus', 'call', '--session',
        '--dest', 'org.freedesktop.portal.Desktop',
        '--object-path', '/org/freedesktop/portal/desktop',
        '--method', 'org.freedesktop.portal.FileChooser.OpenFile',
        '', title, options
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env)
        match = re.search(r"'/org/freedesktop/portal/desktop/request/[^']+'", res.stdout)
        if not match:
            return None
        req_path = match.group(0).strip("'")
    except Exception:
        return None

    try:
        monitor_cmd = ['gdbus', 'monitor', '--session', '--dest', 'org.freedesktop.portal.Desktop', '--object-path', req_path]
        if shutil.which("stdbuf"):
            monitor_cmd = ['stdbuf', '-oL'] + monitor_cmd

        monitor = subprocess.Popen(
            monitor_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=clean_env
        )

        chosen_path = ""
        start_time = time.time()
        accumulated = ""
        reading_response = False

        while time.time() - start_time < 300: # Wait up to 5 minutes
            line = monitor.stdout.readline()
            if not line:
                break
            if "Response" in line or reading_response:
                reading_response = True
                accumulated += " " + line.strip()
                if "file://" in accumulated:
                    uri_match = re.search(r"file://[^\s'\">\]]+", accumulated)
                    if uri_match:
                        raw_uri = uri_match.group(0)
                        chosen_path = unquote(urlparse(raw_uri).path)
                    break
                if ")" in line and "Response" not in line:
                    break

        try:
            monitor.kill()
        except Exception:
            pass

        return chosen_path
    except Exception:
        return None
