"""SABR session worker: stream via the Deno googlevideo helper, then mux locally.

The browser extension captures the YouTube player's own SABR ABR session (the
videoplayback?sabr=1 POST with its protobuf body) and relays it here. This worker
spawns ``core/media/sabr_download.mjs`` with Deno (SabrStream, pure fetch - no yt-dlp,
no aria2), parses its NDJSON progress lines, and reuses the DirectMuxWorker FFmpeg
copy-mux to merge the video/audio MP4 parts. SABR sessions are not resumable, so
pause terminates the stream and resume restarts it from the beginning.
"""

import json
import logging
import os
import subprocess
import threading
import time

from core.workers.direct_mux import DirectMuxWorker

logger = logging.getLogger("bengal.worker.sabr_stream")


class SabrStreamWorker(DirectMuxWorker):
    def __init__(
        self,
        session,
        download_id=0,
        save_dir="",
        filename=None,
        user_agent=None,
        cookies=None,
        temp_dir=None,
        referrer=None,
        total_bytes=0,
        **kwargs,
    ):
        session = session or {}
        super().__init__(
            session.get("serverAbrStreamingUrl") or "",
            "",
            download_id=download_id,
            save_dir=save_dir,
            filename=filename,
            user_agent=user_agent,
            cookies=cookies,
            temp_dir=temp_dir,
            referrer=referrer,
            total_bytes=total_bytes,
            **kwargs,
        )
        self.session = session
        self.video_itag = session.get("videoItag")
        self.audio_itag = session.get("audioItag")

        track_totals = {}
        for item in session.get("formats") or []:
            try:
                track_totals[int(item.get("itag"))] = max(0, int(item.get("contentLength") or 0))
            except (TypeError, ValueError):
                continue
        self._track_totals = track_totals
        if not self.total_bytes:
            self.total_bytes = sum(track_totals.values())

        self._proc = None
        self._proc_lock = threading.Lock()
        self._session_file = None
        self._last_progress_ts = 0.0
        self._last_progress_bytes = 0
        self._restart_requested = False

    def run(self):
        from core.utils import set_linux_process_name

        set_linux_process_name("bengal-sabr-stream")
        self.log_signal.emit("Streaming video + audio from the browser SABR session...")
        self.init_segments_signal.emit(2)

        from core.media.sabr import build_command, prepare_env, write_session_file

        try:
            self._session_file = write_session_file(self.session)
        except OSError as exc:
            logger.error("[SabrStreamWorker] Could not write session file: %s", exc)
            self._fail("Could not prepare the SABR session for streaming.")
            return

        outcome = "error"
        try:
            while self.is_running:
                if self.is_paused and not self._restart_requested:
                    time.sleep(0.2)
                    continue
                self._restart_requested = False
                self.is_resuming = self.is_paused
                self.is_paused = False
                self.is_pause_requested = False
                outcome = self._stream_once(build_command, prepare_env)
                if outcome in ("complete", "error", "stopped"):
                    break
        finally:
            self._remove_session_file()

        if outcome == "complete" and self.is_running:
            self._finish()

    def _stream_once(self, build_command, prepare_env):
        cmd = build_command(self._session_file, self.video_path, self.audio_path)
        self._last_progress_ts = time.monotonic()
        self._last_progress_bytes = 0
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=prepare_env(),
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            logger.error("[SabrStreamWorker] Failed to start Deno helper: %s", exc)
            self._fail("Could not start the SABR streaming engine.")
            return "error"

        with self._proc_lock:
            self._proc = proc

        stderr_tail = []
        done_seen = False
        error_seen = False
        try:
            for line in proc.stdout:
                if not self.is_running:
                    break
                if self.is_pause_requested:
                    self._terminate_proc()
                    while self.is_running and not self._restart_requested:
                        time.sleep(0.1)
                    if not self.is_running:
                        break
                    self._terminate_proc()
                    return "restart"
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("{"):
                    stderr_tail.append(line)
                    del stderr_tail[:-4]
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("ev")
                if kind == "progress":
                    self._emit_progress(event)
                elif kind == "done":
                    done_seen = True
                elif kind == "error":
                    error_seen = True
                    self._last_error_message = str(event.get("message") or "")[:300]
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass

        returncode = proc.wait()
        with self._proc_lock:
            self._proc = None

        if not self.is_running:
            return "stopped"
        if done_seen and returncode == 0:
            return "complete"
        if self.is_pause_requested:
            return "restart"
        message = getattr(self, "_last_error_message", "") or " ".join(stderr_tail)[-300:]
        if not message:
            message = f"SABR stream helper exited with code {returncode}."
        self._fail(f"SABR stream failed: {message}")
        return "error"

    def _emit_progress(self, event):
        downloaded = int(event.get("downloaded") or 0)
        total = int(event.get("total") or 0) or self.total_bytes
        now = time.monotonic()
        elapsed = max(0.001, now - self._last_progress_ts)
        speed = max(0, downloaded - self._last_progress_bytes) / elapsed
        self._last_progress_ts = now
        self._last_progress_bytes = downloaded

        if self.is_pause_requested or self.is_paused:
            speed = 0
            display_state = "Paused"
        elif self.is_resuming:
            display_state = "Resuming..."
        else:
            display_state = "Receiving data..."

        self._last_total = total
        self._last_done = downloaded
        time_left = (total - downloaded) / speed if speed > 0 and total > downloaded else 0
        self.main_bar_signal.emit(downloaded, total)
        self.main_progress_signal.emit(
            self.row_index,
            (
                self.filename,
                self.format_bytes(total, precision=2, pad=False) if total > 0 else "Unknown",
                display_state,
                self.format_time(time_left),
                f"{self.format_bytes(speed, precision=2, pad=False)}/s",
                downloaded,
                total,
                speed,
                getattr(self, "generation", 0),
            ),
        )

        tracks = event.get("tracks") or {}
        v_done = int(tracks.get(str(self.video_itag)) or tracks.get(self.video_itag) or 0)
        a_done = int(tracks.get(str(self.audio_itag)) or tracks.get(self.audio_itag) or 0)
        label = "Complete" if display_state == "Paused" else display_state
        self.segment_update_signal.emit(
            0, v_done, self._track_totals.get(self.video_itag, 0), 0.0, label
        )
        self.segment_update_signal.emit(
            1, a_done, self._track_totals.get(self.audio_itag, 0), 0.0, label
        )

    def _terminate_proc(self):
        with self._proc_lock:
            proc = self._proc
        if not proc or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except OSError:
            return
        for _ in range(30):
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            proc.kill()
        except OSError:
            pass

    def _remove_session_file(self):
        path = self._session_file
        self._session_file = None
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def set_global_speed_limit(self, limit_bytes):
        # The Deno helper has no runtime throttle; the SABR server paces the session itself.
        return

    def stop(self):
        self.is_running = False
        self.is_pause_requested = True
        self.is_paused = True
        self._terminate_proc()

    def pause(self):
        self.is_pause_requested = True
        self.is_paused = True
        self.is_resuming = False
        self.log_signal.emit("Pausing SABR stream...")
        self._terminate_proc()

    def resume(self):
        self.paused_logged = False
        self._restart_requested = True
        self.log_signal.emit(
            "Resuming - SABR sessions restart the stream from the beginning."
        )
