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
import urllib.error
import urllib.request
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


def _run_ytdlp_json(
    page_url: str, format_selector: str, cookies: str = "", user_agent: str = "", referrer: str = ""
) -> dict | None:
    """Run yt-dlp in metadata-only mode and return the parsed info dict."""
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

        logger.info("[Direct] Resolving stream URLs for %s", page_url[:200])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_RESOLVE_TIMEOUT_SEC,
            env=env,
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
            logger.warning("[Direct] yt-dlp could not resolve stream URLs: %s", stderr_tail[0][:300])
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
        return info if isinstance(info, dict) else None
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


def resolve_single_file_url(
    page_url: str, cookies: str = "", user_agent: str = "", referrer: str = ""
) -> dict | None:
    """Resolve one muxed (video+audio) stream URL for a media page.

    Returns ``{"url", "ext", "sizeBytes"}`` or ``None``. Adaptive tiers carry separate
    tracks and are resolved with :func:`resolve_media_tracks` instead.
    """
    info = _run_ytdlp_json(page_url, _MUXED_SELECTOR, cookies, user_agent, referrer)
    if not info:
        return None
    resolved = _resolve_from_info(info)
    if not resolved:
        logger.info("[Direct] No directly downloadable muxed URL for %s", page_url[:200])
    return resolved


def resolve_media_tracks(
    page_url: str,
    cookies: str = "",
    user_agent: str = "",
    referrer: str = "",
    video_itag: str | None = None,
    audio_itag: str | None = None,
) -> dict | None:
    """Resolve separate video and audio stream URLs for an adaptive media page.

    The selected itags come from the browser's format chooser. yt-dlp only locates the
    signed URLs; both transfers run in Aria2 and FFmpeg muxes the result, so the saved
    file always carries audio. Returns ``{"videoUrl", "videoExt", "videoSize",
    "audioUrl", "audioExt", "audioSize", "muxed"}`` or ``None``.
    """
    video_itag = str(video_itag or "").strip()
    audio_itag = str(audio_itag or "").strip()
    if not video_itag and not audio_itag:
        return None

    if video_itag and audio_itag:
        selector = f"{video_itag}+{audio_itag}"
    elif video_itag:
        selector = f"{video_itag}+bestaudio/best"
    else:
        selector = f"{audio_itag}/bestaudio/best"

    info = _run_ytdlp_json(page_url, selector, cookies, user_agent, referrer)
    if not info:
        return None

    requested = info.get("requested_downloads") or info.get("requested_formats")
    entries = [item for item in requested if isinstance(item, dict)] if requested else []
    if not entries:
        entries = [info]

    video_entry = None
    audio_entry = None
    first_candidate = None
    for entry in entries:
        url = _prepare_resolved_url(entry.get("url"))
        if not url:
            continue
        format_id = str(entry.get("format_id") or "")
        vcodec = str(entry.get("vcodec") or "").lower()
        acodec = str(entry.get("acodec") or "").lower()
        has_video = bool(vcodec and vcodec != "none") or (bool(video_itag) and video_itag in format_id)
        has_audio = bool(acodec and acodec != "none") or (bool(audio_itag) and audio_itag in format_id)

        candidate = {
            "url": url,
            "ext": _normalize_ext(entry.get("ext") or info.get("ext") or ""),
            "sizeBytes": _entry_size(entry),
            "muxed": has_video and has_audio,
        }
        if first_candidate is None:
            first_candidate = candidate
        if has_video and not has_audio and video_entry is None:
            video_entry = candidate
        elif has_audio and not has_video and audio_entry is None:
            audio_entry = candidate
        elif has_video and has_audio and video_entry is None:
            # A muxed fallback already contains audio; no FFmpeg merge needed.
            video_entry = candidate

    if video_entry is None and audio_entry is None and first_candidate:
        if video_itag:
            video_entry = first_candidate
        else:
            audio_entry = first_candidate

    if video_entry and not audio_entry:
        if video_entry["muxed"]:
            # The resolved entry already contains audio; a single Aria2 transfer is enough.
            return {
                "videoUrl": video_entry["url"],
                "videoExt": video_entry["ext"] or ".mp4",
                "videoSize": video_entry["sizeBytes"],
                "audioUrl": "",
                "audioExt": "",
                "audioSize": 0,
                "muxed": True,
            }
        logger.warning("[Direct] No audio track resolved for %s; refusing a silent download", page_url[:200])
        return None
    if not video_entry and not audio_entry:
        logger.info("[Direct] No downloadable tracks resolved for %s", page_url[:200])
        return None

    if video_entry and audio_entry:
        return {
            "videoUrl": video_entry["url"],
            "videoExt": video_entry["ext"] or ".mp4",
            "videoSize": video_entry["sizeBytes"],
            "audioUrl": audio_entry["url"],
            "audioExt": audio_entry["ext"] or ".m4a",
            "audioSize": audio_entry["sizeBytes"],
            "muxed": False,
        }

    # Audio-only selection.
    return {
        "videoUrl": "",
        "videoExt": "",
        "videoSize": 0,
        "audioUrl": audio_entry["url"],
        "audioExt": audio_entry["ext"] or ".m4a",
        "audioSize": audio_entry["sizeBytes"],
        "muxed": False,
    }


def _entry_size(entry: dict) -> int:
    size = entry.get("filesize") or entry.get("filesize_approx") or 0
    try:
        return max(0, int(size or 0))
    except (TypeError, ValueError):
        return 0


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


def _format_bytes(num: int) -> str:
    """Human-readable byte size."""
    if not num or num <= 0:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:.2f} {unit}" if unit == "B" else f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def _fetch_size_bytes(url: str, user_agent: str = "", cookies: str = "", referrer: str = "") -> int:
    """Best-effort Content-Length fetch for a direct stream URL.

    Tries HEAD first, falls back to a ranged GET (bytes=0-0). Returns 0 when the
    size cannot be determined (streaming endpoints often omit Content-Length).
    """
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    if cookies:
        headers["Cookie"] = cookies
    if referrer:
        headers["Referer"] = referrer

    def _headers(req_headers: dict) -> int:
        try:
            req = urllib.request.Request(url, headers=req_headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=3) as resp:
                cl = resp.headers.get("Content-Length") or resp.headers.get("content-length")
                if cl:
                    return int(cl)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            pass
        return 0

    try:
        return _headers(headers)
    except Exception:
        return 0


def _start_sabr_download(main_window, payload: dict, session: dict) -> bool:
    """Dispatch a browser-captured SABR session to the Deno SabrStream worker.

    No aria2 involvement: the helper streams both MP4 tracks and the worker muxes
    them with FFmpeg, so the daemon never needs to be started for these rows.
    """
    from core.media.sabr import session_size_bytes

    silent = getattr(main_window, "settings", {}).get("silent_download", False)
    show_start = getattr(main_window, "settings", {}).get("show_start_dialog", True)
    show_dialog = (not silent) and show_start

    url = session["serverAbrStreamingUrl"]
    title = payload.get("title") or payload.get("filename") or ""
    ext = payload.get("ext") or ".mp4"
    filename = build_direct_filename(title, url, ext)
    unique_path = get_unique_filepath(os.path.join(_resolve_save_dir(filename), filename))
    size_bytes = int(payload.get("sizeBytes") or 0) or session_size_bytes(session)
    size_str = str(payload.get("sizeStr") or "").strip() or (
        _format_bytes(size_bytes) if size_bytes else ""
    )

    logger.info(
        "[SABR] Streaming session for video %s -> %s (itag=%s+%s, size=%s)",
        session.get("videoId"), unique_path,
        session.get("videoItag"), session.get("audioItag"), size_str or size_bytes,
    )

    start_kwargs = {
        "custom_filename": os.path.basename(unique_path),
        "custom_save_dir": os.path.dirname(unique_path),
        "size_data": (size_str,) if size_str else None,
        "show_dialog": False,
        "user_agent": payload.get("userAgent") or None,
        "cookies": payload.get("cookies") or None,
        "referer": payload.get("referrer") or "https://www.youtube.com/",
        "prefetch": False,
        "supports_range": False,
        "sabr_session": session,
    }

    if show_dialog:
        file_info = {
            "url": url,
            "filename": filename,
            "size_str": size_str or "Unknown",
            "size_bytes": size_bytes,
            "user_agent": payload.get("userAgent") or None,
            "cookies": payload.get("cookies") or None,
            "referer": payload.get("referrer") or "https://www.youtube.com/",
            "supports_range": False,
        }
        file_info.update(start_kwargs)
        main_window.on_file_info_fetched(file_info)
    else:
        main_window.start_download(url, **start_kwargs)
    return True


def start_direct_download(main_window, payload: dict) -> bool:
    """Dispatch a browser-selected stream pair to the Aria2 engine.

    Adaptive picks carry a separate audio URL; both tracks are transferred through Aria2
    and muxed locally so the saved file always contains audio. Returns False only when
    the URLs are not directly fetchable (the caller must not fall back to yt-dlp).
    """
    payload = payload or {}
    url = str(payload.get("url") or "").strip()
    audio_url = str(payload.get("audioUrl") or "").strip()

    # A browser-captured SABR session streams through the Deno helper instead of aria2.
    # Its ?sabr=1 POST URL intentionally fails is_direct_downloadable_url, so check first.
    raw_sabr = payload.get("sabr")
    if isinstance(raw_sabr, dict) and raw_sabr:
        from core.media.sabr import validate_sabr_session

        sabr_session = validate_sabr_session(raw_sabr)
        if sabr_session:
            return _start_sabr_download(main_window, payload, sabr_session)
        logger.warning("[SABR] Rejected malformed session payload from the extension")

    if not is_direct_downloadable_url(url):
        logger.info("[Direct] Unsupported direct URL: %s", url[:200])
        return False
    if audio_url and not is_direct_downloadable_url(audio_url):
        logger.warning("[Direct] Unsupported audio stream URL: %s", audio_url[:200])
        return False

    if not _ensure_aria2(main_window):
        return True

    # Respect options like other downloads: follow "Show start download dialog" rule
    silent = getattr(main_window, "settings", {}).get("silent_download", False)
    show_start = getattr(main_window, "settings", {}).get("show_start_dialog", True)
    show_dialog = (not silent) and show_start

    title = payload.get("title") or payload.get("filename") or ""
    ext = ".mp4" if audio_url else (payload.get("ext") or "")
    filename = build_direct_filename(title, url, ext)
    unique_path = get_unique_filepath(os.path.join(_resolve_save_dir(filename), filename))
    size_bytes = int(payload.get("sizeBytes") or 0)
    size_str = str(payload.get("sizeStr") or "").strip()

    # Fetch size when the extension did not provide one, so the file info dialog
    # shows an accurate size instead of "Unknown".
    if not size_bytes and not size_str:
        ua = payload.get("userAgent") or ""
        ck = payload.get("cookies") or ""
        ref = payload.get("referrer") or url
        fetched = _fetch_size_bytes(url, ua, ck, ref)
        if fetched:
            size_bytes = fetched
            size_str = _format_bytes(fetched)

    log_target = f"{url[:120]} (+ audio)" if audio_url else url[:200]
    logger.info("[Direct] Dispatching to Aria2: %s -> %s (silent=%s, show_start=%s, show_dialog=%s, size=%s)",
                log_target, unique_path, silent, show_start, show_dialog, size_str or size_bytes)

    # Bundle every start_download argument so the file info dialog (when shown)
    # and the direct dispatch path carry identical metadata.
    start_kwargs = {
        "custom_filename": os.path.basename(unique_path),
        "custom_save_dir": os.path.dirname(unique_path),
        "size_data": (size_str,) if size_str else None,
        "show_dialog": False,
        "user_agent": payload.get("userAgent") or None,
        "cookies": payload.get("cookies") or None,
        "referer": payload.get("referrer") or url,
        "prefetch": False,
        "supports_range": True,
        "direct_audio_url": audio_url or None,
    }

    if show_dialog:
        # Show the file info dialog like standard downloads do, respecting the
        # "Show start download dialog" option checkmark.
        file_info = {
            "url": url,
            "filename": filename,
            "size_str": size_str or "Unknown",
            "size_bytes": size_bytes,
            "user_agent": payload.get("userAgent") or None,
            "cookies": payload.get("cookies") or None,
            "referer": payload.get("referrer") or url,
            "supports_range": True,
        }
        file_info.update(start_kwargs)
        main_window.on_file_info_fetched(file_info)
    else:
        main_window.start_download(url, **start_kwargs)
    return True
