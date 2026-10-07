import os
import logging
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error
import http.cookiejar
import ssl
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import load_extension_config, resolve_filename, is_debug_mode

logger = logging.getLogger("bengal.worker.fetcher")

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
        self._is_cancelled = False
        if is_debug_mode():
            logger.debug("[Fetcher] Initialized for URL: %s", self.url)
    
    def cancel(self):
        """Signals the worker to cancel ongoing requests and suppress result emission."""
        self._is_cancelled = True
    
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
        if is_debug_mode():
            logger.debug("[Fetcher] Probing URL: %s (initial guess: %s)", self.url, initial_filename)
        
        result = {
            "url": self.url,
            "filename": initial_filename,
            "content_type": "",
            "size_str": "Unknown",
            "size_bytes": 0,
            "user_agent": self.user_agent,
            "cookies": self.cookies,
            "referer": self.referrer or self.url,
            "error": None
        }
        
        try:
            if self._is_cancelled:
                return
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
            current_url = self.url
            max_redirects = 10

            # --- TIER 1: ULTRA-FAST HTTP HEAD REQUEST (0 Body Bytes, 1 TCP Round-Trip) ---
            head_success = False
            for hop in range(max_redirects):
                if self._is_cancelled:
                    return
                try:
                    head_req = urllib.request.Request(current_url, headers=headers, method="HEAD")
                    with opener.open(head_req, timeout=8) as resp:
                        if self._is_cancelled:
                            return
                        final_url = resp.geturl()
                        final_headers = resp.headers
                        content_type = final_headers.get("Content-Type", "").lower()
                        result["content_type"] = content_type

                        # If redirected to an HTML landing page without attachment header, follow location
                        if "text/html" in content_type and not final_headers.get("Content-Disposition"):
                            if final_url != current_url:
                                current_url = final_url
                                continue
                            result["error"] = "Target is a webpage, not a file. Redirected to landing page."
                            if not self._is_cancelled:
                                self.finished_signal.emit(result)
                            return

                        result["url"] = final_url
                        result["referer"] = self.url if final_url != self.url else (self.referrer or self.url)
                        result["filename"] = resolve_filename(final_url, final_headers)

                        content_length = final_headers.get("Content-Length")
                        if content_length and content_length.isdigit() and int(content_length) > 0:
                            result["size_bytes"] = int(content_length)
                            result["size_str"] = self.format_bytes(result["size_bytes"])
                            head_success = True
                            if is_debug_mode():
                                logger.debug("[Fetcher] [Tier 1 HEAD Fast Success] %s: %s (%d bytes)",
                                             result["filename"], result["size_str"], result["size_bytes"])
                            resp.close()
                            if not self._is_cancelled:
                                self.finished_signal.emit(result)
                            return
                        resp.close()
                except Exception as head_err:
                    if is_debug_mode():
                        logger.debug("[Fetcher] HEAD request failed or unsupported (%s), falling back to Tier 2 Range request.", head_err)
                    break

            # --- TIER 2: RANGE BYTES=0-0 (1 Byte transfer to read Content-Range total size) ---
            if not head_success:
                range_headers = headers.copy()
                range_headers['Range'] = 'bytes=0-0'
                current_url = result.get("url") or self.url

                for hop in range(max_redirects):
                    if self._is_cancelled:
                        return
                    req = urllib.request.Request(current_url, headers=range_headers)
                    with opener.open(req, timeout=10) as resp:
                        if self._is_cancelled:
                            return
                        final_url = resp.geturl()
                        final_headers = resp.headers
                        content_type = final_headers.get("Content-Type", "").lower()
                        result["content_type"] = content_type

                        if "text/html" in content_type and not final_headers.get("Content-Disposition"):
                            if final_url != current_url:
                                current_url = final_url
                                continue
                            result["error"] = "Target is a webpage, not a file. Redirected to landing page."
                            if not self._is_cancelled:
                                self.finished_signal.emit(result)
                            return

                        result["url"] = final_url
                        result["referer"] = self.url if final_url != self.url else (self.referrer or self.url)
                        result["filename"] = resolve_filename(final_url, final_headers)

                        # Check Content-Range: bytes 0-0/TOTAL
                        content_range = final_headers.get("Content-Range", "")
                        if content_range:
                            import re
                            m_range = re.search(r"bytes\s+\d+-\d+/(\d+)", content_range, re.IGNORECASE)
                            if m_range and m_range.group(1).isdigit():
                                result["size_bytes"] = int(m_range.group(1))
                                result["size_str"] = self.format_bytes(result["size_bytes"])

                        # Fallback to Content-Length if Content-Range was absent (full 200 response)
                        if result["size_bytes"] == 0:
                            content_length = final_headers.get("Content-Length")
                            if content_length and content_length.isdigit():
                                result["size_bytes"] = int(content_length)
                                result["size_str"] = self.format_bytes(result["size_bytes"])

                        if is_debug_mode():
                            logger.debug("[Fetcher] [Tier 2 Range Success] %s: %s (%d bytes)",
                                         result["filename"], result["size_str"], result["size_bytes"])
                        # Read only 1 byte and close socket immediately
                        try:
                            resp.read(1)
                        except Exception:
                            pass
                        resp.close()
                        if not self._is_cancelled:
                            self.finished_signal.emit(result)
                        return
            result["error"] = "Could not resolve file size."
        except Exception as e:
            result["error"] = str(e)
            if is_debug_mode():
                logger.error("[Fetcher] Error probing %s: %s", self.url, e)

        if not self._is_cancelled:
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
