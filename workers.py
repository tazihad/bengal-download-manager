import time
import os
import json
from urllib.parse import urlparse
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from utils import get_unique_filepath

# --- WORKER FOR SINGLE SEGMENT ---
class SegmentWorker(QThread):
    # Signals: index, total_downloaded_in_segment, segment_total_size, speed, status
    progress_signal = pyqtSignal(int, int, int, float, str)
    finished_signal = pyqtSignal(int, bool)

    def __init__(self, index, url, start_byte, end_byte, filepath, initial_downloaded=0):
        super().__init__()
        self.index = index
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.filepath = filepath
        self.initial_downloaded = initial_downloaded
        
        self.is_running = True
        self.is_paused = False
        
        # 'downloaded' tracks total bytes gathered for this segment (past + current session)
        self.downloaded = initial_downloaded
        self.total_size = (end_byte - start_byte) + 1

    def run(self):
        try:
            # Check if already complete
            if self.downloaded >= self.total_size:
                self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Complete")
                self.finished_signal.emit(self.index, True)
                return

            # Calculate where to resume in the file and URL
            resume_offset = self.start_byte + self.downloaded
            
            req = urllib.request.Request(self.url)
            req.add_header("Range", f"bytes={resume_offset}-{self.end_byte}")
            
            self.progress_signal.emit(self.index, self.downloaded, self.total_size, 0, "Resume GET...")
            
            with urllib.request.urlopen(req, timeout=20) as response:
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
                            bytes_in_session = 0 # Reset speed calc on pause
                            continue

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        self.downloaded += len(chunk)
                        bytes_in_session += len(chunk)
                        
                        current_time = time.time()
                        if current_time - last_emit_time > 0.8: 
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

        except Exception as e:
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


# --- MAIN DOWNLOAD MANAGER WORKER ---
class DownloadWorker(QThread):
    main_progress_signal = pyqtSignal(int, tuple) 
    main_bar_signal = pyqtSignal(int, int) 
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, int, int, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir, resume_filename=None):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.is_running = True
        self.is_paused = False
        self.mutex = QMutex()
        
        parsed_url = urlparse(self.url)
        original_filename = os.path.basename(parsed_url.path) or "downloaded_file"
        
        if resume_filename:
            self.save_path = os.path.join(self.save_dir, resume_filename)
            self.filename = resume_filename
        else:
            full_path = os.path.join(self.save_dir, original_filename)
            self.save_path = get_unique_filepath(full_path)
            self.filename = os.path.basename(self.save_path)
        
        # State file for resuming (.bdmx)
        self.state_file = self.save_path + ".bdmx"
        
        self.workers = []
        self.segment_stats = {} 

    def run(self):
        try:
            self.log_signal.emit("Connecting to server...")
            self.log_signal.emit(f"Target file: {self.filename}")
            
            req = urllib.request.Request(self.url, method='HEAD')
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                accept_ranges = response.info().get('Accept-Ranges', 'none')
            
            self.log_signal.emit(f"File size: {self.format_bytes(total_size)}")
            
            # --- RESUME LOGIC ---
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
                # Fresh start setup
                if accept_ranges == 'none' or total_size < 1024 * 1024: 
                    num_threads = 1
                    self.log_signal.emit("Using 1 connection.")
                else:
                    self.log_signal.emit(f"Splitting into {num_threads} connections.")

                # Pre-allocate file (wipe it clean)
                with open(self.save_path, "wb") as f:
                    f.truncate(total_size) 
                
                # Calculate segments
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
            
            # Start Workers
            self.workers = []
            for seg in segments_info:
                idx = seg["index"]
                start = seg["start"]
                end = seg["end"]
                initial_dl = seg.get("downloaded", 0)
                
                worker = SegmentWorker(idx, self.url, start, end, self.save_path, initial_dl)
                worker.progress_signal.connect(self.update_segment_stat)
                self.workers.append(worker)
                
                self.segment_stats[idx] = {'dl': initial_dl, 'speed': 0, 'start': start, 'end': end}
                worker.start()

            # Monitor Loop
            finished_count = 0
            save_counter = 0
            
            while finished_count < num_threads and self.is_running:
                if self.is_paused:
                    time.sleep(0.2)
                    self.save_state(total_size) # Save state on pause
                    self.main_progress_signal.emit(self.row_index, (
                        self.filename, self.format_bytes(total_size), "Paused", "", "0 KB/s"
                    ))
                    continue

                total_dl = sum(s['dl'] for s in self.segment_stats.values())
                total_speed = sum(s['speed'] for s in self.segment_stats.values())
                
                # Progress Calculation
                percent_val = (total_dl / total_size) * 100
                percent_str = f"{percent_val:.1f}%"
                
                time_left = 0
                if total_speed > 0:
                    time_left = (total_size - total_dl) / total_speed
                
                self.main_bar_signal.emit(total_dl, total_size)
                self.main_progress_signal.emit(self.row_index, (
                    self.filename,
                    self.format_bytes(total_size),
                    percent_str,
                    self.format_time(time_left),
                    f"{self.format_bytes(total_speed)}/s"
                ))

                # Periodically save state (every ~2 seconds)
                save_counter += 1
                if save_counter > 20:
                    self.save_state(total_size)
                    save_counter = 0

                finished_count = sum(1 for w in self.workers if w.isFinished())
                self.msleep(100) 

            if self.is_running:
                self.log_signal.emit("File assembled and verified.")
                self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes(total_size), "Completed", "", ""))
                self.finished_signal.emit(self.row_index, "Completed")
                
                # Cleanup state file
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)
            else:
                self.save_state(total_size) # Save on stop
                self.log_signal.emit("Download stopped.")
                self.finished_signal.emit(self.row_index, "Cancelled")

        except Exception as e:
            self.log_signal.emit(f"Critical Error: {str(e)}")
            self.finished_signal.emit(self.row_index, "Error")

    def save_state(self, total_size):
        """Saves the current download progress to a JSON file."""
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
        except Exception as e:
            print(f"Failed to save state: {e}")

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

    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"

    def format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)} sec"
        elif seconds < 3600:
            return f"{int(seconds//60)} min"
        else:
            return f"{int(seconds//3600)} hr"