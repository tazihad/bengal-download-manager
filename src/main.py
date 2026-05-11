import sys
import os
import time
import json
import shutil
import subprocess
import socket
import threading
import urllib.request
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu,
    QFileIconProvider, QInputDialog, QFileDialog, QDialog, 
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit
)
from PyQt6.QtGui import QAction, QFont, QCloseEvent, QIcon, QColor, QPalette, QDesktopServices, QKeySequence
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase, QUrl, QTimer, QThread, pyqtSignal, QObject

from workers import DownloadWorker, Aria2Worker
from dialogs import AddUrlDialog, OptionsDialog, DownloadProgressDialog, PropertiesDialog, load_category_config, load_extension_config
from utils import (
    get_data_dir, get_config_dir, get_unique_filepath, ensure_aria2, 
    load_proxy_config, load_extension_config, generate_proxychains_config, get_proxychains_bin
)

# Default TCP port for extension communication
DM_CONNECTOR_PORT = 9000 

# --- IPC HELPER THREAD ---
class SignalEmitter(QObject):
    """Utility to emit signals safely to the GUI thread."""
    new_download_signal = pyqtSignal(str)

class TcpListenerThread(QThread):
    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.is_running = True
        self.server_socket = None

    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("127.0.0.1", self.port)) 
            self.server_socket.listen(1)
            
            while self.is_running:
                self.server_socket.settimeout(1.0)
                try:
                    conn, addr = self.server_socket.accept()
                    with conn:
                        data = conn.recv(4096).decode('utf-8') 
                        if not data: continue

                        # 1. Handle CORS Preflight (Browser security check)
                        if data.startswith("OPTIONS"):
                            response = (
                                "HTTP/1.1 200 OK\r\n"
                                "Access-Control-Allow-Origin: *\r\n"
                                "Access-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
                                "Access-Control-Allow-Headers: Content-Type\r\n\r\n"
                            )
                            conn.sendall(response.encode('utf-8'))
                            continue
                        
                        # 2. Handle Status Ping and Config Sync
                        if data.startswith("GET"):
                            ext_data = load_extension_config()
                            config_json = json.dumps({
                                "status": "Bengal DM is running",
                                "aria2": {
                                    "port": ext_data.get("port", 56800),
                                    "token": ext_data.get("token", "")
                                }
                            })
                            response = (
                                "HTTP/1.1 200 OK\r\n"
                                "Access-Control-Allow-Origin: *\r\n"
                                "Content-Type: application/json\r\n\r\n" + config_json
                            )
                            conn.sendall(response.encode('utf-8'))
                            continue

                        # 3. Handle actual download POST request
                        url = ""
                        if data.startswith("POST"):
                            # The URL is in the body of the HTTP request, after the headers (\r\n\r\n)
                            parts = data.split("\r\n\r\n", 1)
                            if len(parts) == 2:
                                url = parts[1].strip()
                        elif data.startswith("URL:"): # Fallback for your old method
                            url = data[4:].strip()

                        if url and url.startswith("http"):
                            # Send the URL to the PyQt GUI!
                            self.emitter.new_download_signal.emit(url) 
                            
                            response = "HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\n"
                            conn.sendall(response.encode('utf-8'))
                        else:
                            response = "HTTP/1.1 400 Bad Request\r\nAccess-Control-Allow-Origin: *\r\n\r\n"
                            conn.sendall(response.encode('utf-8'))

                except socket.timeout:
                    continue 
                except OSError as e:
                    if not self.is_running: break
                except Exception as e:
                    pass

        except Exception as e:
            pass

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", self.port))
                self.server_socket.close()
            except: pass

# --- HELPER FOR SORTING ---
class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        v1 = self.data(Qt.ItemDataRole.UserRole)
        v2 = other.data(Qt.ItemDataRole.UserRole)
        if v1 is not None and v2 is not None:
            try:
                return float(v1) < float(v2)
            except:
                pass
        return self.text() < other.text()

def parse_size_to_bytes(text):
    try:
        if not text or text == "...": return 0
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else ""
        multipliers = {'B': 1, 'K': 1024, 'KB': 1024, 'M': 1024**2, 'MB': 1024**2, 'G': 1024**3, 'GB': 1024**3}
        for key, mult in multipliers.items():
            if unit.startswith(key):
                return val * mult
        return val
    except:
        return 0

def parse_time_to_sec(text):
    try:
        if not text or text == "...": return 0
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].lower() if len(parts) > 1 else ""
        if 'hr' in unit: return val * 3600
        if 'min' in unit: return val * 60
        return val 
    except:
        return 0

def get_file_icon(filename):
    db = QMimeDatabase()
    mime = db.mimeTypeForFile(filename, QMimeDatabase.MatchMode.MatchExtension)
    if mime.isValid():
        icon_name = mime.iconName()
        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            return icon
    info = QFileInfo(filename)
    provider = QFileIconProvider()
    icon = provider.icon(info)
    if icon.isNull():
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
    return icon

def format_timestamp_relative(timestamp_str, max_relative_seconds=30): 
    """
    Formats a timestamp string (stored as float seconds since epoch) to either 
    "Just now", "Y min ago", or full date/time based on max_relative_seconds.
    """
    if not timestamp_str or timestamp_str == "...":
        return "..."
        
    try:
        # Convert stored string back to float timestamp 
        timestamp_float = float(timestamp_str)
    except ValueError:
        # If it's not a float, assume it's already a static formatted string
        return timestamp_str
    
    current_time = time.time()
    diff = current_time - timestamp_float
    
    if diff < 60:
        return "Just now"
    elif diff < max_relative_seconds:
        # Show minutes only (Removes 'sec ago' and uses 'min ago' for 1-5 mins)
        minutes_ago = int(diff // 60)
        # Ensure we don't show "0 min ago" right after "Just now"
        if minutes_ago == 0:
            return "Just now"
        return f"{minutes_ago} min ago"
    else:
        # Format to full date and time (e.g., YYYY-MM-DD HH:MM:SS)
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_float))


# --- CUSTOM DIALOG FOR DELETING COMPLETED ITEMS ---
class DeleteDialog(QDialog):
    def __init__(self, count, is_completed=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Completed Downloads" if is_completed else "Delete")
        
        layout = QVBoxLayout(self)
        
        # Message Label
        message = QLabel(f"Are you sure you want to delete {count} {'completed ' if is_completed else 'selected '}download(s)?")
        layout.addWidget(message)
        
        # Checkbox for Disk Deletion
        self.chk_delete_disk = QCheckBox("Also delete files from disk (permanently)")
        self.chk_delete_disk.setChecked(False) # Default to false for safety
        layout.addWidget(self.chk_delete_disk)
        
        # Button Layout
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_yes = QPushButton("Yes")
        self.btn_yes.clicked.connect(self.accept)
        
        self.btn_no = QPushButton("No")
        self.btn_no.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        
        layout.addLayout(btn_layout)

    def should_delete_from_disk(self):
        return self.chk_delete_disk.isChecked()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        icon_path = os.path.join(get_data_dir(), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(200, 150, 1000, 600)
        
        self.settings = self.load_settings()
        
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_central_widget()
        
        # Changed active_downloads to hold the download row reference, not just the dialog ID
        self.active_downloads = {} 
        self.load_data()
        
        # FEATURE: Timer for periodic timestamp updates (Run every 60 seconds)
        self.timestamp_timer = QTimer(self)
        self.timestamp_timer.timeout.connect(self.update_timestamp_display)
        self.timestamp_timer.start(60000) # Update every 60 seconds (1 minute)
        
        # --- IPC Setup: Listener for Browser Extension ---
        self.ipc_emitter = SignalEmitter()
        # Connect the thread's signal to the GUI slot (start_download)
        # Route extension downloads to the pre-fetcher instead of starting immediately
        self.ipc_emitter.new_download_signal.connect(self.process_incoming_url) 
        self.listener_thread = TcpListenerThread(DM_CONNECTOR_PORT, self.ipc_emitter)
        
        self.active_fetchers = [] # Prevent fetcher threads from being garbage collected

        self.listener_thread.start()

        # Initial UI State Update
        self.update_ui_states()
        
        # Auto-start local Aria2 daemon for accelerated downloading
        self.aria2_process = self.start_aria2_daemon()

    def _handle_options_accepted(self):
        # Clean restart aria2 daemon
        if self.aria2_process:
            try:
                self.aria2_process.terminate()
                try: self.aria2_process.wait(timeout=2.0)
                except: self.aria2_process.kill()
            except: pass
        self.aria2_process = self.start_aria2_daemon()

    def start_aria2_daemon(self):
        try:
            aria2_bin = ensure_aria2() or "aria2c"
            ext_data = load_extension_config()
            port = ext_data.get("port", 56800)
            token = ext_data.get("token", "")

            # Note: --no-proxy is not needed for the server side of RPC
            cmd = [
                aria2_bin, "--enable-rpc=true", f"--rpc-listen-port={port}",
                "--rpc-listen-all=false", "--rpc-allow-origin-all",
                "--max-connection-per-server=8", "--min-split-size=1M",
                "--split=8", "--daemon=false",
                "--no-proxy=127.0.0.1,localhost"
            ]
            if token: cmd.append(f"--rpc-secret={token}")

            # --- APPLY PROXY SETTINGS VIA PROXYCHAINS ---
            proxy_conf = generate_proxychains_config()
            proxychains_bin = get_proxychains_bin()

            popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

            if proxy_conf and proxychains_bin:
                if "proxychains4" in proxychains_bin:
                    # Wrap aria2 command with proxychains v4 (supports -f)
                    cmd = [proxychains_bin, "-f", proxy_conf] + cmd
                else:
                    # Wrap with proxychains v3 (no -f support)
                    # It looks for proxychains.conf in the current working directory.
                    cmd = [proxychains_bin] + cmd
                    popen_kwargs["cwd"] = get_config_dir()

            proc = subprocess.Popen(cmd, **popen_kwargs)
            return proc
        except Exception:
            return None
    def closeEvent(self, event: QCloseEvent):
        # Stop IPC Listener Thread before closing
        self.listener_thread.stop()
        self.listener_thread.wait()
        
        self.stop_all_downloads()
        # Stop the timer before closing
        self.timestamp_timer.stop() 
        
        # Kill the aria2 daemon cleanly on exit
        if hasattr(self, 'aria2_process') and self.aria2_process:
            self.aria2_process.terminate()
            try:
                self.aria2_process.wait(timeout=2)
            except:
                self.aria2_process.kill()
                
        self.save_data()
        self.save_settings()
        event.accept()

    def setup_actions(self):
        self.action_add_url = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "Add URL", self)
        self.action_add_url.triggered.connect(self.open_add_url)

        self.action_exit = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "Exit", self)
        self.action_exit.triggered.connect(self.close)

        # Updated text for stop action
        self.action_stop = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop), "Stop/Pause", self)
        self.action_stop.triggered.connect(self.stop_selected_download)
        self.action_stop.setEnabled(False)

        self.action_stop_all = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), "Stop All", self)
        self.action_stop_all.triggered.connect(self.stop_all_downloads)
        self.action_stop_all.setEnabled(False)

        self.action_resume = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Resume", self)
        self.action_resume.triggered.connect(self.resume_selected_download)
        self.action_resume.setEnabled(False)
        
        self.action_download_now = QAction("Download Now", self)
        self.action_download_now.triggered.connect(self.resume_selected_download) 
        
        self.action_redownload = QAction("Redownload", self)
        self.action_redownload.triggered.connect(self.redownload_selected)

        self.action_delete = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Delete", self)
        self.action_delete.triggered.connect(self.delete_selected_download)
        self.action_delete.setEnabled(False)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)

        self.action_delete_completed = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton), "Delete Completed", self)
        self.action_delete_completed.triggered.connect(self.delete_completed_downloads)
        
        self.action_options = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Options", self)
        self.action_options.triggered.connect(self.open_options)

        self.action_open_folder = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), "Open Downloads Folder", self)
        self.action_open_folder.triggered.connect(self.open_downloads_folder_generic)

    def setup_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        # 1. Tasks
        tasks_menu = menu_bar.addMenu("&Tasks")
        tasks_menu.addAction(self.action_add_url)
        tasks_menu.addSeparator()
        tasks_menu.addAction(self.action_exit)

        # 2. File
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.action_stop)
        file_menu.addAction(self.action_delete)
        file_menu.addAction(self.action_download_now)
        file_menu.addAction(self.action_redownload)
        file_menu.addSeparator()
        file_menu.addAction(self.action_open_folder)

        # 3. Downloads
        downloads_menu = menu_bar.addMenu("&Downloads")
        downloads_menu.addAction(self.action_resume)
        downloads_menu.addAction(self.action_stop)
        downloads_menu.addAction(self.action_stop_all)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_delete)
        downloads_menu.addAction(self.action_delete_completed)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_options)

        # 4. View
        view_menu = menu_bar.addMenu("&View")
        
        sort_menu = view_menu.addMenu("Sort by")
        sort_fields = [
            ("File Name", 0), ("Size", 1), ("Status", 2), ("Time Left", 3), 
            ("Transfer Rate", 4), ("Last Try", 5), ("Date Added", 6)
        ]
        for name, col_idx in sort_fields:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=col_idx: self.download_table.sortItems(c, Qt.SortOrder.AscendingOrder))
            sort_menu.addAction(action)

        view_menu.addSeparator()
        toolbar_toggle = QAction("&Toolbar", self)
        toolbar_toggle.setCheckable(True)
        toolbar_toggle.setChecked(True)
        toolbar_toggle.triggered.connect(lambda checked: self.findChild(QToolBar, "MainToolbar").setVisible(checked))
        view_menu.addAction(toolbar_toggle)

        # 5. Help
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About Bengal DM", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_toolbar(self):
        toolbar = self.findChild(QToolBar, "MainToolbar")
        if toolbar is None:
            toolbar = QToolBar("Main Toolbar", self)
            toolbar.setObjectName("MainToolbar")
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        else:
            for action in toolbar.actions():
                toolbar.removeAction(action)
        
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(24, 24))

        toolbar.addAction(self.action_add_url)
        toolbar.addAction(self.action_resume)
        toolbar.addAction(self.action_stop)
        toolbar.addAction(self.action_stop_all)
        toolbar.addAction(self.action_delete) 
        toolbar.addAction(self.action_delete_completed)
        toolbar.addAction(self.action_options)

    def setup_central_widget(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.itemClicked.connect(self.filter_downloads) 
        
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
        
        # Ensure row selection is correctly set up
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        # FIX: Remove blue cell highlight (focus rectangle) on selection
        # Using a comprehensive style to kill the default focus visual
        self.download_table.setStyleSheet("""
            QTableWidget::item:focus { 
                border: none; 
                outline: 0; 
                background: transparent; 
            }
        """)

        self.download_table.itemSelectionChanged.connect(self.update_ui_states)
        
        self.download_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self.show_context_menu)
        
        self.download_table.setHorizontalHeaderLabels([
            "File Name", "Size", "Status", "Time Left", 
            "Transfer Rate", "Last Try", "Date Added"
        ])
        header = self.download_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.category_tree)
        splitter.addWidget(self.download_table)
        splitter.setSizes([200, 800])
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)
        
    def update_timestamp_display(self):
        """
        Periodically updates the displayed format of 'Last Try' and 'Date Added'
        columns. 'Last Try' uses 5-minute relative time threshold. 'Date Added' 
        uses a 30-second threshold.
        """
        
        # Temporarily disable sorting/signals to prevent flickering during mass update
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
            
        self.download_table.blockSignals(True)
        
        try:
            for row in range(self.download_table.rowCount()):
                item_name = self.download_table.item(row, 0)
                if not item_name: continue
                
                is_active = id(item_name) in self.active_downloads
                
                # --- Update Last Try (Column 5) ---
                # Threshold: 5 minutes (300 seconds)
                LAST_TRY_MAX_REL_TIME = 300 
                last_try_ts = item_name.data(Qt.ItemDataRole.UserRole + 2)
                
                # Only run periodic formatting if the download is NOT currently active 
                if last_try_ts and not is_active:
                    new_display_text = format_timestamp_relative(last_try_ts, max_relative_seconds=LAST_TRY_MAX_REL_TIME)
                    item_5 = self.download_table.item(row, 5)
                    if item_5 is not None:
                        if item_5.text() != new_display_text:
                            item_5.setText(new_display_text)

                # --- Update Date Added (Column 6) ---
                # Threshold: 30 seconds
                DATE_ADDED_MAX_REL_TIME = 30
                date_added_ts = item_name.data(Qt.ItemDataRole.UserRole + 3)
                if date_added_ts:
                    new_display_text = format_timestamp_relative(date_added_ts, max_relative_seconds=DATE_ADDED_MAX_REL_TIME)
                    item_6 = self.download_table.item(row, 6)
                    if item_6 is not None:
                        if item_6.text() != new_display_text:
                            item_6.setText(new_display_text)
                        
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self.download_table.viewport().update()

    def update_ui_states(self):
        selected_rows = self.download_table.selectedItems()
        has_selection = len(selected_rows) > 0
        
        has_active_downloads = len(self.active_downloads) > 0
        
        selection_has_active = False
        selection_has_pausable = False
        selection_has_resumable = False
        
        if has_selection:
            rows = set(item.row() for item in selected_rows)
            for r in rows:
                item = self.download_table.item(r, 0)
                key = id(item)
                
                status_item = self.download_table.item(r, 2)
                logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else None
                status = logic_status if logic_status else (status_item.text() if status_item else "")
                
                # Check for active workers
                if key in self.active_downloads:
                    selection_has_active = True
                
                # Pausable statuses (currently downloading)
                if status in ["Connecting...", "Downloading", "Resuming...", "Pending..."]:
                    selection_has_pausable = True
                    
                # Resumable statuses (not active and not completed)
                if status in ["Paused", "Cancelled", "Error"]:
                    selection_has_resumable = True
        
        # STOP action is for pausing an active download
        self.action_stop.setEnabled(selection_has_pausable and not selection_has_resumable)
        self.action_stop_all.setEnabled(has_active_downloads)
        
        # RESUME action is for starting a paused/errored/cancelled download
        self.action_resume.setEnabled(selection_has_resumable and not selection_has_active)
        self.action_download_now.setEnabled(selection_has_resumable and not selection_has_active)
        
        self.action_delete.setEnabled(has_selection)
        self.action_redownload.setEnabled(has_selection)
        
    def refresh_toolbar_state_on_dialog_close(self):
        """
        Called when a DownloadProgressDialog is closed (either by completion,
        cancellation, or manual closing).
        """
        self.save_data() # Save status changes
        self.update_ui_states()
        
    def delete_selected_download(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
        
        dlg = DeleteDialog(self)
        if dlg.exec():
            delete_disk = dlg.should_delete_from_disk()
            for row in rows:
                item_0 = self.download_table.item(row, 0)
                key = id(item_0)
                
                # Stop if active
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop()
                    dialog.reject()
                
                if delete_disk:
                    path = item_0.data(Qt.ItemDataRole.UserRole + 1)
                    if path and os.path.exists(path):
                        try: os.remove(path)
                        except: pass
                
                self.download_table.removeRow(row)
            self.save_data()
            self.update_ui_states()

    def redownload_selected(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()))
        for row in rows:
            item = self.download_table.item(row, 0)
            self.ctx_redownload(item)

    def filter_downloads(self, item, column):
        category = item.text(0)
        ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
            "Programs": [".exe", ".msi", ".sh", ".bin", ".deb", ".bat"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }

        for row in range(self.download_table.rowCount()):
            self.download_table.setRowHidden(row, False) 
            filename = self.download_table.item(row, 0).text().lower()
            status = self.download_table.item(row, 2).text()
            should_hide = False
            
            if category == "All Downloads":
                should_hide = False
            elif category == "Unfinished":
                if status == "Completed": should_hide = True
            elif category == "Finished":
                if status != "Completed": should_hide = True
            elif category in ext_map:
                extensions = ext_map[category]
                if not any(filename.endswith(ext) for ext in extensions):
                    should_hide = True
            
            if should_hide:
                self.download_table.setRowHidden(row, True)

    def save_data(self):
        try:
            downloads = []
            for row in range(self.download_table.rowCount()):
                item_name = self.download_table.item(row, 0)
                if not item_name: continue
                
                def safe_get(col):
                    it = self.download_table.item(row, col)
                    return it.text() if it else ""
                
                url = item_name.data(Qt.ItemDataRole.UserRole)
                path = item_name.data(Qt.ItemDataRole.UserRole + 1) 
                filename = item_name.text()
                size = safe_get(1)
                status = safe_get(2)
                
                # Retrieve raw timestamp values for persistence
                last_try_ts = item_name.data(Qt.ItemDataRole.UserRole + 2) or ""
                date_added_ts = item_name.data(Qt.ItemDataRole.UserRole + 3) or ""
                
                # Save status as 'Paused' if currently active/pending but not completed
                if status in ["Downloading", "Connecting...", "Pending...", "Resuming..."]:
                    status = "Paused"
                
                dl_data = {
                    "url": url,
                    "filename": filename,
                    "path": path,
                    "size": size,
                    "status": status,
                    "time_left": safe_get(3),
                    "rate": safe_get(4),
                    "last_try": str(last_try_ts), # Save raw timestamp
                    "date_added": str(date_added_ts) # Save raw timestamp
                }
                downloads.append(dl_data)
            
            data_dir = get_data_dir()
            with open(os.path.join(data_dir, "downloads.json"), "w") as f:
                json.dump(downloads, f, indent=4)
        except Exception:
            pass

    def load_data(self):
        data_dir = get_data_dir()
        path = os.path.join(data_dir, "downloads.json")
        if not os.path.exists(path):
            return

        try:
            with open(path, "r") as f:
                downloads = json.load(f)
            
            self.download_table.setSortingEnabled(False)
                
            for d in downloads:
                row = self.download_table.rowCount()
                self.download_table.insertRow(row)
                
                filename = d.get("filename", "Unknown")
                item_name = QTableWidgetItem(filename)
                
                # Store raw timestamps in item data
                date_added_ts = d.get("date_added", str(time.time()))
                last_try_ts = d.get("last_try", date_added_ts)
                
                item_name.setData(Qt.ItemDataRole.UserRole, d.get("url", ""))
                item_name.setData(Qt.ItemDataRole.UserRole + 1, d.get("path", "")) 
                item_name.setData(Qt.ItemDataRole.UserRole + 2, last_try_ts) # Raw Last Try TS
                item_name.setData(Qt.ItemDataRole.UserRole + 3, date_added_ts) # Raw Date Added TS
                item_name.setIcon(get_file_icon(filename))
                
                self.download_table.setItem(row, 0, item_name)
                
                self._set_sortable_item(row, 1, d.get("size", "..."), parse_size_to_bytes)
                self.download_table.setItem(row, 2, QTableWidgetItem(d.get("status", "Unknown")))
                self._set_sortable_item(row, 3, d.get("time_left", ""), parse_time_to_sec)
                self._set_sortable_item(row, 4, d.get("rate", ""), parse_size_to_bytes)
                
                # Display formatted timestamps (Last Try uses 5 min/300s threshold, Date Added uses 30s)
                self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(last_try_ts, max_relative_seconds=300)))
                self.download_table.setItem(row, 6, QTableWidgetItem(format_timestamp_relative(date_added_ts, max_relative_seconds=30)))

            self.download_table.setSortingEnabled(True)
            
        except Exception:
            pass

    def _set_sortable_item(self, row, col, text, parser_func):
        item = SortableTableWidgetItem(text)
        raw_val = parser_func(text)
        item.setData(Qt.ItemDataRole.UserRole, raw_val)
        self.download_table.setItem(row, col, item)

    def save_settings(self):
        try:
            config_dir = get_config_dir()
            settings = {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "windowState": self.saveState().toHex().data().decode(),
            }
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def load_settings(self):
        settings = {}
        config_dir = get_config_dir()
        path = os.path.join(config_dir, "settings.json")
        if not os.path.exists(path):
            return settings
        try:
            with open(path, "r") as f:
                settings = json.load(f)
                if "geometry" in settings:
                    self.restoreGeometry(QByteArray.fromHex(settings["geometry"].encode()))
                if "windowState" in settings:
                    self.restoreState(QByteArray.fromHex(settings["windowState"].encode()))
        except Exception:
            pass
        return settings

    def show_context_menu(self, pos):
        item = self.download_table.itemAt(pos)
        if not item: return

        self.download_table.selectRow(item.row())
        
        row_index = item.row()
        item_0 = self.download_table.item(row_index, 0)
        
        status = self.download_table.item(row_index, 2).text()
        is_completed = (status == "Completed")
        is_active = id(item_0) in self.active_downloads
        is_resumable = status in ["Paused", "Cancelled", "Error"]
        is_pausable = status in ["Connecting...", "Downloading", "Resuming..."]

        menu = QMenu(self)
        
        act_open = QAction("Open", self)
        act_open_with = QAction("Open with...", self)
        act_open_folder = QAction("Open folder", self)
        act_move = QAction("Move/Rename", self)
        
        act_move.setEnabled(is_completed)
        act_open.setEnabled(is_completed)
        act_open_with.setEnabled(is_completed)
        
        menu.addActions([act_open, act_open_with, act_open_folder, act_move])
        menu.addSeparator()
        
        # Enhanced State Logic for Context Menu
        act_stop = QAction("Stop/Pause Download", self)
        act_stop.triggered.connect(self.stop_selected_download)
        act_stop.setEnabled(is_active and is_pausable)
        
        act_resume = QAction("Resume download", self)
        act_resume.triggered.connect(self.resume_selected_download)
        act_resume.setEnabled(is_resumable and not is_active)
        
        act_redownload = QAction("Redownload", self)
        act_refresh = QAction("Refresh download address", self)
        
        menu.addActions([act_resume, act_stop])
        menu.addSeparator()
        menu.addActions([act_redownload, act_refresh])
        menu.addSeparator()
        
        act_delete = QAction("Delete", self)
        act_delete.triggered.connect(self.delete_selected_download)
        menu.addAction(act_delete)
        menu.addSeparator()
        
        act_props = QAction("Properties", self)
        menu.addAction(act_props)

        act_open.triggered.connect(lambda: self.ctx_open_file(item))
        act_open_with.triggered.connect(lambda: self.ctx_open_with(item))
        act_open_folder.triggered.connect(lambda: self.ctx_open_folder(item))
        act_move.triggered.connect(lambda: self.ctx_move_rename(item))
        act_redownload.triggered.connect(lambda: self.ctx_redownload(item))
        act_refresh.triggered.connect(lambda: self.ctx_refresh_address(item))
        act_props.triggered.connect(lambda: self.ctx_properties(item))

        menu.exec(self.download_table.viewport().mapToGlobal(pos))

    def ctx_open_file(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")

    def ctx_open_with(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not path or not os.path.exists(path):
             QMessageBox.warning(self, "Error", "File does not exist.")
             return
        app_path, _ = QFileDialog.getOpenFileName(self, "Select Application", "/usr/bin", "Executables (*)")
        if app_path:
            subprocess.Popen([app_path, path])

    def ctx_open_folder(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                if os.name == 'nt':
                    os.startfile(folder)
                else:
                    subprocess.Popen(['xdg-open', folder])

    def open_downloads_folder_generic(self):
        path = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(path):
             if os.name == 'nt':
                 os.startfile(path)
             else:
                 subprocess.Popen(['xdg-open', path])

    def ctx_move_rename(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        old_path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "Error", "File not found to move.")
            return

        new_path, _ = QFileDialog.getSaveFileName(self, "Move/Rename File", old_path)
        if new_path and new_path != old_path:
            try:
                shutil.move(old_path, new_path)
                new_filename = os.path.basename(new_path)
                item_0.setText(new_filename)
                item_0.setData(Qt.ItemDataRole.UserRole + 1, new_path)
                self.save_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to move file: {e}")

    def ctx_redownload(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        url = item_0.data(Qt.ItemDataRole.UserRole)
        
        # Stop any active download for this item first
        key = id(item_0)
        if key in self.active_downloads:
            dialog = self.active_downloads[key]
            dialog.worker.stop()
            dialog.reject() # Closes the dialog and triggers the close handler
            
        if path and os.path.exists(path):
            try: os.remove(path)
            except: pass
        if path and os.path.exists(path + ".tmpbdm"):
            try: os.remove(path + ".tmpbdm")
            except: pass
        if path and os.path.exists(path + ".tmpbdm.bdmx"):
            try: os.remove(path + ".tmpbdm.bdmx")
            except: pass
        
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        
        # Update last try timestamp immediately before restarting
        new_timestamp = str(time.time())
        item_0.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
        self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(new_timestamp, max_relative_seconds=300)))

        self._start_download_worker(url, item_0)

    def ctx_refresh_address(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        url = item_0.data(Qt.ItemDataRole.UserRole)
        new_url, ok = QInputDialog.getText(self, "Refresh Address", "Enter new URL:", text=url)
        if ok and new_url:
            item_0.setData(Qt.ItemDataRole.UserRole, new_url)
            self.save_data()

    def ctx_properties(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        data = {
            "row": row,
            "item": item_0,
            "url": item_0.data(Qt.ItemDataRole.UserRole),
            "path": item_0.data(Qt.ItemDataRole.UserRole + 1),
            "filename": item_0.text(),
            "status": self.download_table.item(row, 2).text(),
            "size": self.download_table.item(row, 1).text(),
            "date_added": format_timestamp_relative(item_0.data(Qt.ItemDataRole.UserRole + 3), max_relative_seconds=0), # Force full time for properties
            "last_try": format_timestamp_relative(item_0.data(Qt.ItemDataRole.UserRole + 2), max_relative_seconds=0) # Force full time for properties
        }
        # Keep reference
        self._prop_dlg = PropertiesDialog(data, self)
        self._prop_dlg.show()

    def open_add_url(self):
        from dialogs import AddUrlDialog
        dialog = AddUrlDialog(self)
        dialog.accepted.connect(lambda: self._handle_add_url_accepted(dialog))
        dialog.show()

    def _handle_add_url_accepted(self, dialog):
        url = dialog.get_url()
        if url:
            self.process_incoming_url(url)

    def process_incoming_url(self, url):
        """Brings the app to the front, fetches file info, and shows the popup"""
        # 1. Un-minimize and bring the main window to the front
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()

        # 2. Start the fetcher
        from workers import FileInfoFetcherWorker
        fetcher = FileInfoFetcherWorker(url)
        self.active_fetchers.append(fetcher)
        
        # 3. Connect to a wrapper that cleans up the thread memory when done
        fetcher.finished_signal.connect(lambda info, f=fetcher: self._handle_fetch_complete(info, f))
        fetcher.start()

    def _handle_fetch_complete(self, file_info, fetcher):
        # Remove the finished thread from memory
        if fetcher in self.active_fetchers:
            self.active_fetchers.remove(fetcher)
            
        # Trigger your existing popup dialog!
        self.on_file_info_fetched(file_info)

    def on_file_info_fetched(self, file_info):
        from dialogs import DownloadFileInfoDialog
        dialog = DownloadFileInfoDialog(file_info, self)
        dialog.accepted.connect(lambda: self._handle_download_dialog_accepted(dialog, file_info))
        dialog.show()

    def _handle_download_dialog_accepted(self, dialog, file_info):
        results = dialog.get_results()
        if results["action"] == 'start':
            self.start_download(
                url=file_info["url"], 
                custom_filename=results["filename"],
                custom_save_dir=os.path.dirname(results["save_path"]),
                size_data=(results["size_str"], results["size_bytes"]),
                start_paused=False
            )
        elif results["action"] == 'later':
            self.start_download(
                url=file_info["url"], 
                custom_filename=results["filename"],
                custom_save_dir=os.path.dirname(results["save_path"]),
                size_data=(results["size_str"], results["size_bytes"]),
                start_paused=True
            )

    def start_download(self, url, custom_filename=None, custom_save_dir=None, size_data=None, start_paused=False):
        sorting_was_enabled = self.download_table.isSortingEnabled()
        self.download_table.setSortingEnabled(False)

        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        try:
             parsed = urlparse(url)
             path = unquote(parsed.path)
             filename_guess = os.path.basename(path)
             if not filename_guess: filename_guess = "file"
        except:
             filename_guess = "file"
             
        if custom_filename:
             filename_guess = custom_filename
        
        current_ts = str(time.time())

        item_name = QTableWidgetItem(filename_guess)
        item_name.setData(Qt.ItemDataRole.UserRole, url)
        item_name.setIcon(get_file_icon(filename_guess))
        
        # Store raw timestamp data in the item
        item_name.setData(Qt.ItemDataRole.UserRole + 3, current_ts) # Date Added
        item_name.setData(Qt.ItemDataRole.UserRole + 2, current_ts) # Last Try
        
        # Determine explicit metadata bindings
        size_str = size_data[0] if size_data else "?"
        
        self.download_table.setItem(row, 0, item_name)
        self._set_sortable_item(row, 1, size_str, parse_size_to_bytes)
        
        status_txt = "Paused" if start_paused else "Pending..."
        self.download_table.setItem(row, 2, QTableWidgetItem(status_txt))
        
        self._set_sortable_item(row, 3, "", parse_time_to_sec) if start_paused else self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "", parse_size_to_bytes) if start_paused else self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        
        # Display formatted timestamp
        self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(current_ts, max_relative_seconds=300)))
        self.download_table.setItem(row, 6, QTableWidgetItem(format_timestamp_relative(current_ts, max_relative_seconds=30)))

        self.download_table.setSortingEnabled(sorting_was_enabled)
        
        # Pre-calculate and bind the target directory strictly to UserRole+1 to survive App restarts
        # even if the initial load is bypassed via "Download Later".
        config = load_category_config()
        categories = config.get("categories", {})
        ext = os.path.splitext(filename_guess)[1].replace(".", "").lower()
        
        final_category = "General"
        for cat_name, cat_data in categories.items():
            if ext in cat_data.get("extensions", "").split():
                final_category = cat_name
                break
                
        save_dir = custom_save_dir if custom_save_dir else categories[final_category]["path"]
        target_path = os.path.join(save_dir, filename_guess)
        item_name.setData(Qt.ItemDataRole.UserRole + 1, target_path)
        
        if not start_paused:
            self._start_download_worker(url, item_name, custom_save_dir=save_dir)
            
        self.save_data()

    def _start_download_worker(self, url, item_ref, resume_filename=None, custom_save_dir=None):
        config = load_category_config()
        categories = config.get("categories", {})
        
        target_filename = resume_filename if resume_filename else item_ref.text()
        
        # If the item already has a pre-determined path bound to data, extract its directory!
        saved_path = item_ref.data(Qt.ItemDataRole.UserRole + 1)
        if saved_path and not custom_save_dir:
            custom_save_dir = os.path.dirname(saved_path)
            
        ext = os.path.splitext(target_filename)[1].replace(".", "").lower()
        
        final_category = "General"
        for cat_name, cat_data in categories.items():
            if ext in cat_data.get("extensions", "").split():
                final_category = cat_name
                break
        
        save_dir = custom_save_dir if custom_save_dir else categories[final_category]["path"]
        if not os.path.exists(save_dir):
            try: os.makedirs(save_dir)
            except: save_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        # SMART ROUTING: Use Aria2 as the primary engine. 
        # Fallback to internal downloader only if Aria2 binary is missing or daemon failed.
        use_aria2 = True
        try:
            # Quick check if it's alive, but don't strictly require it to be responsive 
            # at this exact millisecond (it might be starting up or busy).
            if not hasattr(self, 'aria2_process') or not self.aria2_process:
                use_aria2 = False
        except:
            use_aria2 = False

        if use_aria2:
            worker = Aria2Worker(url, item_ref.row(), save_dir, resume_filename)
        else:
            worker = DownloadWorker(url, item_ref.row(), save_dir, resume_filename)
        
        item_ref.setData(Qt.ItemDataRole.UserRole + 1, worker.target_path)
        item_ref.setText(worker.filename)
        
        worker.main_progress_signal.connect(lambda _, data: self.update_download_row(item_ref, data))
        worker.finished_signal.connect(lambda _, status: self.download_finished(item_ref, status))
        
        # DownloadProgressDialog is now a separate, non-modal window
        progress_dialog = DownloadProgressDialog(worker, None)
        progress_dialog.show()
        
        # Connect to the dialog's finished signal to update the main UI/toolbar
        progress_dialog.finished.connect(self.refresh_toolbar_state_on_dialog_close)
        
        # Use item_ref ID as key to manage active dialogs
        self.active_downloads[id(item_ref)] = progress_dialog
        progress_dialog.finished.connect(lambda: self.active_downloads.pop(id(item_ref), None))
        
        # Trigger UI Update for Stop Buttons
        self.update_ui_states()

    def resume_selected_download(self):
        selected_items = self.download_table.selectedItems()
        if not selected_items: return
        
        rows = set(item.row() for item in selected_items)
        for row in rows:
            item_name = self.download_table.item(row, 0)
            
            # If already active, bring dialog to front
            if id(item_name) in self.active_downloads:
                dialog = self.active_downloads[id(item_name)]
                dialog.activateWindow()
                dialog.raise_()
                continue
            
            # Start/Resume download
            url = item_name.data(Qt.ItemDataRole.UserRole)
            filename = item_name.text()
            
            if url:
                self.download_table.setItem(row, 2, QTableWidgetItem("Resuming..."))
                
                # Update last try timestamp before resuming
                new_timestamp = str(time.time())
                item_name.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(new_timestamp, max_relative_seconds=300)))
                
                self._start_download_worker(url, item_name, resume_filename=filename)

    def stop_selected_download(self):
        for item in self.download_table.selectedItems():
            if item.column() == 0:
                key = id(item)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop() # Drop lock
                    
                    # Update status preserving percentage string
                    status_item = self.download_table.item(item.row(), 2)
                    if not status_item:
                        status_item = QTableWidgetItem()
                        self.download_table.setItem(item.row(), 2, status_item)
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
                    pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                    final_display = f"{pct_data} complete" if pct_data else "Paused"
                    status_item.setText(final_display)
                    
                    # Preserve Time Left but Drop Rate
                    self._set_sortable_item(item.row(), 4, "", parse_size_to_bytes)
                    
                    # Update last try timestamp on pause
                    item_ref = self.download_table.item(item.row(), 0)
                    new_timestamp = str(time.time())
                    item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                    self.download_table.setItem(item.row(), 5, QTableWidgetItem(format_timestamp_relative(new_timestamp, max_relative_seconds=300)))
                    
                    # Close the dialog which will trigger the finished signal connected to refresh_toolbar_state_on_dialog_close
                    dialog.reject() 

    def stop_all_downloads(self):
        for dialog in list(self.active_downloads.values()):
            dialog.worker.stop()
            # Find the corresponding table item and update status/timestamp
            for r in range(self.download_table.rowCount()):
                item_ref = self.download_table.item(r, 0)
                if id(item_ref) == next((k for k, v in self.active_downloads.items() if v == dialog), None):
                    status_item = self.download_table.item(r, 2)
                    if not status_item:
                        status_item = QTableWidgetItem()
                        self.download_table.setItem(r, 2, status_item)
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
                    pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                    final_display = f"{pct_data} complete" if pct_data else "Paused"
                    status_item.setText(final_display)
                    
                    self._set_sortable_item(r, 4, "", parse_size_to_bytes)
                    
                    new_timestamp = str(time.time())
                    item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                    self.download_table.setItem(r, 5, QTableWidgetItem(format_timestamp_relative(new_timestamp, max_relative_seconds=300)))
                    break
            dialog.reject()

    def remove_from_list(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
        
        for row in rows:
            item_name = self.download_table.item(row, 0)
            key = id(item_name)
            if key in self.active_downloads:
                dialog = self.active_downloads[key]
                dialog.worker.stop()
                dialog.reject()
            self.download_table.removeRow(row)
        self.save_data()
        self.update_ui_states()

    def delete_selected_download(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
            
        count = len(rows)
        dialog = DeleteDialog(count, is_completed=False, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            delete_disk = dialog.should_delete_from_disk()
            for row in rows:
                item_name = self.download_table.item(row, 0)
                key = id(item_name)
                if key in self.active_downloads:
                    dlg = self.active_downloads[key]
                    dlg.worker.stop()
                    dlg.reject()
                
                if delete_disk:
                    path = item_name.data(Qt.ItemDataRole.UserRole + 1)
                    if path and os.path.exists(path):
                        try: os.remove(path)
                        except: pass
                    if path and os.path.exists(path + ".tmpbdm"):
                        try: os.remove(path + ".tmpbdm")
                        except: pass
                    if path and os.path.exists(path + ".tmpbdm.bdmx"):
                        try: os.remove(path + ".tmpbdm.bdmx")
                        except: pass
                
                self.download_table.removeRow(row)
            self.save_data()
            self.update_ui_states()

    def delete_completed_downloads(self):
        rows_to_delete = []
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() == "Completed":
                rows_to_delete.append(row)
        
        if not rows_to_delete: return

        # FEATURE: Use custom dialog for checkbox functionality
        count = len(rows_to_delete)
        dialog = DeleteDialog(count, is_completed=True, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            delete_disk = dialog.should_delete_from_disk()
            
            for row in sorted(rows_to_delete, reverse=True):
                item_name = self.download_table.item(row, 0)
                path = item_name.data(Qt.ItemDataRole.UserRole + 1)
                
                if delete_disk:
                    if path and os.path.exists(path):
                        try: os.remove(path)
                        except: pass
                    # Delete temp files too, just in case
                    if path and os.path.exists(path + ".tmpbdm"):
                        try: os.remove(path + ".tmpbdm")
                        except: pass
                    if path and os.path.exists(path + ".tmpbdm.bdmx"):
                        try: os.remove(path + ".tmpbdm.bdmx")
                        except: pass
                
                self.download_table.removeRow(row)
                
            self.save_data()
            self.update_ui_states()

    def update_download_row(self, item_ref, data):
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            return # object has been deleted by remove
        if row == -1: return 
        
        # --- FIX: Block signals during bulk update to prevent flickering ---
        self.download_table.blockSignals(True)
        
        try:
            # --- Update Last Try Timestamp ---
            # Update the stored raw timestamp whenever progress is made
            new_timestamp = str(time.time())
            item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)

            new_name = data[0]
            if item_ref.text() != new_name:
                item_ref.setText(new_name)
                item_ref.setIcon(get_file_icon(new_name))
            
            # Col 1: Size
            self._set_sortable_item(row, 1, data[1], parse_size_to_bytes)
            
            # Col 2: Status
            status_item = self.download_table.item(row, 2)
            old_status = ""
            if not status_item:
                 status_item = QTableWidgetItem()
                 self.download_table.setItem(row, 2, status_item)
            else:
                 old_status = status_item.text()
                 
            # Map worker status to improved table status
            worker_status = data[2]
            if worker_status.startswith("Receiving data"):
                display_status = "Downloading"
            elif worker_status == "Connecting...":
                display_status = "Connecting..."
            elif worker_status == "Complete":
                display_status = "Completed"
            elif worker_status == "Resume GET...":
                display_status = "Resuming..."
            else:
                display_status = worker_status
                
            status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            
            final_display = display_status
            if len(data) > 6:
                comp, tot = data[5], data[6]
                if tot > 0:
                    pct = f"{(comp/tot)*100:.1f}%"
                    status_item.setData(Qt.ItemDataRole.UserRole, pct)
            
            if display_status in ["Paused", "Cancelled"]:
                pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                if pct_data:
                    final_display = f"{pct_data}"
                
            if final_display != old_status:
                status_item.setText(final_display)
                self.update_ui_states()
            
            # Col 3 & 4: Time Left & Rate
            if display_status in ["Completed", "Error"]:
                self._set_sortable_item(row, 3, "", parse_time_to_sec)
                self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            elif display_status in ["Paused", "Cancelled"]:
                self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            else:
                self._set_sortable_item(row, 3, data[3], parse_time_to_sec)
                self._set_sortable_item(row, 4, data[4], parse_size_to_bytes)
            
            # Col 5: Last Try (Formatted for display)
            # This is already being updated here for active downloads
            self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(new_timestamp, max_relative_seconds=300)))
            
        finally:
            self.download_table.blockSignals(False)
            # Request viewport repaint after updates are done
            self.download_table.viewport().update()

    def download_finished(self, item_ref, status_text):
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            return # object has been deleted by remove
        if row != -1:
            if status_text == "Completed":
                 display_status = "Completed"
            elif status_text == "Cancelled":
                 display_status = "Cancelled"
            elif status_text == "Paused":
                 display_status = "Paused"
            else:
                 display_status = "Error"
            
            if display_status in ["Completed", "Error"]:
                 self._set_sortable_item(row, 3, "", parse_time_to_sec)
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            elif display_status in ["Paused", "Cancelled"]:
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)
                 
            status_item = self.download_table.item(row, 2)
            if not status_item:
                status_item = QTableWidgetItem()
                self.download_table.setItem(row, 2, status_item)
                
            status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            
            final_display = display_status
            if display_status in ["Paused", "Cancelled"]:
                pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                if pct_data:
                    final_display = f"{pct_data} complete"
            
            status_item.setText(final_display)
            
            # Update Last Try timestamp one last time when download stops/finishes
            final_timestamp = str(time.time())
            item_ref.setData(Qt.ItemDataRole.UserRole + 2, final_timestamp)
            self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(final_timestamp, max_relative_seconds=300)))
            
            self.save_data()
        
        # Update UI to reflect that a download finished (e.g. Stop button disabled)
        self.update_ui_states()
    
    def open_options(self):
        from dialogs import OptionsDialog
        # Keep a reference to prevent garbage collection
        self._options_dlg = OptionsDialog(self)
        self._options_dlg.accepted.connect(self._handle_options_accepted)
        self._options_dlg.show()

    def _handle_options_accepted(self):
        # Restart aria2 daemon to apply new port/token
        if self.aria2_process:
            try:
                self.aria2_process.terminate()
                try:
                    self.aria2_process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.aria2_process.kill()
            except:
                pass
        self.aria2_process = self.start_aria2_daemon()

    def show_about(self):
        QMessageBox.about(self, "About Bengal DM", 
            "<h2>Bengal Download Manager</h2>"
            "<p>A simple, multi-threaded download manager built with PyQt6 for fast, resumable downloads.</p>"
            "<p>Version: 1.0</p>"
            "<p>Built for the XDG standard on Linux.</p>"
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())