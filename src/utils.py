import os
import sys
import json
import socket
import urllib.request
import platform
import shutil
import tarfile

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
