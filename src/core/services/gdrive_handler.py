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
import http.cookiejar
import urllib.request
from urllib.parse import urlparse, unquote, urlsplit, urlunsplit, parse_qs, urlencode, urljoin


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
    # 1. Foundation: pull credentials from local browser profile
    local_c = get_local_gdrive_cookies()
    if local_c:
        for part in local_c.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookie_map[k] = v

    # 2. Overlay: existing cookies provided with request (latest session / tokens)
    if existing_cookies:
        for part in existing_cookies.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
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


def extract_gdrive_confirmation(html_text: str, current_url: str) -> tuple[str | None, str | None]:
    """
    Extracts the confirmation download URL and filename from Google Drive virus scan
    warning pages for large or dangerous/flagged files.
    """
    if not html_text:
        return None, None

    filename = None
    # 1. Try extracting filename from HTML warning page
    for pat in [
        r'class=["\']uc-name-size["\'][^>]*><a[^>]*>([^<]+)</a>',
        r'class=["\']uc-name-size["\'][^>]*>([^<(]+)',
        r'<strong>([^<]+)</strong>',
        r'<title>([^<]+) - Google Drive</title>',
        r'<title>Google Drive - ([^<]+)</title>'
    ]:
        m = re.search(pat, html_text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if cand and cand.lower() not in ("google drive", "download", "download anyway", "download infected file", "virus scan warning"):
                filename = cand
                break

    # 2. Extract confirmation form (e.g. #download-form or action=".../download")
    form_m = re.search(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</form>', html_text, re.IGNORECASE)
    if form_m:
        action = form_m.group(1).replace("&amp;", "&").strip()
        form_inner = form_m.group(2)
        action_url = urljoin(current_url, action)

        inputs = {}
        input_tags = re.findall(r'<input\b[^>]*>', form_inner, re.IGNORECASE)
        for tag in input_tags:
            name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            val_m = re.search(r'\bvalue=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            type_m = re.search(r'\btype=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            input_type = type_m.group(1).lower() if type_m else "text"
            if name_m:
                name = name_m.group(1)
                val = val_m.group(1) if val_m else ""
                # Do not send submit buttons unless it's explicitly confirm
                if input_type != "submit" or name == "confirm":
                    inputs[name] = val

        # Ensure confirm=t is present
        if "confirm" not in inputs:
            inputs["confirm"] = "t"

        url_parts = list(urlsplit(action_url))
        query_dict = parse_qs(url_parts[3])
        for k, v in inputs.items():
            query_dict[k] = [v]
        url_parts[3] = urlencode(query_dict, doseq=True)
        confirmed_url = urlunsplit(url_parts)
        return confirmed_url, filename

    # 3. Check for direct uc-download-link or export=download anchor
    link_m = (
        re.search(r'id=["\']uc-download-link["\'][^>]*href=["\']([^"\']+)["\']', html_text, re.IGNORECASE) or
        re.search(r'href=["\'](/uc\?export=download[^"\']+)["\']', html_text, re.IGNORECASE) or
        re.search(r'href=["\'](https://[^"\']*(?:googleusercontent\.com|drive\.google\.com)/download[^"\']+)["\']', html_text, re.IGNORECASE)
    )
    if link_m:
        raw_href = link_m.group(1).replace("&amp;", "&").strip()
        full_url = urljoin(current_url, raw_href)
        if "confirm=" not in full_url:
            sep = "&" if "?" in full_url else "?"
            full_url += f"{sep}confirm=t"
        return full_url, filename

    # 4. Check for JSON embedded downloadUrl
    json_m = re.search(r'["\']downloadUrl["\']:\s*["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    if json_m:
        raw_url = json_m.group(1).replace(r'\u003d', '=').replace(r'\u0026', '&').replace(r'\/', '/')
        full_url = urljoin(current_url, raw_url)
        if "confirm=" not in full_url:
            sep = "&" if "?" in full_url else "?"
            full_url += f"{sep}confirm=t"
        return full_url, filename

    # 5. Fallback: If current_url has a file id, construct confirmation query
    id_m = re.search(r'[?&]id=([a-zA-Z0-9_-]{15,})', current_url) or re.search(r'/d/([a-zA-Z0-9_-]{15,})', current_url)
    if id_m:
        fid = id_m.group(1)
        return f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t", filename

    return None, filename


def process_gdrive_download(url: str, user_agent: str = None, cookies: str = None, referrer: str = None) -> dict:
    """
    Specialized pre-fetcher and resolver for Google Drive downloads.
    Extracts binary attachment headers, handles cookie authentication, and follows
    Google virus-scan warning forms for large files and dangerous/infected files.
    """
    ua = user_agent or "Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0"
    ref = referrer or "https://drive.google.com/"
    auth_cookies = merge_gdrive_cookies(cookies)

    # Use CookieJar with HTTPCookieProcessor so session and download_warning cookies
    # are preserved across confirmation redirects
    cookie_jar = http.cookiejar.CookieJar()
    
    # Pre-load merged cookies into cookie_jar for Google domains
    if auth_cookies:
        for domain in (".google.com", ".googleusercontent.com", "drive.google.com", "drive.usercontent.google.com"):
            for part in auth_cookies.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    c = http.cookiejar.Cookie(
                        version=0, name=k, value=v, port=None, port_specified=False,
                        domain=domain, domain_specified=True, domain_initial_dot=domain.startswith("."),
                        path="/", path_specified=True, secure=True, expires=None,
                        discard=True, comment=None, comment_url=None, rest={}, rfc2109=False
                    )
                    cookie_jar.set_cookie(c)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    cookie_processor = urllib.request.HTTPCookieProcessor(cookie_jar)
    opener = urllib.request.build_opener(cookie_processor, urllib.request.HTTPSHandler(context=ctx))

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

    current_url = url
    for _ in range(5):
        # Format current cookies from cookie_jar
        current_cookie_str = "; ".join(f"{c.name}={c.value}" for c in cookie_jar) if list(cookie_jar) else auth_cookies

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": ref,
            "Cookie": current_cookie_str,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-site",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            req = urllib.request.Request(current_url, headers=headers)
            with opener.open(req, timeout=15) as resp:
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
                    # Export complete cookies including download_warning token
                    full_cookies = "; ".join(f"{c.name}={c.value}" for c in cookie_jar) if list(cookie_jar) else current_cookie_str
                    result["cookies"] = full_cookies
                    result["error"] = None
                    return result

                # Read entire HTML response (up to 1MB)
                text = resp.read(1048576).decode("utf-8", errors="ignore")

                # Check if login required
                if "accounts.google.com" in final_url or "Google Drive: Sign-in" in text:
                    result["error"] = "Google Drive login required. Session cookies were missing or expired."
                    return result

                # Parse confirmation URL and possible filename from virus/dangerous file warning
                confirm_url, html_filename = extract_gdrive_confirmation(text, final_url)
                if html_filename and result["filename"] == "Google_Drive_File":
                    result["filename"] = html_filename

                if confirm_url and confirm_url != current_url:
                    current_url = confirm_url
                    continue

                # Plain landing page
                result["error"] = "Target is a Google Drive webpage, not a direct file."
                return result

        except Exception as e:
            result["error"] = str(e)
            break

    return result

