"""Direct media worker: two Aria2 transfers plus a local FFmpeg mux.

Adaptive media pages (YouTube SABR/adaptive tiers) expose video and audio as separate
streams. Downloading only one of them produces a silent video, so Direct mode transfers
both URLs through the Aria2 engine and muxes them with FFmpeg. yt-dlp is never used as a
downloader here - it only located the signed stream URLs beforehand.
"""

import logging
import os
import shutil
import subprocess
import time

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils import call_aria2_rpc, is_debug_mode, load_extension_config

logger = logging.getLogger("bengal.worker.direct_mux")

_DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
_MUX_TIMEOUT_SEC = 1800


def _with_dot(ext: str, fallback: str) -> str:
    value = str(ext or "").strip().lower()
    if not value:
        return fallback
    return value if value.startswith(".") else f".{value}"


class DirectMuxWorker(QThread):
    main_progress_signal = pyqtSignal(int, tuple)
    main_bar_signal = pyqtSignal(object, object)
    finished_signal = pyqtSignal(int, str)
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, object, object, float, str)
    init_segments_signal = pyqtSignal(int)

    def __init__(
        self,
        video_url,
        audio_url,
        download_id=0,
        save_dir="",
        filename=None,
        user_agent=None,
        cookies=None,
        temp_dir=None,
        referrer=None,
        total_bytes=0,
        video_ext=".mp4",
        audio_ext=".m4a",
        **kwargs,
    ):
        super().__init__()
        self.video_url = video_url
        self.audio_url = audio_url
        self.url = video_url or audio_url or ""
        self.download_id = kwargs.get("row_index", download_id)
        self.row_index = self.download_id
        self.save_dir = save_dir
        self.user_agent = user_agent
        self.cookies = cookies
        self.referrer = referrer
        self.temp_dir = temp_dir
        self.filename = filename or "video.mp4"
        self.target_path = os.path.join(save_dir, self.filename)
        self.total_bytes = int(total_bytes or 0)

        ext_data = load_extension_config()
        self.rpc_port = kwargs.get("rpc_port")
        if self.rpc_port is None:
            self.rpc_port = ext_data.get("port", 56800)
        rpc_token = kwargs.get("rpc_token")
        self.rpc_token = ext_data.get("token", "") if rpc_token is None else rpc_token

        try:
            self.max_connections = max(1, min(16, int(ext_data.get("max_connections", 8))))
        except (TypeError, ValueError):
            self.max_connections = 8

        self.working_dir = self.temp_dir if self.temp_dir else self.save_dir
        try:
            os.makedirs(self.working_dir, exist_ok=True)
        except OSError:
            self.working_dir = self.save_dir
        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except OSError:
            pass

        stem = os.path.splitext(self.filename)[0] or "video"
        self.video_path = os.path.join(
            self.working_dir, f"{stem}.video{_with_dot(video_ext, '.mp4')}"
        )
        self.audio_path = os.path.join(
            self.working_dir, f"{stem}.audio{_with_dot(audio_ext, '.m4a')}"
        )

        self.gid_video = None
        self.gid_audio = None
        self.generation = 0
        self.is_running = True
        self.is_paused = False
        self.is_pause_requested = False
        self.is_resuming = False
        self.paused_logged = False
        self._retried = set()
        self._last_total = 0
        self._last_done = 0

        if is_debug_mode():
            logger.debug(
                "[DirectMuxWorker] Initialized row=%d: video=%s audio=%s target=%s temp=%s",
                self.row_index,
                self.video_url[:120],
                self.audio_url[:120],
                self.target_path,
                self.working_dir,
            )

    def call_rpc(self, method, params=None):
        return call_aria2_rpc(
            method, params=params, port=self.rpc_port, token=self.rpc_token
        )

    def run(self):
        from core.utils import set_linux_process_name

        set_linux_process_name("bengal-direct-mux")
        self.log_signal.emit("Starting Direct download (video + audio via Aria2)...")
        self.init_segments_signal.emit(2)

        self.gid_video = self._add_track(
            self.video_url, os.path.basename(self.video_path)
        )
        if not self.gid_video:
            self._fail("Could not queue the video stream in Aria2.")
            return

        self.gid_audio = self._add_track(
            self.audio_url, os.path.basename(self.audio_path)
        )
        if not self.gid_audio:
            self._abort_gid(self.gid_video)
            self._fail("Could not queue the audio stream in Aria2.")
            return

        if is_debug_mode():
            logger.debug(
                "[DirectMuxWorker] GIDs video=%s audio=%s", self.gid_video, self.gid_audio
            )
        self.log_signal.emit(
            f"Downloading video + audio (GIDs {self.gid_video[:6]}/{self.gid_audio[:6]})"
        )

        outcome = self._monitor()
        if outcome == "complete":
            self._finish()
        elif outcome == "error":
            self.finished_signal.emit(self.row_index, "Error")

    def _add_track(self, url, out_name, split=None, allow_resume=True):
        split_value = str(split or self.max_connections)
        options = {
            "dir": self.working_dir,
            "out": out_name,
            "split": split_value,
            "max-connection-per-server": split_value,
            "continue": "true" if allow_resume else "false",
            "allow-overwrite": "true",
            "check-certificate": "false",
            "user-agent": self.user_agent or _DEFAULT_UA,
            "header": self._headers(),
        }
        return self.call_rpc("aria2.addUri", [[url], options])

    def _headers(self):
        headers = [
            f"User-Agent: {self.user_agent or _DEFAULT_UA}",
            "Accept: */*",
            "Accept-Language: en-US,en;q=0.5",
            "Connection: keep-alive",
        ]
        if self.referrer:
            headers.append(f"Referer: {self.referrer}")
        if self.cookies:
            headers.append(f"Cookie: {self.cookies}")
        return headers

    def _monitor(self):
        consecutive_failures = 0
        while self.is_running:
            video_status = self.call_rpc("aria2.tellStatus", [self.gid_video])
            audio_status = self.call_rpc("aria2.tellStatus", [self.gid_audio])

            if not video_status or not audio_status:
                consecutive_failures += 1
                if consecutive_failures < 5:
                    time.sleep(0.5)
                    continue
                if self._both_tracks_downloaded():
                    return "complete"
                logger.error(
                    "[DirectMuxWorker] Lost contact with Aria2 RPC for the track downloads"
                )
                self._fail("Lost contact with the Aria2 engine.")
                return "error"
            consecutive_failures = 0

            if self._retry_single_connection("video", video_status):
                continue
            if self._retry_single_connection("audio", audio_status):
                continue

            video_state = video_status.get("status")
            audio_state = audio_status.get("status")
            if video_state in ("error", "removed") or audio_state in ("error", "removed"):
                self._abort_gid(self.gid_video)
                self._abort_gid(self.gid_audio)
                self._fail("Aria2 could not download the selected tracks.")
                return "error"

            v_total = int(video_status.get("totalLength") or 0)
            v_done = int(video_status.get("completedLength") or 0)
            a_total = int(audio_status.get("totalLength") or 0)
            a_done = int(audio_status.get("completedLength") or 0)
            v_speed = int(video_status.get("downloadSpeed") or 0)
            a_speed = int(audio_status.get("downloadSpeed") or 0)

            if not self.is_paused:
                self._last_total = v_total + a_total
                self._last_done = v_done + a_done

            both_complete = (
                (video_state == "complete" or (v_total > 0 and v_done >= v_total))
                and (audio_state == "complete" or (a_total > 0 and a_done >= a_total))
            )
            if both_complete:
                self.main_bar_signal.emit(self._last_total, self._last_total)
                self.segment_update_signal.emit(0, v_done, v_total, 0.0, "Complete")
                self.segment_update_signal.emit(1, a_done, a_total, 0.0, "Complete")
                return "complete"

            total = v_total + a_total
            done = v_done + a_done
            speed = v_speed + a_speed
            if self.is_pause_requested or self.is_paused:
                speed = 0
                display_state = "Paused"
            elif self.is_resuming:
                if video_state in ("paused", "waiting") and audio_state in ("paused", "waiting"):
                    display_state = "Resuming..."
                else:
                    self.is_resuming = False
                    display_state = "Receiving data..."
            elif video_state == "waiting" or audio_state == "waiting":
                display_state = "Waiting"
            else:
                display_state = "Receiving data..."

            time_left = (total - done) / speed if speed > 0 and total > done else 0
            self.main_bar_signal.emit(done, total)

            total_display = total if total > 0 else self.total_bytes
            self.main_progress_signal.emit(
                self.row_index,
                (
                    self.filename,
                    self.format_bytes(total_display, precision=2, pad=False)
                    if total_display > 0
                    else "Unknown",
                    display_state,
                    self.format_time(time_left),
                    f"{self.format_bytes(speed, precision=2, pad=False)}/s",
                    done,
                    total_display,
                    speed,
                    getattr(self, "generation", 0),
                ),
            )

            self.segment_update_signal.emit(
                0, v_done, v_total, float(v_speed), self._track_label(video_status)
            )
            self.segment_update_signal.emit(
                1, a_done, a_total, float(a_speed), self._track_label(audio_status)
            )

            if video_state == "paused" or audio_state == "paused":
                if not self.paused_logged:
                    self.log_signal.emit("Aria2 download paused.")
                    self.paused_logged = True

            time.sleep(0.2)

        return "stopped"

    def _track_label(self, status):
        if self.is_pause_requested or self.is_paused:
            return "Paused"
        state = status.get("status")
        if state == "complete":
            return "Complete"
        if state == "error":
            return "Error"
        if state == "removed":
            return "Cancelled"
        if state == "waiting":
            return "Waiting"
        return "Receiving data..."

    def _retry_single_connection(self, kind, status):
        if kind in self._retried or status.get("status") != "error":
            return False
        error_code = str(status.get("errorCode") or "")
        error_message = str(status.get("errorMessage") or "").lower()
        if error_code != "8" and "range" not in error_message:
            return False

        self._retried.add(kind)
        gid = self.gid_video if kind == "video" else self.gid_audio
        track_path = self.video_path if kind == "video" else self.audio_path
        self.log_signal.emit(
            "Server rejected multi-connection download. Retrying in single connection..."
        )
        try:
            self.call_rpc("aria2.removeDownloadResult", [gid])
        except Exception:
            pass
        for path in (track_path, f"{track_path}.aria2"):
            try:
                os.remove(path)
            except OSError:
                pass

        new_gid = self._add_track(
            self.video_url if kind == "video" else self.audio_url,
            os.path.basename(track_path),
            split=1,
            allow_resume=False,
        )
        if not new_gid:
            return False
        if kind == "video":
            self.gid_video = new_gid
        else:
            self.gid_audio = new_gid
        if is_debug_mode():
            logger.debug(
                "[DirectMuxWorker] Retried %s track with single connection (GID %s)",
                kind,
                new_gid,
            )
        time.sleep(0.5)
        return True

    def _both_tracks_downloaded(self):
        for path in (self.video_path, self.audio_path):
            if not os.path.exists(path) or os.path.getsize(path) <= 0:
                return False
            if os.path.exists(f"{path}.aria2"):
                return False
        return True

    def _finish(self):
        self.log_signal.emit("Merging audio and video with FFmpeg...")
        total = self._last_total or self.total_bytes
        self.main_progress_signal.emit(
            self.row_index,
            (
                self.filename,
                self.format_bytes(total, precision=2, pad=False) if total > 0 else "Unknown",
                "Processing",
                "-",
                "0.00 B/s",
                self._last_done,
                total,
                0,
                getattr(self, "generation", 0),
            ),
        )

        ffmpeg = self._tool("ffmpeg")
        if not ffmpeg:
            self._fail("FFmpeg is unavailable - Direct download cancelled.")
            return
        if not self._both_tracks_downloaded():
            self._fail("Downloaded tracks are missing or incomplete.")
            return

        target_ext = os.path.splitext(self.filename)[1] or ".mp4"
        temp_out = os.path.join(
            self.save_dir, f"{os.path.splitext(self.filename)[0]}.muxing{target_ext}"
        )
        base_cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            self.video_path,
            "-i",
            self.audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
        copy_cmd = base_cmd + ["-c", "copy", "-movflags", "+faststart", temp_out]
        muxed = self._run_ffmpeg(copy_cmd)
        if not muxed:
            logger.warning("[DirectMuxWorker] Stream copy failed; re-encoding audio")
            aac_cmd = base_cmd + [
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                temp_out,
            ]
            muxed = self._run_ffmpeg(aac_cmd)
        if not muxed:
            self._fail("FFmpeg could not merge the downloaded tracks.")
            return

        if not self._has_audio(temp_out):
            try:
                os.remove(temp_out)
            except OSError:
                pass
            self._fail("Merged file has no audio track.")
            return

        try:
            os.replace(temp_out, self.target_path)
        except OSError as exc:
            logger.error("[DirectMuxWorker] Failed to move merged file: %s", exc)
            self._fail("Could not save the merged media file.")
            return

        self._cleanup_tracks()
        final_size = os.path.getsize(self.target_path)
        self.log_signal.emit("Direct download completed successfully.")
        self.main_progress_signal.emit(
            self.row_index,
            (
                self.filename,
                self.format_bytes(final_size, precision=2, pad=False),
                "Complete",
                "",
                "",
                final_size,
                final_size,
                0,
                getattr(self, "generation", 0),
            ),
        )
        self.main_bar_signal.emit(final_size, final_size)
        self.finished_signal.emit(self.row_index, "Complete")

    def _run_ffmpeg(self, cmd):
        if is_debug_mode():
            logger.debug("[DirectMuxWorker] Running FFmpeg: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_MUX_TIMEOUT_SEC,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("[DirectMuxWorker] FFmpeg failed to run: %s", exc)
            return False
        if result.returncode != 0:
            logger.error(
                "[DirectMuxWorker] FFmpeg exited with %s: %s",
                result.returncode,
                (result.stderr or "").strip()[-500:],
            )
            return False
        return os.path.exists(cmd[-1]) and os.path.getsize(cmd[-1]) > 0

    def _has_audio(self, path):
        ffprobe = self._tool("ffprobe")
        if not ffprobe:
            return True
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            return True
        return bool((result.stdout or "").strip())

    def _tool(self, name):
        try:
            from core.media.dependencies import get_tool_path

            found = get_tool_path(name)
            if found:
                return found
        except Exception:
            pass
        return shutil.which(name)

    def _cleanup_tracks(self):
        for path in (self.video_path, self.audio_path):
            for candidate in (path, f"{path}.aria2"):
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass

    def _abort_gid(self, gid):
        if not gid:
            return
        try:
            self.call_rpc("aria2.remove", [gid])
        except Exception:
            pass
        try:
            self.call_rpc("aria2.removeDownloadResult", [gid])
        except Exception:
            pass

    def _fail(self, message):
        logger.error("[DirectMuxWorker] %s", message)
        self.log_signal.emit(message)
        self.main_progress_signal.emit(
            self.row_index,
            (self.filename, "Unknown", "Error", "--", "--", 0, 0, 0, getattr(self, "generation", 0)),
        )
        self.finished_signal.emit(self.row_index, "Error")
        self.is_running = False

    def set_global_speed_limit(self, limit_bytes):
        value = str(int(limit_bytes)) if limit_bytes and int(limit_bytes) > 0 else "0"
        for gid in (self.gid_video, self.gid_audio):
            if not gid:
                continue
            try:
                self.call_rpc("aria2.changeOption", [gid, {"max-download-limit": value}])
            except Exception:
                pass

    def stop(self):
        """Cancel both Aria2 transfers."""
        self.is_running = False
        self.is_pause_requested = True
        self.is_paused = True
        if self.gid_video or self.gid_audio:
            self.log_signal.emit("Removing download from Aria2...")
        self._abort_gid(self.gid_video)
        self._abort_gid(self.gid_audio)

    def pause(self):
        self.is_pause_requested = True
        self.is_paused = True
        self.is_resuming = False
        for gid in (self.gid_video, self.gid_audio):
            if gid:
                try:
                    self.call_rpc("aria2.pause", [gid])
                except Exception:
                    pass
        if self.gid_video or self.gid_audio:
            self.log_signal.emit("Pausing download in Aria2...")

    def resume(self):
        self.is_pause_requested = False
        self.is_paused = False
        self.is_resuming = True
        self.paused_logged = False
        for gid in (self.gid_video, self.gid_audio):
            if gid:
                try:
                    self.call_rpc("aria2.unpause", [gid])
                except Exception:
                    pass
        if self.gid_video or self.gid_audio:
            self.log_signal.emit("Resuming download in Aria2...")

    def format_bytes(self, size, precision=2, pad=False):
        power = 1024
        n = 0
        power_labels = {0: "", 1: "K", 2: "M", 3: "G", 4: "T"}
        try:
            value = float(size)
        except (TypeError, ValueError):
            value = 0.0
        while value >= power and n < 4:
            value /= power
            n += 1
        if pad:
            width = precision + 5
            return f"{value:{width}.{precision}f}  {power_labels.get(n, '')}B"
        return f"{value:.{precision}f}  {power_labels.get(n, '')}B"

    def format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)} sec"
        if seconds < 3600:
            return f"{int(seconds // 60)} min"
        return f"{int(seconds // 3600)} hr"
