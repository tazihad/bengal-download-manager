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

from core.utils import get_clean_env, sanitize_media_url
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

            stdout, stderr = self.process.communicate(timeout=60)

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
                    stdout, stderr = self.process.communicate(timeout=60)

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
