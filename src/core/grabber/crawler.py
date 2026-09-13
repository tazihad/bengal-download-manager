"""
Site Grabber Crawler Engine
===========================
Asynchronous breadth-first crawler for discovering, filtering, and probing
downloadable resources across websites.
"""

import os
import re
import ipaddress
import socket
import logging
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Set, Optional, Tuple, Any

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("bengal.grabber")

# Security: Cap page body to 16 MiB to prevent memory exhaustion (DoS)
MAX_PAGE_BYTES = 16 * 1024 * 1024

# Common HTML-like extensions that should be explored as pages
HTML_EXTENSIONS = {
    "", "html", "htm", "php", "asp", "aspx", "jsp", "cgi", "shtml", "pl"
}


def is_private_or_loopback_host(host: str) -> bool:
    """
    SSRF gate (CWE-918): Checks if host is loopback, link-local, RFC-1918,
    or AWS/GCP metadata address.
    """
    if not host:
        return True

    host_clean = host.strip().lower()
    if host_clean in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True

    # Try literal IP check
    try:
        ip = ipaddress.ip_address(host_clean)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or str(ip) == "169.254.169.254"
        )
    except ValueError:
        pass

    # Resolve hostname via DNS and verify resolved addresses
    try:
        _, _, ip_list = socket.gethostbyname_ex(host_clean)
        if not ip_list:
            return True
        for resolved_ip in ip_list:
            ip = ipaddress.ip_address(resolved_ip)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
                or str(ip) == "169.254.169.254"
            ):
                return True
    except Exception:
        return True

    return False


def wildcard_to_regex(pattern: str) -> re.Pattern:
    """Convert wildcard pattern (e.g. *.jpg or video_*) into compiled regex."""
    p = pattern.strip()
    if not p:
        return re.compile(r"^.*$")
    # Escape special regex chars except * and ?
    escaped = ""
    for ch in p:
        if ch == "*":
            escaped += ".*"
        elif ch == "?":
            escaped += "."
        elif ch in r"\.+^$()[]{}|":
            escaped += "\\" + ch
        else:
            escaped += ch
    return re.compile(f"^{escaped}$", re.IGNORECASE)


class LinkExtractor(HTMLParser):
    """Robust HTML link and media extractor."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        candidates = []
        if tag_lower in ("a", "link", "area"):
            if "href" in attr_dict:
                candidates.append(attr_dict["href"])
        if tag_lower in ("img", "script", "video", "audio", "source", "iframe", "embed"):
            if "src" in attr_dict:
                candidates.append(attr_dict["src"])
            if "data-src" in attr_dict:
                candidates.append(attr_dict["data-src"])
            if "data-original" in attr_dict:
                candidates.append(attr_dict["data-original"])

        for raw in candidates:
            raw_clean = raw.strip()
            if not raw_clean or raw_clean.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            try:
                resolved = urllib.parse.urljoin(self.base_url, raw_clean)
                self.links.append(resolved)
            except Exception:
                pass


class GrabberCrawler(QThread):
    """
    Asynchronous web crawler thread that explores a site to given depth,
    matches files against filters, and probes sizes.
    """

    progress_changed = pyqtSignal(str)
    file_found = pyqtSignal(dict)
    metadata_updated = pyqtSignal(str, int)  # url, size_bytes
    crawl_finished = pyqtSignal(list)
    crawl_failed = pyqtSignal(str)

    def __init__(self, project_config: dict, parent=None):
        super().__init__(parent)
        self.config = project_config
        self._is_running = True
        self.results: List[Dict[str, Any]] = []
        self._seen_pages: Set[str] = set()
        self._seen_result_keys: Set[str] = set()
        self._resolved_host_cache: Dict[str, bool] = {}

    def cancel(self):
        self._is_running = False

    def is_safe_host(self, host: str) -> bool:
        if not host:
            return False
        h = host.lower()
        if h in self._resolved_host_cache:
            return self._resolved_host_cache[h]
        unsafe = is_private_or_loopback_host(h)
        self._resolved_host_cache[h] = not unsafe
        return not unsafe

    def run(self):
        start_url_raw = self.config.get("start_url", "").strip()
        if not start_url_raw:
            self.crawl_failed.emit("Please enter a valid start URL.")
            return

        if not (start_url_raw.startswith("http://") or start_url_raw.startswith("https://")):
            start_url_raw = "https://" + start_url_raw

        parsed_start = urllib.parse.urlparse(start_url_raw)
        if not parsed_start.netloc:
            self.crawl_failed.emit("Invalid start URL provided.")
            return

        root_domain = parsed_start.netloc.lower()
        if not self.is_safe_host(root_domain):
            self.crawl_failed.emit("Start URL resolves to a private, loopback, or local address.")
            return

        max_depth = int(self.config.get("explore_depth", 1))
        stay_domain = bool(self.config.get("stay_same_domain", True))
        stay_path = bool(self.config.get("stay_same_path", False))
        hide_duplicates = bool(self.config.get("hide_duplicates", True))
        include_masks = self.config.get("file_include_patterns", ["*.*"])
        exclude_masks = self.config.get("file_exclude_patterns", [])
        min_size = int(self.config.get("min_size_bytes", 0))
        max_size = int(self.config.get("max_size_bytes", 0))
        user_agent = self.config.get("user_agent", "Mozilla/5.0 (compatible; BengalGrabber/1.0)")

        # Compile include and exclude regexes
        include_regexes = [wildcard_to_regex(m) for m in include_masks if m.strip()]
        exclude_regexes = [wildcard_to_regex(m) for m in exclude_masks if m.strip()]

        start_path_prefix = parsed_start.path
        if not start_path_prefix.endswith("/"):
            slash_idx = start_path_prefix.rfind("/")
            start_path_prefix = start_path_prefix[: slash_idx + 1] if slash_idx >= 0 else "/"

        queue: List[Tuple[str, int, str]] = [(start_url_raw, 0, "")]
        pages_crawled = 0

        # Thread pool for concurrent HEAD requests
        metadata_pool = ThreadPoolExecutor(max_workers=4)

        try:
            while queue and self._is_running:
                current_url, depth, source_page = queue.pop(0)
                norm_page = self._normalize_url(current_url)
                if norm_page in self._seen_pages:
                    continue
                self._seen_pages.add(norm_page)

                self.progress_changed.emit(f"Exploring {current_url} (depth {depth}/{max_depth})...")

                html_content, final_url = self._fetch_page(current_url, user_agent)
                if html_content is None or not self._is_running:
                    continue

                pages_crawled += 1

                # Parse links
                extractor = LinkExtractor(final_url)
                try:
                    extractor.feed(html_content)
                except Exception as e:
                    logger.debug("[Grabber] Parser warning on %s: %s", final_url, e)

                # Classify links
                for link in extractor.links:
                    if not self._is_running:
                        break

                    parsed_link = urllib.parse.urlparse(link)
                    if parsed_link.scheme not in ("http", "https"):
                        continue

                    link_host = parsed_link.netloc.lower()

                    # Domain check
                    if stay_domain:
                        if link_host != root_domain and not link_host.endswith("." + root_domain):
                            continue

                    # Path check
                    if stay_path and parsed_link.path and not parsed_link.path.startswith(start_path_prefix):
                        continue

                    # SSRF Check
                    if not self.is_safe_host(link_host):
                        continue

                    if self._is_html_page(link):
                        # Queue candidate for deeper exploration
                        if depth + 1 < max_depth:
                            norm_link = self._normalize_url(link)
                            if norm_link not in self._seen_pages:
                                queue.append((link, depth + 1, final_url))
                    else:
                        # Candidate file
                        filename = self._extract_filename(link)
                        if not self._passes_patterns(filename, link, include_regexes, exclude_regexes):
                            continue

                        dup_key = filename.lower() if hide_duplicates else link
                        if dup_key in self._seen_result_keys:
                            continue
                        self._seen_result_keys.add(dup_key)

                        file_info = {
                            "url": link,
                            "filename": filename,
                            "source_page": final_url,
                            "size": -1,
                            "checked": True,
                            "extension": os.path.splitext(filename)[1].lower().lstrip("."),
                        }
                        self.results.append(file_info)
                        self.file_found.emit(file_info)

                        # Submit async metadata probe
                        if self._is_running:
                            metadata_pool.submit(self._probe_metadata, link, user_agent, min_size, max_size)

                self.progress_changed.emit(f"Found {len(self.results)} files across {pages_crawled} pages.")

        finally:
            metadata_pool.shutdown(wait=False)

        if self._is_running:
            self.progress_changed.emit(f"Exploration complete. Found {len(self.results)} files across {pages_crawled} pages.")
            self.crawl_finished.emit(self.results)
        else:
            self.progress_changed.emit(f"Crawl stopped. Found {len(self.results)} files.")
            self.crawl_finished.emit(self.results)

    def _normalize_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        return urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "" # Drop fragment (#)
        ))

    def _is_html_page(self, url: str) -> bool:
        path = urllib.parse.urlparse(url).path.lower()
        if not path or path.endswith("/"):
            return True
        ext = os.path.splitext(path)[1].lstrip(".")
        return ext in HTML_EXTENSIONS

    def _extract_filename(self, url: str) -> str:
        path = urllib.parse.urlparse(url).path
        base = os.path.basename(path.rstrip("/"))
        if not base or "." not in base:
            # Generate sensible filename from host/path
            base = "file_" + str(len(self.results) + 1)
        # Unquote URL encoding
        try:
            base = urllib.parse.unquote(base)
        except Exception:
            pass
        return base

    def _passes_patterns(self, filename: str, url: str, include_re: List[re.Pattern], exclude_re: List[re.Pattern]) -> bool:
        # Check exclusion first
        for rx in exclude_re:
            if rx.search(filename) or rx.search(url):
                return False

        # If no include regexes, allow all
        if not include_re:
            return True

        for rx in include_re:
            if rx.search(filename) or rx.search(url):
                return True
        return False

    def _fetch_page(self, url: str, user_agent: str) -> Tuple[Optional[str], str]:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,*/*"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
                    return None, url
                raw_bytes = resp.read(MAX_PAGE_BYTES)
                encoding = resp.headers.get_content_charset() or "utf-8"
                html_text = raw_bytes.decode(encoding, errors="replace")
                return html_text, resp.geturl()
        except Exception as e:
            logger.debug("[Grabber] Error fetching %s: %s", url, e)
            return None, url

    def _probe_metadata(self, url: str, user_agent: str, min_size: int, max_size: int):
        if not self._is_running:
            return
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": user_agent},
                method="HEAD"
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit():
                    size_bytes = int(cl)
                    if min_size > 0 and size_bytes < min_size:
                        return
                    if max_size > 0 and size_bytes > max_size:
                        return
                    self.metadata_updated.emit(url, size_bytes)
        except Exception:
            pass
