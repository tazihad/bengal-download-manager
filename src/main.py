import sys
import os

# Add the directory containing this script to sys.path
# This helps both during development and when bundled with PyInstaller
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# For PyInstaller onefile bundles
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)

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
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit,
    QSystemTrayIcon, QRubberBand
)
from PyQt6.QtGui import QAction, QFont, QCloseEvent, QIcon, QColor, QPalette, QDesktopServices, QKeySequence
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase, QUrl, QTimer, QThread, pyqtSignal, QObject, QEvent, QPoint, QRect, QItemSelectionModel, QItemSelection

from core.workers import DownloadWorker, Aria2Worker
from ui.dialogs import (
    AddUrlDialog, OptionsDialog, DownloadProgressDialog, 
    PropertiesDialog, DownloadCompleteDialog, ColumnDialog, DeleteDialog
)
from core.config import load_category_config
from core.utils import (
    get_data_dir, get_config_dir, get_unique_filepath, ensure_aria2, 
    load_proxy_config, load_extension_config, generate_proxychains_config, get_proxychains_bin,
    show_in_folder, resolve_filename, open_file_generic, open_with
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
                        user_agent = ""
                        cookies = ""
                        if data.startswith("POST"):
                            # The URL is in the body of the HTTP request, after the headers (\r\n\r\n)
                            parts = data.split("\r\n\r\n", 1)
                            if len(parts) == 2:
                                body = parts[1].strip()
                                try:
                                    # Try parsing as JSON first (new method)
                                    payload = json.loads(body)
                                    url = payload.get("url", "")
                                    user_agent = payload.get("userAgent", "")
                                    cookies = payload.get("cookies", "")
                                except:
                                    # Fallback to plain text (old method)
                                    url = body
                        elif data.startswith("URL:"): # Fallback for your old method
                            url = data[4:].strip()

                        if url and url.startswith("http"):
                            # Send the URL, User-Agent, and Cookies to the PyQt GUI!
                            self.emitter.new_download_signal.emit(f"{url}|{user_agent}|{cookies}") 
                            
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

class EmptyAreaClickFilter(QObject):
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.table.viewport())
        self.origin = QPoint()

    def eventFilter(self, obj, event):
        if obj != self.table.viewport():
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                item = self.table.itemAt(event.pos())
                if not item:
                    # Starting selection from empty area
                    if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                        self.table.clearSelection()
                    self.table.setCurrentItem(None)
                    self.origin = event.pos()
                    self.rubber_band.setGeometry(QRect(self.origin, QSize()))
                    self.rubber_band.show()
                    return True
        elif event.type() == QEvent.Type.MouseMove:
            if self.rubber_band.isVisible():
                self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
                self.update_selection(event.modifiers())
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if self.rubber_band.isVisible():
                self.rubber_band.hide()
                return True
        return super().eventFilter(obj, event)

    def update_selection(self, modifiers):
        rect = self.rubber_band.geometry()
        selection_model = self.table.selectionModel()
        
        # Determine selection command
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            command = QItemSelectionModel.SelectionFlag.Select
        else:
            command = QItemSelectionModel.SelectionFlag.ClearAndSelect
            
        command |= QItemSelectionModel.SelectionFlag.Rows
        
        selection = QItemSelection()
        any_selected = False
        
        for row in range(self.table.rowCount()):
            row_y = self.table.rowViewportPosition(row)
            row_height = self.table.rowHeight(row)
            # Selection happens if the rubber band vertically overlaps the row
            if rect.bottom() >= row_y and rect.top() <= (row_y + row_height):
                index = self.table.model().index(row, 0)
                selection.select(index, index)
                any_selected = True
        
        if any_selected:
            selection_model.select(selection, command)
        elif not (modifiers & Qt.KeyboardModifier.ControlModifier):
            # If nothing touched and no Ctrl, clear everything
            self.table.clearSelection()

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


def get_app_icon():
    """Robustly finds and returns the application icon."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    icon_locations = [
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "logo.png"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "logo.svg"),
        # AppImage specific locations
        os.path.join(os.environ.get('APPDIR', ''), "usr", "share", "icons", "hicolor", "256x256", "apps", "bengal-download-manager.png"),
        os.path.join(os.environ.get('APPDIR', ''), "bengal-download-manager.png"),
        # Development and local paths
        os.path.join(os.path.dirname(current_dir), "assets", "logo.png"),
        os.path.join(os.path.dirname(current_dir), "assets", "logo.svg"),
        os.path.join(current_dir, "assets", "logo.png"),
        os.path.join(current_dir, "assets", "logo.svg"),
        os.path.join(get_data_dir(), "assets", "logo.png"),
        os.path.join(get_data_dir(), "assets", "logo.svg"),
    ]
    
    for loc in icon_locations:
        if loc and os.path.exists(loc):
            icon = QIcon(loc)
            if not icon.isNull():
                return icon
                
    # Fallback to system icon if nothing found
    return QIcon.fromTheme("system-run", QIcon(":/icons/fallback.png")) # Just a safe fallback

# --- CUSTOM DIALOG FOR DELETING COMPLETED ITEMS ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        
        # Set window icon from global app icon
        self.setWindowIcon(QApplication.windowIcon())
        
        self.setGeometry(200, 150, 1000, 600)
        
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_tray_icon()
        self.setup_central_widget()
        
        self.settings = self.load_settings()
        
        # FEATURE: Start Minimized logic
        if getattr(self, "start_minimized", False):
            # We use a timer to hide because some window managers might show it briefly otherwise
            QTimer.singleShot(0, self.hide)
            # Update tray icon action to "Show"
            QTimer.singleShot(0, self.update_tray_action)
        
        self.active_downloads = {} 
        self.active_file_info_dialogs = {}
        self.load_data()
        
        # FEATURE: Timer for periodic timestamp updates (Run every 60 seconds)
        self.timestamp_timer = QTimer(self)
        self.timestamp_timer.timeout.connect(self.update_timestamp_display)
        self.timestamp_timer.start(60000) # Update every 60 seconds (1 minute)
        
        # Enable Drag-and-Drop
        self.setAcceptDrops(True)

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
        self.is_quitting = False

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
            max_conn = str(ext_data.get("max_connections", 8))

            # Note: --no-proxy is not needed for the server side of RPC
            cmd = [
                aria2_bin, "--enable-rpc=true", f"--rpc-listen-port={port}",
                "--rpc-listen-all=false", "--rpc-allow-origin-all",
                f"--max-connection-per-server={max_conn}", "--min-split-size=1M",
                f"--split={max_conn}", "--daemon=false",
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
        if not self.is_quitting:
            event.ignore()
            self.hide()
            self.update_tray_action()
            return

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
        QApplication.quit()

    def quit_app(self):
        self.is_quitting = True
        self.close()

    # --- DRAG AND DROP HANDLERS ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.process_incoming_url(url.toString())

    def setup_actions(self):
        self.action_add_url = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "Add URL", self)
        self.action_add_url.triggered.connect(self.open_add_url)

        self.action_exit = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "Exit", self)
        self.action_exit.triggered.connect(self.quit_app)

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

        self.action_clear = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton), "Clear Completed", self)
        self.action_clear.triggered.connect(self.clear_finished_downloads)
        
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
        downloads_menu.addAction(self.action_clear)
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
        toolbar.addAction(self.action_clear)
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

        # Install event filter to clear selection on empty area click
        self.empty_area_filter = EmptyAreaClickFilter(self.download_table, self)
        self.download_table.viewport().installEventFilter(self.empty_area_filter)

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
        
        # Enable column customization features
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_context_menu)

        # Change resize mode to Interactive for all columns
        for i in range(self.download_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        splitter.addWidget(self.category_tree)
        splitter.addWidget(self.download_table)
        splitter.setSizes([200, 800])
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

    def setup_tray_icon(self):
        """Sets up the system tray icon and its context menu."""
        self.tray_icon = QSystemTrayIcon(self)

        # Set icon from window icon
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
        self.tray_icon.setIcon(icon)        
        # Create tray menu
        tray_menu = QMenu(self)
        
        # Show/Hide Action
        self.action_tray_toggle = QAction("Hide", self) # Default to Hide as window starts visible
        self.action_tray_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMinButton))
        self.action_tray_toggle.triggered.connect(self.toggle_window)
        
        tray_menu.addAction(self.action_tray_toggle)
        tray_menu.addAction(self.action_options)
        tray_menu.addSeparator()
        tray_menu.addAction(self.action_exit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Double click to show/hide
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def toggle_window(self):
        """Toggles the visibility of the main window."""
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()
        self.update_tray_action()

    def update_tray_action(self):
        """Updates the tray action text and icon based on window visibility."""
        if self.isVisible():
            self.action_tray_toggle.setText("Hide")
            self.action_tray_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMinButton))
        else:
            self.action_tray_toggle.setText("Show")
            self.action_tray_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        
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
                if status == "Complete": should_hide = True
            elif category == "Finished":
                if status != "Complete": should_hide = True
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
                # Use standardized internal status if available, otherwise fallback to text
                status_item = self.download_table.item(row, 2)
                internal_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
                display_text = safe_get(2)
                pct_data = status_item.data(Qt.ItemDataRole.UserRole) if status_item else None
                
                status = internal_status if internal_status else display_text
                
                # Normalize exact 100% or Complete variations to "Complete"
                if status == "Complete" or display_text == "Complete" or "100.00%" in str(status) or "100.00%" in str(display_text):
                    status = "Complete"
                
                # If currently active or paused, normalize to include percentage if available
                if status in ["Downloading", "Connecting...", "Pending...", "Resuming...", "Paused", "Cancelled"]:
                    if pct_data:
                        status = pct_data
                    elif "%" in display_text:
                        # Fallback to parsing text if UserRole is empty
                        status = display_text
                    else:
                        status = "Paused"
                
                # STRICT 100% CHECK: only force "Complete" if it's exactly 100%
                if isinstance(status, str) and "100.00%" in status:
                    status = "Complete"
                
                # Retrieve raw timestamp values for persistence
                last_try_ts = item_name.data(Qt.ItemDataRole.UserRole + 2) or ""
                date_added_ts = item_name.data(Qt.ItemDataRole.UserRole + 3) or ""
                
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
                # Col 2: Status (Sanitize: show percentage, never "Paused")
                raw_status = d.get("status", "0.0%")
                display_status = raw_status
                
                # Determine internal state based on status text
                is_actually_complete = False
                if raw_status == "Complete" or "100.00%" in str(raw_status):
                    is_actually_complete = True

                if is_actually_complete:
                    display_status = "Complete"
                    internal_state = "Complete"
                elif "%" in raw_status:
                    display_status = raw_status
                    internal_state = "Paused"
                elif raw_status in ["Paused", "Cancelled", "Error"]:
                    display_status = "0.0%" if raw_status != "Error" else "Error"
                    internal_state = raw_status
                else:
                    internal_state = raw_status

                status_item = QTableWidgetItem(display_status)
                # Store the standardized internal state in UserRole + 1
                status_item.setData(Qt.ItemDataRole.UserRole + 1, internal_state)
                # Also restore the raw percentage string in UserRole for resume logic
                if "%" in raw_status:
                    status_item.setData(Qt.ItemDataRole.UserRole, raw_status)
                
                self.download_table.setItem(row, 2, status_item)
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
            
            column_data = []
            header = self.download_table.horizontalHeader()
            for i in range(self.download_table.columnCount()):
                logical_idx = header.logicalIndex(i)
                column_data.append({
                    "logical_index": logical_idx,
                    "width": self.download_table.columnWidth(logical_idx),
                    "visible": not self.download_table.isColumnHidden(logical_idx)
                })

            settings = {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "windowState": self.saveState().toHex().data().decode(),
                "column_data": column_data,
                "start_minimized": getattr(self, "start_minimized", False)
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
                
                self.start_minimized = settings.get("start_minimized", False)

                header = self.download_table.horizontalHeader()
                if "column_data" in settings:
                    for i, col in enumerate(settings["column_data"]):
                        logical_idx = col["logical_index"]
                        # Move visual index of logical_idx to position i
                        header.moveSection(header.visualIndex(logical_idx), i)
                        self.download_table.setColumnHidden(logical_idx, not col["visible"])
                        self.download_table.setColumnWidth(logical_idx, col["width"])
                elif "column_widths" in settings:
                    for i, width in enumerate(settings["column_widths"]):
                        if i < self.download_table.columnCount():
                            self.download_table.setColumnWidth(i, width)
        except Exception:
            pass
        return settings

    def show_header_context_menu(self, pos):
        menu = QMenu(self)
        act_columns = QAction("Columns", self)
        act_columns.triggered.connect(self.open_column_dialog)
        menu.addAction(act_columns)
        menu.exec(self.download_table.horizontalHeader().viewport().mapToGlobal(pos))

    def open_column_dialog(self):
        header = self.download_table.horizontalHeader()
        columns_data = []
        
        # Map visual index to logical index to get current visual order
        for i in range(self.download_table.columnCount()):
            logical_idx = header.logicalIndex(i)
            name = self.download_table.horizontalHeaderItem(logical_idx).text()
            visible = not self.download_table.isColumnHidden(logical_idx)
            width = self.download_table.columnWidth(logical_idx)
            columns_data.append({
                "name": name, 
                "visible": visible, 
                "width": width, 
                "logical_index": logical_idx
            })
            
        from ui.dialogs import ColumnDialog
        dlg = ColumnDialog(columns_data, self)
        if dlg.exec():
            new_data = dlg.get_results()
            self.apply_column_settings(new_data)
            self.save_settings()

    def apply_column_settings(self, data):
        header = self.download_table.horizontalHeader()
        for i, col in enumerate(data):
            logical_idx = col["logical_index"]
            header.moveSection(header.visualIndex(logical_idx), i)
            self.download_table.setColumnHidden(logical_idx, not col["visible"])
            self.download_table.setColumnWidth(logical_idx, col["width"])

    def show_context_menu(self, pos):
        item = self.download_table.itemAt(pos)
        if not item: return

        self.download_table.selectRow(item.row())
        
        row_index = item.row()
        item_0 = self.download_table.item(row_index, 0)
        
        status_item = self.download_table.item(row_index, 2)
        logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
        status_text = status_item.text() if status_item else ""
        
        is_completed = (logic_status == "Complete" or status_text == "Complete")
        is_active = id(item_0) in self.active_downloads
        is_resumable = (logic_status in ["Paused", "Cancelled", "Error"]) or ("%" in status_text and not is_active)
        is_pausable = (logic_status in ["Connecting...", "Downloading", "Resuming...", "Pending..."]) or (is_active and "%" in status_text)

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
            if not open_file_generic(path):
                QMessageBox.critical(self, "Error", "Failed to open the file with the system default application.")
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")

    def ctx_open_with(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not path or not os.path.exists(path):
             QMessageBox.warning(self, "Error", "File does not exist.")
             return
        
        if not open_with(path):
            # Final fallback: Manual picker if system utilities fail
            app_path, _ = QFileDialog.getOpenFileName(self, "Select Application", "/usr/bin", "Executables (*)")
            if app_path:
                subprocess.Popen([app_path, path])

    def ctx_open_folder(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        show_in_folder(path)

    def open_downloads_folder_generic(self):
        path = os.path.join(os.path.expanduser("~"), "Downloads")
        show_in_folder(path)

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
        
        from ui.dialogs import RefreshAddressDialog
        dlg = RefreshAddressDialog(url, self)
        if dlg.exec():
            new_url = dlg.get_url()
            if new_url:
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
        from ui.dialogs import AddUrlDialog
        dialog = AddUrlDialog(self)
        dialog.accepted.connect(lambda: self._handle_add_url_accepted(dialog))
        dialog.show()

    def _handle_add_url_accepted(self, dialog):
        url = dialog.get_url()
        if url:
            self.process_incoming_url(url)

    def process_incoming_url(self, data):
        """Fetches file info and shows the popup without stealing focus for main window"""
        parts = data.split("|", 2)
        url = parts[0]
        user_agent = parts[1] if len(parts) > 1 else ""
        cookies = parts[2] if len(parts) > 2 else ""

        # 2. Start the fetcher
        from core.workers import FileInfoFetcherWorker
        fetcher = FileInfoFetcherWorker(url, user_agent=user_agent, cookies=cookies)
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
        from ui.dialogs import DownloadFileInfoDialog
        dialog = DownloadFileInfoDialog(file_info, self)
        
        # Add to list but don't start downloading yet (wait for user confirmation)
        results = dialog.get_results()
        item_ref = self.start_download(
            url=file_info["url"], 
            custom_filename=results["filename"],
            custom_save_dir=os.path.dirname(results["save_path"]),
            size_data=(results["size_str"], results["size_bytes"]),
            start_paused=True,
            show_dialog=False,
            user_agent=file_info.get("user_agent"),
            cookies=file_info.get("cookies")
        )
        
        # Connect signals to handle the dialog result
        dialog.accepted.connect(lambda: self._handle_download_dialog_accepted(dialog, file_info, item_ref))
        dialog.rejected.connect(lambda: self._handle_download_dialog_rejected(item_ref))
        dialog.show()

    def _handle_download_dialog_accepted(self, dialog, file_info, item_ref):
        results = dialog.get_results()
        key = id(item_ref)
        
        # Update filename and path in case user changed them in the dialog
        item_ref.setText(results["filename"])
        item_ref.setData(Qt.ItemDataRole.UserRole + 1, results["save_path"])
        
        # Ensure it's in the table
        row = self.download_table.row(item_ref)
        if row == -1: return

        # If "Start Download" was clicked, initiate the worker
        if results["action"] == 'start':
            self.download_table.setItem(row, 2, QTableWidgetItem("Starting..."))
            self._start_download_worker(
                file_info["url"], 
                item_ref, 
                resume_filename=results["filename"],
                custom_save_dir=os.path.dirname(results["save_path"]),
                user_agent=file_info.get("user_agent")
            )
        elif results["action"] == 'later':
            self.download_table.setItem(row, 2, QTableWidgetItem("Paused"))

    def _handle_download_dialog_rejected(self, item_ref):
        # User cancelled - remove the proposed download from the table
        row = self.download_table.row(item_ref)
        if row != -1:
            self.download_table.removeRow(row)
        self.save_data()

    def start_download(self, url, custom_filename=None, custom_save_dir=None, size_data=None, start_paused=False, show_dialog=True, user_agent=None, cookies=None):
        sorting_was_enabled = self.download_table.isSortingEnabled()
        self.download_table.setSortingEnabled(False)

        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        try:
             filename_guess = resolve_filename(url, {})
        except:
             filename_guess = "file"
             
        if custom_filename:
             filename_guess = custom_filename
        
        current_ts = str(time.time())

        item_name = QTableWidgetItem(filename_guess)
        item_name.setData(Qt.ItemDataRole.UserRole, url)
        item_name.setIcon(get_file_icon(filename_guess))
        
        # Store raw timestamp data and cookies in the item
        item_name.setData(Qt.ItemDataRole.UserRole + 3, current_ts) # Date Added
        item_name.setData(Qt.ItemDataRole.UserRole + 2, current_ts) # Last Try
        item_name.setData(Qt.ItemDataRole.UserRole + 4, user_agent) # User-Agent
        item_name.setData(Qt.ItemDataRole.UserRole + 5, cookies) # Cookies
        
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
            self._start_download_worker(url, item_name, resume_filename=filename_guess, custom_save_dir=save_dir, show_dialog=show_dialog, user_agent=user_agent, cookies=cookies)
            
        self.save_data()
        return item_name

    def _start_download_worker(self, url, item_ref, resume_filename=None, custom_save_dir=None, show_dialog=True, user_agent=None, cookies=None):
        if not user_agent:
            user_agent = item_ref.data(Qt.ItemDataRole.UserRole + 4)
        if not cookies:
            cookies = item_ref.data(Qt.ItemDataRole.UserRole + 5)
        
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

        temp_dir = config.get("temp_dir")

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
            worker = Aria2Worker(url, item_ref.row(), save_dir, resume_filename, user_agent=user_agent, cookies=cookies, temp_dir=temp_dir)
        else:
            worker = DownloadWorker(url, item_ref.row(), save_dir, resume_filename, user_agent=user_agent, cookies=cookies, temp_dir=temp_dir)
        item_ref.setData(Qt.ItemDataRole.UserRole + 1, worker.target_path)
        item_ref.setText(worker.filename)
        
        worker.main_progress_signal.connect(lambda _, data: self.update_download_row(item_ref, data))
        worker.finished_signal.connect(lambda _, status: self.download_finished(item_ref, status))
        
        # DownloadProgressDialog is now a separate, non-modal window
        progress_dialog = DownloadProgressDialog(worker, None)
        if show_dialog:
            progress_dialog.show()
        else:
            progress_dialog.hide()
        
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
            config = load_category_config()
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

                # --- ALWAYS CLEAR CACHE/TEMP FILES ---
                self._clear_cache_files(item_name, config)

                self.download_table.removeRow(row)
            self.save_data()
            self.update_ui_states()

    def _clear_cache_files(self, item_name, config):
        """Helper to remove temporary/cache files associated with a download item."""
        filename = item_name.text()
        temp_dir = config.get("temp_dir")
        if not temp_dir: return

        # 1. Aria2 files
        aria_temp = os.path.join(temp_dir, filename)
        aria_control = aria_temp + ".aria2"
        if os.path.exists(aria_temp):
            try: os.remove(aria_temp)
            except: pass
        if os.path.exists(aria_control):
            try: os.remove(aria_control)
            except: pass
        
        # 2. Internal downloader files
        internal_temp = os.path.join(temp_dir, filename + ".tmpbdm")
        internal_state = internal_temp + ".bdmx"
        if os.path.exists(internal_temp):
            try: os.remove(internal_temp)
            except: pass
        if os.path.exists(internal_state):
            try: os.remove(internal_state)
            except: pass

    def clear_finished_downloads(self):
        rows_to_clear = []
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item:
                # Use logical internal status if available (UserRole + 1)
                internal_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
                display_text = status_item.text()

                is_complete = False
                if internal_status == "Complete":
                    is_complete = True
                elif display_text and display_text.strip() == "Complete":
                    is_complete = True

                if is_complete:
                    rows_to_clear.append(row)

        if not rows_to_clear: return

        config = load_category_config()
        # Reverse sort to delete from bottom up correctly
        for row in sorted(rows_to_clear, reverse=True):
            item_name = self.download_table.item(row, 0)
            if item_name:
                key = id(item_name)
                if key in self.active_downloads:
                    dlg = self.active_downloads[key]
                    dlg.worker.stop()
                    dlg.reject()
                
                # Clear cache files for finished items too
                self._clear_cache_files(item_name, config)

            self.download_table.removeRow(row)

        self.save_data()
        self.update_ui_states()
    def update_download_row(self, item_ref, data):
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            return # object has been deleted by remove
        if row == -1: return 

        # --- PROTECTION GUARD ---
        # If the row is already marked as Complete, ignore any late progress signals
        status_item = self.download_table.item(row, 2)
        if status_item:
            internal_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
            if internal_status == "Complete":
                return
        
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
                display_status = "Complete"
            elif worker_status == "Resume GET...":
                display_status = "Resuming..."
            else:
                display_status = worker_status
                
            status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            
            final_display = display_status
            pct_str = ""
            if len(data) > 6:
                comp, tot = data[5], data[6]
                if tot > 0:
                    pct_val = (comp/tot)*100
                    if pct_val >= 99.999:
                        pct_str = "Complete"
                    else:
                        pct_str = f"{pct_val:.2f}%"
                        
                    status_item.setData(Qt.ItemDataRole.UserRole, pct_str)
                    
                    # EXACT 100% CHECK: Switch to Complete in the moment
                    if comp >= tot: 
                        display_status = "Complete"
                        # FORCE UI TEXT IMMEDIATELY
                        status_item.setText("Complete")
                        status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            
            if display_status == "Downloading":
                final_display = pct_str if pct_str else "Downloading"
            elif display_status in ["Paused", "Cancelled"]:
                pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct_data if pct_data else display_status
            
            # CRITICAL: Always force "Complete" if that's the determined status
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setText("Complete")
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
                
            if final_display != old_status:
                status_item.setText(final_display)
                self.update_ui_states()
            
            # Col 3 & 4: Time Left & Rate
            if display_status in ["Complete", "Error"]:
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
        # Normalize status
        if status_text == "Complete":
            display_status = "Complete"
            # SET FLAG EARLY so if confirmation comes later, it knows it's complete
            item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Complete")
        elif status_text == "Cancelled":
            display_status = "Cancelled"
        elif status_text == "Paused":
            display_status = "Paused"
        else:
            display_status = "Error"

        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            return 
            
        if row != -1:
            status_item = self.download_table.item(row, 2)
            if not status_item:
                status_item = QTableWidgetItem()
                self.download_table.setItem(row, 2, status_item)
            
            # Formatting final display text
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            elif display_status in ["Paused", "Cancelled"]:
                pct = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct if pct else "0.0%"
            else:
                final_display = display_status
            
            status_item.setText(final_display)
            
            if display_status in ["Complete", "Error"]:
                 self._set_sortable_item(row, 3, "", parse_time_to_sec)
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            elif display_status in ["Paused", "Cancelled"]:
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)

            final_timestamp = str(time.time())
            item_ref.setData(Qt.ItemDataRole.UserRole + 2, final_timestamp)
            self.download_table.setItem(row, 5, QTableWidgetItem(format_timestamp_relative(final_timestamp, max_relative_seconds=300)))

        # Handle UI Popups / Dialogs
        key = id(item_ref)
        if display_status == "Complete":
            if key in self.active_downloads:
                self.active_downloads[key].close()
            
            # If File Info dialog is still open, return and wait for confirmed action
            if key in self.active_file_info_dialogs:
                return

            # Show IDM-style Download Complete Dialog
            file_data = {
                "url": item_ref.data(Qt.ItemDataRole.UserRole),
                "path": item_ref.data(Qt.ItemDataRole.UserRole + 1),
                "size": self.download_table.item(row, 1).text() if row != -1 else "?"
            }
            self._complete_dlg = DownloadCompleteDialog(file_data, self)
            self._complete_dlg.show()
            
        self.update_ui_states()
        self.save_data()
        # Explicit repaint
        self.download_table.viewport().update()
    
    def open_options(self):
        from ui.dialogs import OptionsDialog
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
            "<p>Version: 1.1</p>"
            "<p>Built for the XDG standard on Linux.</p>"
        )

if __name__ == "__main__":
    from PyQt6.QtCore import Qt
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("bengal-download-manager")
    app.setApplicationName("bengal-download-manager")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 9))
    
    # Initialize and set global application icon
    app_icon = get_app_icon()
    if app_icon.isNull():
        # Last resort fallback to standard Qt icon
        app_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    app.setWindowIcon(app_icon)
    
    window = MainWindow()
    if not getattr(window, "start_minimized", False):
        window.show()
    sys.exit(app.exec())