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
                'Upgrade-Insecure-Requests': '1',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }

            if self.cookies:
                headers['Cookie'] = self.cookies

            # Add Referer if possible
            parsed_orig = urlparse(self.url)
            if "techspot.com" in parsed_orig.netloc:
                headers['Referer'] = 'https://www.techspot.com/'
            else:
                headers['Referer'] = f"{parsed_orig.scheme}://{parsed_orig.netloc}/"

            opener = self.create_opener()
            
            # --- JDOWNLOADER STYLE HANDSHAKE ---
            # Use GET but read only headers. If HTML, check for meta-refresh.
            req = urllib.request.Request(self.url, headers=headers)
            
            with opener.open(req, timeout=15) as resp:
                final_url = resp.geturl()
                final_headers = resp.headers
                
                # Update result URL (might have changed due to redirects)
                result["url"] = final_url
                
                content_type = final_headers.get("Content-Type", "").lower()
                
                # 1. Resolve name from the real headers and final URL
                result["filename"] = resolve_filename(final_url, final_headers)
                
                # 2. Get size
                content_length = final_headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    result["size_bytes"] = int(content_length)
                    result["size_str"] = self.format_bytes(result["size_bytes"])

                # IMPORTANT: Close immediately to stop background download
                resp.close()
                    
        except Exception as e:
            result["error"] = str(e)
            
        self.finished_signal.emit(result)
        
    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"
