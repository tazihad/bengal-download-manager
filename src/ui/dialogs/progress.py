from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QWidget, QProgressBar, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QGridLayout, 
    QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt
from core.utils import show_in_folder

class DownloadProgressDialog(QDialog):
    def __init__(self, worker, parent=None):
        # Passing parent=None allows the window to be a separate top-level window
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle(f"{self.worker.filename}")
        
        # Ensure it behaves like a separate window in the OS
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window) 
        
        self.fixed_width = 520
        self.base_height = 230
        self.setFixedSize(self.fixed_width, self.base_height)
        
        self.is_expanded = False
        self.segment_bars = []
        self.current_bytes = 0
        self.total_bytes = 0
        
        self.worker.log_signal.connect(self.append_log)
        self.worker.main_bar_signal.connect(self.update_progress)
        self.worker.main_progress_signal.connect(self.update_stats)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.init_segments_signal.connect(self.init_segment_table)
        self.worker.segment_update_signal.connect(self.update_segment_row)

        self.setup_ui()
        self.init_segment_table(8)
        self.worker.start()

    def setup_status_tab(self):
        layout = QVBoxLayout(self.status_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        url_text = self.worker.url

        self.lbl_url = QLineEdit(url_text)
        self.lbl_url.setReadOnly(True)
        self.lbl_url.setCursorPosition(0)
        self.lbl_url.setToolTip(url_text)
        self.lbl_url.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                font-size: 8pt;
            }
        """)
        layout.addWidget(self.lbl_url)
        status_layout = QHBoxLayout()
        status_layout.setSpacing(5)
        lbl_status_title = QLabel("Status:")
        status_layout.addWidget(lbl_status_title)
        self.lbl_main_status = QLabel("Connecting...")
        self.lbl_main_status.setStyleSheet("color: #0078d4; font-weight: bold;") 
        status_layout.addWidget(self.lbl_main_status)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        grid = QGridLayout()
        grid.setSpacing(1)
        grid.setContentsMargins(0, 2, 0, 2)
        
        def add_row(label, widget, row):
            l = QLabel(label)
            grid.addWidget(l, row, 0)
            grid.addWidget(widget, row, 1)

        self.lbl_size = QLabel("Calculating...")
        self.lbl_size.setStyleSheet("font-weight: bold;")
        add_row("File size:", self.lbl_size, 0)
        
        self.lbl_downloaded = QLabel("0 bytes")
        self.lbl_downloaded.setStyleSheet("font-weight: bold;")
        add_row("Downloaded:", self.lbl_downloaded, 1)

        self.lbl_speed = QLabel("0 KB/sec")
        self.lbl_speed.setStyleSheet("font-weight: bold;")
        add_row("Transfer rate:", self.lbl_speed, 2)

        self.lbl_time = QLabel("Calculating...")
        self.lbl_time.setStyleSheet("font-weight: bold;")
        add_row("Time left:", self.lbl_time, 3)
        
        self.lbl_resume = QLabel("Unknown")
        add_row("Resume capability:", self.lbl_resume, 4)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
    
    def setup_limiter_tab(self):
        layout = QVBoxLayout(self.limiter_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        lbl_desc = QLabel("Limit download speed to avoid slowing down internet browsing.")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)
        
        control_layout = QHBoxLayout()
        self.chk_limit = QCheckBox("Use Speed Limiter")
        self.chk_limit.setStyleSheet("font-weight: bold;")
        self.chk_limit.toggled.connect(self.apply_speed_limit)
        control_layout.addWidget(self.chk_limit)
        layout.addLayout(control_layout)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Max speed:"))
        
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 100000)
        self.spin_limit.setValue(512)
        self.spin_limit.setEnabled(False) 
        self.spin_limit.valueChanged.connect(self.apply_speed_limit)
        input_layout.addWidget(self.spin_limit)
        input_layout.addWidget(QLabel("KB/sec"))
        input_layout.addStretch()
        layout.addLayout(input_layout)


    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        self.tabs = QTabWidget()
        self.tabs.setFixedHeight(150)
        main_layout.addWidget(self.tabs)
        
        self.status_tab = QWidget()
        self.setup_status_tab()
        self.tabs.addTab(self.status_tab, "Download status")
        
        self.limiter_tab = QWidget()
        self.setup_limiter_tab()
        self.tabs.addTab(self.limiter_tab, "Speed Limiter")

        # Add padding above the progress bar
        main_layout.addSpacing(5)
        main_layout.addSpacing(2)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(16)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet("""
            QProgressBar {
                border: 1px solid palette(mid);
                border-radius: 0px;
                background-color: palette(base);
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                                  stop:0 #90EE90, stop:0.5 #32CD32, stop:1 #228B22);
            }
        """)
        main_layout.addWidget(self.pbar)

        # Details frame (placed above buttons)
        self.details_frame = QFrame()
        details_layout = QVBoxLayout(self.details_frame)
        details_layout.setContentsMargins(0, 5, 0, 0)
        details_layout.setSpacing(2)
        
        lbl_conn = QLabel("Start positions and download progress by connections")
        lbl_conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_conn.setStyleSheet("font-weight: bold; font-size: 8pt; margin: 0px; padding: 0px;")
        details_layout.addWidget(lbl_conn)

        self.segments_container = QWidget()
        self.segments_container.setFixedHeight(18)
        self.segments_layout = QHBoxLayout(self.segments_container)
        self.segments_layout.setSpacing(1)
        self.segments_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(self.segments_container)
        
        self.seg_table = QTableWidget()
        self.seg_table.setColumnCount(4)
        self.seg_table.setHorizontalHeaderLabels(["N.", "Downloaded", "Rate", "Status"])
        self.seg_table.verticalHeader().setVisible(False)
        self.seg_table.setShowGrid(False)
        self.seg_table.setStyleSheet("QTableWidget { border: 1px solid #aaa; font-size: 8pt; }")

        header = self.seg_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(0, 25)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(1, 80) 
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.seg_table.setColumnWidth(2, 70)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) 
        
        self.seg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.seg_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.seg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        details_layout.addWidget(self.seg_table)
        self.details_frame.hide()
        main_layout.addWidget(self.details_frame)

        # Add padding above buttons
        main_layout.addSpacing(5)

        btn_layout = QHBoxLayout()
        self.btn_details = QPushButton("Details >>")
        self.btn_details.setCheckable(True)
        self.btn_details.setFixedHeight(30)
        self.btn_details.clicked.connect(self.toggle_details)
        btn_layout.addWidget(self.btn_details)
        
        btn_layout.addStretch()
        
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setFixedWidth(70)
        self.btn_pause.setFixedHeight(30)
        self.btn_pause.clicked.connect(self.toggle_pause) 
        btn_layout.addWidget(self.btn_pause)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(70)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.cancel_download)
        btn_layout.addWidget(self.btn_cancel)
        
        main_layout.addLayout(btn_layout)

    def apply_speed_limit(self):
        is_enabled = self.chk_limit.isChecked()
        self.spin_limit.setEnabled(is_enabled)
        
        if is_enabled:
            limit_kb = self.spin_limit.value()
            limit_bytes = limit_kb * 1024
            self.worker.set_global_speed_limit(limit_bytes)
        else:
            self.worker.set_global_speed_limit(0)

    def toggle_pause(self):
        if self.btn_pause.text() == "Pause":
            self.worker.pause()
            self.btn_pause.setText("Resume")
            self.lbl_main_status.setText("Paused")
            self.btn_cancel.setText("Close") 
        elif self.btn_pause.text() == "Resume":
            self.worker.resume()
            self.btn_pause.setText("Pause")
            self.lbl_main_status.setText("Resuming...")
            self.btn_cancel.setText("Cancel") 
        elif self.btn_pause.text() == "Open Folder":
            import os
            show_in_folder(self.worker.target_path)

    def toggle_details(self, checked):
        if checked:
            self.details_frame.show()
            self.btn_details.setText("Details <<")
            row_height = 20
            self.seg_table.verticalHeader().setDefaultSectionSize(row_height)
            num_rows = self.seg_table.rowCount()
            header_height = 25
            table_height = header_height + (row_height * num_rows) + 2
            self.seg_table.setFixedHeight(table_height)
            
            # Expand window vertically while keeping width 520
            details_height = table_height + 50
            self.setFixedSize(self.fixed_width, self.base_height + details_height)
        else:
            self.details_frame.hide()
            self.btn_details.setText("Details >>")
            # Restore to base IDM size 520x250
            self.setFixedSize(self.fixed_width, self.base_height)

    def init_segment_table(self, num_segments):
        # Aria2 backend (which has 'gid') supports resume automatically
        if num_segments > 1 or hasattr(self.worker, 'gid'):
            self.lbl_resume.setText("Yes")
        else:
            self.lbl_resume.setText("No/Unknown")

        for i in reversed(range(self.segments_layout.count())): 
            self.segments_layout.itemAt(i).widget().setParent(None)
        self.segment_bars = []

        total_display = 8

        for i in range(total_display):
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

        self.seg_table.setRowCount(total_display)
        for i in range(total_display):
            self.seg_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            if i < num_segments:
                self.seg_table.setItem(i, 1, QTableWidgetItem("0 B")) 
                self.seg_table.setItem(i, 2, QTableWidgetItem("0 B/s"))
                self.seg_table.setItem(i, 3, QTableWidgetItem("Pending..."))
            else:
                self.seg_table.setItem(i, 1, QTableWidgetItem("-")) 
                self.seg_table.setItem(i, 2, QTableWidgetItem("-"))
                self.seg_table.setItem(i, 3, QTableWidgetItem("Unused"))

    def update_segment_row(self, index, dl, total, speed, status):
        if index < len(self.segment_bars):
            if total > 0:
                self.segment_bars[index].setMaximum(10000)
                self.segment_bars[index].setValue(int((dl / total) * 10000))
            else:
                self.segment_bars[index].setMaximum(0)
                self.segment_bars[index].setValue(0)
            
            dl_str = self.worker.format_bytes(dl)
            self.seg_table.setItem(index, 1, QTableWidgetItem(dl_str))
            
            speed_str = f"{self.worker.format_bytes(speed)}/s"
            self.seg_table.setItem(index, 2, QTableWidgetItem(speed_str))
            
            if status == "Receiving data...":
                 display_status = "Downloading"
            elif status == "Complete":
                 display_status = "Complete"
            else:
                 display_status = status
            self.seg_table.setItem(index, 3, QTableWidgetItem(display_status))

    def append_log(self, text):
        if len(text) < 60:
            if text == "Resuming download...":
                display_text = "Resuming..."
            elif text == "Pausing download...":
                display_text = "Paused"
            elif text == "Connecting to server...":
                display_text = "Connecting..."
            else:
                display_text = text
            self.lbl_main_status.setText(display_text)

    def update_progress(self, current, total):
        self.current_bytes = current
        self.total_bytes = total
        
        # Scale for QProgressBar since it takes 32-bit int
        if total > 0:
            self.pbar.setMaximum(10000)
            self.pbar.setValue(int((current / total) * 10000))
        else:
            self.pbar.setMaximum(0)
            self.pbar.setValue(0)

    def update_stats(self, row, data):
        # Only update size if it's not "Unknown" or if current is "Calculating..."
        new_size_text = data[1]
        if new_size_text != "Unknown" or self.lbl_size.text() == "Calculating...":
            self.lbl_size.setText(new_size_text)
            
        self.lbl_speed.setText(data[4])
        self.lbl_time.setText(data[3])
        
        # Update internal byte counts if high-precision data is available (indices 5 and 6)
        if len(data) > 6:
            self.current_bytes = data[5]
            self.total_bytes = data[6]
            
        current_bytes = self.current_bytes
        total_bytes = self.total_bytes
        
        # Calculate percentage properly based on progress bar values
        if total_bytes > 0:
            percent = f"{(current_bytes / total_bytes) * 100:.1f}%"
        else:
            percent = "Unknown %" if current_bytes > 0 else "0.0%"
            
        self.lbl_downloaded.setText(f"{self.worker.format_bytes(current_bytes)} ({percent})")
        
        # Map worker status to display status
        worker_status = data[2]
        if worker_status.startswith("Receiving data"):
            display_status = "Downloading"
        elif worker_status == "Connecting...":
            display_status = "Connecting..."
        elif worker_status == "Complete":
            display_status = "Complete"
        elif worker_status == "Resume GET...":
            display_status = "Resuming..."
        else:
            display_status = worker_status
            
        self.lbl_main_status.setText(display_status)
        
        if display_status in ["Downloading", "Resuming...", "Connecting..."]:
            self.btn_pause.setText("Pause")
            self.btn_cancel.setText("Cancel")
            self.btn_pause.setEnabled(True)
            self.btn_cancel.setEnabled(True)
        elif display_status == "Paused":
            self.btn_pause.setText("Resume")
            self.btn_cancel.setText("Close")
            self.btn_pause.setEnabled(True)
            self.btn_cancel.setEnabled(True)
        elif display_status in ["Cancelled", "Error"]:
            self.btn_pause.setText("Resume")
            self.btn_cancel.setText("Close")
            self.btn_pause.setEnabled(True)
            self.btn_cancel.setEnabled(True)


    def cancel_download(self):
        if self.btn_cancel.text() == "Cancel":
            self.worker.stop()
            self.worker.finished_signal.emit(self.worker.row_index, "Cancelled")
            self.btn_cancel.setText("Close")
        
        self.reject() 

    def on_finished(self, row, status):
        if status == "Complete":
            display_status = "Complete"
        elif status == "Cancelled":
            display_status = "Cancelled"
        elif status == "Error":
            display_status = "Error"
            self.lbl_main_status.setStyleSheet("font-weight: bold; color: red;")
        elif status == "Paused":
            display_status = "Paused"
        else:
            display_status = status
            
        self.lbl_main_status.setText(display_status)
        
        if display_status == "Complete":
            if self.total_bytes > 0:
                self.current_bytes = self.total_bytes
                self.pbar.setMaximum(10000)
                self.pbar.setValue(10000)
                self.lbl_downloaded.setText(f"{self.worker.format_bytes(self.total_bytes)} (100.0%)")
            else:
                self.pbar.setMaximum(10000)
                self.pbar.setValue(10000)
                self.lbl_downloaded.setText(f"{self.worker.format_bytes(self.current_bytes)} (100.0%)")
                
            self.lbl_time.setText("0 sec")
            self.lbl_speed.setText("0 B/s")
            
            self.btn_cancel.setText("Close")
            self.btn_pause.setText("Open Folder")
            self.btn_pause.setEnabled(True)
            try: self.btn_pause.clicked.disconnect() 
            except: pass
            
            def open_target_folder():
                show_in_folder(self.worker.target_path)
            
            self.btn_pause.clicked.connect(open_target_folder)
        elif display_status in ["Cancelled", "Paused", "Error"]:
            self.btn_cancel.setText("Close")
            self.btn_pause.setText("Resume")
            self.btn_pause.setEnabled(True)
            
            
    def closeEvent(self, event):
        if self.btn_cancel.text() == "Cancel":
            self.worker.stop()
            self.worker.finished_signal.emit(self.worker.row_index, "Paused")
        self.reject()
