"""
Media Extractor Module
======================
Handles probing remote media URLs, fetching metadata JSON via yt-dlp,
and parsing audio/video formats and playlist tracks.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils import get_clean_env, sanitize_media_url, is_debug_mode
from core.config import load_category_config
from core.media.dependencies import (
    BIN_DIR,
    YtDlpManager,
    get_tool_path,
)

logger = logging.getLogger("bengal.media.extractor")

_ACTIVE_WORKER_THREADS = set()


def _keep_thread_alive(thread: QThread):
    """Retains reference to worker threads to prevent garbage collection while active."""
    _ACTIVE_WORKER_THREADS.add(thread)
    thread.finished.connect(lambda: _ACTIVE_WORKER_THREADS.discard(thread))


class MediaExtractorWorker(QThread):
    """Background worker thread to fetch and parse video/playlist metadata using yt-dlp."""

    status_signal = pyqtSignal(str)
    single_video_analyzed = pyqtSignal(dict)
    playlist_analyzed = pyqtSignal(dict)
    analysis_failed = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        referrer: Optional[str] = None,
        user_agent: Optional[str] = None,
        cookies: Optional[str] = None,
    ):
        super().__init__()
        self.url = sanitize_media_url(url)
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.referrer = referrer
        self.user_agent = user_agent
        self.cookies = cookies
        self.process = None
        self.is_running = True
        _keep_thread_alive(self)

    def stop(self):
        self.is_running = False
        if hasattr(self, "process") and self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass

    def run(self):
        temp_cookies_file = None
        try:
            self.status_signal.emit("Checking yt-dlp engine...")
            yt_dlp_bin = YtDlpManager.ensure_binary(progress_callback=lambda msg: self.status_signal.emit(msg))

            self.status_signal.emit("Analyzing media URL metadata...")

            import sys
            md = sys.modules.get("core.media_downloader")
            cfg_fn = getattr(md, "load_category_config", load_category_config) if md else load_category_config
            subp = getattr(md, "subprocess", subprocess) if md else subprocess
            env_fn = getattr(md, "get_clean_env", get_clean_env) if md else get_clean_env

            bin_dir = str(BIN_DIR)
            clean_env = env_fn(bin_dir)
            is_debug = "--debug" in sys.argv or os.environ.get("DEBUG") == "1" or logger.isEnabledFor(logging.DEBUG)

            try:
                cfg = cfg_fn()
                media_defaults = cfg.get("media_downloader_defaults", {})
                yt_client = media_defaults.get("youtube_player_client", "default") or "default"
            except Exception:
                cfg = {}
                media_defaults = {}
                yt_client = "default"

            yt_client = yt_client.strip() or "default"

            cmd = [
                yt_dlp_bin,
                "-J",
                "--flat-playlist",
                "--playlist-end", "100",
                "--verbose" if is_debug else "--no-warnings",
                "--remote-components", "ejs:github",
                "--extractor-args", f"youtube:player_client={yt_client}",
            ]
            cmd.extend(get_js_runtime_args())

            ffmpeg_bin = get_tool_path("ffmpeg") or shutil.which("ffmpeg")
            if ffmpeg_bin:
                cmd.extend(["--ffmpeg-location", ffmpeg_bin])
            elif os.path.exists(bin_dir):
                cmd.extend(["--ffmpeg-location", bin_dir])

            if self.referrer:
                cmd.extend(["--referer", self.referrer])
                try:
                    from urllib.parse import urlparse
                    p_ref = urlparse(self.referrer)
                    if p_ref.scheme and p_ref.netloc:
                        cmd.extend(["--add-header", f"Origin:{p_ref.scheme}://{p_ref.netloc}"])
                except Exception:
                    pass

            if self.user_agent:
                cmd.extend(["--user-agent", self.user_agent])

            # Supply standard browser headers (Accept-Language) to satisfy strict CDNs
            cmd.extend(["--add-header", "Accept-Language:en-US,en;q=0.9"])

            effective_cookies_file = self.cookies_file
            if not effective_cookies_file:
                opt_cpath = cfg.get("media_downloader_cookies_path") or media_defaults.get("cookies_path", "")
                if opt_cpath and os.path.exists(opt_cpath):
                    effective_cookies_file = opt_cpath

            if effective_cookies_file and os.path.exists(str(effective_cookies_file)):
                cmd.extend(["--cookies", str(effective_cookies_file)])
            elif self.cookies_browser and self.cookies_browser.lower() not in ("none", ""):
                cmd.extend(["--cookies-from-browser", self.cookies_browser.lower()])
            elif getattr(self, "cookies", None):
                from core.media.worker import create_temp_netscape_cookie_file
                temp_cookies_file = create_temp_netscape_cookie_file(self.cookies, self.url)
                if temp_cookies_file and os.path.exists(temp_cookies_file):
                    cmd.extend(["--cookies", temp_cookies_file])
                else:
                    cmd.extend(["--add-header", f"Cookie:{self.cookies}"])

            cmd.append(self.url)

            if is_debug:
                logger.debug("[MediaExtractor] Running command: %s", " ".join(cmd))

            self.process = subp.Popen(
                cmd,
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            try:
                stdout, stderr = self.process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                if self.process:
                    try:
                        self.process.kill()
                        stdout, stderr = self.process.communicate()
                    except Exception:
                        pass
                raise RuntimeError("yt-dlp metadata extraction timed out after 30s")

            if self.process.returncode != 0:
                err_text = (stderr or "") + " " + (stdout or "")
                err_lower = err_text.lower()
                has_cookie_err = bool(
                    (self.cookies_browser and self.cookies_browser.lower() not in ("none", ""))
                    or (effective_cookies_file and os.path.exists(str(effective_cookies_file)))
                    or getattr(self, "cookies", None)
                )
                is_bot_or_client_err = any(e in err_lower for e in ("sign in", "bot", "429", "login_required", "format is not available"))

                if has_cookie_err or is_bot_or_client_err:
                    msg = "Retrying clean metadata extraction..."
                    if "bot" in err_lower or "sign in" in err_lower:
                        msg = "YouTube bot check detected, retrying clean extraction..."
                    elif has_cookie_err:
                        msg = "Cookies invalid or rejected, retrying clean metadata extraction..."
                    self.status_signal.emit(msg)

                    clean_cmd = [
                        yt_dlp_bin,
                        "-J",
                        "--flat-playlist",
                        "--playlist-end", "100",
                        "--verbose" if is_debug else "--no-warnings",
                        "--remote-components", "ejs:github",
                        "--extractor-args", f"youtube:player_client={yt_client}",
                        "--add-header", "Accept-Language:en-US,en;q=0.9",
                    ]
                    clean_cmd.extend(get_js_runtime_args())
                    if ffmpeg_bin:
                        clean_cmd.extend(["--ffmpeg-location", ffmpeg_bin])
                    elif os.path.exists(bin_dir):
                        clean_cmd.extend(["--ffmpeg-location", bin_dir])
                    if self.referrer:
                        clean_cmd.extend(["--referer", self.referrer])
                    if self.user_agent:
                        clean_cmd.extend(["--user-agent", self.user_agent])
                    clean_cmd.append(self.url)

                    self.process = subp.Popen(
                        clean_cmd,
                        env=clean_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                    )
                    try:
                        stdout, stderr = self.process.communicate(timeout=30)
                    except subprocess.TimeoutExpired:
                        if self.process:
                            try:
                                self.process.kill()
                                stdout, stderr = self.process.communicate()
                            except Exception:
                                pass
                        raise RuntimeError("Clean metadata extraction retry timed out after 30s")

            if self.process.returncode != 0:
                err_msg = stderr.strip() or stdout.strip() or f"yt-dlp process failed with code {self.process.returncode}"
                logger.error("[MediaExtractor] yt-dlp metadata extraction failed: %s", err_msg)
                self.analysis_failed.emit(err_msg)
                return

            try:
                data = json.loads(stdout)
            except json.JSONDecodeError as json_err:
                logger.error("[MediaExtractor] Failed to parse yt-dlp metadata JSON: %s", json_err)
                self.analysis_failed.emit(f"Failed to parse yt-dlp metadata JSON: {json_err}")
                return

            if data.get("_type") == "playlist" or (isinstance(data.get("entries"), list) and len(data.get("entries")) > 0 and not data.get("formats")):
                parsed_playlist = self._parse_playlist_data(data)
                self.playlist_analyzed.emit(parsed_playlist)
            else:
                parsed_video = self._parse_single_video_data(data)
                self.single_video_analyzed.emit(parsed_video)

        except Exception as e:
            self.analysis_failed.emit(str(e))
        finally:
            if temp_cookies_file and os.path.exists(temp_cookies_file):
                try:
                    os.remove(temp_cookies_file)
                except Exception:
                    pass

    def _parse_single_video_data(self, raw_data: dict) -> dict:
        """Parses raw yt-dlp video JSON output into a structured dictionary."""
        formats = []
        raw_formats = raw_data.get("formats", [])

        for fmt in raw_formats:
            fmt_id = fmt.get("format_id", "")
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec", "none") or "none"
            acodec = fmt.get("acodec", "none") or "none"

            if ext in ("mhtml", "html", "htm") or (vcodec == "none" and acodec == "none"):
                continue

            height = fmt.get("height")
            width = fmt.get("width")
            duration = raw_data.get("duration") or 0
            filesize = fmt.get("filesize") or fmt.get("filesize_approx")
            fps = fmt.get("fps")
            tbr = fmt.get("tbr")
            if not filesize and duration and tbr:
                try:
                    filesize = int(float(duration) * float(tbr) * 125)
                except Exception:
                    filesize = 0
            format_note = fmt.get("format_note", "")
            url = fmt.get("url", "")

            if height:
                res_label = f"{height}p"
            elif width:
                res_label = f"{width}w"
            elif vcodec != "none":
                res_label = "Video"
            else:
                res_label = "Audio Only"

            is_video = vcodec != "none"
            is_audio = acodec != "none"

            formats.append({
                "format_id": fmt_id,
                "ext": ext,
                "vcodec": vcodec,
                "acodec": acodec,
                "height": height or 0,
                "width": width or 0,
                "fps": fps or 0,
                "filesize": filesize or 0,
                "tbr": tbr or 0,
                "res_label": res_label,
                "format_note": format_note,
                "is_video": is_video,
                "is_audio": is_audio,
                "url": url,
                "manifest_url": fmt.get("manifest_url", ""),
            })

        def format_sort_key(fmt):
            is_video = fmt.get("is_video", False)
            height = fmt.get("height", 0) or 0
            tbr = fmt.get("tbr", 0) or 0
            if is_video:
                return (0, -height, -tbr)
            else:
                return (1, 0, -tbr)

        formats.sort(key=format_sort_key)

        thumb = raw_data.get("thumbnail") or ""
        if not thumb and isinstance(raw_data.get("thumbnails"), list) and raw_data.get("thumbnails"):
            thumb = raw_data["thumbnails"][-1].get("url", "")

        return {
            "title": raw_data.get("title") or "Untitled Media",
            "id": raw_data.get("id", ""),
            "uploader": raw_data.get("uploader") or raw_data.get("channel") or "Unknown",
            "duration": raw_data.get("duration", 0),
            "thumbnail": thumb,
            "webpage_url": raw_data.get("webpage_url") or self.url,
            "formats": formats,
        }

    def _parse_playlist_data(self, raw_data: dict) -> dict:
        """Parses playlist yt-dlp JSON output into list of items."""
        entries = []
        raw_entries = raw_data.get("entries", [])

        for idx, entry in enumerate(raw_entries, start=1):
            if not isinstance(entry, dict):
                continue
            item_url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
            entry_thumb = entry.get("thumbnail") or ""
            if not entry_thumb and isinstance(entry.get("thumbnails"), list) and entry.get("thumbnails"):
                entry_thumb = entry["thumbnails"][-1].get("url", "")
            entries.append({
                "index": idx,
                "id": entry.get("id", ""),
                "title": entry.get("title") or f"Item {idx}",
                "duration": entry.get("duration", 0),
                "url": item_url,
                "thumbnail": entry_thumb,
            })

        pl_thumb = raw_data.get("thumbnail") or ""
        if not pl_thumb and isinstance(raw_data.get("thumbnails"), list) and raw_data.get("thumbnails"):
            pl_thumb = raw_data["thumbnails"][-1].get("url", "")
        if not pl_thumb and entries and entries[0].get("thumbnail"):
            pl_thumb = entries[0]["thumbnail"]

        return {
            "title": raw_data.get("title") or "Playlist",
            "total_items": len(entries),
            "thumbnail": pl_thumb,
            "entries": entries,
        }


def get_js_runtime_args() -> list[str]:
    """Return --js-runtimes argument for yt-dlp if node, deno, or bun is available."""
    node_bin = shutil.which("node")
    if node_bin:
        return ["--js-runtimes", f"node:{node_bin}"]
    deno_bin = shutil.which("deno")
    if deno_bin:
        return ["--js-runtimes", f"deno:{deno_bin}"]
    bun_bin = shutil.which("bun")
    if bun_bin:
        return ["--js-runtimes", f"bun:{bun_bin}"]
    return []


def get_installed_browser_for_cookies() -> Optional[str]:
    """Find an installed browser that yt-dlp can extract authentication cookies from."""
    for b in ("chrome", "firefox", "brave", "edge", "chromium", "opera", "vivaldi"):
        if shutil.which(b) or shutil.which(f"google-{b}") or shutil.which(f"{b}-browser"):
            return b
    return None


def _get_vcodec_score(vcodec: Optional[str]) -> int:
    """Score video codecs to mirror yt-dlp's standard format sorting order."""
    if not vcodec or vcodec == "none":
        return 0
    vc = vcodec.lower()
    if "av01" in vc or "av1" in vc:
        return 40
    if "vp09" in vc or "vp9" in vc:
        return 30
    if "hevc" in vc or "h265" in vc:
        return 25
    if "avc1" in vc or "h264" in vc:
        return 20
    if "vp8" in vc:
        return 10
    return 5


def _get_acodec_score(acodec: Optional[str]) -> int:
    """Score audio codecs to mirror yt-dlp's standard format sorting order."""
    if not acodec or acodec == "none":
        return 0
    ac = acodec.lower()
    if "opus" in ac:
        return 30
    if "mp4a" in ac or "aac" in ac:
        return 20
    if "vorbis" in ac:
        return 15
    if "mp3" in ac:
        return 10
    return 5


def get_format_size_bytes(fmt: dict) -> int:
    """Safely extracts filesize in bytes from format dictionary."""
    if not isinstance(fmt, dict):
        return 0
    val = fmt.get("filesize") or fmt.get("filesize_approx") or 0
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return 0


def get_effective_resolution(fmt: dict) -> int:
    """Returns the effective video resolution standard (e.g. 1080 for 1920x1080 landscape or 1080x1920 portrait)."""
    if not isinstance(fmt, dict):
        return 0
    h = int(fmt.get("height") or 0)
    w = int(fmt.get("width") or 0)
    if h > 0 and w > 0:
        return min(h, w)
    return h or w or 0


def determine_media_container_ext(
    selected_fmts: list[dict],
    video_container: str = "auto",
    is_audio: bool = False,
    audio_format: str = "auto"
) -> str:
    """Determines the exact file extension (.mp4, .mkv, .webm, .opus, etc.) that yt-dlp will output."""
    if is_audio:
        afmt = (audio_format or "auto").lower().strip()
        if afmt and afmt not in ("auto", "best"):
            return f".{afmt}"
        if selected_fmts:
            a_ext = (selected_fmts[0].get("ext") or "").lower().strip()
            if a_ext:
                if a_ext == "m4a":
                    return ".m4a"
                if a_ext == "webm":
                    return ".opus" if "opus" in (selected_fmts[0].get("acodec") or "").lower() else ".webm"
                return f".{a_ext}"
        return ".opus"

    vfmt = (video_container or "auto").lower().strip()
    if vfmt and vfmt not in ("auto", "best"):
        return f".{vfmt}"

    # Auto / Best container
    if not selected_fmts:
        return ".mp4"

    if len(selected_fmts) == 1:
        ext = (selected_fmts[0].get("ext") or "mp4").lower().strip()
        return f".{ext}" if ext else ".mp4"

    # Multiple streams (video + audio merged)
    v_fmt = selected_fmts[0]
    a_fmt = selected_fmts[1] if len(selected_fmts) > 1 else {}
    v_ext = (v_fmt.get("ext") or "").lower().strip()
    a_ext = (a_fmt.get("ext") or "").lower().strip()

    # yt-dlp merge rules:
    # If both are mp4/m4a -> mp4
    # If both are webm -> webm
    # If mixed (e.g. mp4 + webm, or webm + m4a) -> mkv
    if (v_ext in ("mp4", "m4v") and a_ext in ("m4a", "mp4")):
        return ".mp4"
    elif v_ext == "webm" and a_ext == "webm":
        return ".webm"
    elif v_ext and a_ext and v_ext != a_ext:
        return ".mkv"
    elif v_ext:
        return f".{v_ext}"
    return ".mp4"


def get_selected_download_size(
    raw_data: dict,
    height: Optional[int] = None,
    is_audio_only: bool = False,
    video_container: str = "auto",
    audio_format: str = "auto",
    video_codec: str = "auto",
) -> tuple[int, bool, list[dict]]:
    """
    Calculates the download size in bytes and approximation flag for the selected format.
    Returns: (total_size_bytes, is_approximate, selected_formats_list)
    """
    if not isinstance(raw_data, dict):
        return 0, False, []

    raw_formats = raw_data.get("formats", [])
    if not raw_formats:
        return 0, False, []

    duration = float(raw_data.get("duration") or 0)

    if is_audio_only:
        # 1. Filter audio streams (acodec != 'none')
        audio_candidates = [
            f for f in raw_formats
            if f.get("acodec") and f.get("acodec") != "none" and (f.get("ext") or "").lower() not in ("mhtml", "html")
        ]
        if not audio_candidates:
            return 0, False, []

        pref_ext = (audio_format or "auto").lower()
        if pref_ext == "m4a":
            matching = [f for f in audio_candidates if (f.get("ext") or "").lower() in ("m4a", "mp4") or "mp4a" in (f.get("acodec") or "").lower()]
        elif pref_ext == "opus":
            matching = [f for f in audio_candidates if (f.get("ext") or "").lower() == "webm" or "opus" in (f.get("acodec") or "").lower()]
        else:
            matching = audio_candidates

        pool = matching if matching else audio_candidates
        # Pick best audio by codec priority and abr / tbr
        best_audio = max(
            pool,
            key=lambda f: (
                _get_acodec_score(f.get("acodec")),
                float(f.get("abr") or 0) or float(f.get("tbr") or 0),
                get_format_size_bytes(f),
            )
        )
        sz = get_format_size_bytes(best_audio)
        is_approx = not bool(best_audio.get("filesize")) and bool(best_audio.get("filesize_approx"))
        if sz == 0 and duration > 0 and (best_audio.get("tbr") or best_audio.get("abr")):
            bitrate = float(best_audio.get("abr") or best_audio.get("tbr") or 0)
            if bitrate > 0:
                sz = int(duration * bitrate * 125)
                is_approx = True

        return sz, is_approx, [best_audio]

    # Video + Audio
    video_only = [
        f for f in raw_formats
        if (f.get("vcodec") and f.get("vcodec") != "none") and (not f.get("acodec") or f.get("acodec") == "none") and (f.get("ext") or "").lower() not in ("mhtml", "html")
    ]
    audio_only = [
        f for f in raw_formats
        if (f.get("acodec") and f.get("acodec") != "none") and (not f.get("vcodec") or f.get("vcodec") == "none") and (f.get("ext") or "").lower() not in ("mhtml", "html")
    ]
    combined = [
        f for f in raw_formats
        if (f.get("vcodec") and f.get("vcodec") != "none") and (f.get("acodec") and f.get("acodec") != "none") and (f.get("ext") or "").lower() not in ("mhtml", "html")
    ]

    pref_container = (video_container or "auto").lower()
    pref_codec = (video_codec or "auto").lower()

    # Step A: Find best matching video stream
    if video_only:
        v_pool = video_only
        if height:
            h_filtered = [f for f in v_pool if get_effective_resolution(f) <= height]
            if h_filtered:
                v_pool = h_filtered
            else:
                lowest_res = min(get_effective_resolution(f) for f in v_pool)
                v_pool = [f for f in v_pool if get_effective_resolution(f) == lowest_res]

        if pref_codec not in ("auto", "any", ""):
            if "av1" in pref_codec:
                codec_filtered = [f for f in v_pool if "av01" in (f.get("vcodec") or "").lower() or "av1" in (f.get("vcodec") or "").lower()]
            elif "h264" in pref_codec or "avc" in pref_codec:
                codec_filtered = [f for f in v_pool if "avc" in (f.get("vcodec") or "").lower() or "h264" in (f.get("vcodec") or "").lower()]
            elif "vp9" in pref_codec:
                codec_filtered = [f for f in v_pool if "vp9" in (f.get("vcodec") or "").lower()]
            else:
                codec_filtered = []
            if codec_filtered:
                v_pool = codec_filtered

        if pref_container == "mp4":
            c_filtered = [f for f in v_pool if (f.get("ext") or "").lower() == "mp4" or (f.get("vcodec") or "").startswith(("avc", "h264"))]
            if c_filtered:
                v_pool = c_filtered
        elif pref_container == "webm":
            c_filtered = [f for f in v_pool if (f.get("ext") or "").lower() == "webm" or (f.get("vcodec") or "").startswith(("vp9", "av01"))]
            if c_filtered:
                v_pool = c_filtered

        best_video = max(
            v_pool,
            key=lambda f: (
                get_effective_resolution(f),
                _get_vcodec_score(f.get("vcodec")),
                float(f.get("vbr") or 0) or float(f.get("tbr") or 0),
                get_format_size_bytes(f),
            )
        )

        # Step B: Find best matching audio stream
        a_pool = audio_only
        if not a_pool:
            a_pool = [f for f in raw_formats if f.get("acodec") and f.get("acodec") != "none"]

        if pref_container == "mp4":
            a_filtered = [f for f in a_pool if (f.get("ext") or "").lower() in ("m4a", "mp4") or "mp4a" in (f.get("acodec") or "").lower()]
            if a_filtered:
                a_pool = a_filtered
        elif pref_container == "webm":
            a_filtered = [f for f in a_pool if (f.get("ext") or "").lower() == "webm" or "opus" in (f.get("acodec") or "").lower()]
            if a_filtered:
                a_pool = a_filtered

        best_audio = max(
            a_pool,
            key=lambda f: (
                _get_acodec_score(f.get("acodec")),
                float(f.get("abr") or 0) or float(f.get("tbr") or 0),
                get_format_size_bytes(f),
            )
        ) if a_pool else None

        v_sz = get_format_size_bytes(best_video)
        v_approx = not bool(best_video.get("filesize")) and bool(best_video.get("filesize_approx"))
        if v_sz == 0 and duration > 0 and (best_video.get("tbr") or best_video.get("vbr")):
            v_bitrate = float(best_video.get("vbr") or best_video.get("tbr") or 0)
            if v_bitrate > 0:
                v_sz = int(duration * v_bitrate * 125)
                v_approx = True

        a_sz = 0
        a_approx = False
        selected_fmts = [best_video]
        if best_audio:
            selected_fmts.append(best_audio)
            a_sz = get_format_size_bytes(best_audio)
            a_approx = not bool(best_audio.get("filesize")) and bool(best_audio.get("filesize_approx"))
            if a_sz == 0 and duration > 0 and (best_audio.get("tbr") or best_audio.get("abr")):
                a_bitrate = float(best_audio.get("abr") or best_audio.get("tbr") or 0)
                if a_bitrate > 0:
                    a_sz = int(duration * a_bitrate * 125)
                    a_approx = True

        total_sz = v_sz + a_sz
        is_approx = v_approx or a_approx
        return total_sz, is_approx, selected_fmts

    # Fallback to combined progressive streams
    if combined:
        c_pool = combined
        if height:
            h_filtered = [f for f in c_pool if get_effective_resolution(f) <= height]
            if h_filtered:
                c_pool = h_filtered
            else:
                lowest_res = min(get_effective_resolution(f) for f in c_pool)
                c_pool = [f for f in c_pool if get_effective_resolution(f) == lowest_res]
        best_combined = max(
            c_pool,
            key=lambda f: (
                get_effective_resolution(f),
                float(f.get("tbr") or 0),
                get_format_size_bytes(f),
            )
        )
        sz = get_format_size_bytes(best_combined)
        is_approx = not bool(best_combined.get("filesize")) and bool(best_combined.get("filesize_approx"))
        if sz == 0 and duration > 0 and best_combined.get("tbr"):
            bitrate = float(best_combined.get("tbr") or 0)
            if bitrate > 0:
                sz = int(duration * bitrate * 125)
                is_approx = True
        return sz, is_approx, [best_combined]

    return 0, False, []


_MEDIA_SIZES_CACHE = {}  # key -> (timestamp, data_dict)
_MEDIA_SIZES_CACHE_TTL = 600  # 10 minutes


def probe_media_sizes(
    url: str,
    heights: Optional[list[int]] = None,
    referrer: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookies: Optional[str] = None,
    cookies_file: Optional[str] = None,
    cookies_browser: Optional[str] = None,
    video_container: str = "auto",
    audio_format: str = "auto",
    video_codec: str = "auto",
    timeout: int = 20,
) -> dict:
    """
    Probes remote media URL with yt-dlp and calculates accurate download sizes
    for each resolution and audio stream. Used by the browser extension media popup.
    """
    import time
    clean_url = sanitize_media_url(url)
    if not clean_url:
        return {"success": False, "error": "Invalid URL"}

    cache_key = f"{clean_url}|{video_container}|{audio_format}|{video_codec}"
    now = time.time()
    if cache_key in _MEDIA_SIZES_CACHE:
        ts, cached_res = _MEDIA_SIZES_CACHE[cache_key]
        if now - ts < _MEDIA_SIZES_CACHE_TTL:
            return cached_res

    temp_cookies_file = None
    try:
        yt_dlp_bin = YtDlpManager.ensure_binary()
        bin_dir = str(BIN_DIR)
        clean_env = get_clean_env(bin_dir)
        is_debug = is_debug_mode() or logger.isEnabledFor(logging.DEBUG)

        try:
            cfg = load_category_config()
            media_defaults = cfg.get("media_downloader_defaults", {})
            yt_client = media_defaults.get("youtube_player_client", "default") or "default"
            if video_codec == "auto" and media_defaults.get("video_codec"):
                video_codec = media_defaults.get("video_codec", "auto")
            if video_container == "auto" and media_defaults.get("video_container"):
                _raw_vc = media_defaults.get("video_container", "auto")
                video_container = _raw_vc.split()[0].lower() if _raw_vc else "auto"
            if audio_format == "auto" and media_defaults.get("audio_format"):
                _raw_af = media_defaults.get("audio_format", "auto")
                audio_format = _raw_af.split()[0].lower() if _raw_af else "auto"
        except Exception:
            media_defaults = {}
            yt_client = "default"

        yt_client = (yt_client or "default").strip() or "default"

        cmd = [
            yt_dlp_bin,
            "-J",
            "--flat-playlist",
            "--verbose" if is_debug else "--no-warnings",
            "--remote-components", "ejs:github",
            "--extractor-args", f"youtube:player_client={yt_client}",
        ]
        cmd.extend(get_js_runtime_args())

        ffmpeg_bin = get_tool_path("ffmpeg") or shutil.which("ffmpeg")
        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-location", ffmpeg_bin])
        elif os.path.exists(bin_dir):
            cmd.extend(["--ffmpeg-location", bin_dir])

        if referrer:
            cmd.extend(["--referer", referrer])
        if user_agent:
            cmd.extend(["--user-agent", user_agent])

        effective_cookies_file = cookies_file
        if not effective_cookies_file and media_defaults:
            opt_cpath = media_defaults.get("cookies_path", "")
            if opt_cpath and os.path.exists(opt_cpath):
                effective_cookies_file = opt_cpath

        if effective_cookies_file and os.path.exists(str(effective_cookies_file)):
            cmd.extend(["--cookies", str(effective_cookies_file)])
        elif cookies:
            from core.media.worker import create_temp_netscape_cookie_file
            temp_cookies_file = create_temp_netscape_cookie_file(cookies, clean_url)
            if temp_cookies_file and os.path.exists(temp_cookies_file):
                cmd.extend(["--cookies", temp_cookies_file])
            else:
                cmd.extend(["--add-header", f"Cookie:{cookies}"])
        elif cookies_browser and cookies_browser.lower() not in ("none", ""):
            cmd.extend(["--cookies-from-browser", cookies_browser.lower()])

        cmd.append(clean_url)

        proc = subprocess.Popen(
            cmd,
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {"success": False, "error": f"yt-dlp probe timed out after {timeout}s"}

        if proc.returncode != 0 or not stdout:
            err_text = ((stderr or "") + " " + (stdout or "")).lower()
            if any(e in err_text for e in ("bot", "429", "sign in", "login_required", "cookie")):
                browser_candidate = get_installed_browser_for_cookies()
                if browser_candidate:
                    retry_cmd = [
                        yt_dlp_bin,
                        "-J",
                        "--flat-playlist",
                        "--verbose" if is_debug else "--no-warnings",
                        "--remote-components", "ejs:github",
                        "--extractor-args", f"youtube:player_client={yt_client}",
                        "--cookies-from-browser", browser_candidate,
                    ]
                    retry_cmd.extend(get_js_runtime_args())
                    if ffmpeg_bin:
                        retry_cmd.extend(["--ffmpeg-location", ffmpeg_bin])
                    elif os.path.exists(bin_dir):
                        retry_cmd.extend(["--ffmpeg-location", bin_dir])
                    retry_cmd.append(clean_url)
                    try:
                        retry_proc = subprocess.Popen(
                            retry_cmd,
                            env=clean_env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                        )
                        r_stdout, r_stderr = retry_proc.communicate(timeout=timeout)
                        if retry_proc.returncode == 0 and r_stdout:
                            proc = retry_proc
                            stdout = r_stdout
                            stderr = r_stderr
                    except Exception:
                        pass

        if proc.returncode != 0 or not stdout:
            return {"success": False, "error": f"yt-dlp probe failed: {stderr[:200]}"}

        data = json.loads(stdout)
        if data.get("_type") == "playlist" and data.get("entries"):
            for ent in data.get("entries", []):
                if ent and isinstance(ent, dict) and ent.get("formats"):
                    data = ent
                    break

        from core.utils import format_bytes

        test_heights = set(heights or [2160, 1440, 1080, 720, 480, 360, 240, 144])
        for fmt in data.get("formats", []):
            h = get_effective_resolution(fmt)
            if h and h > 0:
                test_heights.add(int(h))

        sorted_heights = sorted(list(test_heights), reverse=True)
        sizes_map = {}

        for h in sorted_heights:
            sz_bytes, is_approx, sel_fmts = get_selected_download_size(
                data,
                height=h,
                is_audio_only=False,
                video_container=video_container,
                audio_format=audio_format,
                video_codec=video_codec,
            )
            if sz_bytes > 0:
                h_ext = determine_media_container_ext(sel_fmts, video_container=video_container, is_audio=False, audio_format=audio_format)
                sizes_map[str(h)] = {
                    "height": h,
                    "sizeBytes": sz_bytes,
                    "sizeStr": (("~ " if is_approx else "") + format_bytes(sz_bytes)),
                    "isApproximate": is_approx,
                    "ext": h_ext,
                }

        audio_sz_bytes, audio_approx, sel_audio_fmts = get_selected_download_size(
            data,
            is_audio_only=True,
            video_container=video_container,
            audio_format=audio_format,
            video_codec=video_codec,
        )
        if audio_sz_bytes > 0:
            a_ext = determine_media_container_ext(sel_audio_fmts, video_container=video_container, is_audio=True, audio_format=audio_format)
            sizes_map["audio"] = {
                "height": 0,
                "sizeBytes": audio_sz_bytes,
                "sizeStr": (("~ " if audio_approx else "") + format_bytes(audio_sz_bytes)),
                "isApproximate": audio_approx,
                "ext": a_ext,
            }

        result = {
            "success": True,
            "url": clean_url,
            "title": data.get("title", ""),
            "duration": float(data.get("duration") or 0),
            "sizes": sizes_map,
        }

        if len(_MEDIA_SIZES_CACHE) > 200:
            _MEDIA_SIZES_CACHE.clear()
        _MEDIA_SIZES_CACHE[cache_key] = (now, result)
        return result

    except Exception as e:
        logger.warning("[probe_media_sizes] Failed: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        if temp_cookies_file and os.path.exists(temp_cookies_file):
            try:
                os.remove(temp_cookies_file)
            except Exception:
                pass



class MediaInfoFetcherWorker(QThread):
    """Background worker thread to probe media metadata and calculate accurate format download size."""

    finished_signal = pyqtSignal(dict)

    def __init__(
        self,
        url: str,
        selected_quality: str = "",
        height: Optional[int] = None,
        is_audio: bool = False,
        video_container: str = "auto",
        audio_format: str = "auto",
        video_codec: str = "auto",
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        referrer: Optional[str] = None,
        user_agent: Optional[str] = None,
        cookies: Optional[str] = None,
        custom_title: str = "",
        format_spec: str = "bestvideo+bestaudio/best",
        initial_ext: str = ".mp4",
        fallback_size_bytes: int = 0,
        is_special_case: bool = False,
    ):
        super().__init__()
        self.url = sanitize_media_url(url)
        self.selected_quality = selected_quality
        self.height = height
        self.is_audio = is_audio
        self.video_container = video_container
        self.audio_format = audio_format
        self.video_codec = video_codec
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.referrer = referrer
        self.user_agent = user_agent
        self.cookies = cookies
        self.custom_title = custom_title
        self.format_spec = format_spec
        self.initial_ext = initial_ext
        self.fallback_size_bytes = fallback_size_bytes
        self.is_special_case = is_special_case
        self.process = None
        self.is_running = True
        _keep_thread_alive(self)

    def stop(self):
        self.is_running = False
        if hasattr(self, "process") and self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass

    def run(self):
        temp_cookies_file = None
        try:
            yt_dlp_bin = YtDlpManager.ensure_binary()
            bin_dir = str(BIN_DIR)
            clean_env = get_clean_env(bin_dir)
            is_debug = "--debug" in sys.argv or os.environ.get("DEBUG") == "1" or logger.isEnabledFor(logging.DEBUG)

            try:
                cfg = load_category_config()
                media_defaults = cfg.get("media_downloader_defaults", {})
                yt_client = media_defaults.get("youtube_player_client", "default") or "default"
            except Exception:
                yt_client = "default"

            yt_client = (yt_client or "default").strip() or "default"

            cmd = [
                yt_dlp_bin,
                "-J",
                "--flat-playlist",
                "--verbose" if is_debug else "--no-warnings",
                "--remote-components", "ejs:github",
                "--extractor-args", f"youtube:player_client={yt_client}",
            ]
            cmd.extend(get_js_runtime_args())

            ffmpeg_bin = get_tool_path("ffmpeg") or shutil.which("ffmpeg")
            if ffmpeg_bin:
                cmd.extend(["--ffmpeg-location", ffmpeg_bin])
            elif os.path.exists(bin_dir):
                cmd.extend(["--ffmpeg-location", bin_dir])

            if self.referrer:
                cmd.extend(["--referer", self.referrer])
            if self.user_agent:
                cmd.extend(["--user-agent", self.user_agent])

            if self.cookies_file and os.path.exists(str(self.cookies_file)):
                cmd.extend(["--cookies", str(self.cookies_file)])
            elif self.cookies:
                from core.media.worker import create_temp_netscape_cookie_file
                temp_cookies_file = create_temp_netscape_cookie_file(self.cookies, self.url)
                if temp_cookies_file and os.path.exists(temp_cookies_file):
                    cmd.extend(["--cookies", temp_cookies_file])
                else:
                    cmd.extend(["--add-header", f"Cookie:{self.cookies}"])
            elif self.cookies_browser and self.cookies_browser.lower() not in ("none", ""):
                cmd.extend(["--cookies-from-browser", self.cookies_browser.lower()])

            cmd.append(self.url)

            self.process = subprocess.Popen(
                cmd,
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            try:
                stdout, stderr = self.process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                if self.process:
                    try:
                        self.process.kill()
                        stdout, stderr = self.process.communicate()
                    except Exception:
                        pass
                raise RuntimeError("yt-dlp probe timed out after 20s")

            if self.process.returncode != 0 or not stdout:
                err_text = ((stderr or "") + " " + (stdout or "")).lower()
                if any(e in err_text for e in ("bot", "429", "sign in", "login_required", "cookie")):
                    browser_candidate = get_installed_browser_for_cookies()
                    if browser_candidate:
                        retry_cmd = [
                            yt_dlp_bin,
                            "-J",
                            "--flat-playlist",
                            "--verbose" if is_debug else "--no-warnings",
                            "--remote-components", "ejs:github",
                            "--extractor-args", f"youtube:player_client={yt_client}",
                            "--cookies-from-browser", browser_candidate,
                        ]
                        retry_cmd.extend(get_js_runtime_args())
                        if ffmpeg_bin:
                            retry_cmd.extend(["--ffmpeg-location", ffmpeg_bin])
                        elif os.path.exists(bin_dir):
                            retry_cmd.extend(["--ffmpeg-location", bin_dir])
                        retry_cmd.append(self.url)
                        try:
                            retry_proc = subprocess.Popen(
                                retry_cmd,
                                env=clean_env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                encoding="utf-8",
                            )
                            r_stdout, r_stderr = retry_proc.communicate(timeout=20)
                            if retry_proc.returncode == 0 and r_stdout:
                                self.process = retry_proc
                                stdout = r_stdout
                                stderr = r_stderr
                        except Exception:
                            pass

            if self.process.returncode != 0 or not stdout:
                raise RuntimeError(f"yt-dlp probe failed: {stderr[:200]}")

            data = json.loads(stdout)
            size_bytes, is_approx, sel_fmts = get_selected_download_size(
                data,
                height=self.height,
                is_audio_only=self.is_audio,
                video_container=self.video_container,
                audio_format=self.audio_format,
                video_codec=self.video_codec,
            )

            resolved_ext = determine_media_container_ext(
                sel_fmts,
                video_container=self.video_container,
                is_audio=self.is_audio,
                audio_format=self.audio_format
            ) or self.initial_ext

            from core.utils import format_bytes, sanitize_media_filename, is_generic_media_title
            real_title = data.get("title") or ""
            if self.is_special_case:
                final_title = self.custom_title
            else:
                if real_title and (not self.custom_title or is_generic_media_title(self.custom_title)):
                    chosen_title = real_title
                else:
                    chosen_title = self.custom_title or real_title or "media"
                clean_title = chosen_title.rstrip("-_| ").strip() or chosen_title
                if self.height and not self.is_audio and f"{self.height}p" not in clean_title:
                    final_title = f"{clean_title} [{self.height}p]"
                else:
                    final_title = clean_title

            filename = sanitize_media_filename(final_title, ext=resolved_ext)
            size_str = (("~" if is_approx else "") + format_bytes(size_bytes)) if size_bytes > 0 else "Size unavailable"

            resolved_format_spec = self.format_spec
            if sel_fmts:
                fids = [f.get("format_id") for f in sel_fmts if f.get("format_id")]
                if fids:
                    resolved_format_spec = "+".join(fids)

            self.finished_signal.emit({
                "url": self.url,
                "filename": filename,
                "ext": resolved_ext,
                "size_bytes": size_bytes,
                "size_str": size_str,
                "size_is_approximate": is_approx,
                "format_spec": resolved_format_spec,
                "is_audio_only": self.is_audio,
                "video_container": self.video_container,
                "audio_format": self.audio_format,
                "cookies_file": self.cookies_file,
                "cookies_browser": self.cookies_browser,
                "referrer": self.referrer,
                "user_agent": self.user_agent,
                "cookies": self.cookies,
                "success": True,
            })

        except Exception as e:
            logger.warning("[MediaInfoFetcher] Metadata probe fallback (%s) for %s", e, self.url)
            from core.utils import format_bytes, sanitize_media_filename
            title = self.custom_title or "media"
            filename = sanitize_media_filename(title, ext=self.initial_ext)
            fb_size = self.fallback_size_bytes or 0
            size_str = format_bytes(fb_size) if fb_size > 0 else "Size unavailable"
            self.finished_signal.emit({
                "url": self.url,
                "filename": filename,
                "size_bytes": fb_size,
                "size_str": size_str,
                "size_is_approximate": True if fb_size > 0 else False,
                "format_spec": self.format_spec,
                "is_audio_only": self.is_audio,
                "video_container": self.video_container,
                "audio_format": self.audio_format,
                "cookies_file": self.cookies_file,
                "cookies_browser": self.cookies_browser,
                "referrer": self.referrer,
                "user_agent": self.user_agent,
                "cookies": self.cookies,
                "success": False,
            })
        finally:
            if temp_cookies_file and os.path.exists(temp_cookies_file):
                try:
                    os.remove(temp_cookies_file)
                except Exception:
                    pass

