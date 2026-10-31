"""
SABR Session Downloads
======================
Streams the browser-captured YouTube SABR ABR session with a Deno helper
(googlevideo SabrStream) instead of resolving it through yt-dlp. The helper
writes separate video/audio MP4 parts; the desktop muxes them with FFmpeg.
"""

import base64
import binascii
import json
import logging
import os
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse

from core.media.dependencies import BIN_DIR, get_tool_path
from core.media.pot_provider import get_deno_executable_path
from core.utils import get_clean_env, get_data_dir

logger = logging.getLogger("bengal.media.sabr")

_MAX_SESSION_BYTES = 4 * 1024 * 1024
_VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")
_CONFIG_RE = re.compile(r"^[A-Za-z0-9_+/=.:-]{1,131072}$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")

_CAPABILITY_CACHE = {"ts": 0.0, "value": False}
_CAPABILITY_TTL_SEC = 30


def _is_sabr_stream_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and not parsed.username and not parsed.password
        and (host == "googlevideo.com" or host.endswith(".googlevideo.com"))
        and parsed.path == "/videoplayback"
        and "sabr=1" in (parsed.query or "").split("&")
    )


def _to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_sabr_session(obj) -> dict | None:
    """Port of awesome-downloader normalizeSabrSession input checks.

    Returns the normalized session (both raw track dicts selected by itag) or None.
    """
    if not isinstance(obj, dict):
        return None
    if not _VIDEO_ID_RE.match(str(obj.get("videoId") or "")):
        return None
    if not _is_sabr_stream_url(obj.get("serverAbrStreamingUrl") or ""):
        return None
    config = obj.get("videoPlaybackUstreamerConfig")
    if not isinstance(config, str) or not _CONFIG_RE.match(config):
        return None

    raw_formats = obj.get("formats")
    if not isinstance(raw_formats, list) or not raw_formats or len(raw_formats) > 150:
        return None
    formats = []
    for item in raw_formats:
        if not isinstance(item, dict):
            return None
        itag = _to_int(item.get("itag"))
        mime = str(item.get("mimeType") or "")
        if itag is None or itag < 0 or not mime:
            return None
        formats.append(item)

    audio_itag = _to_int(obj.get("audioItag"))
    if audio_itag is None:
        return None
    # An itag is shared by dubbed languages, DRC and voice-boost variants: keep precisely
    # the chosen default audio and video, not every matching itag.
    audio_candidates = [
        f for f in formats
        if _to_int(f.get("itag")) == audio_itag
        and "audio/mp4" in str(f.get("mimeType") or "").lower()
        and not f.get("isDrc") and not f.get("isVb")
    ]
    audio = (
        next((f for f in audio_candidates if (f.get("audioTrack") or {}).get("audioIsDefault")), None)
        or next((f for f in audio_candidates if not f.get("audioTrack")), None)
        or (audio_candidates[0] if audio_candidates else None)
    )
    if not audio:
        return None

    video_itag = _to_int(obj.get("videoItag")) if obj.get("videoItag") not in (None, "") else None
    if video_itag is not None:
        video = next(
            (f for f in formats
             if _to_int(f.get("itag")) == video_itag
             and "video/mp4" in str(f.get("mimeType") or "").lower()),
            None,
        )
        if not video:
            return None
    else:
        video = None

    request_body = obj.get("requestBody")
    if request_body not in (None, ""):
        if not isinstance(request_body, str) or len(request_body) > 350000 or not _B64_RE.match(request_body):
            return None
        try:
            decoded = base64.b64decode(request_body)
        except (binascii.Error, ValueError):
            return None
        if not decoded or len(decoded) > 262144:
            return None

    client = obj.get("clientInfo") if isinstance(obj.get("clientInfo"), dict) else {}
    return {
        "videoId": str(obj["videoId"]),
        "serverAbrStreamingUrl": obj["serverAbrStreamingUrl"],
        "videoPlaybackUstreamerConfig": config,
        "clientInfo": {
            "clientName": _to_int(client.get("clientName"), 1) or 1,
            "clientVersion": str(client.get("clientVersion") or "")[:80],
        },
        "formats": [f for f in (video, audio) if f is not None],
        "videoItag": video_itag,
        "audioItag": audio_itag,
        "requestBody": request_body or None,
    }


def session_size_bytes(session: dict) -> int:
    total = 0
    for item in session.get("formats") or []:
        total += max(0, _to_int(item.get("contentLength"), 0) or 0)
    return total


def get_helper_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sabr_download.mjs")


def sabr_runtime_available() -> bool:
    """True when Deno (Bengal DM tools or system), the helper script, and FFmpeg exist."""
    now = time.monotonic()
    if now - _CAPABILITY_CACHE["ts"] < _CAPABILITY_TTL_SEC:
        return _CAPABILITY_CACHE["value"]
    value = bool(
        get_deno_executable_path()
        and os.path.isfile(get_helper_path())
        and (get_tool_path("ffmpeg") or shutil.which("ffmpeg"))
    )
    _CAPABILITY_CACHE.update(ts=now, value=value)
    return value


def write_session_file(session: dict) -> str:
    """Materialize the validated session as a 0600 temp JSON for the helper process."""
    handle, path = tempfile.mkstemp(prefix="bdm-sabr-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(session, fh, separators=(",", ":"))
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)
    return path


def build_command(session_file: str, video_out: str, audio_out: str) -> list[str]:
    deno = get_deno_executable_path()
    return [
        deno, "run", "--no-lock", "--allow-net", "--allow-read", "--allow-write",
        get_helper_path(),
        "--session", session_file,
        "--video-out", video_out,
        "--audio-out", audio_out,
    ]


def prepare_env() -> dict:
    env = get_clean_env(str(BIN_DIR))
    env["DENO_DIR"] = os.path.join(get_data_dir(), "deno")
    return env
