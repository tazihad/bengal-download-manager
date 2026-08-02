import time
import os
import json
from urllib.parse import urlparse, unquote
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from core.utils import get_unique_filepath, resolve_filename

class SegmentWorker(QThread):
    progress_signal = pyqtSignal(int, object, object, float, str)
    finished_signal = pyqtSignal(int, bool)

    def __init__(self, index, url, start_byte, end_byte, filepath, initial_downloaded=0, opener=None, user_agent=None, cookies=None):
        super().__init__()
        self.index = index
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.filepath = filepath
        self.initial_downloaded = initial_downloaded
        self.opener = opener
        self.user_agent = user_agent
        self.cookies = cookies
        
        self.is_running = True
        self.is_paused = False
        self.speed_limit = 0 
        
        self.downloaded = initial_downloaded
        self.total_size = (end_byte - start_byte) + 1

    def set_speed_limit(self, limit):
        self.speed_limit = limit

    def run(self):
        try:
            if self.downloaded >= self.total_size:
                self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Complete")
                self.finished_signal.emit(self.index, True)
                return

            resume_offset = self.start_byte + self.downloaded
            
            req = urllib.request.Request(self.url)
            # --- FULL BROWSER HEADERS (Mimic JD2) ---
            req.add_header('User-Agent', self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0")
            req.add_header('Accept', '*/*')
            req.add_header('Accept-Language', 'en-US,en;q=0.5')
            req.add_header('Connection', 'keep-alive')
            req.add_header('Range', f"bytes={resume_offset}-{self.end_byte}")
            
            if self.cookies:
                req.add_header('Cookie', self.cookies)
            
            # Add Referer if possible (use base domain)
            parsed = urlparse(self.url)
            req.add_header('Referer', f"{parsed.scheme}://{parsed.netloc}/")
            
            self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Resume GET...")
            
            opener = self.opener if self.opener else urllib.request.build_opener()
            
            with opener.open(req, timeout=20) as response:
                self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Receiving data...")
                
                with open(self.filepath, "r+b") as f:
                    f.seek(resume_offset)
                    
                    start_time = time.time()
                    last_emit_time = start_time
                    chunk_size = 16384 
                    bytes_in_session = 0

                    while self.is_running:
                        if self.is_paused:
                            time.sleep(0.2)
                            start_time = time.time()
                            last_emit_time = time.time()
                            bytes_in_session = 0 
                            continue
                        
                        read_start = time.time()
                        chunk = response.read(chunk_size)
                        read_duration = time.time() - read_start

                        if not chunk:
                            break
                        
                        if self.speed_limit > 0:
                            expected_duration = len(chunk) / self.speed_limit
                            if read_duration < expected_duration:
                                sleep_needed = expected_duration - read_duration
                                while sleep_needed > 0 and self.is_running and not self.is_paused:
                                    nap = min(sleep_needed, 0.1) 
                                    time.sleep(nap)
                                    sleep_needed -= nap

                        f.write(chunk)
                        self.downloaded += len(chunk)
                        bytes_in_session += len(chunk)
                        
                        current_time = time.time()
                        if current_time - last_emit_time > 0.2: 
                            speed = bytes_in_session / (current_time - last_emit_time)
                            self.progress_signal.emit(
                                self.index, self.downloaded, self.total_size, speed, "Receiving data..."
                            )
                            last_emit_time = current_time
                            bytes_in_session = 0

            if self.downloaded >= self.total_size:
                self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Complete")
                self.finished_signal.emit(self.index, True)
            else:
                raise Exception("Incomplete download")

        except Exception:
            if self.downloaded >= self.total_size:
                 self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Complete")
                 self.finished_signal.emit(self.index, True)
            else:
                self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Error")
                self.finished_signal.emit(self.index, False)

    def stop(self):
        self.is_running = False

    def set_pause(self, paused):
        self.is_paused = paused

import shutil

class DownloadWorker(QThread):
    main_progress_signal = pyqtSignal(int, tuple) 
    main_bar_signal = pyqtSignal(object, object) 
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, object, object, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir, resume_filename=None, user_agent=None, cookies=None, temp_dir=None):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.temp_dir = temp_dir
        self.user_agent = user_agent
        self.cookies = cookies
        self.is_running = True
        self.is_paused = False
        self.mutex = QMutex()
        
        self.current_global_limit = 0 
        self.last_active_count = 0
        
        # Initial guess. Real resolution might happen in run() during the first GET.
        if resume_filename:
            self.filename = resume_filename
        else:
            self.filename = resolve_filename(self.url, {})

        self.target_path = os.path.join(self.save_dir, self.filename)
        # If it was a generic fallback name, ensure it's unique
        if not resume_filename:
            self.target_path = get_unique_filepath(self.target_path)
            self.filename = os.path.basename(self.target_path)

        # Working directory: Use temp_dir if provided, else final save_dir
        self.working_dir = self.temp_dir if self.temp_dir else self.save_dir
        if not os.path.exists(self.working_dir):
            try: os.makedirs(self.working_dir, exist_ok=True)
            except: self.working_dir = self.save_dir

        self.save_path = os.path.join(self.working_dir, self.filename + ".tmpbdm")
        self.state_file = self.save_path + ".bdmx"
        self.workers = []
        self.segment_stats = {} 
        
        self.opener = self.create_opener()

    def create_opener(self):
        return urllib.request.build_opener()

    def set_global_speed_limit(self, limit_bytes_per_sec):
        self.current_global_limit = limit_bytes_per_sec
        self.distribute_speed_limit()
        if limit_bytes_per_sec > 0:
            self.log_signal.emit(f"Speed limit set to {self.format_bytes(limit_bytes_per_sec)}/s")
        else:
            self.log_signal.emit("Speed limit disabled")

    def distribute_speed_limit(self):
        active_workers = [w for w in self.workers if w.isRunning() and not w.isFinished()]
        count = len(active_workers)
        
        if count > 0 and self.current_global_limit > 0:
            limit_per_worker = self.current_global_limit / count
            for w in active_workers:
                w.set_speed_limit(limit_per_worker)
        else:
            for w in self.workers:
                w.set_speed_limit(0)

    def run(self):
        try:
            self.log_signal.emit("Connecting to server...")
            self.log_signal.emit(f"Target file: {self.filename}")
            
            req = urllib.request.Request(self.url, method='HEAD')
            if self.cookies:
                req.add_header('Cookie', self.cookies)
            if self.user_agent:
                req.add_header('User-Agent', self.user_agent)

            with self.opener.open(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                accept_ranges = response.info().get('Accept-Ranges', 'none')
            
            self.log_signal.emit(f"File size: {self.format_bytes(total_size)}")
            
            segments_info = []
            is_resuming = False
            num_threads = 8

            if os.path.exists(self.state_file) and os.path.exists(self.save_path):
                try:
                    with open(self.state_file, 'r') as f:
                        state_data = json.load(f)
                        if state_data.get("total_size") == total_size:
                            segments_info = state_data.get("segments", [])
                            num_threads = len(segments_info)
                            is_resuming = True
                            self.log_signal.emit("Resuming from previous session...")
                except Exception as e:
                    self.log_signal.emit(f"State file corrupted, starting fresh: {e}")
            
            if not is_resuming:
                if accept_ranges == 'none' or total_size < 1024 * 1024: 
                    num_threads = 1
                    self.log_signal.emit("Using 1 connection.")
                else:
                    self.log_signal.emit(f"Splitting into {num_threads} connections.")

                with open(self.save_path, "wb") as f:
                    f.truncate(total_size) 
                
                part_size = total_size // num_threads
                segments_info = []
                for i in range(num_threads):
                    start = i * part_size
                    end = start + part_size - 1
                    if i == num_threads - 1:
                        end = total_size - 1
                    segments_info.append({
                        "index": i, "start": start, "end": end, "downloaded": 0
                    })

            self.init_segments_signal.emit(num_threads)
            
            self.workers = []
            for seg in segments_info:
                idx = seg["index"]
                start = seg["start"]
                end = seg["end"]
                initial_dl = seg.get("downloaded", 0)
                
                worker = SegmentWorker(idx, self.url, start, end, self.save_path, initial_dl, opener=self.opener, user_agent=self.user_agent, cookies=self.cookies)
                worker.progress_signal.connect(self.update_segment_stat)
                self.workers.append(worker)
                
                self.segment_stats[idx] = {'dl': initial_dl, 'speed': 0, 'start': start, 'end': end}
                worker.start()
            
            self.distribute_speed_limit()
            self.last_active_count = len(self.workers)

            finished_count = 0
            save_counter = 0
            
            while finished_count < num_threads and self.is_running:
                total_dl = sum(s['dl'] for s in self.segment_stats.values())
                total_speed = sum(s['speed'] for s in self.segment_stats.values())
                
                if self.is_paused:
                    time.sleep(0.2)
                    self.save_state(total_size) 
                    self.main_progress_signal.emit(self.row_index, (
                        self.filename, 
                        self.format_bytes(total_size, precision=2, pad=False) if total_size > 0 else "Unknown", 
                        "Paused", 
                        "", 
                        "0 KB/s",
                        total_dl,
                        total_size
                    ))
                    continue
                
                active_count = sum(1 for w in self.workers if w.isRunning() and not w.isFinished())
                if active_count != self.last_active_count:
                    self.distribute_speed_limit()
                    self.last_active_count = active_count

                percent_val = (total_dl / total_size) * 100 if total_size > 0 else 0
                
                time_left = 0
                if total_speed > 0 and total_size > 0:
                    time_left = (total_size - total_dl) / total_speed
                
                self.main_bar_signal.emit(total_dl, total_size)
                self.main_progress_signal.emit(self.row_index, (
                    self.filename,
                    self.format_bytes(total_size, precision=2, pad=False) if total_size > 0 else "Unknown",
                    "Receiving data..." if not self.is_paused else "Paused", 
                    self.format_time(time_left),
                    f"{self.format_bytes(total_speed, precision=3, pad=False)}/s",
                    total_dl,
                    total_size
                ))

                save_counter += 1
                if save_counter > 20:
                    self.save_state(total_size)
                    save_counter = 0

                finished_count = sum(1 for w in self.workers if w.isFinished())
                self.msleep(100) 

            if self.is_running:
                self.log_signal.emit("File assembled. Verifying...")
                
                try:
                    self.log_signal.emit(f"Finalizing: Moving file to {self.save_dir}")
                    if os.path.exists(self.target_path):
                         os.remove(self.target_path) 
                    shutil.move(self.save_path, self.target_path)
                    
                    self.log_signal.emit("Download completed.")
                    self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes(total_size, precision=2, pad=False) if total_size > 0 else "Unknown", "Complete", "", "", total_size, total_size))
                    self.finished_signal.emit(self.row_index, "Complete")
                    
                    if os.path.exists(self.state_file):
                        os.remove(self.state_file)
                except Exception as e:
                    self.log_signal.emit(f"Error finalizing file: {e}")
                    self.finished_signal.emit(self.row_index, "Error")
            else:
                self.save_state(total_size) 
                
                if self.is_paused:
                    self.log_signal.emit("Download paused.")
                    self.finished_signal.emit(self.row_index, "Paused")
                else:
                    self.log_signal.emit("Download stopped/cancelled.")
                    self.finished_signal.emit(self.row_index, "Cancelled")

        except Exception as e:
            self.log_signal.emit(f"Critical Error: {str(e)}")
            self.finished_signal.emit(self.row_index, "Error")

    def save_state(self, total_size):
        try:
            segments_data = []
            self.mutex.lock()
            for idx, stats in self.segment_stats.items():
                segments_data.append({
                    "index": idx,
                    "start": stats.get("start", 0),
                    "end": stats.get("end", 0),
                    "downloaded": stats.get("dl", 0)
                })
            self.mutex.unlock()
            
            data = {
                "url": self.url,
                "total_size": total_size,
                "segments": segments_data
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def update_segment_stat(self, index, dl, total, speed, status):
        self.mutex.lock()
        if index in self.segment_stats:
            self.segment_stats[index]['dl'] = dl
            self.segment_stats[index]['speed'] = speed
        self.mutex.unlock()
        self.segment_update_signal.emit(index, dl, total, speed, status)

    def stop(self):
        self.is_running = False
        for w in self.workers:
            w.stop()
            w.quit()
            w.wait()

    def pause(self):
        self.is_paused = True 
        self.log_signal.emit("Pausing download...")
        for w in self.workers:
            w.set_pause(True)

    def resume(self):
        self.is_paused = False
        self.log_signal.emit("Resuming download...")
        for w in self.workers:
            w.set_pause(False)

    def format_bytes(self, size, precision=3, pad=False):
        power = 1024
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size >= power and n < 4:
            size /= power
            n += 1
        if pad:
            width = precision + 5
            return f"{size:{width}.{precision}f}  {power_labels.get(n, '')}B"
        else:
            return f"{size:.{precision}f}  {power_labels.get(n, '')}B"

    def format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)} sec"
        elif seconds < 3600:
            return f"{int(seconds//60)} min"
        else:
            return f"{int(seconds//3600)} hr"
