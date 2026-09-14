"""
Batch Prober Worker for Bengal Download Manager
================================================
Performs fast, asynchronous non-blocking HTTP HEAD/Range requests
to probe file sizes, status, and Content-Disposition headers for batch downloads.
"""

import http.cookiejar
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from core.utils import format_bytes, resolve_filename, is_debug_mode

logger = logging.getLogger("bengal.batch_prober")


class ProbeSignals(QObject):
    probe_finished = pyqtSignal(int, dict)  # (row_index, result_dict)


class ProbeTask(QRunnable):
    def __init__(
        self,
        row_index: int,
        url: str,
        signals: ProbeSignals,
        user_agent: Optional[str] = None,
        cookies: Optional[str] = None,
        referrer: Optional[str] = None,
        timeout: int = 8
    ):
        super().__init__()
        self.row_index = row_index
        self.url = url
        self.signals = signals
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.cookies = cookies
        self.referrer = referrer
        self.timeout = timeout
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _create_opener(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        cookie_jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            urllib.request.HTTPSHandler(context=ctx)
        )

    def run(self):
        if self._is_cancelled or not self.url:
            return

        result: Dict[str, Any] = {
            "row_index": self.row_index,
            "url": self.url,
            "filename": resolve_filename(self.url, {}),
            "size_bytes": -1,
            "size_str": "",
            "status": "Checking...",
            "error": None
        }

        # Torrent or Magnet links
        clean_url = self.url.lower().strip()
        if clean_url.startswith("magnet:?") or clean_url.endswith(".torrent"):
            result["status"] = "Found"
            result["size_str"] = ""
            self.signals.probe_finished.emit(self.row_index, result)
            return

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Connection": "close"
        }
        if self.cookies:
            headers["Cookie"] = self.cookies
        if self.referrer:
            headers["Referer"] = self.referrer
        else:
            try:
                p = urllib.parse.urlparse(self.url)
                if p.scheme and p.netloc:
                    headers["Referer"] = f"{p.scheme}://{p.netloc}/"
            except Exception:
                pass

        opener = self._create_opener()

        # Step 1: Attempt HTTP HEAD request
        probe_success = False
        try:
            req = urllib.request.Request(self.url, headers=headers, method="HEAD")
            with opener.open(req, timeout=self.timeout) as resp:
                final_url = resp.geturl()
                resp_headers = resp.headers
                content_len = resp_headers.get("Content-Length")
                content_disp = resp_headers.get("Content-Disposition")

                resolved_name = resolve_filename(final_url, resp_headers)
                if resolved_name and resolved_name != "download":
                    result["filename"] = resolved_name

                if content_len and content_len.strip().isdigit():
                    bytes_val = int(content_len.strip())
                    if bytes_val > 0:
                        result["size_bytes"] = bytes_val
                        result["size_str"] = format_bytes(bytes_val)

                result["url"] = final_url
                result["status"] = "Found"
                probe_success = True
        except urllib.error.HTTPError as e:
            # If server forbids HEAD (e.g. 405 Method Not Allowed), we fall back to GET Range request
            if e.code in (405, 403, 501):
                pass
            else:
                result["status"] = "Not Found"
                result["error"] = f"HTTP {e.code}"
        except Exception as e:
            if is_debug_mode():
                logger.debug("[BatchProber] HEAD error on %s: %s", self.url, e)

        # Step 2: Fallback to GET with Range: bytes=0-0 if HEAD didn't resolve size
        if not probe_success and not self._is_cancelled and result["status"] != "Not Found":
            try:
                headers["Range"] = "bytes=0-0"
                req = urllib.request.Request(self.url, headers=headers, method="GET")
                with opener.open(req, timeout=self.timeout) as resp:
                    final_url = resp.geturl()
                    resp_headers = resp.headers
                    crange = resp_headers.get("Content-Range", "")
                    # e.g., Content-Range: bytes 0-0/10485760
                    if "/" in crange:
                        tot = crange.split("/")[-1].strip()
                        if tot.isdigit() and int(tot) > 0:
                            result["size_bytes"] = int(tot)
                            result["size_str"] = format_bytes(int(tot))
                    elif resp_headers.get("Content-Length") and resp_headers.get("Content-Length").isdigit():
                        clen = int(resp_headers.get("Content-Length"))
                        # If response was 200 OK full body rather than 206 Partial Content
                        if resp.status == 200 and clen > 1:
                            result["size_bytes"] = clen
                            result["size_str"] = format_bytes(clen)

                    resolved_name = resolve_filename(final_url, resp_headers)
                    if resolved_name and resolved_name != "download":
                        result["filename"] = resolved_name

                    result["url"] = final_url
                    result["status"] = "Found"
                    probe_success = True
            except urllib.error.HTTPError as e:
                result["status"] = "Not Found"
                result["error"] = f"HTTP {e.code}"
            except Exception as e:
                result["status"] = "Not Found"
                result["error"] = str(e)

        if not probe_success and not result["error"]:
            result["status"] = "Not Found"

        if not self._is_cancelled:
            self.signals.probe_finished.emit(self.row_index, result)


class BatchProberManager(QObject):
    """Manages the thread pool for probing multiple batch items."""
    probe_finished = pyqtSignal(int, dict)

    def __init__(self, max_concurrent: int = 6, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(max_concurrent)
        self.signals = ProbeSignals()
        self.signals.probe_finished.connect(self.probe_finished)
        self.active_tasks: List[ProbeTask] = []

    def probe_items(self, items: List[Dict[str, Any]]):
        """Starts probing the given list of file item dictionaries."""
        for idx, item in enumerate(items):
            url = item.get("url", "")
            if not url:
                continue
            task = ProbeTask(
                row_index=idx,
                url=url,
                signals=self.signals,
                user_agent=item.get("user_agent"),
                cookies=item.get("cookies"),
                referrer=item.get("referrer")
            )
            self.active_tasks.append(task)
            self.thread_pool.start(task)

    def stop_all(self):
        """Cancels all pending probe tasks and clears the pool."""
        for task in self.active_tasks:
            task.cancel()
        self.active_tasks.clear()
        self.thread_pool.clear()
