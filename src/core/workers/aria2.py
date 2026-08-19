import time
import os
import random
from urllib.parse import urlparse, unquote
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import get_unique_filepath, load_extension_config, call_aria2_rpc, resolve_filename

import shutil

class Aria2Worker(QThread):
    main_progress_signal = pyqtSignal(int, tuple) 
    main_bar_signal = pyqtSignal(object, object) 
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, object, object, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir, resume_filename=None, user_agent=None, cookies=None, temp_dir=None, referrer=None):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.temp_dir = temp_dir
        self.user_agent = user_agent
        self.cookies = cookies
        self.referrer = referrer
        self.is_running = True
        self.gid = None
        
        ext_data = load_extension_config()
        self.rpc_port = ext_data.get("port", 56800)
        self.rpc_token = ext_data.get("token", "")
        self.rpc_url = f"http://127.0.0.1:{self.rpc_port}/jsonrpc"
        
        if resume_filename:
            self.filename = resume_filename
        else:
            self.filename = resolve_filename(self.url, {})

        # Final target path
        self.target_path = os.path.join(self.save_dir, self.filename)
        # Ensure unique if not resumed
        if not resume_filename:
            self.target_path = get_unique_filepath(self.target_path)
            self.filename = os.path.basename(self.target_path)

        # Working directory: Use temp_dir if provided, else final save_dir
        self.working_dir = self.temp_dir if self.temp_dir else self.save_dir
        if not os.path.exists(self.working_dir):
            try: os.makedirs(self.working_dir, exist_ok=True)
            except: self.working_dir = self.save_dir

    def call_rpc(self, method, params=None):
        return call_aria2_rpc(method, params=params, port=self.rpc_port, token=self.rpc_token)

    def run(self):
        self.log_signal.emit("Connecting to Aria2 engine...")
        
        ext_data = load_extension_config()
        max_conn_val = ext_data.get("max_connections", 8)
        if not isinstance(max_conn_val, int) or max_conn_val < 1:
            max_conn_val = 8 # Fallback to default if invalid or 0
        
        max_conn = str(max_conn_val)
        
        self.init_segments_signal.emit(max_conn_val) 
        
        # Download to working_dir (could be temp)
        options = {
            "dir": self.working_dir, 
            "out": self.filename, 
            "split": max_conn, 
            "max-connection-per-server": max_conn, 
            "continue": "true"
        }
        
        # --- FULL BROWSER HEADERS (Mimic JD2) ---
        ua = self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
        headers = [
            f"User-Agent: {ua}",
            "Accept: */*",
            "Accept-Language: en-US,en;q=0.5",
            "Connection: keep-alive"
        ]
        
        if self.referrer:
            headers.append(f"Referer: {self.referrer}")
        else:
            parsed = urlparse(self.url)
            headers.append(f"Referer: {parsed.scheme}://{parsed.netloc}/")
        
        if self.cookies:
            headers.append(f"Cookie: {self.cookies}")
        
        options["header"] = headers
        options["user-agent"] = ua # Still set explicitly for safety
            
        params = [[self.url], options]
        self.gid = self.call_rpc("aria2.addUri", params)
        
        if not self.gid:
            self.log_signal.emit("Failed to communicate with Aria2 RPC.")
            self.finished_signal.emit(self.row_index, "Error")
            return

        self.log_signal.emit(f"Download started via Aria2 (GID: {self.gid[:6]})")
        
        max_conn_int = max_conn_val
        simulated_dls = [0] * max_conn_int
        simulated_speeds = [0] * max_conn_int
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
            
            # FORCE Complete if progress is 100%
            if total_length > 0 and completed_length >= total_length:
                state = "complete"

            if getattr(self, 'is_pause_requested', False):
                download_speed = 0
                state = "paused"
            elif getattr(self, 'is_resuming', False):
                if state == "paused":
                    state = "active"
                    display_state = "Resuming..."
                else:
                    self.is_resuming = False

            self.main_bar_signal.emit(completed_length, total_length)

            time_left = 0
            if download_speed > 0 and total_length > 0:
                time_left = (total_length - completed_length) / download_speed

            display_state = "Receiving data..."
            if state == "paused": display_state = "Paused"
            elif state == "complete": display_state = "Complete"
            elif state == "error": display_state = "Error"
            elif state == "removed": display_state = "Cancelled"

            self.main_progress_signal.emit(self.row_index, (
                self.filename,
                self.format_bytes(total_length, precision=2, pad=False) if total_length > 0 else "Unknown",
                display_state,
                self.format_time(time_left),
                f"{self.format_bytes(download_speed, precision=2, pad=False)}/s",
                completed_length,
                total_length,
                download_speed
            ))

            current_time = time.time()
            dt = current_time - last_update_time
            last_update_time = current_time
            
            real_seg_dls = [0] * max_conn_int
            real_seg_totals = [0] * max_conn_int

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
                    chunk_req = numPieces / float(max_conn_int)
                    for i in range(max_conn_int):
                        start_idx = int(i * chunk_req)
                        end_idx = int((i + 1) * chunk_req)
                        if i == max_conn_int - 1: end_idx = numPieces
                        
                        chunk_bits = bits[start_idx:end_idx]
                        seg_total = len(chunk_bits) * pieceLength
                        if i == max_conn_int - 1 and total_length > 0:
                             seg_total = max(0, total_length - (start_idx * pieceLength))
                        
                        real_seg_dls[i] = min(sum(chunk_bits) * pieceLength, seg_total)
                        real_seg_totals[i] = seg_total
            else:
                if total_length > 0:
                    part = total_length // max_conn_int
                    for i in range(max_conn_int):
                        seg_total = part if i < max_conn_int - 1 else max(0, total_length - part * (max_conn_int - 1))
                        real_seg_totals[i] = seg_total
                        real_seg_dls[i] = max(0, min(completed_length - (i * part), seg_total))

            if sum(real_seg_totals) > 0:
                incomplete_indices = [i for i in range(max_conn_int) if real_seg_dls[i] < real_seg_totals[i]]
                active_indices = [i for i in active_indices if i in incomplete_indices]
                
                target_connections = min(connections if connections > 0 else max_conn_int, len(incomplete_indices))
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
                    for idx in range(max_conn_int):
                        if idx in active_indices:
                            w_i = active_indices.index(idx)
                            speed_alloc = download_speed * (weights[w_i] / tot_w)
                            simulated_speeds[idx] = speed_alloc
                            simulated_dls[idx] += speed_alloc * dt
                        else:
                            simulated_speeds[idx] = 0
                else:
                    simulated_speeds = [0] * max_conn_int
                    
                for i in range(max_conn_int):
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
                
                # Move file from working_dir (temp) to final save_dir if different
                if self.working_dir != self.save_dir:
                    try:
                        temp_path = os.path.join(self.working_dir, self.filename)
                        if os.path.exists(temp_path):
                            self.log_signal.emit(f"Finalizing: Moving file to {self.save_dir}")
                            # Remove existing target if any
                            if os.path.exists(self.target_path):
                                os.remove(self.target_path)
                            shutil.move(temp_path, self.target_path)
                            
                            # Cleanup .aria2 control file in temp
                            control_file = temp_path + ".aria2"
                            if os.path.exists(control_file):
                                os.remove(control_file)
                    except Exception as e:
                        self.log_signal.emit(f"Error moving file to final destination: {e}")
                        self.finished_signal.emit(self.row_index, "Error")
                        break

                self.main_progress_signal.emit(self.row_index, (
                    self.filename,
                    self.format_bytes(total_length, precision=2, pad=False) if total_length > 0 else "Unknown",
                    "Complete",
                    "",
                    "",
                    total_length,
                    total_length,
                    0
                ))
                self.main_bar_signal.emit(total_length, total_length)
                self.finished_signal.emit(self.row_index, "Complete")
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
        self.is_paused = True
        self.is_resuming = False
        if self.gid:
            self.call_rpc("aria2.pause", [self.gid])
            self.log_signal.emit("Pausing download in Aria2...")

    def resume(self):
        self.is_pause_requested = False
        self.is_paused = False
        self.is_resuming = True
        self.paused_logged = False
        if self.gid:
            self.call_rpc("aria2.unpause", [self.gid])
            self.log_signal.emit("Resuming download in Aria2...")

    def set_global_speed_limit(self, limit):
        if self.gid:
            self.call_rpc("aria2.changeOption", [self.gid, {"max-download-limit": str(int(limit))}])

    def format_bytes(self, size, precision=2, pad=False):
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
        if seconds < 60: return f"{int(seconds)} sec"
        elif seconds < 3600: return f"{int(seconds//60)} min"
        else: return f"{int(seconds//3600)} hr"
