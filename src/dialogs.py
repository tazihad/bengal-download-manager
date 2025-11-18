import os
import time
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QWidget, QGroupBox, QProgressBar, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QGridLayout, 
    QMessageBox, QStyle, QLayout, QComboBox
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt

# --- ADD URL DIALOG ---
class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setFixedSize(600, 100)
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
        
        # Setup Tabs
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

    def get_theme(self):
        # Placeholder for theme removal
        return None


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
        
        main_layout.addStretch()

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
        grid.addWidget(self.lbl_resume, 4, 1)

        layout.addLayout(grid)
        layout.addStretch()

    def toggle_details(self, checked):
        if checked:
            self.details_frame.show()
            self.btn_details.setText("Hide Details <<")
            
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

    def on_finished(self, row, status):
        self.lbl_main_status.setText(status)
        
        if status == "Completed":
            self.pbar.setValue(self.pbar.maximum())
            self.btn_cancel.setText("Close")
            
            # Turn the Pause button into an Open Folder button
            self.btn_pause.setText("Open Folder")
            self.btn_pause.setEnabled(True)
            # Disconnect old pause connection and connect new open folder logic
            try: self.btn_pause.clicked.disconnect() 
            except: pass
            self.btn_pause.clicked.connect(lambda: os.startfile(self.worker.save_dir) if os.name == 'nt' else subprocess.Popen(['xdg-open', self.worker.save_dir]))
            
        elif status == "Error":
             self.lbl_main_status.setStyleSheet("font-weight: bold; color: red;")