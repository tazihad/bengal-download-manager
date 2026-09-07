"""
Google Drive Dedicated Download Handler
========================================
Dedicated service module for Google Drive and Google UserContent downloads.
Isolates Google Drive authentication, cookie resolution, and virus-scan form
handling so standard file downloads remain completely unaffected.
"""

import os
import re
import ssl
import glob
import sqlite3
import urllib.request
from urllib.parse import urlparse, unquote


def is_gdrive_url(url: str) -> bool:
    """Checks if the URL is a Google Drive or Google UserContent download link."""
    if not url:
        return False
    u = url.lower()
    return (
        "drive.google.com" in u or
        "drive.usercontent.google.com" in u or
        "docs.google.com" in u or
        ("googleusercontent.com" in u and ("export=download" in u or "id=" in u or "/download" in u))
    )


def get_local_gdrive_cookies() -> str:
    """
    Directly retrieves Google Drive session cookies from the local user profile
    (Firefox cookies.sqlite). This ensures private Google Drive downloads succeed
    even if browser cookie isolation (Total Cookie Protection / dFPI) prevented
    the browser extension from capturing OSID or __Secure-OSID.
    """
    cookies = {}

    # 1. Inspect Firefox profiles
    firefox_dbs = glob.glob(os.path.expanduser("~/.mozilla/firefox/*/cookies.sqlite"))
    for db in firefox_dbs:
        try:
            # Connect in read-only immutable mode so active Firefox sessions are never locked
            conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE ? OR host LIKE ?;",
                ("%google.com", "%usercontent.com")
            )
            for name, val in cursor.fetchall():
                if name and val and name not in cookies:
                    cookies[name] = val
            conn.close()
        except Exception:
            pass

    cookie_list = [f"{k}={v}" for k, v in cookies.items()]
    return "; ".join(cookie_list)


def merge_gdrive_cookies(existing_cookies: str = None) -> str:
    """
    Merges existing cookies with local browser Google credentials to ensure
    crucial authentication cookies ('OSID', '__Secure-OSID', 'SID') are always present.
    """
    cookie_map = {}
    if existing_cookies:
        for part in existing_cookies.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookie_map[k] = v

    # If missing Google Drive authentication credentials, pull from local browser store
    has_osid = "OSID" in cookie_map or "__Secure-OSID" in cookie_map
    if not has_osid:
        local_c = get_local_gdrive_cookies()
        if local_c:
            for part in local_c.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    if k not in cookie_map:
                        cookie_map[k] = v

    return "; ".join(f"{k}={v}" for k, v in cookie_map.items())


def format_bytes(size: int, precision: int = 2) -> str:
    """Formats byte count to human-readable string."""
    power = 1024
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    val = float(size)
    while val >= power and n < 4:
        val /= power
        n += 1
    return f"{val:.{precision}f} {power_labels.get(n, 'B')}"


def extract_filename_from_headers(headers, fallback_url: str = "") -> str:
    """Extracts filename from Google Drive Content-Disposition header."""
    content_disp = headers.get("Content-Disposition", "") if headers else ""
    if content_disp:
        # Check filename* (RFC 5987 UTF-8 encoded)
        m_utf8 = re.search(r"filename\*=UTF-8''([^;\r\n]+)", content_disp, re.IGNORECASE)
        if m_utf8:
            return unquote(m_utf8.group(1).strip().strip('"\''))
        # Check standard filename=
        m_std = re.search(r'filename=["\']?([^";\r\n]+)["\']?', content_disp, re.IGNORECASE)
        if m_std:
            name = m_std.group(1).strip().strip('"\'')
            if name and name.lower() != "download":
                return unquote(name)

    # Fallback to URL parsing
    if fallback_url:
        clean = fallback_url.split("?")[0].split("#")[0]
        base = clean.split("/")[-1]
        if base and base.lower() not in ("download", "uc"):
            return unquote(base)

    return "Google_Drive_File"


def process_gdrive_download(url: str, user_agent: str = None, cookies: str = None, referrer: str = None) -> dict:
    """
    Specialized pre-fetcher and resolver for Google Drive downloads.
    Extracts binary attachment headers, handles cookie authentication, and follows
    Google virus-scan warning forms for large files.
    """
    ua = user_agent or "Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0"
    ref = referrer or "https://drive.google.com/"
    auth_cookies = merge_gdrive_cookies(cookies)

    result = {
        "url": url,
        "filename": "Google_Drive_File",
        "size_str": "Unknown",
        "size_bytes": 0,
        "user_agent": ua,
        "cookies": auth_cookies,
        "referer": ref,
        "error": None
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    current_url = url
    for _ in range(5):
        headers = {
            "User-Agent": ua,
            "Cookie": auth_cookies,
            "Referer": ref,
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-site",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            req = urllib.request.Request(current_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                final_url = resp.geturl()
                resp_headers = resp.headers
                content_type = (resp_headers.get("Content-Type") or "").lower()
                content_disp = resp_headers.get("Content-Disposition") or ""

                # Direct binary attachment found!
                if content_disp or ("text/html" not in content_type and "application/xhtml+xml" not in content_type):
                    result["url"] = final_url
                    result["filename"] = extract_filename_from_headers(resp_headers, final_url)
                    cl = resp_headers.get("Content-Length")
                    if cl and cl.isdigit():
                        result["size_bytes"] = int(cl)
                        result["size_str"] = format_bytes(result["size_bytes"])
                    result["error"] = None
                    return result

                # Inspect HTML response for virus scan confirmation form or redirect
                text = resp.read(65536).decode("utf-8", errors="ignore")

                # Check if login required
                if "accounts.google.com" in final_url or "Google Drive: Sign-in" in text:
                    result["error"] = "Google Drive login required. Session cookies were missing or expired."
                    return result

                # Check for Google Drive virus scan warning download confirmation link / form
                confirm_match = re.search(r'id=["\']uc-download-link["\'][^>]*href=["\']([^"\']+)["\']', text, re.IGNORECASE) or \
                                re.search(r'action=["\'](https://[^"\']*googleusercontent\.com/[^"\']+)["\']', text, re.IGNORECASE)
                if confirm_match:
                    clean_link = confirm_match.group(1).replace("&amp;", "&").strip()
                    if clean_link.startswith("/"):
                        clean_link = "https://drive.google.com" + clean_link
                    current_url = clean_link
                    continue

                # Plain landing page
                result["error"] = "Target is a Google Drive webpage, not a direct file."
                return result

        except Exception as e:
            result["error"] = str(e)
            break

    return result
