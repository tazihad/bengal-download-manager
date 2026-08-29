import os
import re
from urllib.parse import urlparse, unquote, parse_qs
import urllib.request
import urllib.error
import http.cookiejar
import ssl
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import load_extension_config, resolve_filename, format_bytes

class FileInfoFetcherWorker(QThread):
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, url, user_agent=None, cookies=None, referrer=None):
        super().__init__()
        self.url = url
        self.referrer = referrer
        # Use Chrome UA by default as it's more widely accepted by WAFs
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.cookies = cookies
        self.cookie_jar = http.cookiejar.CookieJar()
    
    def create_opener(self):
        """Standard opener with cookie support and redirect handling."""
        # Use a permissive SSL context for handshakes
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=ctx)
        )
        return opener

    def run(self):
        # Initial guess before network request
        initial_filename = resolve_filename(self.url, {})
        
        result = {
            "url": self.url,
            "filename": initial_filename,
            "size_str": "Unknown",
            "size_bytes": 0,
            "user_agent": self.user_agent,
            "cookies": self.cookies,
            "referer": self.referrer or self.url,
            "error": None
        }
        
        try:
            # --- FULL BROWSER HEADERS (Avoid Cloudflare/WAF blocks) ---
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            if self.cookies:
                headers['Cookie'] = self.cookies

            if self.referrer:
                headers['Referer'] = self.referrer
            else:
                parsed_orig = urlparse(self.url)
                headers['Referer'] = f"{parsed_orig.scheme}://{parsed_orig.netloc}/"

            opener = self.create_opener()
            
            # Follow redirects manually to inspect each stage
            current_url = self.url
            max_redirects = 10
            
            for _ in range(max_redirects):
                req = urllib.request.Request(current_url, headers=headers)
                with opener.open(req, timeout=15) as resp:
                    final_url = resp.geturl()
                    final_headers = resp.headers
                    content_type = final_headers.get("Content-Type", "").lower()
                    
                    # If we hit an HTML page with no attachment header, it's NOT the file.
                    if "text/html" in content_type and not final_headers.get("Content-Disposition"):
                        if final_url != current_url:
                            current_url = final_url
                            continue
                        
                        result["error"] = "Target is a webpage, not a file. Redirected to landing page."
                        self.finished_signal.emit(result)
                        return

                    # We found a binary or an explicit attachment!
                    result["url"] = final_url
                    result["referer"] = self.url if final_url != self.url else (self.referrer or self.url)
                    result["filename"] = resolve_filename(final_url, final_headers)
                    
                    # 1. Content-Length check
                    size_bytes = 0
                    content_length = final_headers.get("Content-Length")
                    if content_length and content_length.isdigit() and int(content_length) > 0:
                        size_bytes = int(content_length)
                    else:
                        # 2. Content-Range header check (e.g., bytes 0-0/12345)
                        content_range = final_headers.get("Content-Range", "")
                        cr_match = re.search(r'/(\d+)', content_range)
                        if cr_match:
                            size_bytes = int(cr_match.group(1))

                    if not size_bytes:
                        # 3. Content-Disposition size parameter (e.g. size=12345)
                        cd = final_headers.get("Content-Disposition", "")
                        cd_match = re.search(r'size\s*=\s*(\d+)', cd, re.IGNORECASE)
                        if cd_match:
                            size_bytes = int(cd_match.group(1))

                    if not size_bytes:
                        # 4. URL Query parameters (e.g. ?size=12345, ?filesize=12345, ?length=12345)
                        try:
                            parsed_final = urlparse(final_url)
                            if parsed_final.query:
                                qs = parse_qs(parsed_final.query)
                                for q_key in ["size", "filesize", "file_size", "length", "bytes", "total_bytes"]:
                                    for v in qs.get(q_key, []):
                                        if v.isdigit() and int(v) > 0:
                                            size_bytes = int(v)
                                            break
                                    if size_bytes:
                                        break
                        except Exception:
                            pass

                    if not size_bytes:
                        # 5. Secondary HEAD probe
                        try:
                            probe_headers = dict(headers)
                            head_req = urllib.request.Request(final_url, method='HEAD', headers=probe_headers)
                            with opener.open(head_req, timeout=5) as head_resp:
                                head_cl = head_resp.headers.get("Content-Length")
                                if head_cl and head_cl.isdigit() and int(head_cl) > 0:
                                    size_bytes = int(head_cl)
                                else:
                                    head_cr = head_resp.headers.get("Content-Range", "")
                                    head_cr_match = re.search(r'/(\d+)', head_cr)
                                    if head_cr_match:
                                        size_bytes = int(head_cr_match.group(1))
                        except Exception:
                            pass

                    if size_bytes > 0:
                        result["size_bytes"] = size_bytes
                        result["size_str"] = format_bytes(size_bytes)
                    else:
                        result["size_bytes"] = 0
                        result["size_str"] = "Unknown"
                    
                    resp.close()
                    self.finished_signal.emit(result)
                    return

            result["error"] = "Too many redirects. Could not find direct file link."
                    
        except Exception as e:
            result["error"] = str(e)
            
        self.finished_signal.emit(result)
        
    def format_bytes(self, size, precision=2, pad=False):
        power = 1024
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size >= power and n < 4:
            size /= power
            n += 1
        if pad:
            width = precision + 5
            return f"{size:{width}.{precision}f}  {power_labels.get(n, '')}B"
        else:
            return f"{size:.{precision}f}  {power_labels.get(n, '')}B"


class BackgroundSizeProbeWorker(QThread):
    size_found_signal = pyqtSignal(str, int)  # size_str, size_bytes

    def __init__(self, url, user_agent=None, cookies=None, referrer=None):
        super().__init__()
        self.url = url
        self.user_agent = user_agent
        self.cookies = cookies
        self.referrer = referrer
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        if not self.url or not self.url.startswith("http"):
            return

        try:
            try:
                ctx = ssl._create_unverified_context()
            except AttributeError:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
            headers = {
                'User-Agent': self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                'Accept': '*/*',
                'Connection': 'close'
            }
            if self.cookies:
                headers['Cookie'] = self.cookies
            if self.referrer:
                headers['Referer'] = self.referrer

            size_bytes = 0

            # 1. Probe with Range: bytes=0-1
            if self._is_running:
                try:
                    range_headers = dict(headers)
                    range_headers['Range'] = 'bytes=0-1'
                    req_range = urllib.request.Request(self.url, headers=range_headers)
                    with opener.open(req_range, timeout=6) as resp:
                        cr = resp.headers.get("Content-Range", "")
                        cr_match = re.search(r'/(\d+)', cr)
                        if cr_match:
                            size_bytes = int(cr_match.group(1))
                        elif resp.headers.get("Content-Length", "").isdigit():
                            cl = int(resp.headers.get("Content-Length"))
                            if cl > 2:
                                size_bytes = cl
                except Exception:
                    pass

            # 2. Probe with HEAD
            if not size_bytes and self._is_running:
                try:
                    head_req = urllib.request.Request(self.url, method='HEAD', headers=headers)
                    with opener.open(head_req, timeout=6) as resp:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit() and int(cl) > 0:
                            size_bytes = int(cl)
                        else:
                            cr = resp.headers.get("Content-Range", "")
                            cr_match = re.search(r'/(\d+)', cr)
                            if cr_match:
                                size_bytes = int(cr_match.group(1))
                except Exception:
                    pass

            if size_bytes > 0 and self._is_running:
                size_str = format_bytes(size_bytes)
                self.size_found_signal.emit(size_str, size_bytes)
        except Exception:
            pass

