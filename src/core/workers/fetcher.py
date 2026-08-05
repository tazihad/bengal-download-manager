import os
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error
import http.cookiejar
import ssl
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import load_extension_config, resolve_filename

class FileInfoFetcherWorker(QThread):
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, url, user_agent=None, cookies=None):
        super().__init__()
        self.url = url
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
                    result["filename"] = resolve_filename(final_url, final_headers)
                    
                    content_length = final_headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        result["size_bytes"] = int(content_length)
                        result["size_str"] = self.format_bytes(result["size_bytes"])
                    
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
