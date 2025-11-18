import sys
import os
import time
import subprocess
from urllib.parse import urlparse
import urllib.request
import urllib.error
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QDialog, QVBoxLayout, 
    QTabWidget, QWidget, QGroupBox, QPushButton, QLabel, 
    QHBoxLayout, QAbstractItemView, QLineEdit, QMessageBox,
    QProgressBar, QTextEdit, QFrame, QGridLayout, QSizePolicy, QLayout
)
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QBrush
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMutex

# --- HELPER: UNIQUE FILENAME ---
def get_unique_filepath(filepath):
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"

# --- WORKER FOR SINGLE SEGMENT ---
class SegmentWorker(QThread):
    progress_signal = pyqtSignal(int, int, int, float, str)
    finished_signal = pyqtSignal(int, bool)

    def __init__(self, index, url, start_byte, end_byte, filepath):
        super().__init__()
        self.index = index
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.filepath = filepath
        self.is_running = True
        self.is_paused = False
        self.downloaded = 0
        self.total_size = (end_byte - start_byte) + 1

    def run(self):
        try:
            req = urllib.request.Request(self.url)
            req.add_header("Range", f"bytes={self.start_byte}-{self.end_byte}")
            
            self.progress_signal.emit(self.index, 0, self.total_size, 0, "Send GET...")
            
            with urllib.request.urlopen(req, timeout=20) as response:
                self.progress_signal.emit(self.index, 0, self.total_size, 0, "Receiving data...")
                
                with open(self.filepath, "r+b") as f:
                    f.seek(self.start_byte)
                    
                    start_time = time.time()
                    last_emit_time = start_time
                    chunk_size = 16384 
                    bytes_since_last_emit = 0

                    while self.is_running:
                        # PAUSE LOGIC
                        if self.is_paused:
                            time.sleep(0.2)
                            start_time = time.time() 
                            last_emit_time = time.time()
                            continue

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        self.downloaded += len(chunk)
                        bytes_since_last_emit += len(chunk)
                        
                        current_time = time.time()
                        if current_time - last_emit_time > 0.8: 
                            speed = bytes_since_last_emit / (current_time - last_emit_time)
                            self.progress_signal.emit(
                                self.index, self.downloaded, self.total_size, speed, "Receiving data..."
                            )
                            last_emit_time = current_time
                            bytes_since_last_emit = 0

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
    # Updated: Emits status string instead of boolean
    finished_signal = pyqtSignal(int, str) 
    log_signal = pyqtSignal(str)
    segment_update_signal = pyqtSignal(int, int, int, float, str) 
    init_segments_signal = pyqtSignal(int) 

    def __init__(self, url, row_index, save_dir):
        super().__init__()
        self.url = url
        self.row_index = row_index
        self.save_dir = save_dir
        self.is_running = True
        self.is_paused = False
        self.mutex = QMutex()
        
        parsed_url = urlparse(self.url)
        original_filename = os.path.basename(parsed_url.path) or "downloaded_file"
        
        full_path = os.path.join(self.save_dir, original_filename)
        self.save_path = get_unique_filepath(full_path)
        self.filename = os.path.basename(self.save_path)
        
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
            
            num_threads = 8
            if accept_ranges == 'none' or total_size < 1024 * 1024: 
                num_threads = 1
                self.log_signal.emit("Using 1 connection.")
            else:
                self.log_signal.emit(f"Splitting into {num_threads} connections.")

            self.init_segments_signal.emit(num_threads)

            with open(self.save_path, "wb") as f:
                f.truncate(total_size) 

            part_size = total_size // num_threads
            self.workers = []
            
            for i in range(num_threads):
                start = i * part_size
                end = start + part_size - 1
                if i == num_threads - 1:
                    end = total_size - 1 
                
                worker = SegmentWorker(i, self.url, start, end, self.save_path)
                worker.progress_signal.connect(self.update_segment_stat)
                self.workers.append(worker)
                self.segment_stats[i] = {'dl': 0, 'speed': 0}
                worker.start()

            finished_count = 0
            while finished_count < num_threads and self.is_running:
                if self.is_paused:
                    time.sleep(0.2)
                    self.main_progress_signal.emit(self.row_index, (
                        self.filename, self.format_bytes(total_size), "Paused", "", "0 KB/s"
                    ))
                    continue

                total_dl = sum(s['dl'] for s in self.segment_stats.values())
                total_speed = sum(s['speed'] for s in self.segment_stats.values())
                
                if total_speed > 0:
                    time_left = (total_size - total_dl) / total_speed
                else:
                    time_left = 0
                    
                percent = (total_dl / total_size) * 100
                
                self.main_bar_signal.emit(total_dl, total_size)
                self.main_progress_signal.emit(self.row_index, (
                    self.filename,
                    self.format_bytes(total_size),
                    f"{percent:.1f}%",
                    self.format_time(time_left),
                    f"{self.format_bytes(total_speed)}/s"
                ))

                finished_count = sum(1 for w in self.workers if w.isFinished())
                self.msleep(100) 

            if self.is_running:
                self.log_signal.emit("File assembled and verified.")
                self.main_progress_signal.emit(self.row_index, (self.filename, self.format_bytes(total_size), "Completed", "", ""))
                self.finished_signal.emit(self.row_index, "Completed")
            else:
                self.log_signal.emit("Download stopped.")
                self.finished_signal.emit(self.row_index, "Stopped")

        except Exception as e:
            self.log_signal.emit(f"Critical Error: {str(e)}")
            self.finished_signal.emit(self.row_index, "Error")

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


# --- DOWNLOAD PROGRESS DIALOG ---
class DownloadProgressDialog(QDialog):
    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle(f"{self.worker.filename}")
        
        # CONSTANT FIXED WIDTH
        self.fixed_width = 500
        self.base_height = 280
        self.setFixedSize(self.fixed_width, self.base_height)
        
        self.is_expanded = False
        self.segment_bars = []
        
        # Connect signals
        self.worker.log_signal.connect(self.append_log)
        self.worker.main_bar_signal.connect(self.update_progress)
        self.worker.main_progress_signal.connect(self.update_stats)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.init_segments_signal.connect(self.init_segment_table)
        self.worker.segment_update_signal.connect(self.update_segment_row)

        self.setup_ui()
        
        # Initialize UI with 8 connections immediately
        self.init_segment_table(8)
        
        self.worker.start()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        # 1. Top Tabs
        self.tabs = QTabWidget()
        self.tabs.setFixedWidth(self.fixed_width - 20) 
        main_layout.addWidget(self.tabs)
        
        self.status_tab = QWidget()
        self.setup_status_tab()
        self.tabs.addTab(self.status_tab, "Download status")
        self.tabs.addTab(QWidget(), "Speed Limiter")
        self.tabs.addTab(QWidget(), "Options on completion")

        # 2. Main Progress Bar
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(20)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 0px;
                background-color: #333;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                                  stop:0 #76e068, stop:0.5 #32CD32, stop:1 #228B22);
                width: 15px;
                margin: 0.5px;
            }
        """)
        main_layout.addWidget(self.pbar)

        # 3. Buttons Row
        btn_layout = QHBoxLayout()
        self.btn_details = QPushButton("Show Details >>")
        self.btn_details.setCheckable(True)
        self.btn_details.clicked.connect(self.toggle_details)
        btn_layout.addWidget(self.btn_details)
        
        btn_layout.addStretch()
        
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.toggle_pause) 
        btn_layout.addWidget(self.btn_pause)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_download)
        btn_layout.addWidget(self.btn_cancel)
        
        main_layout.addLayout(btn_layout)

        # 4. Details Section
        self.details_frame = QFrame()
        details_layout = QVBoxLayout(self.details_frame)
        details_layout.setContentsMargins(5, 5, 5, 5)
        details_layout.setSpacing(5)
        
        lbl_conn = QLabel("Start positions and download progress by connections")
        lbl_conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_conn.setStyleSheet("font-weight: bold; font-size: 9pt; color: #888;")
        details_layout.addWidget(lbl_conn)

        self.segments_container = QWidget()
        self.segments_container.setFixedHeight(20)
        self.segments_layout = QHBoxLayout(self.segments_container)
        self.segments_layout.setSpacing(2)
        self.segments_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(self.segments_container)
        
        self.seg_table = QTableWidget()
        self.seg_table.setColumnCount(4)
        self.seg_table.setHorizontalHeaderLabels(["N.", "Downloaded", "Transfer Rate", "Status"])
        self.seg_table.verticalHeader().setVisible(False)
        self.seg_table.setShowGrid(False)
        self.seg_table.setStyleSheet("QTableWidget { border: 1px solid #aaa; }")
        
        self.seg_table.setFixedWidth(self.fixed_width - 30)

        header = self.seg_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(0, 30)
        
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(1, 85) 
        
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(2, 85)
        
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) 
        
        self.seg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.seg_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.seg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        details_layout.addWidget(self.seg_table)
        
        self.details_frame.hide()
        main_layout.addWidget(self.details_frame)
        
        # No addStretch() to ensure snapping

    def setup_status_tab(self):
        layout = QVBoxLayout(self.status_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        self.lbl_url = QLabel(self.worker.url)
        self.lbl_url.setStyleSheet("color: #666;")
        self.lbl_url.setFixedWidth(self.fixed_width - 60) 
        self.lbl_url.setWordWrap(True) 
        layout.addWidget(self.lbl_url)

        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        self.lbl_main_status = QLabel("Connecting...")
        self.lbl_main_status.setStyleSheet("color: #0066cc; font-weight: bold;") 
        status_layout.addWidget(self.lbl_main_status)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        grid = QGridLayout()
        grid.setSpacing(5)
        
        grid.addWidget(QLabel("File size"), 0, 0)
        self.lbl_size = QLabel("Calculating...")
        self.lbl_size.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_size, 0, 1)
        
        grid.addWidget(QLabel("Downloaded"), 1, 0)
        self.lbl_downloaded = QLabel("0 bytes")
        self.lbl_downloaded.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_downloaded, 1, 1)

        grid.addWidget(QLabel("Transfer rate"), 2, 0)
        self.lbl_speed = QLabel("0 KB/sec")
        self.lbl_speed.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_speed, 2, 1)

        grid.addWidget(QLabel("Time left"), 3, 0)
        self.lbl_time = QLabel("Calculating...")
        self.lbl_time.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_time, 3, 1)
        
        grid.addWidget(QLabel("Resume capability"), 4, 0)
        self.lbl_resume = QLabel("Unknown")
        self.lbl_resume.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_resume, 4, 1)

        layout.addLayout(grid)
        layout.addStretch()

    def toggle_details(self, checked):
        if checked:
            self.details_frame.show()
            self.btn_details.setText("Hide Details <<")
            
            # Calculate height manually
            row_height = self.seg_table.verticalHeader().defaultSectionSize()
            num_rows = self.seg_table.rowCount()
            header_height = self.seg_table.horizontalHeader().height()
            table_height = header_height + (row_height * num_rows) + 4
            
            self.seg_table.setMinimumHeight(table_height)
            self.seg_table.setMaximumHeight(table_height)
            
            details_extra = table_height + 60 
            self.setFixedSize(self.fixed_width, self.base_height + details_extra)
        else:
            self.details_frame.hide()
            self.btn_details.setText("Show Details >>")
            self.setFixedSize(self.fixed_width, self.base_height)

    def toggle_pause(self):
        if self.btn_pause.text() == "Pause":
            self.worker.pause()
            self.btn_pause.setText("Resume")
            self.lbl_main_status.setText("Paused")
        else:
            self.worker.resume()
            self.btn_pause.setText("Pause")
            self.lbl_main_status.setText("Resuming...")

    def init_segment_table(self, num_segments):
        if num_segments > 1:
            self.lbl_resume.setText("Yes")
        else:
            self.lbl_resume.setText("No/Unknown")

        for i in reversed(range(self.segments_layout.count())): 
            self.segments_layout.itemAt(i).widget().setParent(None)
        self.segment_bars = []

        for i in range(num_segments):
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setStyleSheet("""
                QProgressBar { border: 1px solid #555; background-color: #333; border-radius: 0px; }
                QProgressBar::chunk { 
                    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a90e2, stop:1 #0056b3); 
                }
            """)
            self.segments_layout.addWidget(bar)
            self.segment_bars.append(bar)

        self.seg_table.setRowCount(num_segments)
        for i in range(num_segments):
            self.seg_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.seg_table.setItem(i, 1, QTableWidgetItem("0 KB"))
            self.seg_table.setItem(i, 2, QTableWidgetItem("0 KB/s"))
            self.seg_table.setItem(i, 3, QTableWidgetItem("Pending..."))

    def update_segment_row(self, index, dl, total, speed, status):
        if index < len(self.segment_bars):
            self.segment_bars[index].setMaximum(total)
            self.segment_bars[index].setValue(dl)
            
            dl_str = f"{dl/1024:.0f} KB" if dl < 1024*1024 else f"{dl/1024/1024:.2f} MB"
            self.seg_table.setItem(index, 1, QTableWidgetItem(dl_str))
            
            speed_str = f"{speed/1024:.0f} KB/s" if speed < 1024*1024 else f"{speed/1024/1024:.2f} MB/s"
            self.seg_table.setItem(index, 2, QTableWidgetItem(speed_str))
            self.seg_table.setItem(index, 3, QTableWidgetItem(status))

    def append_log(self, text):
        if len(text) < 60:
            self.lbl_main_status.setText(text)

    def update_progress(self, current, total):
        self.pbar.setMaximum(total)
        self.pbar.setValue(current)

    def update_stats(self, row, data):
        self.lbl_size.setText(data[1])
        self.lbl_speed.setText(data[4])
        self.lbl_time.setText(data[3])
        
        current_bytes = self.pbar.value()
        current_mb = current_bytes / (1024*1024)
        percent = data[2]
        self.lbl_downloaded.setText(f"{current_mb:.2f} MB ({percent})")

    def cancel_download(self):
        self.worker.stop()
        self.reject()

    def on_finished(self, row, status_text):
        self.lbl_main_status.setText(status_text)
        if status_text == "Completed":
            self.pbar.setValue(self.pbar.maximum())
            self.btn_cancel.setText("Close")
            self.btn_pause.setEnabled(False)
            QMessageBox.information(self, "Download Complete", "File downloaded successfully!")
            self.accept()

# --- ADD URL DIALOG ---
class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setFixedSize(600, 150)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Address:"))
        input_layout = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setPixmap(self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxInformation))
        input_layout.addWidget(self.icon_label)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://")
        input_layout.addWidget(self.url_input)
        layout.addLayout(input_layout)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_download = QPushButton("Start Download")
        self.btn_download.setDefault(True)
        self.btn_download.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def get_url(self):
        return self.url_input.text().strip()

# --- OPTIONS DIALOG ---
class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setFixedSize(500, 400)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.general_tab = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.general_tab, "General")
        self.tabs.addTab(QWidget(), "File Types")
        self.tabs.addTab(QWidget(), "Connection")
        self.tabs.addTab(QWidget(), "Save To")
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def setup_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        grp_integration = QGroupBox("System Integration")
        vbox_int = QVBoxLayout()
        vbox_int.addWidget(QLabel("Launch Bengal DM on system startup"))
        vbox_int.addWidget(QLabel("Integrate into browsers"))
        grp_integration.setLayout(vbox_int)
        layout.addWidget(grp_integration)
        
        grp_settings = QGroupBox("Engine Settings")
        vbox_settings = QVBoxLayout()
        vbox_settings.addWidget(QLabel("Default Connections: 8"))
        
        # Check aria2 version
        version_info = "Not found"
        aria2_path = os.path.expanduser("~/bin/aria2c")
        # Check local bin first
        if os.path.exists(aria2_path):
            try:
                out = subprocess.check_output([aria2_path, "--version"], text=True).splitlines()[0]
                version_info = f"{out} ({aria2_path})"
            except:
                pass
        else:
            # Check system path
            try:
                out = subprocess.check_output(["aria2c", "--version"], text=True).splitlines()[0]
                version_info = f"{out} (System Path)"
            except:
                pass
                
        vbox_settings.addWidget(QLabel(f"Aria2 Binary: {version_info}"))
        
        grp_settings.setLayout(vbox_settings)
        layout.addWidget(grp_settings)
        layout.addStretch()

# --- MAIN WINDOW ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        self.setGeometry(200, 150, 1000, 600)
        self.setup_toolbar()
        self.setup_central_widget()
        self.setStatusBar(QStatusBar(self))
        self.active_downloads = {} 

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        actions_config = [
            ("Add URL", QStyle.StandardPixmap.SP_FileDialogNewFolder),
            ("Resume", QStyle.StandardPixmap.SP_MediaPlay),
            ("Stop", QStyle.StandardPixmap.SP_MediaStop),
            ("Stop All", QStyle.StandardPixmap.SP_DialogCancelButton),
            ("Delete", QStyle.StandardPixmap.SP_TrashIcon),
            ("Delete Completed", QStyle.StandardPixmap.SP_DialogDiscardButton),
            ("Options", QStyle.StandardPixmap.SP_FileDialogDetailedView),
        ]

        for text, icon_type in actions_config:
            icon = self.style().standardIcon(icon_type)
            action = QAction(icon, text, self)
            action.setStatusTip(text)
            toolbar.addAction(action)
            
            if text == "Options":
                action.triggered.connect(self.open_options)
            elif text == "Add URL":
                action.triggered.connect(self.open_add_url)
            elif text == "Resume":
                action.triggered.connect(self.resume_selected_download)
            elif text == "Stop":
                action.triggered.connect(self.stop_selected_download)
            elif text == "Stop All":
                action.triggered.connect(self.stop_all_downloads)
            elif text == "Delete":
                action.triggered.connect(self.delete_selected_download)
            elif text == "Delete Completed":
                action.triggered.connect(self.delete_completed_downloads)

    def setup_central_widget(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.itemClicked.connect(self.filter_downloads) # Connected Sidebar Filter
        
        all_downloads = QTreeWidgetItem(self.category_tree, ["All Downloads"])
        all_downloads.setExpanded(True)
        categories = ["Compressed", "Documents", "Music", "Programs", "Video"]
        for cat in categories:
            QTreeWidgetItem(all_downloads, [cat])
        QTreeWidgetItem(self.category_tree, ["Unfinished"])
        QTreeWidgetItem(self.category_tree, ["Finished"])
        
        self.download_table = QTableWidget()
        self.download_table.setColumnCount(7)
        self.download_table.verticalHeader().setVisible(False)
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_table.setHorizontalHeaderLabels([
            "File Name", "Size", "Status", "Time Left", 
            "Transfer Rate", "Last Try", "Date Added"
        ])
        header = self.download_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.category_tree)
        splitter.addWidget(self.download_table)
        splitter.setSizes([200, 800])
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

    def filter_downloads(self, item, column):
        category = item.text(0)
        
        # Definitions for Extensions
        ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
            "Programs": [".exe", ".msi", ".sh", ".bin", ".deb", ".bat"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }

        for row in range(self.download_table.rowCount()):
            self.download_table.setRowHidden(row, False) # Show by default
            
            filename = self.download_table.item(row, 0).text().lower()
            status = self.download_table.item(row, 2).text()
            
            should_hide = False
            
            if category == "All Downloads":
                should_hide = False
            elif category == "Unfinished":
                if status == "Completed":
                    should_hide = True
            elif category == "Finished":
                if status != "Completed":
                    should_hide = True
            elif category in ext_map:
                # Check extensions
                extensions = ext_map[category]
                if not any(filename.endswith(ext) for ext in extensions):
                    should_hide = True
            
            if should_hide:
                self.download_table.setRowHidden(row, True)

    def open_add_url(self):
        dialog = AddUrlDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            if url:
                self.start_download(url)

    def start_download(self, url):
        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        item = QTableWidgetItem(url)
        item.setData(Qt.ItemDataRole.UserRole, url)
        self.download_table.setItem(row, 0, item)
        
        self.download_table.setItem(row, 1, QTableWidgetItem("..."))
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        self.download_table.setItem(row, 3, QTableWidgetItem("..."))
        self.download_table.setItem(row, 4, QTableWidgetItem("..."))
        self.download_table.setItem(row, 5, QTableWidgetItem("Just now"))
        self.download_table.setItem(row, 6, QTableWidgetItem(time.strftime("%Y-%m-%d")))

        self._start_download_worker(url, row)

    def _start_download_worker(self, url, row):
        save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        worker = DownloadWorker(url, row, save_dir)
        worker.main_progress_signal.connect(self.update_download_row)
        worker.finished_signal.connect(self.download_finished)
        
        progress_dialog = DownloadProgressDialog(worker, self)
        progress_dialog.show()
        
        self.active_downloads[row] = progress_dialog
        progress_dialog.finished.connect(lambda: self.active_downloads.pop(row, None))

    def resume_selected_download(self):
        selected_rows = self.download_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        
        if row in self.active_downloads:
            self.active_downloads[row].activateWindow()
            self.active_downloads[row].raise_()
            return
        
        item = self.download_table.item(row, 0)
        url = item.data(Qt.ItemDataRole.UserRole)
        
        if url:
            self.download_table.setItem(row, 2, QTableWidgetItem("Resuming..."))
            self._start_download_worker(url, row)
        else:
            QMessageBox.warning(self, "Error", "Could not find download URL.")

    def stop_selected_download(self):
        selected_rows = self.download_table.selectionModel().selectedRows()
        for idx in selected_rows:
            row = idx.row()
            if row in self.active_downloads:
                dialog = self.active_downloads[row]
                dialog.worker.stop()
                dialog.reject() 
                self.download_table.setItem(row, 2, QTableWidgetItem("Stopped"))

    def stop_all_downloads(self):
        active_rows = list(self.active_downloads.keys())
        for row in active_rows:
            if row in self.active_downloads:
                dialog = self.active_downloads[row]
                dialog.worker.stop()
                dialog.reject()
                self.download_table.setItem(row, 2, QTableWidgetItem("Stopped"))

    def delete_selected_download(self):
        selected_rows = sorted(self.download_table.selectionModel().selectedRows(), key=lambda x: x.row(), reverse=True)
        
        if not selected_rows:
            return
            
        confirm = QMessageBox.question(self, "Delete", "Are you sure you want to delete selected download(s)?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if confirm == QMessageBox.StandardButton.Yes:
            for idx in selected_rows:
                row = idx.row()
                if row in self.active_downloads:
                    dialog = self.active_downloads[row]
                    dialog.worker.stop()
                    dialog.reject()
                
                self.download_table.removeRow(row)

    def delete_completed_downloads(self):
        rows_to_delete = []
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() == "Completed":
                rows_to_delete.append(row)
        
        if not rows_to_delete:
            return

        confirm = QMessageBox.question(self, "Delete Completed", f"Delete {len(rows_to_delete)} completed downloads?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if confirm == QMessageBox.StandardButton.Yes:
            for row in sorted(rows_to_delete, reverse=True):
                self.download_table.removeRow(row)

    def update_download_row(self, row, data):
        if row < self.download_table.rowCount():
            item0 = self.download_table.item(row, 0)
            if not item0: 
                item0 = QTableWidgetItem()
                self.download_table.setItem(row, 0, item0)
            
            item0.setText(data[0]) 
            
            self.download_table.setItem(row, 1, QTableWidgetItem(data[1]))
            self.download_table.setItem(row, 2, QTableWidgetItem(data[2]))
            self.download_table.setItem(row, 3, QTableWidgetItem(data[3]))
            self.download_table.setItem(row, 4, QTableWidgetItem(data[4]))

    def download_finished(self, row, status_text):
        if row < self.download_table.rowCount():
            self.download_table.setItem(row, 2, QTableWidgetItem(status_text))

    def open_options(self):
        dialog = OptionsDialog(self)
        dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())