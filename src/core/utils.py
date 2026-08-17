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
import logging
from urllib.parse import urlparse, unquote

def setup_logging(debug=False):
    """
    Configures application-wide logging levels and formatting.
    When debug=True (--debug flag), enables verbose DEBUG logs with file/line context.
    """
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s" if debug else "[%(asctime)s] [%(levelname)s] %(message)s"
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )
    logger = logging.getLogger("bengal")
    logger.setLevel(log_level)
    if debug:
        logger.debug("=== BENGAL DOWNLOAD MANAGER DEBUG LOGGING ENABLED ===")
        logger.debug("Python Version: %s", sys.version)
        logger.debug("Platform: %s", platform.platform())
        logger.debug("Process PID: %d", os.getpid())
    return logger


def format_bytes(size: float, precision: int = 2) -> str:
    """Format bytes into human readable string (B, KB, MB, GB, TB)."""
    try:
        s = float(size)
    except (ValueError, TypeError):
        return "0 B"
    if s <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while s >= 1024.0 and idx < len(units) - 1:
        s /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(s)} B"
    return f"{s:.{precision}f} {units[idx]}"


def get_process_memory() -> int:
    """
    Returns current process resident set size (RSS) memory in bytes.
    Cross-platform support (Linux /proc/self/status or resource, Windows psapi, macOS resource).
    """
    system = platform.system()
    if system == "Linux":
        try:
            if os.path.exists("/proc/self/status"):
                with open("/proc/self/status", "r") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            return int(line.split()[1]) * 1024
        except Exception:
            pass
    elif system == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t)
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except Exception:
            pass

    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if system == "Darwin":
            return int(usage)
        return int(usage) * 1024
    except Exception:
        return 0


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

    if filename and len(filename.encode('utf-8')) > 180:
        base, ext = os.path.splitext(filename)
        base_bytes = base.encode('utf-8')[:150].decode('utf-8', errors='ignore').strip()
        filename = f"{base_bytes}{ext}"

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

def get_clean_env(extra_paths=None):
    """
    Returns a copy of the environment with PyInstaller, Qt, and Python paths completely sanitized.
    Ensures external binaries and scripts (e.g. yt-dlp, python3, ffmpeg, aria2c) load host system libraries.
    """
    clean_env = os.environ.copy()

    # 1. Collect all PyInstaller bundle paths (e.g. /tmp/_MEIxxxxxx)
    mei_dirs = set()
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        mei_dirs.add(os.path.abspath(meipass))

    for k, v in list(clean_env.items()):
        if "_MEI" in v or "_mei" in v:
            for part in v.split(os.pathsep):
                if "_MEI" in part or "_mei" in part:
                    mei_dirs.add(os.path.abspath(part))

    # 2. Hard clear PyInstaller, loader, and Qt specific environment keys
    keys_to_clear = [
        "LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "ORIG_LD_LIBRARY_PATH",
        "LD_PRELOAD", "LD_AUDIT",
        "DYLD_LIBRARY_PATH", "DYLD_LIBRARY_PATH_ORIG", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
        "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
        "PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "_MEIPASS2"
    ]
    for key in keys_to_clear:
        clean_env.pop(key, None)

    # 3. Restore original LD_LIBRARY_PATH only if it does NOT point to any MEIPASS directory
    for orig_key in ("LD_LIBRARY_PATH_ORIG", "ORIG_LD_LIBRARY_PATH"):
        orig_val = os.environ.get(orig_key, "")
        if orig_val:
            safe_parts = [
                p for p in orig_val.split(os.pathsep)
                if p and not any(m in p for m in ("_MEI", "_mei")) and not any(p.startswith(d) for d in mei_dirs)
            ]
            if safe_parts:
                clean_env["LD_LIBRARY_PATH"] = os.pathsep.join(safe_parts)
            break

    # 4. Scrub ALL remaining environment variables from containing any MEIPASS paths
    for k, v in list(clean_env.items()):
        if any(m in v for m in ("_MEI", "_mei")) or any(d in v for d in mei_dirs):
            parts = v.split(os.pathsep)
            filtered = [
                p for p in parts
                if p and not any(m in p for m in ("_MEI", "_mei")) and not any(p.startswith(d) for d in mei_dirs)
            ]
            if filtered:
                clean_env[k] = os.pathsep.join(filtered)
            else:
                clean_env.pop(k, None)

    # 5. Prepend extra tool paths to PATH if provided
    if extra_paths:
        clean_env["PATH"] = f"{extra_paths}:{clean_env.get('PATH', '')}"

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


def choose_portal_open_file_path(title="Select File", folder=""):
    """
    Triggers XDG Desktop Portal FileChooser.OpenFile via DBus to open native XDG Portal File Picker.
    Returns the chosen file path string, "" if user cancelled, or None if portal unavailable.
    """
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

            options = {"directory": False}
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
    return None


def get_autostart_filepath():
    autostart_dir = os.path.expanduser("~/.config/autostart")
    return os.path.join(autostart_dir, "bengal-download-manager.desktop")


def is_autostart_enabled():
    filepath = get_autostart_filepath()
    return os.path.exists(filepath)


def get_executable_command(start_minimized=False):
    min_flag = " --minimized" if start_minimized else ""

    # 1. Check if running from AppImage
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path and os.path.exists(appimage_path):
        return f'"{appimage_path}"{min_flag}'

    # 2. Check if running inside Flatpak
    if os.path.exists("/.flatpak-info") or os.environ.get("FLATPAK_ID"):
        flatpak_id = os.environ.get("FLATPAK_ID", "io.github.tazihad.bengal-download-manager")
        return f'flatpak run {flatpak_id}{min_flag}'

    # 3. Check if running as PyInstaller binary / frozen executable
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"{min_flag}'

    # 4. Standard Python / dev environment
    main_py = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{main_py}"{min_flag}'


def set_autostart_enabled(enabled, start_minimized=False):
    filepath = get_autostart_filepath()
    if enabled:
        exec_cmd = get_executable_command(start_minimized)
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Bengal Download Manager
Comment=High-performance multi-threaded download manager
Exec={exec_cmd}
Icon=bengal-download-manager
Terminal=false
Categories=Network;FileTransfer;
X-GNOME-Autostart-enabled=true
"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(desktop_content)
            os.chmod(filepath, 0o755)
            return True
        except Exception as e:
            print(f"Failed to write autostart file: {e}")
            return False
    else:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                return True
            except Exception as e:
                print(f"Failed to remove autostart file: {e}")
                return False
        return True


POPULAR_MEDIA_DOMAINS = {
    # YouTube & Shorts
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com",
    # Twitter / X
    "twitter.com", "www.twitter.com", "x.com", "www.x.com", "vxtwitter.com", "fxtwitter.com", "fixupx.com", "t.co",
    # Facebook & Reels
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch", "fb.com", "www.fb.com",
    # TikTok
    "tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    # Instagram & Reels
    "instagram.com", "www.instagram.com", "instagr.am",
    # Vimeo
    "vimeo.com", "www.vimeo.com", "player.vimeo.com",
    # Dailymotion
    "dailymotion.com", "www.dailymotion.com", "dai.ly",
    # Twitch
    "twitch.tv", "www.twitch.tv", "m.twitch.tv", "clips.twitch.tv",
    # Reddit
    "reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it",
    # Other popular media sites
    "bilibili.com", "www.bilibili.com",
    "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com",
    "pinterest.com", "www.pinterest.com", "pin.it",
    "streamable.com", "www.streamable.com",
    "vk.com", "www.vk.com",
    "rumble.com", "www.rumble.com",
    "kick.com", "www.kick.com",
    "bitchute.com", "www.bitchute.com",
    "odysee.com", "www.odysee.com",
    "ok.ru", "www.ok.ru",
    "bandcamp.com", "www.bandcamp.com",
    "mixcloud.com", "www.mixcloud.com"
}


def is_media_downloader_url(data):
    """
    Checks if the provided URL string originates from a popular media/video source
    supported by yt-dlp.
    """
    if not data:
        return False
    raw_url = str(data).split("|", 1)[0].strip()
    try:
        parsed = urlparse(raw_url)
        netloc = parsed.netloc.lower()
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        if not netloc:
            return False
        for domain in POPULAR_MEDIA_DOMAINS:
            if netloc == domain or netloc.endswith("." + domain):
                return True
    except Exception:
        pass
    return False


def sanitize_media_url(data: str) -> str:
    """
    Sanitizes media URLs by stripping tracking, dynamic search, and autogenerated
    mix/radio parameters (e.g. YouTube Mix/Radio &list=RD..., &start_radio=1,
    &pp=..., &si=..., &feature=...) while preserving genuine playlists (/playlist?list=PL...)
    and video parameters.
    """
    if not data:
        return ""
    raw_url = str(data).split("|", 1)[0].strip()
    try:
        from urllib.parse import parse_qs, urlencode, urlunparse
        parsed = urlparse(raw_url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]
        if "youtube.com" in domain or "youtu.be" in domain:
            qs = parse_qs(parsed.query, keep_blank_values=True)
            if "v" in qs or "shorts" in parsed.path:
                if "list" in qs:
                    lists = qs["list"]
                    # RD = YouTube Radio/Mix, UL = User Uploads Mix, PU = Popular Uploads Mix, WL = Watch Later
                    if any(l.startswith("RD") or l.startswith("UL") or l.startswith("PU") or l == "WL" for l in lists):
                        del qs["list"]
                qs.pop("start_radio", None)
                qs.pop("pp", None)
                qs.pop("si", None)
                qs.pop("feature", None)
                qs.pop("index", None)
                clean_query = urlencode(qs, doseq=True)
                return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))
            elif "youtu.be" in domain:
                qs = parse_qs(parsed.query, keep_blank_values=True)
                qs.pop("si", None)
                qs.pop("feature", None)
                clean_query = urlencode(qs, doseq=True)
                return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))
        elif "tiktok.com" in domain:
            qs = parse_qs(parsed.query, keep_blank_values=True)
            for k in ["is_from_webapp", "sender_device", "share_app_id", "share_item_id", "share_link_id"]:
                qs.pop(k, None)
            clean_query = urlencode(qs, doseq=True)
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))
    except Exception:
        pass
    return raw_url


def sanitize_media_filename(title: str, ext: str = ".mp4", max_len: int = 90) -> str:
    """
    Sanitize and truncate media title to avoid filesystem errors (e.g. Errno 36 File name too long)
    and ensure consistent filename resolution across the app while preserving counter suffixes.
    """
    if not title:
        title = "media"
    clean_base = re.sub(r'[\\/*?:"<>|]', "_", str(title)).strip()
    if not clean_base:
        clean_base = "media"

    # Extract any existing duplicate counter suffix like " (1)", " (2)"
    m = re.search(r'^(.*?)(\s*\(\d+\))$', clean_base)
    if m:
        main_part, suffix = m.group(1), m.group(2)
        eff_limit = max(10, max_len - len(suffix.encode("utf-8")))
        while len(main_part.encode("utf-8")) > eff_limit:
            main_part = main_part.encode("utf-8")[:eff_limit].decode("utf-8", errors="ignore").rstrip("_ ").strip()
            if not main_part:
                main_part = "media"
                break
        clean_base = f"{main_part}{suffix}"
    else:
        while len(clean_base.encode("utf-8")) > max_len:
            clean_base = clean_base.encode("utf-8")[:max_len].decode("utf-8", errors="ignore").rstrip("_ ").strip()
            if not clean_base:
                clean_base = "media"
                break

    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{clean_base}{ext}"


def get_unique_media_filepath(save_dir: str, filename: str) -> str:
    """
    Ensures a unique filepath for media downloads. Checks across all potential
    media extensions (.mp4, .mkv, .webm, .mp3, .m4a, .flv, .avi) to prevent
    yt-dlp from skipping downloads when re-downloading different qualities of the same media.
    """
    base_name, ext = os.path.splitext(filename)
    if not ext:
        ext = ".mp4"

    media_exts = [ext, ".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flv", ".avi"]

    def _exists(stem):
        return any(os.path.exists(os.path.join(save_dir, f"{stem}{e}")) for e in media_exts)

    cand_path = os.path.join(save_dir, f"{base_name}{ext}")
    counter = 1
    current_stem = base_name
    while _exists(current_stem):
        current_stem = f"{base_name} ({counter})"
        cand_path = os.path.join(save_dir, f"{current_stem}{ext}")
        counter += 1

    return cand_path


def advance_semantic_version(x: int, y: int, z: int) -> tuple[int, int, str]:
    """
    Advances the patch version. When patch version reaches or exceeds 99,
    rolls over minor version (y + 1) and resets patch to '00'.
    e.g. (0, 1, 79) -> (0, 1, '80')
         (0, 1, 99) -> (0, 2, '00')
    """
    if z >= 99:
        return x, y + 1, "00"
    return x, y, str(z + 1)


def determine_next_release_tag(
    manual_tag: str = "",
    ref: str = "refs/heads/dev",
    tags_list: list[str] | None = None
) -> tuple[str, str]:
    """
    Determines next git tag and version string based on existing tags and git branch ref.
    Alpha releases on non-main branches use upcoming advance version tags (e.g. 0.1.79 -> 0.1.80-alpha.1).
    """
    pattern = re.compile(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([a-zA-Z]+)\.([0-9]+))?$")
    if manual_tag:
        tag = manual_tag if manual_tag.startswith("v") else f"v{manual_tag}"
        version = tag[1:] if tag.startswith("v") else tag
        return tag, version

    if tags_list is None:
        try:
            tags_list = subprocess.check_output(["git", "tag", "-l"]).decode("utf-8").split("\n")
        except Exception:
            tags_list = []

    parsed = []
    existing_tags = set()
    for t in tags_list:
        t_clean = t.strip()
        if not t_clean:
            continue
        existing_tags.add(t_clean)
        m = pattern.match(t_clean)
        if m:
            x = int(m.group(1))
            y = int(m.group(2))
            z = int(m.group(3))
            z_raw = m.group(3)
            suffix = m.group(4) or ""
            is_stable = (suffix == "")
            n = int(m.group(5)) if m.group(5) else 0
            parsed.append((x, y, z, is_stable, n, z_raw, suffix, t_clean))

    if not parsed:
        latest = (0, 1, 0, False, 0, "0", "alpha", "v0.1.0-alpha.0")
    else:
        parsed.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
        latest = parsed[-1]

    x, y, z, is_stable, n, z_raw, suffix, latest_tag = latest
    suffix = suffix or "alpha"

    is_main = (ref == "refs/heads/main")

    if is_main:
        if not is_stable:
            tag = f"v{x}.{y}.{z_raw}"
        else:
            nx, ny, nz = advance_semantic_version(x, y, z)
            tag = f"v{nx}.{ny}.{nz}"

        while tag in existing_tags:
            m = pattern.match(tag)
            if m:
                tx, ty, tz = int(m.group(1)), int(m.group(2)), int(m.group(3))
                nx, ny, nz = advance_semantic_version(tx, ty, tz)
                tag = f"v{nx}.{ny}.{nz}"
            else:
                break
    else:
        if not is_stable:
            next_n = n + 1
            tag = f"v{x}.{y}.{z_raw}-{suffix}.{next_n}"
        else:
            nx, ny, nz = advance_semantic_version(x, y, z)
            tag = f"v{nx}.{ny}.{nz}-alpha.1"

        while tag in existing_tags:
            m = pattern.match(tag)
            if m:
                tx, ty, tz_raw = m.group(1), m.group(2), m.group(3)
                tsuffix = m.group(4) or "alpha"
                tn = int(m.group(5)) if m.group(5) else 0
                tag = f"v{tx}.{ty}.{tz_raw}-{tsuffix}.{tn + 1}"
            else:
                break

    version = tag[1:] if tag.startswith("v") else tag
    return tag, version



