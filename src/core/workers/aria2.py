import time
import os
import random
from urllib.parse import urlparse, unquote
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import get_unique_filepath, load_extension_config, call_aria2_rpc

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
        return call_aria2_rpc(method, params=params, port=self.rpc_port, token=self.rpc_token)

    def run(self):
        self.log_signal.emit("Connecting to Aria2 engine...")
        self.init_segments_signal.emit(8) 
        
        params = [[self.url], {"dir": self.save_dir, "out": self.filename, "split": "8", "max-connection-per-server": "8", "continue": "true"}]
        self.gid = self.call_rpc("aria2.addUri", params)
        
        if not self.gid:
            self.log_signal.emit("Failed to communicate with Aria2 RPC.")
            self.finished_signal.emit(self.row_index, "Error")
            return

        self.log_signal.emit(f"Download started via Aria2 (GID: {self.gid[:6]})")
        
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
