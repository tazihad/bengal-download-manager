import time
import os
import json
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from utils import get_unique_filepath, load_proxy_config, load_extension_config

# --- WORKER FOR PRE-FETCHING FILE INFO ---
class FileInfoFetcherWorker(QThread):
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
    
    def create_opener(self):
        """Standard opener (uses system proxies if any)."""
        return urllib.request.build_opener()

    def run(self):
        result = {
            "url": self.url,
            "filename": "Unknown",
            "size_str": "Unknown",
            "size_bytes": 0,
            "error": None
        }
        
        try:
            # ... URL parsing logic ...
            parsed = urlparse(self.url)
            path = unquote(parsed.path)
            basename = os.path.basename(path)
            if basename: 
                result["filename"] = basename
            else:
                result["filename"] = "file"
                
            req = urllib.request.Request(self.url, method='GET') 
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            
            opener = self.create_opener()
            with opener.open(req, timeout=10) as resp:
                content_length = resp.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    result["size_bytes"] = int(content_length)
                    result["size_str"] = self.format_bytes(result["size_bytes"])
                
                content_disp = resp.headers.get("Content-Disposition")
                header_filename = None
                if content_disp:
                    import re
                    # Look for filename* (RFC 5987) or filename=
                    cd_match = re.search(r'filename\*=UTF-8\'\'([^"\';]+)', content_disp, re.IGNORECASE)
                    if not cd_match:
                        cd_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp, re.IGNORECASE)
                    
                    if cd_match:
                        extracted = unquote(cd_match.group(1).strip())
                        if extracted:
                            header_filename = extracted

                # SMART FILENAME LOGIC:
                # 1. If we have a header filename, check if it's "garbage" (like a UUID)
                # 2. If it's garbage and our URL basename looks good, prefer basename.
                # 3. Otherwise, prefer header filename.
                
                is_garbage = False
                if header_filename:
                    # Check if UUID-like: 8-4-4-4-12 hex chars
                    import re
                    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', header_filename, re.I):
                        is_garbage = True
                    # Check if purely hex hash (like SHA1/MD5)
                    elif re.match(r'^[0-9a-f]{32,64}$', header_filename, re.I):
                        is_garbage = True
                
                if header_filename and not is_garbage:
                    result["filename"] = header_filename
                elif basename and basename != "file":
                    # Keep the original basename if it looks like a real file
                    result["filename"] = basename
                elif header_filename:
                    # Last resort: use the garbage header filename
                    result["filename"] = header_filename
                    
        except Exception as e:
            result["error"] = str(e)
            
        self.finished_signal.emit(result)
        
    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"

# --- WORKER FOR SINGLE SEGMENT ---
class SegmentWorker(QThread):
    # Signals: index, total_downloaded_in_segment, segment_total_size, speed, status
    progress_signal = pyqtSignal(int, object, object, float, str)
    finished_signal = pyqtSignal(int, bool)

    def __init__(self, index, url, start_byte, end_byte, filepath, initial_downloaded=0, opener=None):
        super().__init__()
        self.index = index
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.filepath = filepath
        self.initial_downloaded = initial_downloaded
        self.opener = opener
        
        self.is_running = True
        self.is_paused = False
        self.speed_limit = 0 # 0 means unlimited (bytes/sec)
        
        # 'downloaded' tracks total bytes gathered for this segment (past + current session)
        self.downloaded = initial_downloaded
        self.total_size = (end_byte - start_byte) + 1

    def set_speed_limit(self, limit):
        """Sets the speed limit for this specific worker in bytes/second."""
        self.speed_limit = limit

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
            
            # Use custom opener if provided (for proxy)
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
                            bytes_in_session = 0 # Reset speed calc on pause
                            continue
                        
                        # --- SPEED LIMITER LOGIC ---
                        read_start = time.time()
                        chunk = response.read(chunk_size)
                        read_duration = time.time() - read_start

                        if not chunk:
                            break
                        
                        # If a limit is set, we throttle here
                        if self.speed_limit > 0:
                            # expected_duration = size / rate
                            expected_duration = len(chunk) / self.speed_limit
                            if read_duration < expected_duration:
                                sleep_needed = expected_duration - read_duration
                                # Break large sleeps into small chunks to remain responsive
                                while sleep_needed > 0 and self.is_running and not self.is_paused:
                                    nap = min(sleep_needed, 0.1) # max 100ms sleep per check
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
    main_bar_signal = pyqtSignal(object, object) 
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, object, object, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir, resume_filename=None):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.is_running = True
        self.is_paused = False
        self.mutex = QMutex()
        
        self.current_global_limit = 0 # 0 means no limit
        self.last_active_count = 0
        
        parsed_url = urlparse(self.url)
        # Decode the path to handle %20 and other URL encodings
        decoded_path = unquote(parsed_url.path)
        original_filename = os.path.basename(decoded_path) or "downloaded_file"
        
        if resume_filename:
            self.target_path = os.path.join(self.save_dir, resume_filename)
            self.save_path = self.target_path + ".tmpbdm"
            self.filename = resume_filename
        else:
            full_path = os.path.join(self.save_dir, original_filename)
            self.target_path = get_unique_filepath(full_path)
            self.save_path = self.target_path + ".tmpbdm"
            self.filename = os.path.basename(self.target_path)
        
        self.state_file = self.save_path + ".bdmx"
        self.workers = []
        self.segment_stats = {} 
        
        self.opener = self.create_opener()

    def create_opener(self):
        """Standard opener (uses system proxies if any)."""
        return urllib.request.build_opener()

    def set_global_speed_limit(self, limit_bytes_per_sec):
        """Sets the total download speed limit."""
        self.current_global_limit = limit_bytes_per_sec
        self.distribute_speed_limit()
        if limit_bytes_per_sec > 0:
            self.log_signal.emit(f"Speed limit set to {self.format_bytes(limit_bytes_per_sec)}/s")
        else:
            self.log_signal.emit("Speed limit disabled")

    def distribute_speed_limit(self):
        """Distributes the global limit equally among active workers."""
        active_workers = [w for w in self.workers if w.isRunning() and not w.isFinished()]
        count = len(active_workers)
        
        if count > 0 and self.current_global_limit > 0:
            limit_per_worker = self.current_global_limit / count
            for w in active_workers:
                w.set_speed_limit(limit_per_worker)
        else:
            # Disable limit on all workers
            for w in self.workers:
                w.set_speed_limit(0)

    def run(self):
        try:
            self.log_signal.emit("Connecting to server...")
            self.log_signal.emit(f"Target file: {self.filename}")
            
            req = urllib.request.Request(self.url, method='HEAD')
            with self.opener.open(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                accept_ranges = response.info().get('Accept-Ranges', 'none')
            
            self.log_signal.emit(f"File size: {self.format_bytes(total_size)}")
            
            # --- RESUME LOGIC ---
            segments_info = []
            is_resuming = False
            num_threads = 8

            # Check for .bdmx and the .tmpbdm file
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
                
                # NOTE: Workers write to self.save_path (the .tmpbdm file)
                worker = SegmentWorker(idx, self.url, start, end, self.save_path, initial_dl, opener=self.opener)
                worker.progress_signal.connect(self.update_segment_stat)
                self.workers.append(worker)
                
                self.segment_stats[idx] = {'dl': initial_dl, 'speed': 0, 'start': start, 'end': end}
                worker.start()
            
            # Initial Speed Limit Application
            self.distribute_speed_limit()
            self.last_active_count = len(self.workers)

            # Monitor Loop
            finished_count = 0
            save_counter = 0
            
            while finished_count < num_threads and self.is_running:
                total_dl = sum(s['dl'] for s in self.segment_stats.values())
                total_speed = sum(s['speed'] for s in self.segment_stats.values())
                
                if self.is_paused:
                    time.sleep(0.2)
                    self.save_state(total_size) # Save state on pause
                    self.main_progress_signal.emit(self.row_index, (
                        self.filename, 
                        self.format_bytes(total_size) if total_size > 0 else "Unknown", 
                        "Paused", 
                        "", 
                        "0 KB/s",
                        total_dl,
                        total_size
                    ))
                    continue
                
                # Check if threads finished to redistribute speed limit
                active_count = sum(1 for w in self.workers if w.isRunning() and not w.isFinished())
                if active_count != self.last_active_count:
                    self.distribute_speed_limit()
                    self.last_active_count = active_count

                # Progress Calculation
                percent_val = (total_dl / total_size) * 100 if total_size > 0 else 0
                percent_str = f"{percent_val:.1f}%"
                
                time_left = 0
                if total_speed > 0 and total_size > 0:
                    time_left = (total_size - total_dl) / total_speed
                
                self.main_bar_signal.emit(total_dl, total_size)
                self.main_progress_signal.emit(self.row_index, (
                    self.filename,
                    self.format_bytes(total_size) if total_size > 0 else "Unknown",
                    "Receiving data..." if not self.is_paused else "Paused", # Use the worker's internal state
                    self.format_time(time_left),
                    f"{self.format_bytes(total_speed)}/s",
                    total_dl,
                    total_size
                ))

                # Periodically save state (every ~2 seconds)
                save_counter += 1
                if save_counter > 20:
                    self.save_state(total_size)
                    save_counter = 0

                finished_count = sum(1 for w in self.workers if w.isFinished())
                self.msleep(100) 

            if self.is_running:
                self.log_signal.emit("File assembled. Verifying...")
                
                # Finalize: Rename .tmpbdm to actual filename
                try:
                    if os.path.exists(self.target_path):
                         os.remove(self.target_path) # Overwrite if exists
                    os.rename(self.save_path, self.target_path)
                    
                    self.log_signal.emit("Download completed.")
                    self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes(total_size) if total_size > 0 else "Unknown", "Completed", "", "", total_size, total_size))
                    self.finished_signal.emit(self.row_index, "Completed")
                    
                    # Cleanup state file
                    if os.path.exists(self.state_file):
                        os.remove(self.state_file)
                except Exception as e:
                    self.log_signal.emit(f"Error renaming file: {e}")
                    self.finished_signal.emit(self.row_index, "Error")
            else:
                self.save_state(total_size) # Save on stop
                
                # Decide final status based on whether it was manually paused or cancelled
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
        # Set is_paused flag first, which stops the thread loop
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

# --- NEW ARIA2 RPC WORKER ---
class Aria2Worker(QThread):
    main_progress_signal = pyqtSignal(int, tuple) 
    main_bar_signal = pyqtSignal(object, object) 
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, object, object, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir, resume_filename=None):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.is_running = True
        self.gid = None
        
        ext_data = load_extension_config()
        self.rpc_port = ext_data.get("port", 56800)
        self.rpc_token = ext_data.get("token", "")
        self.rpc_url = f"http://127.0.0.1:{self.rpc_port}/jsonrpc"
        
        parsed_url = urlparse(self.url)
        decoded_path = unquote(parsed_url.path)
        original_filename = os.path.basename(decoded_path) or "downloaded_file"
        
        if resume_filename:
            self.filename = resume_filename
            self.target_path = os.path.join(self.save_dir, self.filename)
        else:
            full_path = os.path.join(self.save_dir, original_filename)
            self.target_path = get_unique_filepath(full_path)
            self.filename = os.path.basename(self.target_path)

    def call_rpc(self, method, params=None):
        from utils import call_aria2_rpc
        return call_aria2_rpc(method, params=params, port=self.rpc_port, token=self.rpc_token)

    def run(self):
        self.log_signal.emit("Connecting to Aria2 engine...")
        self.init_segments_signal.emit(8) # Emulate 8 segments for UI consistency
        
        # Add continue flag for automatic resume functionality
        params = [[self.url], {"dir": self.save_dir, "out": self.filename, "split": "8", "max-connection-per-server": "8", "continue": "true"}]
        self.gid = self.call_rpc("aria2.addUri", params)
        
        if not self.gid:
            self.log_signal.emit("Failed to communicate with Aria2 RPC.")
            self.finished_signal.emit(self.row_index, "Error")
            return

        self.log_signal.emit(f"Download started via Aria2 (GID: {self.gid[:6]})")
        
        import random
        simulated_dls = [0] * 8
        simulated_speeds = [0] * 8
        active_indices = []
        last_update_time = time.time()
        
        while self.is_running:
            status = self.call_rpc("aria2.tellStatus", [self.gid])
            if not status:
                time.sleep(1)
                continue

            total_length = int(status.get("totalLength", 0))
            completed_length = int(status.get("completedLength", 0))
            download_speed = int(status.get("downloadSpeed", 0))
            connections = int(status.get("connections", 0))
            state = status.get("status")
            
            # Immediately kill UI speed numbers after pause is clicked to mask Aria2's TCP flush delay
            if getattr(self, 'is_pause_requested', False):
                download_speed = 0
                state = "paused"

            self.main_bar_signal.emit(completed_length, total_length)

            time_left = 0
            if download_speed > 0 and total_length > 0:
                time_left = (total_length - completed_length) / download_speed

            display_state = "Receiving data..."
            if state == "paused": display_state = "Paused"
            elif state == "complete": display_state = "Completed"
            elif state == "error": display_state = "Error"
            elif state == "removed": display_state = "Cancelled"

            self.main_progress_signal.emit(self.row_index, (
                self.filename,
                self.format_bytes(total_length) if total_length > 0 else "Unknown",
                display_state,
                self.format_time(time_left),
                f"{self.format_bytes(download_speed)}/s",
                completed_length,
                total_length
            ))

            current_time = time.time()
            dt = current_time - last_update_time
            last_update_time = current_time
            
            real_seg_dls = [0] * 8
            real_seg_totals = [0] * 8

            bitfield = status.get("bitfield", "")
            numPieces = int(status.get("numPieces", 0))
            pieceLength = int(status.get("pieceLength", 0))

            if numPieces > 0 and bitfield:
                try:
                    bin_str = bin(int(bitfield, 16))[2:]
                    bin_str = bin_str.zfill(len(bitfield) * 4)
                    bits = [int(b) for b in bin_str[:numPieces]]
                except Exception:
                    bits = []

                if bits:
                    chunk_req = numPieces / 8.0
                    for i in range(8):
                        start_idx = int(i * chunk_req)
                        end_idx = int((i + 1) * chunk_req)
                        if i == 7: end_idx = numPieces
                        
                        chunk_bits = bits[start_idx:end_idx]
                        seg_total = len(chunk_bits) * pieceLength
                        if i == 7 and total_length > 0:
                             seg_total = max(0, total_length - (start_idx * pieceLength))
                        
                        real_seg_dls[i] = min(sum(chunk_bits) * pieceLength, seg_total)
                        real_seg_totals[i] = seg_total
            else:
                if total_length > 0:
                    part = total_length // 8
                    for i in range(8):
                        seg_total = part if i < 7 else max(0, total_length - part * 7)
                        real_seg_totals[i] = seg_total
                        real_seg_dls[i] = max(0, min(completed_length - (i * part), seg_total))

            if sum(real_seg_totals) > 0:
                incomplete_indices = [i for i in range(8) if real_seg_dls[i] < real_seg_totals[i]]
                active_indices = [i for i in active_indices if i in incomplete_indices]
                
                target_connections = min(connections if connections > 0 else 8, len(incomplete_indices))
                if download_speed > 0 and target_connections == 0 and incomplete_indices:
                    target_connections = 1
                    
                while len(active_indices) < target_connections:
                    cands = [i for i in incomplete_indices if i not in active_indices]
                    if not cands: break
                    active_indices.append(random.choice(cands))
                    
                while len(active_indices) > target_connections:
                    active_indices.pop()
                    
                if download_speed > 0 and active_indices:
                    weights = [random.uniform(0.8, 1.2) for _ in active_indices]
                    tot_w = sum(weights)
                    for idx in range(8):
                        if idx in active_indices:
                            w_i = active_indices.index(idx)
                            speed_alloc = download_speed * (weights[w_i] / tot_w)
                            simulated_speeds[idx] = speed_alloc
                            simulated_dls[idx] += speed_alloc * dt
                        else:
                            simulated_speeds[idx] = 0
                else:
                    simulated_speeds = [0] * 8
                    
                for i in range(8):
                    simulated_dls[i] = max(simulated_dls[i], real_seg_dls[i])
                    upper = real_seg_totals[i]
                    if real_seg_dls[i] < real_seg_totals[i]:
                        upper = upper - 1024 if upper > 1024 else upper - 1
                    simulated_dls[i] = min(simulated_dls[i], upper)
                    
                    if real_seg_dls[i] >= real_seg_totals[i] and real_seg_totals[i] > 0:
                        sg_status = "Complete"
                        sg_speed = 0
                        simulated_dls[i] = real_seg_totals[i]
                    elif i in active_indices and download_speed > 0:
                        sg_status = "Receiving data..."
                        sg_speed = simulated_speeds[i]
                    else:
                        sg_status = "Pending..." if state != "complete" else "Complete"
                        sg_speed = 0
                        
                    self.segment_update_signal.emit(i, int(simulated_dls[i]), real_seg_totals[i], sg_speed, sg_status)
            else:
                self.segment_update_signal.emit(0, completed_length, total_length, download_speed, display_state)

            if state == "complete":
                self.log_signal.emit("Aria2 download completed successfully.")
                self.finished_signal.emit(self.row_index, "Completed")
                break
            elif state in ["error", "removed"]:
                self.log_signal.emit(f"Aria2 download stopped: {state}")
                self.finished_signal.emit(self.row_index, "Error" if state == "error" else "Cancelled")
                break
            elif state == "paused":
                if not getattr(self, "paused_logged", False):
                    self.log_signal.emit("Aria2 download paused.")
                    self.paused_logged = True
                
            time.sleep(0.2)

    def stop(self):
        self.is_running = False
        if self.gid:
            self.call_rpc("aria2.remove", [self.gid])
            self.log_signal.emit("Removing download from Aria2...")

    def pause(self):
        self.is_pause_requested = True
        if self.gid:
            self.call_rpc("aria2.pause", [self.gid])
            self.log_signal.emit("Pausing download in Aria2...")

    def resume(self):
        self.is_pause_requested = False
        self.paused_logged = False
        if self.gid:
            self.call_rpc("aria2.unpause", [self.gid])
            self.log_signal.emit("Resuming download in Aria2...")

    def set_global_speed_limit(self, limit):
        if self.gid:
            self.call_rpc("aria2.changeOption", [self.gid, {"max-download-limit": str(int(limit))}])

    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"

    def format_time(self, seconds):
        if seconds < 60: return f"{int(seconds)} sec"
        elif seconds < 3600: return f"{int(seconds//60)} min"
        else: return f"{int(seconds//3600)} hr"