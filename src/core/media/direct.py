"""
Direct Media Download Method
============================
Downloads an already-muxed progressive stream URL exactly as the browser plays it,
using the Aria2 engine only. No yt-dlp extraction, no FFmpeg muxing, no probing.
"""

import json
import logging
import os
import re
import subprocess
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from core.config import load_category_config
from core.utils import (
    get_unique_filepath,
    get_user_downloads_dir,
    is_generic_media_title,
    sanitize_media_filename,
)

logger = logging.getLogger("bengal.media.direct")

METHOD_STANDARD = "standard"
METHOD_DIRECT = "direct"

_MANIFEST_RE = re.compile(r"\.(m3u8|mpd|m4s)(?:[?#]|$)", re.IGNORECASE)
_SEGMENT_PATH_RE = re.compile(r"\.(ts|m2ts)(?:[?#]|$)", re.IGNORECASE)
_SEGMENT_PARAM_RE = re.compile(
    r"[?&](range|rn|rbuf|sq|sabr|bytestart|byteend)=", re.IGNORECASE
)
_EXT_RE = re.compile(r"^[a-z0-9]{1,5}$")
_URL_EXT_RE = re.compile(r"\.([a-z0-9]{1,5})$", re.IGNORECASE)
_AUDIO_EXTS = {"aac", "flac", "m4a", "mp3", "ogg", "opus", "wav", "weba"}
_HTML_EXTS = {".htm", ".html", ".xhtml", ".php", ".asp", ".aspx", ".jsp"}

_RESOLVE_TIMEOUT_SEC = 90
# A muxed format already contains audio, so the transfer stays a single Aria2 job with
# no FFmpeg merge. Direct HTTP protocols only: muxed HLS/DASH variants are playlists and
# would not fetch a whole file over Aria2.
_MUXED_SELECTOR = (
    "best[protocol^=http][ext=mp4][acodec!=none][vcodec!=none]/"
    "best[protocol^=http][acodec!=none][vcodec!=none]/"
    "best[acodec!=none][vcodec!=none]"
)


def is_direct_method(method: str) -> bool:
    return str(method or "").strip().lower() == METHOD_DIRECT


def _normalize_ext(ext: str) -> str:
    value = str(ext or "").strip().lower().lstrip(".")
    if not value or not _EXT_RE.match(value):
        return ""
    return f".{value}"


def _ext_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
    except Exception:
        return ""
    match = _URL_EXT_RE.search(path or "")
    return _normalize_ext(match.group(1)) if match else ""


def is_direct_downloadable_url(url: str) -> bool:
    """True only for plain HTTP(S) files that can be fetched as-is (no manifests/pages)."""
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    path = (parsed.path or "").lower()
    if not path or path == "/":
        return False
    searchable = path + "?" + (parsed.query or "")
    if _MANIFEST_RE.search(searchable.lower()):
        return False
    # Range/segment URLs fetch only a fragment of the media, never a usable file.
    if _SEGMENT_PARAM_RE.search(searchable):
        return False
    if _SEGMENT_PATH_RE.search(path) or "/sq/" in path:
        return False
    if path.endswith("/"):
        return False
    if os.path.splitext(path)[1] in _HTML_EXTS and "videoplayback" not in path:
        return False
    return True


def build_direct_filename(title: str, url: str, ext: str = "", fallback_ext: str = ".mp4") -> str:
    requested_ext = _normalize_ext(ext) or _ext_from_url(url) or fallback_ext
    base = str(title or "").strip()
    if not base or is_generic_media_title(base):
        base = "video"

    stem, tail = os.path.splitext(base)
    if tail and _normalize_ext(tail):
        base = stem or "video"

    return sanitize_media_filename(base, requested_ext)


def _prepare_resolved_url(url: str) -> str:
    """Return a whole-file URL, or "" when the URL can only fetch a fragment.

    yt-dlp can print URLs with a ``range`` query parameter for some formats; dropping it
    restores a full-file fetch unless the signature itself binds ``range`` (``sparams``).
    """
    try:
        parts = urlsplit(str(url or "").strip())
    except Exception:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if any(key == "range" for key, _ in pairs):
        sparams = next((value for key, value in pairs if key == "sparams"), "")
        if "range" in {item.strip() for item in sparams.split(",")}:
            return ""
        pairs = [(key, value) for key, value in pairs if key != "range"]
        parts = parts._replace(query=urlencode(pairs))

    candidate = urlunsplit(parts)
    return candidate if is_direct_downloadable_url(candidate) else ""


def _resolve_from_info(info: dict) -> dict | None:
    entries = []
    requested = info.get("requested_downloads")
    if isinstance(requested, list):
        entries.extend(item for item in requested if isinstance(item, dict))
    entries.append(info)

    for entry in entries:
        resolved = _prepare_resolved_url(entry.get("url"))
        if not resolved:
            continue
        ext = str(entry.get("ext") or info.get("ext") or "").strip().lower()
        size_bytes = entry.get("filesize") or entry.get("filesize_approx") or 0
        try:
            size_bytes = max(0, int(size_bytes or 0))
        except (TypeError, ValueError):
            size_bytes = 0
        return {
            "url": resolved,
            "ext": f".{ext}" if _EXT_RE.match(ext) else "",
            "sizeBytes": size_bytes,
        }
    return None


def resolve_single_file_url(
    page_url: str, cookies: str = "", user_agent: str = "", referrer: str = "",
    video_itag: str | None = None, audio_itag: str | None = None
) -> dict | None:
    """Resolve one muxed (video+audio) stream URL for a media page.

    Modern YouTube players only hand out ciphered or SABR-only formats, which Aria2
    cannot download directly. The already-installed yt-dlp engine is used solely to
    resolve one progressive URL; the transfer itself still runs in Aria2 and nothing is
    merged or probed with FFmpeg. Returns ``{"url", "ext", "sizeBytes"}`` or ``None``.
    """
    if not isinstance(page_url, str) or not page_url.lower().startswith(("http://", "https://")):
        return None

    temp_cookie_file = ""
    try:
        from core.config import load_category_config
        from core.media.dependencies import BIN_DIR, YtDlpManager
        from core.media.extractor import get_js_runtime_args
        from core.media.pot_provider import (
            get_pot_env,
            get_pot_extractor_args,
            get_pot_plugin_args,
            get_youtube_player_client_args,
        )
        from core.utils import get_clean_env

        try:
            yt_dlp_bin = YtDlpManager.ensure_binary()
        except Exception:
            logger.exception("[Direct] yt-dlp engine is unavailable for URL resolution")
            return None

        cfg = load_category_config() or {}
        media_defaults = cfg.get("media_downloader_defaults", {}) or {}
        client = str(media_defaults.get("youtube_player_client") or "auto").strip() or "auto"

        # Build format selector: specific itags when requested (YouTube SABR), else muxed selector
        if video_itag:
            if audio_itag:
                format_selector = f"{video_itag}+{audio_itag}"
            else:
                format_selector = video_itag
        else:
            format_selector = _MUXED_SELECTOR

        cmd = [
            yt_dlp_bin,
            "-j",
            "--no-playlist",
            "--no-warnings",
            "--remote-components", "ejs:github",
            "-f", format_selector,
        ]
        cmd.extend(get_youtube_player_client_args(cfg, client))
        cmd.extend(get_js_runtime_args())
        cmd.extend(get_pot_plugin_args())
        cmd.extend(get_pot_extractor_args(cfg))

        if referrer:
            cmd.extend(["--referer", str(referrer)])
        if user_agent:
            cmd.extend(["--user-agent", str(user_agent)])
        if cookies:
            from core.media.worker import create_temp_netscape_cookie_file

            temp_cookie_file = create_temp_netscape_cookie_file(str(cookies), page_url)
            if temp_cookie_file:
                cmd.extend(["--cookies", temp_cookie_file])

        cmd.append(page_url)

        env = get_clean_env(str(BIN_DIR))
        env.update(get_pot_env())

        logger.info("[Direct] Resolving a muxed stream URL for %s", page_url[:200])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_RESOLVE_TIMEOUT_SEC,
            env=env,
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
            logger.warning("[Direct] yt-dlp could not resolve a muxed URL: %s", stderr_tail[0][:300])
            return None

        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            logger.warning("[Direct] yt-dlp returned no metadata for %s", page_url[:200])
            return None

        try:
            info = json.loads(lines[-1])
        except json.JSONDecodeError:
            logger.warning("[Direct] yt-dlp returned unparseable metadata")
            return None
        if not isinstance(info, dict):
            return None

        resolved = _resolve_from_info(info)
        if not resolved:
            logger.info("[Direct] No directly downloadable muxed URL for %s", page_url[:200])
        return resolved
    except subprocess.TimeoutExpired:
        logger.warning("[Direct] yt-dlp URL resolution timed out after %ss", _RESOLVE_TIMEOUT_SEC)
        return None
    except Exception:
        logger.exception("[Direct] Failed to resolve a direct stream URL")
        return None
    finally:
        if temp_cookie_file:
            try:
                os.remove(temp_cookie_file)
            except OSError:
                pass


def _resolve_save_dir(filename: str) -> str:
    ext = os.path.splitext(filename)[1].replace(".", "").lower()
    categories = load_category_config().get("categories", {}) or {}
    target = "Music" if ext in _AUDIO_EXTS else "Video"
    if target not in categories:
        target = "General"
        for cat_name, cat_data in categories.items():
            if ext in str(cat_data.get("extensions", "")).split():
                target = cat_name
                break

    save_dir = categories.get(target, {}).get("path") or get_user_downloads_dir()
    if not os.path.exists(save_dir):
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception:
            save_dir = get_user_downloads_dir()
    return save_dir


def _ensure_aria2(main_window) -> bool:
    try:
        from core.aria2_daemon import get_aria2_daemon_manager

        manager = getattr(main_window, "aria2_daemon_manager", None) or get_aria2_daemon_manager()
        if not manager.is_running():
            logger.info("[Direct] Aria2 daemon is not running; starting it before dispatch...")
            starter = getattr(main_window, "start_aria2_daemon", None)
            if callable(starter):
                starter()
            else:
                manager.start()
        if manager.is_running():
            return True
    except Exception:
        logger.exception("[Direct] Failed to start the Aria2 daemon")

    logger.error("[Direct] Aria2 engine is unavailable; Direct download cancelled.")
    try:
        from PyQt6.QtCore import QCoreApplication

        notice = QCoreApplication.translate(
            "MainWindow", "Aria2 engine unavailable - Direct download cancelled."
        )
        main_window.statusBar().showMessage(notice, 5000)
    except Exception:
        pass
    return False


def start_direct_download(main_window, payload: dict) -> bool:
    """Dispatch a browser-captured muxed stream to Aria2.

    Returns True when the request was handled (including an Aria2 failure, which must not
    fall through to the yt-dlp path), and False only when the URL is not directly fetchable.
    """
    payload = payload or {}
    url = str(payload.get("url") or "").strip()
    if payload.get("pageExtract"):
        # Resolution-select Direct tiers send the media page, not a stream file: the
        # media pipeline extracts the chosen quality and Aria2 performs the transfer.
        logger.info("[Direct] Page-based resolution request; deferring to media extraction")
        return False
    if not is_direct_downloadable_url(url):
        logger.info("[Direct] Unsupported direct URL; deferring to Standard: %s", url[:200])
        return False

    if not _ensure_aria2(main_window):
        return True

    title = payload.get("title") or payload.get("filename") or ""
    filename = build_direct_filename(title, url, payload.get("ext") or "")
    unique_path = get_unique_filepath(os.path.join(_resolve_save_dir(filename), filename))
    size_str = str(payload.get("sizeStr") or "").strip()

    logger.info("[Direct] Dispatching to Aria2: %s -> %s", url[:200], unique_path)
    main_window.start_download(
        url,
        custom_filename=os.path.basename(unique_path),
        custom_save_dir=os.path.dirname(unique_path),
        size_data=(size_str,) if size_str else None,
        show_dialog=None,
        user_agent=payload.get("userAgent") or None,
        cookies=payload.get("cookies") or None,
        referer=payload.get("referrer") or url,
        prefetch=False,
        supports_range=True,
    )
    return True
