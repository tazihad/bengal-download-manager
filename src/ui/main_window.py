"""
Main Application Window Component
=================================
Coordinates download management UI, table views, categories, dialogs, and workers.
"""

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
import platform
import re
import glob
import configparser
from pathlib import Path
from typing import Optional, Tuple

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

try:
    from gi.repository import Gio  # type: ignore
    _HAS_GIO = True
except Exception:
    _HAS_GIO = False

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QToolButton, QStatusBar, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu,
    QFileIconProvider, QInputDialog, QDialog, 
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit,
    QSystemTrayIcon, QRubberBand
)
from PyQt6.QtGui import QAction, QActionGroup, QFont, QCloseEvent, QIcon, QColor, QPalette, QDesktopServices, QKeySequence, QPixmap, QImage, QShortcut, QKeyEvent
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase, QUrl, QTimer, QThread, pyqtSignal, QObject, QEvent, QPoint, QRect, QItemSelectionModel, QItemSelection
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


from core.workers import DownloadWorker, Aria2Worker
from ui.dialogs import (
    AddUrlDialog, OptionsDialog, DownloadProgressDialog, 
    PropertiesDialog, DownloadCompleteDialog, ColumnDialog, DeleteDialog, RenameDialog,
    MediaDownloaderDialog, SchedulerDialog
)
from core.config import load_category_config
from core.utils import (
    get_data_dir, get_config_dir, get_unique_filepath, ensure_aria2, 
    load_proxy_config, load_extension_config, get_aria2_proxy_url,
    show_in_folder, resolve_filename, open_file_generic, open_with, choose_portal_save_path,
    is_media_downloader_url, setup_logging, format_bytes, get_clean_env, get_process_memory,
    get_user_downloads_dir
)
from core.memory_guard import MemoryGuard

from core.services.ipc_service import (
    DM_CONNECTOR_PORT,
    SignalEmitter,
    IPCEmitter,
    IPCRequestHandler,
    TcpListenerThread,
    IPCListenerThread,
    get_single_instance_key,
    SingleInstanceServer,
    check_single_instance,
)

from core.database import (
    init_db,
    get_all_downloads,
    save_all_downloads,
    get_all_queues,
    save_all_queues,
    upsert_queue,
    delete_queue,
)



from core.services.theme_service import (
    ACCENT_COLORS,
    CURRENT_ICON_THEME,
    CATEGORY_EXTENSIONS,
    FREEDESKTOP_MAP,
    apply_app_theme,
    detect_accent,
    ensure_adaptive_icon_theme,
    format_timestamp_relative,
    get_app_icon,
    get_monochrome_app_icon,
    get_category_for_filename,
    get_file_icon,
    get_themed_icon,
    get_themed_tray_icon,
    init_app_font,
    make_faded_icon,
    normalize_accent_name,
    normalize_icon_theme_name,
    normalize_theme_name,
    normalize_tray_icon_name,
    parse_size_to_bytes,
    parse_time_to_sec,
)

from ui.components import (
    SortableTableWidgetItem,
    EmptyAreaClickFilter,
    SidebarItemDelegate,
    ToolbarHoverFilter,
)

def _resolve_symbol(name: str, fallback):
    """Dynamically resolves a symbol from main module or returns fallback to support monkeypatching."""
    main_mod = sys.modules.get("main")
    if main_mod and hasattr(main_mod, name):
        return getattr(main_mod, name)
    return fallback


# --- CUSTOM DIALOG FOR DELETING COMPLETED ITEMS ---
class MainWindow(QMainWindow):
    def __init__(self, start_ipc=True):
        super().__init__()
        self.start_ipc = start_ipc
        self.setWindowTitle("Bengal Download Manager")
        
        # Set window icon from global app icon
        self.setWindowIcon(QApplication.windowIcon())
        
        self.setGeometry(200, 150, 1000, 600)
        
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_tray_icon()
        self.setup_central_widget()
        self.setup_status_bar()
        
        self.settings = self.load_settings()
        
        # FEATURE: Start Minimized logic
        if getattr(self, "start_minimized", False):
            # We use a timer to hide because some window managers might show it briefly otherwise
            self._is_in_tray = True
            QTimer.singleShot(0, self.hide)
            # Update tray icon action to "Show"
            QTimer.singleShot(0, self.update_tray_action)
        else:
            self._is_in_tray = False
        
        self.active_downloads = {}
        self.active_speeds = {}
        self._pending_tray_updates = {}
        self.MAX_CONCURRENT_DOWNLOADS = 4  # Default max simultaneous downloads
        self.active_file_info_dialogs = {}
        self.active_complete_dialogs = {}
        self.load_data()
        
        # FEATURE: Timer for periodic timestamp updates (Run every 10 seconds)
        self.timestamp_timer = QTimer(self)
        self.timestamp_timer.timeout.connect(self.update_timestamp_display)
        self.timestamp_timer.start(10000) # Update every 10 seconds

        # FEATURE: Timer for real-time status bar updates (Run every second)
        self.status_bar_timer = QTimer(self)
        self.status_bar_timer.timeout.connect(self.update_periodic_status)
        self.status_bar_timer.start(1000)
        
        # FEATURE: Periodic memory compaction and leak protection (Run every 45 seconds)
        self.memory_guard_timer = MemoryGuard.start_periodic_trim(self, interval_ms=45000)

        # Enable Drag-and-Drop
        self.setAcceptDrops(True)

        # --- IPC Setup: Listener for Browser Extension ---
        self.ipc_emitter = SignalEmitter()
        # Connect the thread's signal to the GUI slot (start_download)
        # Route extension downloads to the pre-fetcher instead of starting immediately
        self.ipc_emitter.new_download_signal.connect(self.process_incoming_url) 
        self.listener_thread = TcpListenerThread(DM_CONNECTOR_PORT, self.ipc_emitter)
        
        self.active_fetchers = [] # Prevent fetcher threads from being garbage collected

        if self.start_ipc:
            self.listener_thread.start()

        # Initial UI State Update
        self.update_ui_states()

        # Listen for dynamic system/OS theme changes
        app_inst = QApplication.instance()
        if app_inst:
            sh_inst = app_inst.styleHints()
            if hasattr(sh_inst, "colorSchemeChanged"):
                sh_inst.colorSchemeChanged.connect(self.on_system_theme_changed)
            if hasattr(app_inst, "paletteChanged"):
                app_inst.paletteChanged.connect(self.on_system_theme_changed)
        
        # Auto-start local Aria2 daemon for accelerated downloading
        self.aria2_process = self.start_aria2_daemon()
        self.is_quitting = False
        
        # Scheduler periodic background timer
        self._last_scheduled_minute = {}
        self._last_sync_times = {}
        self.download_retry_counts = {}
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.setInterval(1000)
        self.scheduler_timer.timeout.connect(self._check_scheduled_queues)
        self.scheduler_timer.start()

        # Check and start queues configured to run on application startup
        QTimer.singleShot(100, self._check_startup_queues)

    def _handle_options_accepted(self):
        # Clean restart aria2 daemon
        if self.aria2_process:
            try:
                self.aria2_process.terminate()
                try: self.aria2_process.wait(timeout=2.0)
                except: self.aria2_process.kill()
            except: pass
        self.aria2_process = self.start_aria2_daemon()
        self.update_status_bar_aria2()

    def start_aria2_daemon(self):
        try:
            if hasattr(self, 'aria2_process') and self.aria2_process:
                try:
                    self.aria2_process.terminate()
                    try:
                        self.aria2_process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self.aria2_process.kill()
                except Exception:
                    pass

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

            # --- APPLY PROXY SETTINGS NATIVELY ---
            proxy_url = get_aria2_proxy_url()
            if proxy_url:
                cmd.append(f"--all-proxy={proxy_url}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=get_clean_env()
            )
            return proc
        except Exception:
            return None
    def closeEvent(self, event: QCloseEvent):
        if not self.is_quitting:
            event.ignore()
            self._is_in_tray = True
            self.hide()
            self.update_tray_action()
            return

        # 1. Hide tray icon immediately to prevent ghost tray icons in taskbars
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.hide()
            except Exception:
                pass

        # 2. Stop IPC Listener Thread and Single Instance Server
        if hasattr(self, "listener_thread") and self.listener_thread:
            try:
                self.listener_thread.stop()
                self.listener_thread.wait(1000)
            except Exception:
                pass
        
        if hasattr(self, 'single_instance_server') and self.single_instance_server:
            try:
                self.single_instance_server.stop()
            except Exception:
                pass

        # 3. Stop all download workers & segment threads
        self.stop_all_downloads()

        # 4. Stop all active fetcher threads
        if hasattr(self, "active_fetchers"):
            for fetcher in list(self.active_fetchers):
                try:
                    if hasattr(fetcher, "requestInterruption"):
                        fetcher.requestInterruption()
                    if hasattr(fetcher, "quit"):
                        fetcher.quit()
                    if hasattr(fetcher, "wait"):
                        fetcher.wait(500)
                except Exception:
                    pass
            self.active_fetchers.clear()

        # 5. Close all active dialog windows
        if hasattr(self, "active_file_info_dialogs"):
            for dlg in list(self.active_file_info_dialogs.values()):
                try:
                    dlg.close()
                    dlg.deleteLater()
                except Exception:
                    pass
            self.active_file_info_dialogs.clear()

        if hasattr(self, "active_complete_dialogs"):
            for dlg in list(self.active_complete_dialogs.values()):
                try:
                    dlg.close()
                    dlg.deleteLater()
                except Exception:
                    pass
            self.active_complete_dialogs.clear()

        for dlg_attr in ("_options_dlg", "_media_downloader_dlg", "_scheduler_dlg"):
            dlg = getattr(self, dlg_attr, None)
            if dlg:
                try:
                    dlg.close()
                    dlg.deleteLater()
                except Exception:
                    pass
                setattr(self, dlg_attr, None)

        # Close all top-level Qt windows
        try:
            QApplication.closeAllWindows()
        except Exception:
            pass

        # 6. Stop all timers before closing
        if hasattr(self, "timestamp_timer") and self.timestamp_timer:
            self.timestamp_timer.stop() 
        if hasattr(self, 'status_bar_timer') and self.status_bar_timer:
            self.status_bar_timer.stop()
        if hasattr(self, 'memory_guard_timer') and self.memory_guard_timer:
            self.memory_guard_timer.stop()
        
        # 7. Kill the aria2 daemon cleanly on exit
        if hasattr(self, 'aria2_process') and self.aria2_process:
            try:
                self.aria2_process.terminate()
                try:
                    self.aria2_process.wait(timeout=1.5)
                except Exception:
                    self.aria2_process.kill()
            except Exception:
                pass
                
        # 8. Save application state
        self.save_data()
        self.save_settings()

        # 9. Clean memory & accept close
        MemoryGuard.clean_and_trim()
        event.accept()
        QApplication.quit()

    def quit_app(self):
        self.is_quitting = True
        self.close()
        try:
            QApplication.closeAllWindows()
            QApplication.quit()
        except Exception:
            pass



    # --- DRAG AND DROP HANDLERS ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.process_incoming_url(url.toString())


    def setup_actions(self):
        self.action_add_url = QAction(get_themed_icon("add_url"), "Add URL", self)
        self.action_add_url.setShortcut(QKeySequence("Ctrl+N"))
        self.action_add_url.setToolTip("Add a new download URL address (Ctrl+N)")
        self.action_add_url.triggered.connect(lambda: self.open_add_url(paste_clipboard=False))

        self.action_paste_url = QAction(get_themed_icon("add_url"), "Paste URL", self)
        self.action_paste_url.setShortcut(QKeySequence("Ctrl+V"))
        self.action_paste_url.setToolTip("Paste URL address from clipboard (Ctrl+V)")
        self.action_paste_url.triggered.connect(lambda: self.open_add_url(paste_clipboard=True))

        self.action_exit = QAction(get_themed_icon("exit"), "Exit", self)
        self.action_exit.setToolTip("Exit Bengal Download Manager")
        self.action_exit.triggered.connect(self.quit_app)

        _fi = make_faded_icon  # shorthand

        self.action_stop = QAction(_fi(get_themed_icon("stop")), "Stop/Pause", self)
        self.action_stop.setToolTip("Pause or stop selected download(s)")
        self.action_stop.triggered.connect(self.stop_selected_download)
        self.action_stop.setEnabled(False)

        self.action_stop_all = QAction(_fi(get_themed_icon("stop_all")), "Stop All", self)
        self.action_stop_all.setToolTip("Pause or stop all currently active downloads")
        self.action_stop_all.triggered.connect(self.stop_all_downloads)
        self.action_stop_all.setEnabled(False)

        self.action_resume = QAction(_fi(get_themed_icon("resume")), "Resume", self)
        self.action_resume.setToolTip("Resume downloading selected file(s)")
        self.action_resume.triggered.connect(self.resume_selected_download)
        self.action_resume.setEnabled(False)

        self.action_download_now = QAction(_fi(get_themed_icon("resume")), "Download Now", self)
        self.action_download_now.setToolTip("Start downloading selected file immediately")
        self.action_download_now.triggered.connect(self.resume_selected_download)

        self.action_redownload = QAction(_fi(get_themed_icon("unfinished")), "Redownload", self)
        self.action_redownload.setToolTip("Restart download from the beginning")
        self.action_redownload.triggered.connect(self.redownload_selected)

        self.action_delete = QAction(_fi(get_themed_icon("delete")), "Delete", self)
        self.action_delete.setToolTip("Delete selected download(s) from the list (Delete key)")
        self.action_delete.triggered.connect(self.delete_selected_download)
        self.action_delete.setEnabled(False)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)

        self.action_clear = QAction(get_themed_icon("clear_completed"), "Clear Completed", self)
        self.action_clear.setToolTip("Remove completed downloads from the list")
        self.action_clear.triggered.connect(self.clear_finished_downloads)
        
        self.action_options = QAction(get_themed_icon("options"), "Options", self)
        self.action_options.setToolTip("Configure download manager options, connection limits, and engine settings")
        self.action_options.triggered.connect(self.open_options)

        self.action_scheduler = QAction(get_themed_icon("scheduler"), "Scheduler", self)
        self.action_scheduler.setToolTip("Manage download queues and scheduling")
        self.action_scheduler.triggered.connect(self.open_scheduler)

        self.action_media_downloader = QAction(get_themed_icon("media_downloader"), "Media Downloader", self)
        self.action_media_downloader.setToolTip("Parse and download video or audio streams and playlists from media sites")
        self.action_media_downloader.triggered.connect(self.open_media_downloader)

        self.action_open_folder = QAction(get_themed_icon("open_folder"), "Open Downloads Folder", self)
        self.action_open_folder.setToolTip("Open default downloads directory")
        self.action_open_folder.triggered.connect(self.open_downloads_folder_generic)

    def setup_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        # 1. Tasks
        tasks_menu = menu_bar.addMenu("&Tasks")
        tasks_menu.addAction(self.action_add_url)
        tasks_menu.addAction(self.action_paste_url)
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
        downloads_menu.addAction(self.action_media_downloader)

        # 4. View
        view_menu = menu_bar.addMenu("&View")

        table_style_menu = view_menu.addMenu("Table style")
        self.table_style_group = QActionGroup(self)
        self.table_style_group.setExclusive(True)

        self.action_table_style_classic = QAction("Classic", self)
        self.action_table_style_classic.setCheckable(True)
        self.action_table_style_classic.setChecked(True)
        self.action_table_style_classic.triggered.connect(lambda checked: self.set_table_style("classic") if checked else None)
        self.table_style_group.addAction(self.action_table_style_classic)
        table_style_menu.addAction(self.action_table_style_classic)

        self.action_table_style_modern = QAction("Modern", self)
        self.action_table_style_modern.setCheckable(True)
        self.action_table_style_modern.triggered.connect(lambda checked: self.set_table_style("modern") if checked else None)
        self.table_style_group.addAction(self.action_table_style_modern)
        table_style_menu.addAction(self.action_table_style_modern)

        view_menu.addSeparator()

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
        self.action_hide_categories = QAction("&Hide categories", self)
        self.action_hide_categories.setCheckable(True)
        self.action_hide_categories.setChecked(False)
        self.action_hide_categories.setEnabled(True)
        self.action_hide_categories.triggered.connect(self.toggle_hide_categories)
        view_menu.addAction(self.action_hide_categories)

        self.action_toolbar_toggle = QAction("&Toolbar", self)
        self.action_toolbar_toggle.setCheckable(True)
        self.action_toolbar_toggle.setChecked(True)
        self.action_toolbar_toggle.triggered.connect(self._on_toolbar_toggled)
        view_menu.addAction(self.action_toolbar_toggle)

        self.action_status_bar_toggle = QAction("&Status Bar", self)
        self.action_status_bar_toggle.setCheckable(True)
        self.action_status_bar_toggle.setChecked(True)
        self.action_status_bar_toggle.triggered.connect(self.toggle_status_bar)
        view_menu.addAction(self.action_status_bar_toggle)

        # 5. Help
        help_menu = menu_bar.addMenu("&Help")
        self.action_homepage = QAction("BDM &Homepage", self)
        self.action_homepage.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/tazihad/bengal-download-manager")))
        help_menu.addAction(self.action_homepage)

        self.action_bug_report = QAction("&File bug report", self)
        self.action_bug_report.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/tazihad/bengal-download-manager/issues")))
        help_menu.addAction(self.action_bug_report)

        help_menu.addSeparator()

        about_action = QAction("&About Bengal DM", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def is_dark_theme(self) -> bool:
        theme = getattr(self, "settings", {}).get("theme", "BDM Dark (Default)")
        theme_lower = str(theme).lower()
        if "light" in theme_lower:
            return False
        if any(d in theme_lower for d in ("dark", "dracula", "nord", "obsidian")):
            return True
        app = QApplication.instance()
        if app:
            pal = app.palette()
            return pal.color(QPalette.ColorRole.Window).value() < 128
        return True

    def get_toolbar_stylesheet(self) -> str:
        glow_text_color = "#ffffff" if self.is_dark_theme() else "#000000"
        return f"""
            QToolBar {{
                background-color: palette(window);
                border: none;
                spacing: 3px;
                padding: 2px 4px;
            }}
            QToolButton {{
                color: palette(window-text);
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 4px 6px;
                font-weight: normal;
                opacity: 1.0;
            }}
            QToolButton:hover {{
                color: {glow_text_color};
                background-color: palette(midlight);
                border: 1px solid palette(highlight);
                font-weight: bold;
                opacity: 1.0;
            }}
            QToolButton:pressed {{
                background-color: palette(highlight);
                color: {glow_text_color};
                border: 1px solid palette(highlight);
                font-weight: bold;
            }}
            QToolButton:disabled {{
                opacity: 0.30;
                background-color: transparent;
                border: 1px solid transparent;
            }}
        """

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
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setStyleSheet(self.get_toolbar_stylesheet())

        toolbar.addAction(self.action_add_url)
        toolbar.addAction(self.action_resume)
        toolbar.addAction(self.action_stop)
        toolbar.addAction(self.action_stop_all)
        toolbar.addAction(self.action_delete) 
        toolbar.addAction(self.action_clear)
        toolbar.addAction(self.action_scheduler)
        toolbar.addAction(self.action_options)
        toolbar.addAction(self.action_media_downloader)

        self.toolbar_hover_filter = ToolbarHoverFilter(self)
        for child in toolbar.findChildren(QToolButton):
            child.installEventFilter(self.toolbar_hover_filter)

    def setup_central_widget(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.category_tree = QTreeWidget()
        self.category_tree.setMouseTracking(True)
        self.category_tree.viewport().setMouseTracking(True)
        self.category_tree.setItemDelegate(SidebarItemDelegate(self.category_tree))
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setRootIsDecorated(False)
        self.category_tree.setIconSize(QSize(18, 18))
        self.category_tree.setIndentation(10)
        self.category_tree.setAnimated(True)
        self.category_tree.itemClicked.connect(self.filter_downloads)
        self.category_tree.setExpandsOnDoubleClick(False)
        self.category_tree.itemDoubleClicked.connect(self._sidebar_item_double_clicked)

        self.category_tree.setStyleSheet("""
            QTreeWidget {
                show-decoration-selected: 0;
                font-size: 13px;
                font-weight: 500;
                padding: 4px 2px;
                border: none;
                outline: 0;
                background-color: palette(base);
                color: palette(window-text);
            }
            QTreeWidget::item {
                height: 26px;
                padding: 2px 8px;
                margin: 1px 2px;
                border-radius: 4px;
                color: palette(window-text);
            }
            QTreeWidget::item:focus {
                outline: none;
                border: none;
            }
            QTreeWidget::item:hover {
                background-color: palette(highlight);
                color: #111111;
            }
            QTreeWidget::item:selected {
                background-color: palette(highlight);
                color: #111111;
                font-weight: 600;
            }
            QTreeWidget::item:disabled {
                background: transparent;
                background-color: transparent;
                color: palette(placeholder-text);
            }
            QTreeWidget::branch {
                background: transparent;
                background-color: transparent;
                border: none;
                outline: none;
            }
            QTreeWidget::branch:selected,
            QTreeWidget::branch:selected:active,
            QTreeWidget::branch:selected:inactive,
            QTreeWidget::branch:hover {
                background: transparent;
                background-color: transparent;
            }
        """)

        def make_section_header(title: str, tooltip: str = ""):
            header_item = QTreeWidgetItem(self.category_tree, [title])
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Non-selectable, non-interactive
            header_item.setData(0, Qt.ItemDataRole.UserRole, "header")
            header_font = QFont(self.font())
            header_font.setPointSize(8)
            header_font.setBold(True)
            header_item.setFont(0, header_font)
            if tooltip:
                header_item.setToolTip(0, tooltip)
            return header_item

        # 1. Categories Section Header
        self.header_categories = make_section_header("Categories", "Download categories")

        self.all_downloads_header = QTreeWidgetItem(self.category_tree, ["All Downloads"])
        all_downloads = self.all_downloads_header
        all_downloads.setIcon(0, get_themed_icon("all_downloads"))
        all_downloads.setToolTip(0, "Show all downloads regardless of category or status")
        all_downloads.setExpanded(True)


        cat_icons = {
            "Compressed": get_themed_icon("compressed"),
            "Documents": get_themed_icon("documents"),
            "Music": get_themed_icon("music"),
            "Programs": get_themed_icon("programs"),
            "Video": get_themed_icon("video")
        }
        for cat_name, cat_icon in cat_icons.items():
            child = QTreeWidgetItem(all_downloads, [cat_name])
            child.setIcon(0, cat_icon)
            child.setToolTip(0, f"Filter downloads in {cat_name} category")

        # 2. Status Section Header
        self.header_status = make_section_header("Status", "Filter by download status")

        self.item_unfinished = QTreeWidgetItem(self.category_tree, ["Incomplete"])
        item_unfinished = self.item_unfinished
        item_unfinished.setIcon(0, get_themed_icon("unfinished"))
        item_unfinished.setToolTip(0, "Show active, paused, or pending downloads")

        self.item_finished = QTreeWidgetItem(self.category_tree, ["Finished"])
        item_finished = self.item_finished
        item_finished.setIcon(0, get_themed_icon("finished"))
        item_finished.setToolTip(0, "Show completed downloads")

        # 3. Schedule Section Header
        self.header_schedule = make_section_header("Schedule", "Download scheduler and queues")

        self.queues_header = QTreeWidgetItem(self.category_tree, ["Queues"])
        self.queues_header.setIcon(0, get_themed_icon("scheduler"))
        self.queues_header.setToolTip(0, "Download queues and scheduler")
        self.queues_header.setExpanded(True)

        from ui.dialogs.scheduler import DEFAULT_QUEUES, _make_default_queue
        # _queues_data is loaded from SQLite database, falling back to defaults if empty
        db_queues = get_all_queues()
        self._queues_data = [dict(q) for q in (db_queues if db_queues else DEFAULT_QUEUES)]
        for q in self._queues_data:
            q["daily_days"] = list(q.get("daily_days", [True, True, True, True, True, True, True]))
        self._sidebar_queue_names = []
        for q in self._queues_data:
            child = QTreeWidgetItem(self.queues_header, [q["name"]])
            child.setIcon(0, get_themed_icon("scheduler"))
            child.setToolTip(0, f"Queue: {q['name']}")
            child.setData(0, Qt.ItemDataRole.UserRole, "queue")
            self._sidebar_queue_names.append(q["name"])

        self.category_tree.setCurrentItem(all_downloads)

        # Enable right-click context menu on the category tree for queue items
        self.category_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_tree.customContextMenuRequested.connect(self._show_sidebar_context_menu)
        
        self.download_table = QTableWidget()
        self.download_table.setWordWrap(False)
        self.download_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._default_table_delegate = self.download_table.itemDelegate()
        self.table_style = "classic"
        self.download_table.setIconSize(QSize(16, 16))
        self.download_table.setColumnCount(7)
        self.download_table.verticalHeader().setVisible(False)
        
        # Ensure row selection is correctly set up
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Install event filter to clear selection on empty area click
        self.empty_area_filter = EmptyAreaClickFilter(self.download_table, self)
        self.download_table.installEventFilter(self.empty_area_filter)
        self.download_table.viewport().installEventFilter(self.empty_area_filter)

        # FIX: Remove blue cell highlight (focus rectangle) on selection

        self.download_table.setStyleSheet("""
            QTableWidget {
                selection-color: #000000;
                selection-background-color: palette(highlight);
            }
            QTableWidget::item:selected, QTableWidget::item:selected:active, QTableWidget::item:selected:!active {
                color: #000000;
                background-color: palette(highlight);
            }
            QTableWidget::item:focus { 
                border: none; 
                outline: 0; 
            }
            QHeaderView::section {
                font-weight: normal;
            }
        """)

        self.download_table.itemSelectionChanged.connect(self.update_ui_states)
        
        self.download_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self.show_context_menu)
        self.download_table.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        
        header_labels_info = [
            ("File Name", "Name of the downloaded file"),
            ("Size", "Total file size"),
            ("Status", "Current download status and percentage"),
            ("Time Left", "Estimated time remaining until completion"),
            ("Transfer Rate", "Current download transfer speed"),
            ("Last Try", "Timestamp of the last download attempt"),
            ("Date Added", "Timestamp when the download was added")
        ]
        self.download_table.setHorizontalHeaderLabels([h[0] for h in header_labels_info])
        header = self.download_table.horizontalHeader()
        for idx, (_, tooltip) in enumerate(header_labels_info):
            item = self.download_table.horizontalHeaderItem(idx)
            if item:
                item.setToolTip(tooltip)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        
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
        splitter.setSizes([230, 770])
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

    def setup_status_bar(self):
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)
        status_bar.setStyleSheet("""
            QStatusBar {
                background-color: palette(window);
                color: palette(window-text);
                border-top: 1px solid palette(mid);
                min-height: 26px;
                max-height: 26px;
                font-size: 11px;
                padding: 0px 6px;
            }
            QStatusBar::item {
                border: none;
            }
        """)

        tnum_font = QFont(self.font())
        tnum_font.setPointSize(9)
        tnum_font.setFeature(QFont.Tag.fromString('tnum'), 1)

        # 1. Item Selection Status (Left, stretchable)
        self.status_items_label = QLabel("0 items", self)
        self.status_items_label.setFont(tnum_font)
        self.status_items_label.setStyleSheet("color: palette(window-text); padding: 0px 4px;")
        status_bar.addWidget(self.status_items_label, 1)

        # Helper to create separator
        def create_sep():
            sep = QLabel("│", self)
            sep.setStyleSheet("color: palette(mid); padding: 0px 2px;")
            return sep

        # 2. Download Speed Status (Permanent widget on right)
        self.status_speed_label = QLabel("Speed: 0 B/s", self)
        self.status_speed_label.setFont(tnum_font)
        self.status_speed_label.setStyleSheet("color: palette(window-text); padding: 0px 6px;")
        self.status_speed_label.setToolTip("Total Download Speed: 0 B/s")
        status_bar.addPermanentWidget(self.status_speed_label)

        status_bar.addPermanentWidget(create_sep())

        # 3. Aria2 Status (Permanent widget on right)
        self.status_aria2_label = QLabel("● Aria2: Ready", self)
        self.status_aria2_label.setFont(tnum_font)
        self.status_aria2_label.setStyleSheet("color: palette(window-text); padding: 0px 6px;")
        self.status_aria2_label.setToolTip("Aria2 RPC Status")
        status_bar.addPermanentWidget(self.status_aria2_label)

        status_bar.addPermanentWidget(create_sep())

        # 4. Memory Status (Permanent widget on right)
        self.status_memory_label = QLabel("Memory: 0 B", self)
        self.status_memory_label.setFont(tnum_font)
        self.status_memory_label.setStyleSheet("color: palette(window-text); padding: 0px 6px;")
        self.status_memory_label.setToolTip("Application Memory Usage (Resident Set Size)")
        status_bar.addPermanentWidget(self.status_memory_label)

        self.update_status_bar()

    def update_status_bar_items(self):
        if not hasattr(self, "status_items_label") or not hasattr(self, "download_table"):
            return
        total_rows = self.download_table.rowCount()
        selected_rows = set(item.row() for item in self.download_table.selectedItems())
        sel_count = len(selected_rows)

        visible_rows = 0
        for r in range(total_rows):
            if not self.download_table.isRowHidden(r):
                visible_rows += 1

        if total_rows == 0:
            self.status_items_label.setText("0 items")
            self.status_items_label.setToolTip("No downloads in list")
        elif sel_count == 0:
            unit = "item" if total_rows == 1 else "items"
            if visible_rows < total_rows:
                self.status_items_label.setText(f"{visible_rows} of {total_rows} {unit}")
                self.status_items_label.setToolTip(f"{visible_rows} visible ({total_rows} total downloads)")
            else:
                self.status_items_label.setText(f"{total_rows} {unit}")
                self.status_items_label.setToolTip(f"{total_rows} total downloads")
        else:
            unit = "item" if total_rows == 1 else "items"
            self.status_items_label.setText(f"Selected: {sel_count} of {total_rows} {unit}")
            tot_bytes = 0
            for r in selected_rows:
                size_item = self.download_table.item(r, 1)
                if size_item:
                    tot_bytes += parse_size_to_bytes(size_item.text())
            size_str = f" — Total size: {format_bytes(tot_bytes)}" if tot_bytes > 0 else ""
            self.status_items_label.setToolTip(f"{sel_count} of {total_rows} {unit} selected{size_str}")

    def update_status_bar_speed(self):
        if not hasattr(self, "active_speeds"):
            self.active_speeds = {}
        if not hasattr(self, "active_downloads"):
            self.active_downloads = {}

        total_speed = sum(self.active_speeds.values()) if self.active_speeds else 0.0
        active_count = len(self.active_downloads) or len(self.active_speeds)

        # 1. Update Status Bar Label
        if hasattr(self, "status_speed_label") and self.status_speed_label:
            if total_speed <= 0:
                self.status_speed_label.setText("Speed: 0 B/s")
                self.status_speed_label.setToolTip("Total Download Speed: 0 B/s (0 active downloads)")
            else:
                speed_str = f"Speed: {format_bytes(total_speed)}/s"
                self.status_speed_label.setText(speed_str)
                self.status_speed_label.setToolTip(f"Total Download Speed: {format_bytes(total_speed)}/s ({active_count} active downloads)")

        # 2. Update Tray Icon ToolTip
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                if total_speed > 0:
                    plural = "downloads" if active_count != 1 else "download"
                    self.tray_icon.setToolTip(f"Bengal Download Manager\n{format_bytes(total_speed)}/s — {active_count} active {plural}")
                elif active_count > 0:
                    plural = "downloads" if active_count != 1 else "download"
                    self.tray_icon.setToolTip(f"Bengal Download Manager\nConnecting... ({active_count} active {plural})")
                else:
                    self.tray_icon.setToolTip("Bengal Download Manager")
            except Exception:
                pass

    def update_status_bar_aria2(self):
        if not hasattr(self, "status_aria2_label"):
            return
        is_running = False
        pid = None

        try:
            ext_data = load_extension_config()
            port = ext_data.get("port", 56800)
        except Exception:
            port = 56800

        if hasattr(self, "aria2_process") and self.aria2_process and self.aria2_process.poll() is None:
            is_running = True
            pid = getattr(self.aria2_process, "pid", None)
        else:
            # If process object is not running or not tracked, check if an Aria2 RPC daemon is active on port
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.15)
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        is_running = True
            except Exception:
                pass

        if is_running:
            pid_info = f", PID {pid}" if pid else ""
            self.status_aria2_label.setText("● Aria2: Connected")
            self.status_aria2_label.setStyleSheet("color: #2ecc71; font-weight: 500; padding: 0px 6px;")
            self.status_aria2_label.setToolTip(f"Aria2 RPC Engine: Connected (Port {port}{pid_info})")
        else:
            self.status_aria2_label.setText("● Aria2: Stopped")
            self.status_aria2_label.setStyleSheet("color: #e74c3c; font-weight: 500; padding: 0px 6px;")
            self.status_aria2_label.setToolTip(f"Aria2 RPC Engine: Stopped (Port {port})")

    def update_status_bar_memory(self):
        if not hasattr(self, "status_memory_label"):
            return
        mem_bytes = get_process_memory()
        self.status_memory_label.setText(f"Memory: {format_bytes(mem_bytes)}")
        self.status_memory_label.setToolTip(f"Application Memory Usage (RSS): {format_bytes(mem_bytes)}")

    def update_periodic_status(self):
        self.update_status_bar_memory()
        self.update_status_bar_aria2()
        self.update_status_bar_speed()

    def update_status_bar(self):
        self.update_status_bar_items()
        self.update_status_bar_speed()
        self.update_status_bar_aria2()
        self.update_status_bar_memory()

    def toggle_hide_categories(self, hide: bool, save: bool = True):
        """Hides or shows the left categories panel."""
        if hasattr(self, "category_tree") and self.category_tree:
            self.category_tree.setVisible(not hide)
        if hasattr(self, "action_hide_categories") and self.action_hide_categories:
            self.action_hide_categories.setChecked(hide)
        if save and hasattr(self, "save_settings"):
            self.save_settings()

    def _on_toolbar_toggled(self, checked: bool, save: bool = True):
        tb = self.findChild(QToolBar, "MainToolbar")
        if tb:
            tb.setVisible(checked)
        if hasattr(self, "action_toolbar_toggle") and self.action_toolbar_toggle:
            self.action_toolbar_toggle.setChecked(checked)
        if save and hasattr(self, "save_settings"):
            self.save_settings()

    def toggle_status_bar(self, visible: bool, save: bool = True):
        """Shows or hides the bottom status bar."""
        sb = self.statusBar()
        if sb:
            sb.setVisible(visible)
        if hasattr(self, "action_status_bar_toggle") and self.action_status_bar_toggle:
            self.action_status_bar_toggle.setChecked(visible)
        if save and hasattr(self, "save_settings"):
            self.save_settings()

    def setup_tray_icon(self):
        """Sets up the system tray icon and its context menu safely."""
        self.tray_icon = None
        self.action_tray_toggle = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        try:
            self.tray_icon = QSystemTrayIcon(self)

            # Set themed icon for tray
            tray_opt = getattr(self, "settings", {}).get("tray_icon", None)
            icon = get_themed_tray_icon(tray_opt)
            if icon.isNull():
                icon = self.windowIcon()
            if icon.isNull():
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
            self.tray_icon.setIcon(icon)        
            # Create tray menu
            tray_menu = QMenu(self)
            
            # Show/Hide Action
            self.action_tray_toggle = QAction("Hide", self) # Default to Hide as window starts visible
            self.action_tray_toggle.setIcon(get_themed_icon("show_hide"))
            self.action_tray_toggle.triggered.connect(self.toggle_window)
            
            tray_menu.addAction(self.action_tray_toggle)
            tray_menu.addSeparator()
            tray_menu.addAction(self.action_add_url)
            tray_menu.addAction(self.action_media_downloader)
            tray_menu.addAction(self.action_options)
            tray_menu.addSeparator()
            tray_menu.addAction(self.action_exit)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.setToolTip("Bengal Download Manager")
            self.tray_icon.show()
            
            # Double click to show/hide
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
        except Exception as e:
            print(f"Warning: System tray icon initialization failed ({e})")
            self.tray_icon = None

    def show_download_progress_dialog(self, target):
        """
        Brings the DownloadProgressDialog for an active download to the foreground.
        Creates and connects the dialog on-the-fly if running in headless/silent mode.
        """
        key = None
        if isinstance(target, str):
            key = target
        elif isinstance(target, int):
            row = target
            if 0 <= row < self.download_table.rowCount():
                item_ref = self.download_table.item(row, 0)
                if item_ref:
                    key = self._get_item_key(item_ref)
        elif isinstance(target, QTableWidgetItem):
            key = self._get_item_key(target)

        if not key or key not in getattr(self, "active_downloads", {}):
            return None

        entry = self.active_downloads[key]
        dialog = None
        if isinstance(entry, DownloadProgressDialog) and MemoryGuard.is_widget_alive(entry):
            dialog = entry
        else:
            worker = getattr(entry, "worker", entry)
            if worker:
                dialog = DownloadProgressDialog(worker, None)
                dialog.finished.connect(self.refresh_toolbar_state_on_dialog_close)
                dialog.finished.connect(lambda *_, k=key: self.active_downloads.pop(k, None))
                dialog.finished.connect(self._try_start_queued)
                self.active_downloads[key] = dialog

        if dialog and MemoryGuard.is_widget_alive(dialog):
            if dialog.isMinimized():
                dialog.setWindowState(dialog.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
            dialog.show()
            dialog.showNormal()
            dialog.raise_()
            dialog.activateWindow()
            return dialog
        return None

    def show_all_active_progress_dialogs(self):
        """Brings all active download progress dialogs to the front."""
        active_keys = list(getattr(self, "active_downloads", {}).keys())
        for key in active_keys:
            self.show_download_progress_dialog(key)

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def restore_window(self):
        """Restores the window from minimized or hidden state and brings it to the foreground."""
        self._is_in_tray = False
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_tray_action()
        self._flush_pending_tray_updates()

    def toggle_window(self):
        """Toggles the visibility of the main window."""
        if self.isVisible() and not self.isMinimized():
            self._is_in_tray = True
            self.hide()
            self.update_tray_action()
        else:
            self.restore_window()


    def update_tray_action(self):
        """Updates the tray action text and icon based on window visibility."""
        if not hasattr(self, "action_tray_toggle") or self.action_tray_toggle is None:
            return
        if self.isVisible():
            self.action_tray_toggle.setText("Hide")
            self.action_tray_toggle.setIcon(get_themed_icon("show_hide"))
        else:
            self.action_tray_toggle.setText("Show")
            self.action_tray_toggle.setIcon(get_themed_icon("show_hide"))
        
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
                
                is_active = self._is_download_active(item_name)
                
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
            self._notify_views_changed()

    def _notify_views_changed(self):
        """Notifies QML bridge and scheduler dialog of download list/progress changes."""
        if not self.isVisible():
            return
        if MemoryGuard.is_widget_alive(getattr(self, '_scheduler_dlg', None)):
            if hasattr(self._scheduler_dlg, 'tabs') and self._scheduler_dlg.tabs.currentIndex() == 1:
                self._scheduler_dlg._refresh_files_table(self._scheduler_dlg._selected_index)
        if hasattr(self, 'bridge') and self.bridge:
            self.bridge.refresh()

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
                if not item:
                    continue
                key = self._get_item_key(item)
                
                status_item = self.download_table.item(r, 2)
                logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else None
                status = logic_status if logic_status else (status_item.text() if status_item else "")
                
                is_active = self._is_download_active(item)
                if is_active:
                    selection_has_active = True
                
                is_complete = status in ["Complete", "Finished"] or (item.data(Qt.ItemDataRole.UserRole + 11) == "Complete")
                is_resuming_or_connecting = logic_status in ["Resuming...", "Starting...", "Pending...", "Connecting..."] or status in ["Resuming...", "Starting...", "Pending...", "Connecting..."]
                
                if not is_complete and not is_resuming_or_connecting:
                    if is_active:
                        selection_has_active = True
                        selection_has_pausable = True
                    else:
                        selection_has_resumable = True
                elif is_active:
                    selection_has_pausable = True
        
        # STOP action is for pausing an active download
        self.action_stop.setEnabled(selection_has_pausable)
        self.action_stop_all.setEnabled(has_active_downloads)
        
        # RESUME action is for starting a paused/errored/cancelled download
        self.action_resume.setEnabled(selection_has_resumable)
        self.action_download_now.setEnabled(selection_has_resumable)
        
        self.action_delete.setEnabled(has_selection)
        self.action_redownload.setEnabled(has_selection)
        self.update_status_bar_items()
        for r in range(self.download_table.rowCount()):
            self._set_row_bold(r, self._is_row_active(r))
        
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
        if item.data(0, Qt.ItemDataRole.UserRole) == "header":
            return

        category = item.text(0)
        ext_map = CATEGORY_EXTENSIONS

        # Queues header — double-click toggles collapse (handled in _sidebar_item_double_clicked)
        if item is getattr(self, "queues_header", None):
            return

        # Queue child — filter by queue name stored in UserRole+8
        if item.data(0, Qt.ItemDataRole.UserRole) == "queue":
            queue_name = item.text(0)
            for row in range(self.download_table.rowCount()):
                row_item = self.download_table.item(row, 0)
                row_queue = row_item.data(Qt.ItemDataRole.UserRole + 8) if row_item else None
                # Rows with no queue tag belong to the Main download queue
                if row_queue is None:
                    row_queue = "Main download queue"
                self.download_table.setRowHidden(row, row_queue != queue_name)
            self.update_status_bar_items()
            return

        for row in range(self.download_table.rowCount()):
            self.download_table.setRowHidden(row, False) 
            filename = self.download_table.item(row, 0).text().lower()
            status = self.download_table.item(row, 2).text()
            should_hide = False
            
            if category == "All Downloads":
                should_hide = False
            elif category in ("Incomplete", "Unfinished"):
                if status in ("Complete", "Finished"): should_hide = True
            elif category in ("Finished", "Complete", "Completed"):
                if status not in ("Complete", "Finished"): should_hide = True
            elif category in ext_map:
                extensions = ext_map[category]
                if not any(filename.endswith(ext) for ext in extensions):
                    should_hide = True
            
            if should_hide:
                self.download_table.setRowHidden(row, True)

        self.update_status_bar_items()

    def _sidebar_item_double_clicked(self, item, column):
        """Handles double-click on sidebar tree items.

        - All Downloads header: toggle expand/collapse.
        - Queues header: toggle expand/collapse.
        """
        if item.data(0, Qt.ItemDataRole.UserRole) == "header":
            return
        if item is getattr(self, "all_downloads_header", None):
            item.setExpanded(not item.isExpanded())
            return
        if item is getattr(self, "queues_header", None):
            item.setExpanded(not item.isExpanded())
            return

    def _is_queue_active(self, queue_name: str) -> bool:
        """Returns True if any incomplete download in the queue is actively downloading, resuming, connecting, or queued."""
        for r in range(self.download_table.rowCount()):
            item_name = self.download_table.item(r, 0)
            if not item_name:
                continue
            row_q = item_name.data(Qt.ItemDataRole.UserRole + 8) or "Main download queue"
            if row_q != queue_name:
                continue

            status_item = self.download_table.item(r, 2)
            logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
            status_text = status_item.text() if status_item else ""
            is_completed = (
                logic_status in ["Complete", "Finished"] or
                status_text in ["Complete", "Finished"] or
                (item_name.data(Qt.ItemDataRole.UserRole + 11) == "Complete")
            )
            if is_completed:
                continue

            if self._is_download_active(item_name):
                return True
            if logic_status in ("Downloading", "Downloading...", "Resuming...", "Connecting...", "Queued"):
                return True
            if status_text in ("Downloading", "Downloading...", "Resuming...", "Connecting...", "Queued"):
                return True
        return False

    def _show_sidebar_context_menu(self, pos):
        """Shows a context menu for queue items in the sidebar tree."""
        item = self.category_tree.itemAt(pos)
        if not item:
            return

        # Only show context menu for queue child items or the Queues header
        is_queue_child = item.data(0, Qt.ItemDataRole.UserRole) == "queue"
        is_queue_header = item is getattr(self, "queues_header", None)

        if not is_queue_child and not is_queue_header:
            return

        menu = QMenu(self)

        if is_queue_child:
            queue_name = item.text(0)
            queue_is_running = self._is_queue_active(queue_name)

            act_start = menu.addAction("Start now")
            act_start.setEnabled(not queue_is_running)
            act_start.triggered.connect(lambda: self._queue_action_start(queue_name))

            act_stop = menu.addAction("Stop")
            act_stop.setEnabled(queue_is_running)
            act_stop.triggered.connect(lambda: self._queue_action_stop(queue_name))

            menu.addSeparator()

            act_edit = menu.addAction("Edit queue")
            act_edit.triggered.connect(lambda: self._open_scheduler_for_queue(queue_name, tab_index=1))

            act_schedule = menu.addAction("Schedule")
            act_schedule.triggered.connect(lambda: self._open_scheduler_for_queue(queue_name, tab_index=0))

            menu.addSeparator()

            # Determine if this is a default queue (cannot delete)
            is_default = queue_name in ("Main download queue", "Synchronization queue")
            act_delete = menu.addAction("Delete")
            act_delete.setIcon(make_faded_icon(get_themed_icon("delete")) if is_default else get_themed_icon("delete"))
            act_delete.setEnabled(not is_default)
            act_delete.triggered.connect(lambda: self._delete_sidebar_queue(item))

        act_new = menu.addAction("Create new queue")
        act_new.triggered.connect(self._create_sidebar_queue)

        menu.exec(self.category_tree.viewport().mapToGlobal(pos))

    def _open_scheduler_for_queue(self, queue_name, tab_index=0):
        """Opens the scheduler dialog, selects the given queue, and activates the specified tab."""
        self.open_scheduler()
        if MemoryGuard.is_widget_alive(getattr(self, "_scheduler_dlg", None)):
            # Find and select the queue by name
            for i, q in enumerate(self._scheduler_dlg.queues):
                if q["name"] == queue_name:
                    self._scheduler_dlg.queue_list.setCurrentRow(i)
                    break
            if hasattr(self._scheduler_dlg, "tabs") and tab_index < self._scheduler_dlg.tabs.count():
                self._scheduler_dlg.tabs.setCurrentIndex(tab_index)

    def _check_scheduled_queues(self):
        """Periodically checks queue schedules (start_at, stop_at, sync_interval)."""
        from PyQt6.QtCore import QDateTime
        now = QDateTime.currentDateTime()
        current_time_str = now.toString("HH:mm:ss")
        current_time_hm = now.toString("HH:mm")
        current_date_str = now.toString("yyyy-MM-dd")
        current_weekday = (now.date().dayOfWeek() % 7)  # 0=Sun, 1=Mon, ..., 6=Sat

        queues = getattr(self, "_queues_data", [])
        if not queues:
            db_queues = get_all_queues()
            queues = db_queues if db_queues else []

        for q in queues:
            if not isinstance(q, dict):
                continue
            q_name = q.get("name", "Main download queue")
            max_c = q.get("max_concurrent", 4)

            # 1. Start At Check
            if q.get("start_at_enabled", False):
                sched_type = q.get("schedule_type", "daily")
                can_run_today = False
                if sched_type == "once":
                    can_run_today = (q.get("once_date") == current_date_str)
                else:
                    days = q.get("daily_days", [True] * 7)
                    if current_weekday < len(days) and days[current_weekday]:
                        can_run_today = True

                if can_run_today:
                    target_time = q.get("start_at_time", "23:00:00")
                    match_time = (current_time_str == target_time) or (len(target_time) == 5 and current_time_hm == target_time) or (len(target_time) >= 5 and current_time_hm == target_time[:5] and not target_time.endswith(":00") and current_time_str == target_time)
                    trigger_key = f"start_{q_name}_{current_date_str}_{target_time}"
                    if match_time and not getattr(self, "_last_scheduled_minute", {}).get(trigger_key):
                        if not hasattr(self, "_last_scheduled_minute"):
                            self._last_scheduled_minute = {}
                        self._last_scheduled_minute[trigger_key] = True
                        self._start_queue_downloads(q_name, max_concurrent=max_c, show_dialog=False)

            # 2. Stop At Check
            if q.get("stop_at_enabled", False):
                target_stop_time = q.get("stop_at_time", "07:30:00")
                match_stop = (current_time_str == target_stop_time) or (len(target_stop_time) == 5 and current_time_hm == target_stop_time)
                trigger_stop_key = f"stop_{q_name}_{current_date_str}_{target_stop_time}"
                if match_stop and not getattr(self, "_last_scheduled_minute", {}).get(trigger_stop_key):
                    if not hasattr(self, "_last_scheduled_minute"):
                        self._last_scheduled_minute = {}
                    self._last_scheduled_minute[trigger_stop_key] = True
                    self._stop_queue_downloads(q_name)

            # 3. Periodic Sync Check
            if q.get("mode") == "sync" and q.get("sync_interval_enabled", False):
                interval_sec = q.get("sync_hours", 2) * 3600 + q.get("sync_minutes", 0) * 60
                if interval_sec > 0:
                    if not hasattr(self, "_last_sync_times"):
                        self._last_sync_times = {}
                    last_sync = self._last_sync_times.get(q_name, 0)
                    if time.time() - last_sync >= interval_sec:
                        self._last_sync_times[q_name] = time.time()
                        self._start_queue_downloads(q_name, max_concurrent=max_c, show_dialog=False)

    def _check_startup_queues(self):
        """Starts any queues configured to run on application startup."""
        db_queues = get_all_queues()
        queues = db_queues if db_queues else getattr(self, "_queues_data", [])
        for q in queues:
            if isinstance(q, dict) and q.get("start_on_startup", False):
                qname = q.get("name", "Main download queue")
                max_c = q.get("max_concurrent", 4)
                self._start_queue_downloads(qname, max_concurrent=max_c, show_dialog=False)

    def _start_queue_downloads(self, queue_name: str, max_concurrent: int = 4, show_dialog: bool = False):
        """Starts incomplete downloads belonging to the specified queue."""
        active_in_queue = 0
        for r in range(self.download_table.rowCount()):
            item_name = self.download_table.item(r, 0)
            if not item_name:
                continue
            row_q = item_name.data(Qt.ItemDataRole.UserRole + 8) or "Main download queue"
            if row_q != queue_name:
                continue

            status_item = self.download_table.item(r, 2)
            logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
            status_text = status_item.text() if status_item else ""
            is_completed = (logic_status in ["Complete", "Finished"] or status_text in ["Complete", "Finished"] or (item_name.data(Qt.ItemDataRole.UserRole + 11) == "Complete"))
            if is_completed:
                continue

            key = self._get_item_key(item_name)
            if key in self.active_downloads and self._is_download_active(item_name):
                active_in_queue += 1
                continue

            url = item_name.data(Qt.ItemDataRole.UserRole)
            if not url:
                continue

            if active_in_queue < max_concurrent and len(self.active_downloads) < self.MAX_CONCURRENT_DOWNLOADS:
                active_in_queue += 1
                item_name.setData(Qt.ItemDataRole.UserRole + 14, True)  # Mark as active queue batch execution
                filename = item_name.text()
                self._set_status_text(r, "Resuming...", logic_status="Resuming...")
                if status_item:
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Resuming...")
                new_timestamp = str(time.time())
                item_name.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                self._set_timestamp_item(r, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                self._set_row_bold(r, True)

                # Check media vs HTTP
                format_spec = item_name.data(Qt.ItemDataRole.UserRole + 6)
                if format_spec is not None:
                    from core.media_downloader import YtDlpDownloadWorker
                    save_dir = os.path.dirname(item_name.data(Qt.ItemDataRole.UserRole + 1) or "")
                    is_audio_only = bool(item_name.data(Qt.ItemDataRole.UserRole + 7))
                    cookies_browser = item_name.data(Qt.ItemDataRole.UserRole + 9)
                    cookies_file = item_name.data(Qt.ItemDataRole.UserRole + 10)
                    worker = YtDlpDownloadWorker(
                        url=url,
                        row_index=r,
                        save_dir=save_dir,
                        filename=filename,
                        format_spec=format_spec,
                        is_audio_only=is_audio_only,
                        cookies_browser=cookies_browser,
                        cookies_file=cookies_file
                    )
                    self.active_downloads[key] = worker
                    worker.main_progress_signal.connect(lambda _, data, ref=item_name: self.update_download_row(ref, data))
                    worker.finished_signal.connect(lambda _, path, ref=item_name, k=key: self._on_media_download_finished(k, ref, path))
                    self._set_status_text(r, "Downloading...")
                    worker.start()
                else:
                    self._start_download_worker(url, item_name, resume_filename=filename, show_dialog=show_dialog)
            else:
                self._set_status_text(r, "Queued", logic_status="Queued")
                if status_item:
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Queued")

    def _stop_queue_downloads(self, queue_name: str):
        """Pauses/stops active and queued downloads in the specified queue."""
        for r in range(self.download_table.rowCount()):
            item_name = self.download_table.item(r, 0)
            if not item_name:
                continue
            row_q = item_name.data(Qt.ItemDataRole.UserRole + 8) or "Main download queue"
            if row_q != queue_name:
                continue

            status_item = self.download_table.item(r, 2)
            logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
            status_text = status_item.text() if status_item else ""
            is_completed = (
                logic_status in ["Complete", "Finished"] or
                status_text in ["Complete", "Finished"] or
                (item_name.data(Qt.ItemDataRole.UserRole + 11) == "Complete")
            )
            if is_completed:
                continue

            key = self._get_item_key(item_name)
            if key in self.active_downloads:
                dialog = self.active_downloads[key]
                worker = getattr(dialog, 'worker', dialog)
                if worker is not None and hasattr(worker, 'pause'):
                    try:
                        worker.pause()
                    except Exception:
                        pass

            item_name.setData(Qt.ItemDataRole.UserRole + 11, "Paused")
            if status_item:
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
            self._set_status_text(r, "Paused", logic_status="Paused")
            self._set_row_bold(r, False)

    def _queue_action_start(self, queue_name):
        """Starts downloads in the named queue."""
        max_c = 4
        if hasattr(self, "_queues_data"):
            for q in self._queues_data:
                if isinstance(q, dict) and q.get("name") == queue_name:
                    max_c = q.get("max_concurrent", 4)
                    break
        self._start_queue_downloads(queue_name, max_concurrent=max_c, show_dialog=True)

    def _queue_action_stop(self, queue_name):
        """Stops downloads in the named queue."""
        self._stop_queue_downloads(queue_name)

    def _delete_sidebar_queue(self, item):
        """Deletes a queue from the sidebar and from the scheduler if open."""
        queue_name = item.text(0)
        if queue_name in ("Main download queue", "Synchronization queue"):
            return

        parent = item.parent()
        if parent:
            parent.removeChild(item)

        if queue_name in self._sidebar_queue_names:
            self._sidebar_queue_names.remove(queue_name)

        # Remove from persistent queue data
        self._queues_data = [q for q in self._queues_data if q["name"] != queue_name]
        try:
            delete_queue(queue_name)
        except Exception:
            pass

        # Also remove from scheduler if it's open
        if MemoryGuard.is_widget_alive(getattr(self, "_scheduler_dlg", None)):
            for i, q in enumerate(self._scheduler_dlg.queues):
                if q["name"] == queue_name:
                    self._scheduler_dlg._selected_index = -1
                    del self._scheduler_dlg.queues[i]
                    self._scheduler_dlg.queue_list.takeItem(i)
                    break

    def _create_sidebar_queue(self):
        """Creates a new queue and adds it to both sidebar and scheduler."""
        from ui.dialogs.scheduler import _make_default_queue
        base = "Queue"
        existing = set(self._sidebar_queue_names)
        i = 1
        while f"{base} # {i}" in existing:
            i += 1
        name = f"{base} # {i}"

        # Persist into the source-of-truth list
        new_q = _make_default_queue(name)
        self._queues_data.append(new_q)
        try:
            upsert_queue(new_q)
        except Exception:
            pass

        # Add to sidebar
        child = QTreeWidgetItem(self.queues_header, [name])
        child.setIcon(0, get_themed_icon("scheduler"))
        child.setToolTip(0, f"Queue: {name}")
        child.setData(0, Qt.ItemDataRole.UserRole, "queue")
        self._sidebar_queue_names.append(name)

        # Reflect in scheduler dialog if it's open
        if MemoryGuard.is_widget_alive(getattr(self, "_scheduler_dlg", None)):
            self._scheduler_dlg.queues.append(dict(new_q))
            self._scheduler_dlg.queues[-1]["daily_days"] = list(new_q["daily_days"])
            from PyQt6.QtWidgets import QListWidgetItem as QLWI
            self._scheduler_dlg.queue_list.addItem(QLWI(name))
            self._scheduler_dlg.queue_list.setCurrentRow(len(self._scheduler_dlg.queues) - 1)
            self._scheduler_dlg.show()
            self._scheduler_dlg.raise_()
            self._scheduler_dlg.activateWindow()

    def _sync_sidebar_queues(self):
        """Synchronizes the sidebar queue list with the scheduler dialog's queue list."""
        if not MemoryGuard.is_widget_alive(getattr(self, "_scheduler_dlg", None)):
            return

        # Save the dialog's current queue state back into the persistent store
        self._queues_data = [dict(q) for q in self._scheduler_dlg.queues]
        for q in self._queues_data:
            q["daily_days"] = list(q["daily_days"])
        try:
            save_all_queues(self._queues_data)
        except Exception:
            pass

        # Rebuild sidebar from the updated persistent store
        while self.queues_header.childCount() > 0:
            self.queues_header.removeChild(self.queues_header.child(0))
        self._sidebar_queue_names.clear()

        for q in self._queues_data:
            child = QTreeWidgetItem(self.queues_header, [q["name"]])
            child.setIcon(0, get_themed_icon("scheduler"))
            child.setToolTip(0, f"Queue: {q['name']}")
            child.setData(0, Qt.ItemDataRole.UserRole, "queue")
            self._sidebar_queue_names.append(q["name"])

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
                if (not size or size in ["Unknown", "?", "Calculating...", "0 B", "0.00 B"]) and path and os.path.exists(path) and os.path.isfile(path):
                    try:
                        file_sz = os.path.getsize(path)
                        if file_sz > 0:
                            size = format_bytes(file_sz)
                            self._set_sortable_item(row, 1, size, parse_size_to_bytes)
                    except Exception:
                        pass
                # Use standardized internal status if available, otherwise fallback to text
                status_item = self.download_table.item(row, 2)
                internal_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
                display_text = safe_get(2)
                pct_data = status_item.data(Qt.ItemDataRole.UserRole) if status_item else None
                complete_flag = item_name.data(Qt.ItemDataRole.UserRole + 11)
                
                status = internal_status if internal_status else display_text
                
                # Normalize exact 100% or Complete variations to "Complete"
                if status == "Complete" or display_text == "Complete" or complete_flag == "Complete" or "100.00%" in str(status) or "100.00%" in str(display_text):
                    status = "Complete"
                elif status in ["Downloading", "Connecting...", "Pending...", "Resuming...", "Paused", "Cancelled"]:
                    # Verify if file already fully exists on disk without temp/part files
                    if path and os.path.exists(path) and os.path.isfile(path) and not os.path.exists(path + ".aria2") and not os.path.exists(path + ".tmpbdm") and not path.endswith(".part"):
                        file_sz = os.path.getsize(path)
                        parsed_table_sz = parse_size_to_bytes(size)
                        if file_sz > 0 and (parsed_table_sz == 0 or file_sz >= parsed_table_sz):
                            status = "Complete"

                    if status != "Complete":
                        if pct_data and "%" in str(pct_data):
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
                    "last_try": str(last_try_ts),   # Save raw timestamp
                    "date_added": str(date_added_ts), # Save raw timestamp
                    "queue": item_name.data(Qt.ItemDataRole.UserRole + 8) if item_name.data(Qt.ItemDataRole.UserRole + 8) is not None else "Main download queue",
                    "extra_data": {
                        "referer": item_name.data(Qt.ItemDataRole.UserRole + 15) or url
                    }
                }
                downloads.append(dl_data)
            
            save_all_downloads(downloads)
            save_all_queues(self._queues_data)
        except Exception:
            pass

    def load_data(self):
        try:
            downloads = get_all_downloads()
            if not downloads:
                return
            
            self.download_table.setSortingEnabled(False)
                
            for d in downloads:
                row = self.download_table.rowCount()
                self.download_table.insertRow(row)
                
                filename = d.get("filename", "Unknown")
                item_name = QTableWidgetItem(filename)
                item_name.setToolTip(filename)
                
                # Store raw timestamps in item data
                date_added_ts = d.get("date_added", str(time.time()))
                last_try_ts = d.get("last_try", date_added_ts)
                
                item_name.setData(Qt.ItemDataRole.UserRole, d.get("url", ""))
                item_name.setData(Qt.ItemDataRole.UserRole + 1, d.get("path", ""))
                item_name.setData(Qt.ItemDataRole.UserRole + 2, last_try_ts)   # Raw Last Try TS
                item_name.setData(Qt.ItemDataRole.UserRole + 3, date_added_ts) # Raw Date Added TS
                item_name.setData(Qt.ItemDataRole.UserRole + 8, d.get("queue", "Main download queue") if d.get("queue") is not None else "Main download queue")  # Queue
                extra = d.get("extra_data", {})
                item_name.setData(Qt.ItemDataRole.UserRole + 15, extra.get("referer", d.get("url", "")) if isinstance(extra, dict) else d.get("url", ""))
                item_name.setIcon(get_file_icon(filename))
                
                self.download_table.setItem(row, 0, item_name)
                
                # Col 1: Size
                file_path = d.get("path", "")
                saved_size = d.get("size", "")
                if (not saved_size or saved_size in ["Unknown", "?", "Calculating...", "0 B", "0.00 B"]) and file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                    try:
                        file_sz = os.path.getsize(file_path)
                        if file_sz > 0:
                            saved_size = format_bytes(file_sz)
                    except Exception:
                        pass
                self._set_sortable_item(row, 1, saved_size if saved_size else "Unknown", parse_size_to_bytes)
                
                # Col 2: Status (Sanitize: show percentage, never "Paused")
                raw_status = d.get("status", "0.00%")
                display_status = raw_status
                
                # Determine internal state based on status text and file existence
                is_actually_complete = False
                if raw_status == "Complete" or "100.00%" in str(raw_status):
                    is_actually_complete = True
                elif file_path and os.path.exists(file_path) and os.path.isfile(file_path) and not os.path.exists(file_path + ".aria2") and not os.path.exists(file_path + ".tmpbdm") and not file_path.endswith(".part"):
                    file_sz = os.path.getsize(file_path)
                    expected_sz = parse_size_to_bytes(d.get("size", "0"))
                    if file_sz > 0 and (expected_sz == 0 or file_sz >= expected_sz):
                        is_actually_complete = True

                if is_actually_complete:
                    display_status = "Complete"
                    internal_state = "Complete"
                    item_name.setData(Qt.ItemDataRole.UserRole + 11, "Complete")
                elif "%" in raw_status:
                    display_status = raw_status
                    internal_state = "Paused"
                elif raw_status in ["Paused", "Cancelled", "Error"]:
                    display_status = "0.00%" if raw_status != "Error" else "Error"
                    internal_state = raw_status
                else:
                    internal_state = raw_status

                status_item = QTableWidgetItem(display_status)
                # Store the standardized internal state in UserRole + 1
                status_item.setData(Qt.ItemDataRole.UserRole + 1, internal_state)
                # Also restore the raw percentage string in UserRole for resume logic
                if "%" in raw_status:
                    status_item.setData(Qt.ItemDataRole.UserRole, raw_status)
                
                # Apply bold tabular numbers font
                self._set_status_text(row, display_status)
                
                # Re-fetch status_item because _set_status_text might have created/updated it
                status_item = self.download_table.item(row, 2)
                status_item.setData(Qt.ItemDataRole.UserRole + 1, internal_state)
                if "%" in raw_status:
                    status_item.setData(Qt.ItemDataRole.UserRole, raw_status)
                self._set_sortable_item(row, 3, d.get("time_left", ""), parse_time_to_sec)
                self._set_sortable_item(row, 4, d.get("rate", ""), parse_size_to_bytes)
                
                # Display formatted timestamps (Last Try uses 5 min/300s threshold, Date Added uses 30s)
                self._set_timestamp_item(row, 5, format_timestamp_relative(last_try_ts, max_relative_seconds=300))
                self._set_timestamp_item(row, 6, format_timestamp_relative(date_added_ts, max_relative_seconds=30))
                self._set_row_bold(row, self._is_row_active(row))

            self.download_table.setSortingEnabled(True)
            self.update_status_bar_items()
            
        except Exception:
            pass

    def _set_sortable_item(self, row, col, text, parser_func):
        item = self.download_table.item(row, col)
        created = False
        if not item:
            item = SortableTableWidgetItem(text)
            self.download_table.setItem(row, col, item)
            created = True
        elif item.text() != text:
            item.setText(text)
            
        # Set descriptive tooltips based on column
        col_names = {1: "Size", 3: "Time Left", 4: "Transfer Rate"}
        if col in col_names:
            item.setToolTip(f"{col_names[col]}: {text}" if text else f"{col_names[col]}: N/A")

    def _get_item_key(self, item):
        """Returns a persistent, unique identifier for a download table item."""
        if item is None:
            return None
        # Always check column 0 item if this is from another column
        if hasattr(item, "column") and item.column() != 0 and hasattr(self, "download_table"):
            r = item.row()
            if r >= 0:
                item = self.download_table.item(r, 0)
                if not item:
                    return None
        uid = item.data(Qt.ItemDataRole.UserRole + 12)
        if not uid:
            import uuid
            uid = str(uuid.uuid4())
            item.setData(Qt.ItemDataRole.UserRole + 12, uid)
        return uid

    def _is_download_active(self, item):
        """Checks if a download item is actively downloading (not paused, cancelled, or finished)."""
        if item is None:
            return False
        key = self._get_item_key(item)
        if not key or key not in getattr(self, "active_downloads", {}):
            return False
        entry = self.active_downloads.get(key)
        if entry is not None:
            try:
                worker = getattr(entry, "worker", entry)
                if getattr(worker, "is_paused", False) or getattr(worker, "is_pause_requested", False):
                    return False
                return True
            except (RuntimeError, AttributeError, Exception):
                pass
        try:
            row = self.download_table.row(item)
            if row >= 0:
                status_item = self.download_table.item(row, 2)
                if status_item:
                    logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
                    if logic_status in ["Paused", "Cancelled", "Error", "Complete"]:
                        return False
        except (RuntimeError, Exception):
            return False
        return True

    def _is_row_active(self, row: int) -> bool:
        """Determines if a table row represents an actively running download."""
        if row < 0 or row >= self.download_table.rowCount():
            return False
        item_0 = self.download_table.item(row, 0)
        return self._is_download_active(item_0)

    def _set_row_bold(self, row: int, is_bold: bool):
        """Sets bold/normal font weight for all items in a table row based on active state."""
        if getattr(self, "table_style", "classic") == "modern":
            return
        if row < 0 or row >= self.download_table.rowCount():
            return
        changed = False
        for col in range(self.download_table.columnCount()):
            item = self.download_table.item(row, col)
            if item:
                font = item.font()
                if font.bold() != is_bold:
                    font.setBold(is_bold)
                    font.setFeature(QFont.Tag.fromString('tnum'), 1)
                    item.setFont(font)
                    changed = True
        if changed and hasattr(self, "download_table"):
            row_top = self.download_table.rowViewportPosition(row)
            row_height = self.download_table.rowHeight(row)
            if row_height > 0:
                self.download_table.viewport().update(0, row_top, self.download_table.viewport().width(), row_height)

    def _set_sortable_item(self, row, col, text, parser_func):
        item = self.download_table.item(row, col)
        created = False
        if not item:
            item = SortableTableWidgetItem(text)
            font = QFont(QApplication.font())
            font.setFeature(QFont.Tag.fromString('tnum'), 1)
            item.setFont(font)
            self.download_table.setItem(row, col, item)
            created = True
        elif item.text() != text:
            item.setText(text)
            
        # Set descriptive tooltips based on column
        col_names = {1: "Size", 3: "Time Left", 4: "Transfer Rate"}
        if col in col_names:
            item.setToolTip(f"{col_names[col]}: {text}" if text else f"{col_names[col]}: N/A")
            
        raw_val = parser_func(text)
        if item.data(Qt.ItemDataRole.UserRole) != raw_val:
            item.setData(Qt.ItemDataRole.UserRole, raw_val)

    def _set_status_text(self, row, text, logic_status=None):
        item = self.download_table.item(row, 2)
        created = False
        if not item:
            item = QTableWidgetItem(text)
            font = QFont(QApplication.font())
            font.setFeature(QFont.Tag.fromString('tnum'), 1)
            item.setFont(font)
            self.download_table.setItem(row, 2, item)
            created = True
        elif item.text() != text:
            item.setText(text)
            
        item.setToolTip(f"Status: {text}" if text else "Status: N/A")
        if logic_status is not None:
            item.setData(Qt.ItemDataRole.UserRole + 1, logic_status)
        elif text in ["Paused", "Complete", "Finished", "Error", "Cancelled", "Connecting...", "Downloading", "Resuming...", "Pending...", "Queued"]:
            item.setData(Qt.ItemDataRole.UserRole + 1, text)

    def _set_timestamp_item(self, row, col, text):
        item = self.download_table.item(row, col)
        if not item:
            item = QTableWidgetItem(text)
            font = QFont(QApplication.font())
            font.setFeature(QFont.Tag.fromString('tnum'), 1)
            item.setFont(font)
            self.download_table.setItem(row, col, item)
        elif item.text() != text:
            item.setText(text)
            
        col_name = "Last Attempt" if col == 5 else "Date Added"
        item.setToolTip(f"{col_name}: {text}" if text else f"{col_name}: N/A")
        return item

    def add_new_download(self, url, category="General", save_path=""):
        if url:
            self.start_download(url, custom_save_dir=save_path if save_path else None)

    def get_qml_downloads_data(self):
        data = []
        for r in range(self.download_table.rowCount()):
            item0 = self.download_table.item(r, 0)
            item1 = self.download_table.item(r, 1)
            item2 = self.download_table.item(r, 2)
            item3 = self.download_table.item(r, 3)
            item4 = self.download_table.item(r, 4)
            item5 = self.download_table.item(r, 5)
            item6 = self.download_table.item(r, 6)
            if item0:
                data.append({
                    "filename": item0.text(),
                    "url": item0.data(Qt.ItemDataRole.UserRole) or "",
                    "referer": item0.data(Qt.ItemDataRole.UserRole + 15) or item0.data(Qt.ItemDataRole.UserRole) or "",
                    "path": item0.data(Qt.ItemDataRole.UserRole + 1) or "",
                    "size": item1.text() if item1 else "",
                    "status": item2.text() if item2 else "",
                    "time_left": item3.text() if item3 else "",
                    "rate": item4.text() if item4 else "",
                    "last_try": item5.text() if item5 else "",
                    "date_added": item6.text() if item6 else "",
                    "category": get_category_for_filename(item0.text())
                })
        return data

    def qml_pause_download(self, index):
        if 0 <= index < self.download_table.rowCount():
            item = self.download_table.item(index, 0)
            if item:
                key = self._get_item_key(item)
                if key in self.active_downloads:
                    self._stop_worker_entry(self.active_downloads[key])

    def qml_resume_download(self, index):
        if 0 <= index < self.download_table.rowCount():
            item = self.download_table.item(index, 0)
            if item:
                url = item.data(Qt.ItemDataRole.UserRole)
                if url:
                    self._start_download_worker(url, item, resume_filename=item.text())

    def qml_delete_download(self, index):
        if 0 <= index < self.download_table.rowCount():
            self.download_table.removeRow(index)

    def qml_move_download(self, index):
        if 0 <= index < self.download_table.rowCount():
            item = self.download_table.item(index, 0)
            if item:
                self.ctx_move(item)

    def qml_rename_download(self, index):
        if 0 <= index < self.download_table.rowCount():
            item = self.download_table.item(index, 0)
            if item:
                self.ctx_rename(item)

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
                "start_minimized": getattr(self, "start_minimized_on_autostart", False),
                "ui_scale": getattr(self, "settings", {}).get("ui_scale", "100%"),
                "theme": getattr(self, "settings", {}).get("theme", "BDM Dark (Default)"),
                "accent": getattr(self, "settings", {}).get("accent", "BDM (Default)"),
                "icon_theme": getattr(self, "settings", {}).get("icon_theme", "BDM Auto (Default)"),
                "tray_icon": getattr(self, "settings", {}).get("tray_icon", "App Icon (Default)"),
                "table_style": getattr(self, "table_style", "classic"),
                "system_notifications": getattr(self, "system_notifications", False) or (isinstance(getattr(self, "settings", {}), dict) and self.settings.get("system_notifications", False)),
                "show_status_bar": not self.statusBar().isHidden() if self.statusBar() else True,
                "show_toolbar": not self.findChild(QToolBar, "MainToolbar").isHidden() if self.findChild(QToolBar, "MainToolbar") else True,
                "hide_categories": self.category_tree.isHidden() if hasattr(self, "category_tree") and self.category_tree else False,
                "silent_download": getattr(self, "settings", {}).get("silent_download", False),
                "show_start_dialog": getattr(self, "settings", {}).get("show_start_dialog", True),
                "show_progress_dialog": getattr(self, "settings", {}).get("show_progress_dialog", True),
                "show_complete_dialog": getattr(self, "settings", {}).get("show_complete_dialog", True),
                "show_queue_complete_dialog": getattr(self, "settings", {}).get("show_queue_complete_dialog", False)
            }
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def apply_appearance_setting(self, theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None):
        if getattr(self, "_is_applying_theme", False):
            return
        self._is_applying_theme = True
        try:
            if not hasattr(self, "settings") or not isinstance(self.settings, dict):
                self.settings = {}
            self.settings["theme"] = theme_name
            self.settings["accent"] = accent_name
            self.settings["icon_theme"] = icon_theme_name
            self.settings["tray_icon"] = tray_icon_name
            apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name)
            self.save_settings()
            self.refresh_theme_ui()
        finally:
            self._is_applying_theme = False

    def preview_appearance(self, theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None):
        if getattr(self, "_is_applying_theme", False):
            return
        self._is_applying_theme = True
        try:
            apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name)
            self.refresh_theme_ui()
        finally:
            self._is_applying_theme = False

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "timestamp_timer") and self.timestamp_timer.isActive():
            self.timestamp_timer.stop()
        if hasattr(self, "status_bar_timer") and self.status_bar_timer.isActive():
            self.status_bar_timer.stop()
        MemoryGuard.clean_and_trim()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "timestamp_timer") and not self.timestamp_timer.isActive():
            self.timestamp_timer.start(10000)
        if hasattr(self, "status_bar_timer") and not self.status_bar_timer.isActive():
            self.status_bar_timer.start(1000)
        self._flush_pending_tray_updates()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event and event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                if hasattr(self, "timestamp_timer") and self.timestamp_timer.isActive():
                    self.timestamp_timer.stop()
                if hasattr(self, "status_bar_timer") and self.status_bar_timer.isActive():
                    self.status_bar_timer.stop()
                MemoryGuard.clean_and_trim()
            elif not self.isMinimized() and self.isVisible():
                if hasattr(self, "timestamp_timer") and not self.timestamp_timer.isActive():
                    self.timestamp_timer.start(10000)
                if hasattr(self, "status_bar_timer") and not self.status_bar_timer.isActive():
                    self.status_bar_timer.start(1000)
                self._flush_pending_tray_updates()

    def _flush_pending_tray_updates(self):
        if not getattr(self, "_pending_tray_updates", None):
            return
        updates = list(self._pending_tray_updates.values())
        self._pending_tray_updates.clear()
        
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            for item_ref, data in updates:
                try:
                    self._apply_download_row_data(item_ref, data)
                except Exception:
                    pass
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self._notify_views_changed()
            self.update_status_bar_speed()
            self.download_table.viewport().update()

    def on_system_theme_changed(self, *args):
        if getattr(self, "_is_applying_theme", False):
            return
        current_theme = getattr(self, "settings", {}).get("theme", "BDM Dark (Default)")
        if str(current_theme).lower() in ("bdm auto", "bdmauto", "automatic", "auto", "system"):
            self.apply_theme_setting(current_theme)

    def apply_theme_setting(self, theme_name):
        accent_name = getattr(self, "settings", {}).get("accent", "BDM (Default)")
        icon_theme_name = getattr(self, "settings", {}).get("icon_theme", "BDM Auto (Default)")
        tray_icon_name = getattr(self, "settings", {}).get("tray_icon", "App Icon (Default)")
        self.apply_appearance_setting(theme_name, accent_name, icon_theme_name, tray_icon_name)

    def refresh_theme_ui(self):
        app = QApplication.instance()
        if app:
            self.setPalette(app.palette())

        # Refresh category tree style & icons
        if hasattr(self, "category_tree"):
            self.style().unpolish(self.category_tree)
            self.style().polish(self.category_tree)
            self.category_tree.update()
            if hasattr(self, "all_downloads_header") and self.all_downloads_header:
                self.all_downloads_header.setIcon(0, get_themed_icon("all_downloads"))
                cat_icons = {
                    "Compressed": get_themed_icon("compressed"),
                    "Documents": get_themed_icon("documents"),
                    "Music": get_themed_icon("music"),
                    "Programs": get_themed_icon("programs"),
                    "Video": get_themed_icon("video")
                }
                for i in range(self.all_downloads_header.childCount()):
                    child = self.all_downloads_header.child(i)
                    if child and child.text(0) in cat_icons:
                        child.setIcon(0, cat_icons[child.text(0)])

            if hasattr(self, "item_unfinished") and self.item_unfinished:
                self.item_unfinished.setIcon(0, get_themed_icon("unfinished"))
            if hasattr(self, "item_finished") and self.item_finished:
                self.item_finished.setIcon(0, get_themed_icon("finished"))

            # Refresh Queues section icons
            if hasattr(self, "queues_header") and self.queues_header:
                self.queues_header.setIcon(0, get_themed_icon("scheduler"))
                for i in range(self.queues_header.childCount()):
                    child = self.queues_header.child(i)
                    if child:
                        child.setIcon(0, get_themed_icon("scheduler"))

        # Refresh action icons
        action_icon_map = {
            "action_add_url": ("add_url", False),
            "action_paste_url": ("add_url", False),
            "action_exit": ("exit", False),
            "action_stop": ("stop", True),
            "action_stop_all": ("stop_all", True),
            "action_resume": ("resume", True),
            "action_download_now": ("resume", True),
            "action_redownload": ("unfinished", True),
            "action_delete": ("delete", True),
            "action_clear": ("clear_completed", False),
            "action_options": ("options", False),
            "action_open_folder": ("open_folder", False),
            "action_scheduler": ("scheduler", False),
            "action_media_downloader": ("media_downloader", False)
        }
        _fi = make_faded_icon
        for attr, (icon_name, use_fi) in action_icon_map.items():
            if hasattr(self, attr):
                ic = get_themed_icon(icon_name)
                if use_fi:
                    ic = _fi(ic)
                getattr(self, attr).setIcon(ic)

        if hasattr(self, "update_tray_action"):
            self.update_tray_action()

        if hasattr(self, "tray_icon") and self.tray_icon:
            tray_ic = get_themed_tray_icon()
            if not tray_ic.isNull():
                self.tray_icon.setIcon(tray_ic)

        if hasattr(self, "toolbar_hover_filter") and self.toolbar_hover_filter:
            self.toolbar_hover_filter.clear_cache()

        toolbar = self.findChild(QToolBar, "MainToolbar")
        if toolbar and hasattr(self, "get_toolbar_stylesheet"):
            toolbar.setStyleSheet(self.get_toolbar_stylesheet())

        app = QApplication.instance()
        if app:
            self.setPalette(app.palette())

        mb = self.menuBar()
        if mb and app:
            mb.setPalette(app.palette())
            app.style().unpolish(mb)
            app.style().polish(mb)
            mb.update()
            for m in mb.findChildren(QMenu):
                m.setPalette(app.palette())
                app.style().unpolish(m)
                app.style().polish(m)
                m.update()

        sb = self.statusBar()
        if sb and app:
            sb.setPalette(app.palette())
            app.style().unpolish(sb)
            app.style().polish(sb)
            sb.update()

        self.update_status_bar()
        self.update()
        self.repaint()

    def load_settings(self):
        settings = {
            "theme": "BDM Dark (Default)",
            "accent": "BDM (Default)",
            "icon_theme": "BDM Auto (Default)",
            "tray_icon": "App Icon (Default)"
        }
        config_dir = get_config_dir()
        path = os.path.join(config_dir, "settings.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    file_settings = json.load(f)
                    settings.update(file_settings)
                    if "geometry" in settings:
                        self.restoreGeometry(QByteArray.fromHex(settings["geometry"].encode()))
                    if "windowState" in settings:
                        self.restoreState(QByteArray.fromHex(settings["windowState"].encode()))
                    
                    self.start_minimized_on_autostart = settings.get("start_minimized", False)

                    header = self.download_table.horizontalHeader()
                    if "column_data" in settings:
                        for i, col in enumerate(settings["column_data"]):
                            logical_idx = col["logical_index"]
                            header.moveSection(header.visualIndex(logical_idx), i)
                            self.download_table.setColumnHidden(logical_idx, not col["visible"])
                            self.download_table.setColumnWidth(logical_idx, col["width"])
                    elif "column_widths" in settings:
                        for i, width in enumerate(settings["column_widths"]):
                            self.download_table.setColumnWidth(i, width)
            except Exception:
                pass

        settings["theme"] = normalize_theme_name(settings.get("theme"))
        settings["accent"] = normalize_accent_name(settings.get("accent"))
        settings["icon_theme"] = normalize_icon_theme_name(settings.get("icon_theme"))
        settings["tray_icon"] = normalize_tray_icon_name(settings.get("tray_icon"))
        settings["table_style"] = settings.get("table_style", "classic")
        self.system_notifications = settings.get("system_notifications", False)
        settings["system_notifications"] = self.system_notifications
        settings["silent_download"] = settings.get("silent_download", False)
        settings["show_start_dialog"] = settings.get("show_start_dialog", True)
        settings["show_progress_dialog"] = settings.get("show_progress_dialog", True)
        settings["show_complete_dialog"] = settings.get("show_complete_dialog", True)
        settings["show_queue_complete_dialog"] = settings.get("show_queue_complete_dialog", False)

        apply_app_theme(
            settings["theme"],
            settings["accent"],
            settings["icon_theme"],
            settings["tray_icon"]
        )

        if hasattr(self, "tray_icon") and self.tray_icon:
            tray_ic = get_themed_tray_icon(settings["tray_icon"])
            if not tray_ic.isNull():
                self.tray_icon.setIcon(tray_ic)

        self.set_table_style(settings["table_style"], initial=True)

        show_status_bar = settings.get("show_status_bar", True)
        self.toggle_status_bar(show_status_bar, save=False)

        show_toolbar = settings.get("show_toolbar", True)
        self._on_toolbar_toggled(show_toolbar, save=False)

        hide_categories = settings.get("hide_categories", False)
        self.toggle_hide_categories(hide_categories, save=False)
        return settings

    def set_table_style(self, style_name: str, initial=False):
        """Switches between Classic and Modern table presentation styles."""
        style_name = (style_name or "classic").lower()
        self.table_style = style_name

        if hasattr(self, "action_table_style_classic"):
            self.action_table_style_classic.setChecked(style_name == "classic")
        if hasattr(self, "action_table_style_modern"):
            self.action_table_style_modern.setChecked(style_name == "modern")

        if style_name == "modern":
            from ui.delegates import ModernTableDelegate
            if not hasattr(self, "_modern_delegate") or self._modern_delegate is None:
                self._modern_delegate = ModernTableDelegate(self.download_table)
            self.download_table.setItemDelegate(self._modern_delegate)
            self.download_table.verticalHeader().setDefaultSectionSize(50)
            for r in range(self.download_table.rowCount()):
                self.download_table.setRowHeight(r, 50)
        else:
            # Classic style - exact unmodified original
            if hasattr(self, "_default_table_delegate") and self._default_table_delegate:
                self.download_table.setItemDelegate(self._default_table_delegate)
            self.download_table.verticalHeader().setDefaultSectionSize(26)
            for r in range(self.download_table.rowCount()):
                self.download_table.setRowHeight(r, 26)

        self.download_table.viewport().update()
        if not initial and hasattr(self, "save_settings"):
            self.save_settings()

    def show_header_context_menu(self, pos):
        menu = QMenu(self)
        header = self.download_table.horizontalHeader()

        # Add toggle action for each column in visual order
        for visual_idx in range(self.download_table.columnCount()):
            logical_idx = header.logicalIndex(visual_idx)
            header_item = self.download_table.horizontalHeaderItem(logical_idx)
            col_name = header_item.text() if header_item else f"Column {logical_idx + 1}"
            is_visible = not self.download_table.isColumnHidden(logical_idx)

            act = QAction(col_name, menu)
            act.setCheckable(True)
            act.setChecked(is_visible)

            def make_toggle(l_idx=logical_idx):
                return lambda checked: self.toggle_column_visibility(l_idx, checked)

            act.triggered.connect(make_toggle(logical_idx))
            menu.addAction(act)

        menu.addSeparator()
        act_columns = QAction("Columns...", self)
        act_columns.triggered.connect(self.open_column_dialog)
        menu.addAction(act_columns)
        menu.exec(self.download_table.horizontalHeader().viewport().mapToGlobal(pos))

    def toggle_column_visibility(self, logical_idx: int, visible: bool):
        if not visible:
            visible_count = sum(
                1 for i in range(self.download_table.columnCount())
                if not self.download_table.isColumnHidden(i) and i != logical_idx
            )
            if visible_count == 0:
                return
        self.download_table.setColumnHidden(logical_idx, not visible)
        self.save_settings()

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
        dlg.deleteLater()

    def apply_column_settings(self, data):
        header = self.download_table.horizontalHeader()
        for i, col in enumerate(data):
            logical_idx = col["logical_index"]
            header.moveSection(header.visualIndex(logical_idx), i)
            self.download_table.setColumnHidden(logical_idx, not col["visible"])
            self.download_table.setColumnWidth(logical_idx, col["width"])

    def _on_table_cell_double_clicked(self, row: int, column: int):
        """Restores progress dialog on double click if download is active, or opens file if complete."""
        if row < 0 or row >= self.download_table.rowCount():
            return
        item_0 = self.download_table.item(row, 0)
        if not item_0:
            return

        if self._is_download_active(item_0):
            self.show_download_progress_dialog(item_0)
        else:
            status_item = self.download_table.item(row, 2)
            logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
            status_text = status_item.text() if status_item else ""
            is_completed = (logic_status in ["Complete", "Finished"] or status_text in ["Complete", "Finished"] or (item_0.data(Qt.ItemDataRole.UserRole + 11) == "Complete"))
            if is_completed:
                path = item_0.data(Qt.ItemDataRole.UserRole + 1)
                if path and os.path.exists(path):
                    open_file_generic(path)
                else:
                    self.ctx_properties(item_0)
            elif logic_status in ["Paused", "Cancelled", "Error"]:
                self.resume_selected_download()

    def show_context_menu(self, pos):
        item = self.download_table.itemAt(pos)
        if not item: return

        selected_rows = set(it.row() for it in self.download_table.selectedItems())
        if item.row() not in selected_rows:
            self.download_table.selectRow(item.row())
        
        row_index = item.row()
        item_0 = self.download_table.item(row_index, 0)
        
        status_item = self.download_table.item(row_index, 2)
        logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
        status_text = status_item.text() if status_item else ""
        
        is_completed = (logic_status in ["Complete", "Finished"] or status_text in ["Complete", "Finished"] or (item_0.data(Qt.ItemDataRole.UserRole + 11) == "Complete"))
        is_active = self._is_download_active(item_0)
        is_pausable = not is_completed and is_active
        is_resumable = not is_completed and not is_active

        menu = QMenu(self)
        
        _fi = make_faded_icon

        act_open     = QAction(_fi(get_themed_icon("documents")),   "Open",             self)
        act_open_with= QAction(_fi(get_themed_icon("documents")),   "Open with...",     self)
        act_open_folder = QAction(get_themed_icon("open_folder"),   "Open folder",      self)
        act_move     = QAction(_fi(get_themed_icon("open_folder")), "Move...",           self)
        act_rename   = QAction(_fi(get_themed_icon("documents")),   "Rename...",         self)

        act_move.setEnabled(is_completed)
        act_rename.setEnabled(is_completed)
        act_open.setEnabled(is_completed)
        act_open_with.setEnabled(is_completed)

        menu.addActions([act_open, act_open_with, act_open_folder, act_move, act_rename])
        menu.addSeparator()

        # Enhanced State Logic for Context Menu
        act_stop = QAction(_fi(get_themed_icon("stop")),   "Stop/Pause Download", self)
        act_stop.triggered.connect(self.stop_selected_download)
        act_stop.setEnabled(is_pausable)

        act_resume = QAction(_fi(get_themed_icon("resume")), "Resume download", self)
        act_resume.triggered.connect(self.resume_selected_download)
        act_resume.setEnabled(is_resumable)

        # Check if progress dialog is currently visible or hidden
        is_progress_hidden = True
        key = self._get_item_key(item_0)
        if key and key in getattr(self, "active_downloads", {}):
            entry = self.active_downloads.get(key)
            if isinstance(entry, DownloadProgressDialog) and MemoryGuard.is_widget_alive(entry):
                if entry.isVisible() and not entry.isMinimized() and not entry.isHidden():
                    is_progress_hidden = False
        elif not is_active:
            is_progress_hidden = False

        act_show_progress = QAction(_fi(get_themed_icon("resume")), "Show progress window", self)
        act_show_progress.triggered.connect(lambda _, it=item_0: self.ctx_show_progress_dialog(it))
        act_show_progress.setEnabled(bool(is_active and is_progress_hidden))
        
        menu.addActions([act_resume, act_stop, act_show_progress])
        menu.addSeparator()

        act_redownload = QAction(get_themed_icon("unfinished"), "Redownload", self)
        act_refresh = QAction(get_themed_icon("clear_completed"), "Refresh download address", self)
        menu.addActions([act_redownload, act_refresh])
        menu.addSeparator()
        
        act_delete = QAction(get_themed_icon("delete"), "Delete", self)
        act_delete.triggered.connect(self.delete_selected_download)
        menu.addAction(act_delete)
        menu.addSeparator()

        # Queue Management: Move to queue & Delete from queue (Below Delete, Above Properties)
        menu_queue = menu.addMenu(get_themed_icon("scheduler"), "Move to queue")
        
        existing_queues = []
        if hasattr(self, "_queues_data") and self._queues_data:
            for q in self._queues_data:
                qname = q.get("name") if isinstance(q, dict) else str(q)
                if qname and qname not in existing_queues:
                    existing_queues.append(qname)
        if "Main download queue" not in existing_queues:
            existing_queues.insert(0, "Main download queue")
        if "Synchronization queue" not in existing_queues:
            existing_queues.append("Synchronization queue")

        current_item_queue = item_0.data(Qt.ItemDataRole.UserRole + 8) or "Main download queue"

        for qname in existing_queues:
            act_q = menu_queue.addAction(qname)
            if qname == current_item_queue:
                act_q.setCheckable(True)
                act_q.setChecked(True)
            act_q.triggered.connect(lambda checked=False, qn=qname: self._move_selected_to_queue(qn))

        menu_queue.addSeparator()
        act_create_queue = menu_queue.addAction(get_themed_icon("add_url"), "Create new queue...")
        act_create_queue.triggered.connect(self._create_new_queue_and_move_selected)

        act_del_from_queue = QAction(get_themed_icon("clear"), "Delete from queue", self)
        act_del_from_queue.triggered.connect(self._delete_selected_from_queue)
        act_del_from_queue.setEnabled(bool(item_0.data(Qt.ItemDataRole.UserRole + 8)))
        menu.addAction(act_del_from_queue)
        menu.addSeparator()
        
        act_props = QAction(get_themed_icon("options"), "Properties", self)
        menu.addAction(act_props)

        act_open.triggered.connect(lambda: self.ctx_open_file(item))
        act_open_with.triggered.connect(lambda: self.ctx_open_with(item))
        act_open_folder.triggered.connect(lambda: self.ctx_open_folder(item))
        act_move.triggered.connect(lambda: self.ctx_move(item))
        act_rename.triggered.connect(lambda: self.ctx_rename(item))
        act_redownload.triggered.connect(lambda: self.ctx_redownload(item))
        act_refresh.triggered.connect(lambda: self.ctx_refresh_address(item))
        act_props.triggered.connect(lambda: self.ctx_properties(item))

        menu.exec(self.download_table.viewport().mapToGlobal(pos))

    def ctx_show_progress_dialog(self, item):
        if not item:
            return
        row = item.row() if hasattr(item, "row") else -1
        if row >= 0:
            item_0 = self.download_table.item(row, 0)
            if item_0:
                self.show_download_progress_dialog(item_0)
                return
        self.show_download_progress_dialog(item)

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
        
        open_with(path)

    def ctx_open_folder(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        show_in_folder(path)

    def open_downloads_folder_generic(self):
        path = get_user_downloads_dir()
        show_in_folder(path)

    def ctx_move(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        old_path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "Error", "File not found to move.")
            return

        filename = os.path.basename(old_path)
        folder = os.path.dirname(old_path)

        portal_fn = _resolve_symbol("choose_portal_save_path", choose_portal_save_path)
        new_path = portal_fn("Move File", filename, folder)

        if new_path and new_path != old_path:
            try:
                shutil.move(old_path, new_path)
                new_filename = os.path.basename(new_path)
                item_0.setText(new_filename)
                item_0.setToolTip(new_filename)
                item_0.setData(Qt.ItemDataRole.UserRole + 1, new_path)
                self.save_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to move file: {e}")

    def ctx_rename(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        old_path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "Error", "File not found to rename.")
            return

        folder = os.path.dirname(old_path)
        old_filename = os.path.basename(old_path)

        rename_dlg_cls = _resolve_symbol("RenameDialog", RenameDialog)
        dialog = rename_dlg_cls(old_filename, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_filename = dialog.get_filename()

            if new_filename and new_filename != old_filename:
                new_path = os.path.join(folder, new_filename)

                if os.path.exists(new_path):
                    QMessageBox.warning(self, "Error", f"A file named '{new_filename}' already exists in this directory.")
                    return

                try:
                    shutil.move(old_path, new_path)
                    item_0.setText(new_filename)
                    item_0.setToolTip(new_filename)
                    item_0.setData(Qt.ItemDataRole.UserRole + 1, new_path)
                    self.save_data()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to rename file: {e}")

    def ctx_redownload(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        url = item_0.data(Qt.ItemDataRole.UserRole)
        
        # Stop any active download for this item first
        key = self._get_item_key(item_0)
        if key in self.active_downloads:
            dialog = self.active_downloads.pop(key, None)
            self._stop_worker_entry(dialog)
            
        if path and os.path.exists(path):
            try: os.remove(path)
            except: pass
        if path and os.path.exists(path + ".tmpbdm"):
            try: os.remove(path + ".tmpbdm")
            except: pass
        if path and os.path.exists(path + ".aria2"):
            try: os.remove(path + ".aria2")
            except: pass
        
        # Clear completed flag & reset status metadata
        item_0.setData(Qt.ItemDataRole.UserRole + 11, None)
        self._set_status_text(row, "Pending...")
        status_item = self.download_table.item(row, 2)
        if status_item:
            status_item.setData(Qt.ItemDataRole.UserRole, None)
            status_item.setData(Qt.ItemDataRole.UserRole + 1, "Pending...")
        
        self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        self._set_row_bold(row, True)
        
        # Update last try timestamp immediately before restarting
        new_timestamp = str(time.time())
        item_0.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
        self._set_timestamp_item(row, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))

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
            "url": item_0.data(Qt.ItemDataRole.UserRole) or "",
            "referer": item_0.data(Qt.ItemDataRole.UserRole + 15) or item_0.data(Qt.ItemDataRole.UserRole) or "",
            "path": item_0.data(Qt.ItemDataRole.UserRole + 1) or "",
            "filename": item_0.text(),
            "status": self.download_table.item(row, 2).text(),
            "size": self.download_table.item(row, 1).text(),
            "date_added": format_timestamp_relative(item_0.data(Qt.ItemDataRole.UserRole + 3), max_relative_seconds=0), # Force full time for properties
            "last_try": format_timestamp_relative(item_0.data(Qt.ItemDataRole.UserRole + 2), max_relative_seconds=0) # Force full time for properties
        }
        # Keep reference
        self._prop_dlg = PropertiesDialog(data, self)
        self._prop_dlg.show()

    def _move_selected_to_queue(self, queue_name: str):
        """Assigns selected download items to the specified queue."""
        selected_rows = set(it.row() for it in self.download_table.selectedItems())
        if not selected_rows:
            return
        for r in selected_rows:
            item_0 = self.download_table.item(r, 0)
            if item_0:
                item_0.setData(Qt.ItemDataRole.UserRole + 8, queue_name)
        self.save_data()
        current_cat = self.category_tree.currentItem()
        if current_cat:
            self.filter_downloads(current_cat, 0)

    def _delete_selected_from_queue(self):
        """Removes selected download items from any queue."""
        selected_rows = set(it.row() for it in self.download_table.selectedItems())
        if not selected_rows:
            return
        for r in selected_rows:
            item_0 = self.download_table.item(r, 0)
            if item_0:
                item_0.setData(Qt.ItemDataRole.UserRole + 8, "")
        self.save_data()
        current_cat = self.category_tree.currentItem()
        if current_cat:
            self.filter_downloads(current_cat, 0)

    def _create_new_queue_and_move_selected(self):
        """Prompts for a new queue name, creates it, and moves selected items to it."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Queue", "Enter queue name:")
        if ok and name.strip():
            queue_name = name.strip()
            from ui.dialogs.scheduler import _make_default_queue
            if not hasattr(self, "_queues_data") or not self._queues_data:
                self._queues_data = []

            if not any(q.get("name") == queue_name for q in self._queues_data):
                new_q = _make_default_queue(queue_name)
                self._queues_data.append(new_q)
                try:
                    upsert_queue(new_q)
                except Exception:
                    pass

                if hasattr(self, "queues_header") and self.queues_header:
                    child = QTreeWidgetItem(self.queues_header, [queue_name])
                    child.setIcon(0, get_themed_icon("scheduler"))
                    child.setToolTip(0, f"Queue: {queue_name}")
                    child.setData(0, Qt.ItemDataRole.UserRole, "queue")
                    if not hasattr(self, "_sidebar_queue_names"):
                        self._sidebar_queue_names = []
                    self._sidebar_queue_names.append(queue_name)

            self._move_selected_to_queue(queue_name)

    def open_add_url(self, paste_clipboard=False):
        from ui.dialogs import AddUrlDialog
        self._add_url_dialog = AddUrlDialog(self, paste_clipboard=paste_clipboard)
        if self._add_url_dialog.exec():
            self._handle_add_url_accepted(self._add_url_dialog)

    def _handle_add_url_accepted(self, dialog):
        url = dialog.get_url()
        if url:
            if getattr(dialog, "is_media_mode", False):
                self.open_media_downloader(url=url, auto_analyze=True)
            else:
                self.process_incoming_url(url)

    def process_incoming_url(self, data, allow_duplicate=False):
        """Fetches file info and shows the popup without stealing focus for main window"""
        parts = data.split("|", 3)
        url = parts[0]
        user_agent = parts[1] if len(parts) > 1 else ""
        cookies = parts[2] if len(parts) > 2 else ""
        referrer = parts[3] if len(parts) > 3 else ""

        if not url:
            return

        # 0. Check if URL is a media / video streaming link supported by yt-dlp
        from core.utils import is_media_downloader_url
        if is_media_downloader_url(url):
            from core.config import load_category_config
            cfg = load_category_config()
            media_defaults = cfg.get("media_downloader_defaults", {})
            auto_start = bool(media_defaults.get("auto_start_media", False))
            target_preset = media_defaults.get("auto_media_quality_preset", "Best Quality (Video + Audio merged)")
            self.open_media_downloader(
                url=url,
                auto_analyze=True,
                auto_start=auto_start,
                target_preset=target_preset
            )
            return

        GENERIC_ENDPOINTS = {"uc", "download", "get", "fetch", "file", "files", "attachment", "export", "dl", "release", "index.php", "index.html", "view"}

        def _canonical_fn(target_url):
            if not target_url: return ""
            clean = target_url.split("?")[0].split("#")[0]
            seg = [s for s in clean.split("/") if s and s not in ("http:", "https:")]
            if not seg: return ""
            last = seg[-1].lower()
            if last in GENERIC_ENDPOINTS:
                return ""
            if "." in last and len(last.split(".")[-1]) <= 6:
                return last
            return ""

        canon_name = _canonical_fn(url)

        if not allow_duplicate:
            # 1. Check if a fetcher worker is already actively fetching info for this URL / filename
            for fetcher in getattr(self, 'active_fetchers', []):
                if hasattr(fetcher, 'url') and (fetcher.url == url or (_canonical_fn(fetcher.url) == canon_name and canon_name)):
                    return

            # 2. Check if a popup dialog is ALREADY open for this URL / filename
            for dialog in getattr(self, 'active_file_info_dialogs', {}).values():
                if hasattr(dialog, 'file_info') and isinstance(dialog.file_info, dict):
                    existing_d_url = dialog.file_info.get("url")
                    if existing_d_url == url or (_canonical_fn(existing_d_url) == canon_name and canon_name):
                        dialog.show()
                        dialog.raise_()
                        dialog.activateWindow()
                        return

            # 3. Check if download already exists in main download table for this URL / filename
            for row in range(self.download_table.rowCount()):
                item = self.download_table.item(row, 0)
                if item:
                    existing_url = item.data(Qt.ItemDataRole.UserRole)
                    if existing_url == url or (_canonical_fn(existing_url) == canon_name and canon_name):
                        self._handle_duplicate_download(row, item, url, user_agent, cookies)
                        return

        # 4. Start the fetcher
        from core.workers import FileInfoFetcherWorker
        fetcher = FileInfoFetcherWorker(url, user_agent=user_agent, cookies=cookies, referrer=referrer)
        self.active_fetchers.append(fetcher)
        
        # Connect to a wrapper that cleans up the thread memory when done
        fetcher.finished_signal.connect(lambda info, f=fetcher: self._handle_fetch_complete(info, f))
        fetcher.start()

    def _handle_duplicate_download(self, row, item_ref, url, user_agent, cookies):
        """Handles duplicate download requests based on download status (IDM style)."""
        filename = item_ref.text()
        saved_path = item_ref.data(Qt.ItemDataRole.UserRole + 1) or ""
        status_item = self.download_table.item(row, 2)
        status_text = status_item.text() if status_item else ""
        logic_status = (status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else "") or status_text
        size_item = self.download_table.item(row, 1)
        size_str = size_item.text() if size_item else "Unknown"

        key = self._get_item_key(item_ref)
        is_in_active = key in self.active_downloads
        is_active = (is_in_active and logic_status not in ["Paused", "Cancelled", "Canceled", "Error", "Complete"]) or logic_status in ["Downloading", "Starting...", "Pending...", "Queued", "Resuming..."]

        # Case 1: Actively downloading or queued
        if is_active:
            self.show()
            self.raise_()
            self.activateWindow()
            self.download_table.selectRow(row)
            if is_in_active:
                dlg = self.active_downloads.get(key)
                if dlg and MemoryGuard.is_widget_alive(dlg):
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
            if hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage(f"Download is already in progress: {filename}", 5000)
            return

        # Case 2: Completed or Paused/Incomplete
        is_complete = logic_status in ["Complete", "Finished", "Downloaded"] or status_text in ["Complete", "100%"]
        
        file_data = {
            "url": url or item_ref.data(Qt.ItemDataRole.UserRole),
            "filename": filename,
            "path": saved_path,
            "size": size_str,
            "status": "Complete" if is_complete else logic_status,
            "user_agent": user_agent,
            "cookies": cookies
        }

        from ui.dialogs.duplicate import DuplicateDownloadDialog
        dlg = DuplicateDownloadDialog(file_data, parent=None)
        dlg.exec()
        action = dlg.get_action()

        if action == "resume":
            self.download_table.selectRow(row)
            self.resume_selected_download()
        elif action in ["restart", "redownload"]:
            self._restart_download_row(row, item_ref, url, user_agent, cookies)
        elif action == "download_copy":
            self._start_duplicate_copy(url, user_agent, cookies)

    def _restart_download_row(self, row, item_ref, url=None, user_agent=None, cookies=None):
        """Restarts a download from 0%, resetting progress and deleting previous partial chunks."""
        if not item_ref:
            return

        key = self._get_item_key(item_ref)
        if key in self.active_downloads:
            dlg = self.active_downloads.pop(key, None)
            if dlg:
                try:
                    worker = getattr(dlg, 'worker', dlg)
                    if worker and hasattr(worker, 'stop'):
                        worker.stop()
                    dlg.close()
                except Exception:
                    pass

        url = url or item_ref.data(Qt.ItemDataRole.UserRole)
        filename = item_ref.text()
        user_agent = user_agent or item_ref.data(Qt.ItemDataRole.UserRole + 4)
        cookies = cookies or item_ref.data(Qt.ItemDataRole.UserRole + 5)

        # Reset item intent status
        item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Normal")

        # Reset status column & progress percentage to 0%
        self._set_status_text(row, "Starting...", logic_status="Starting...")
        status_item = self.download_table.item(row, 2)
        if status_item:
            status_item.setData(Qt.ItemDataRole.UserRole, "0%")
            status_item.setData(Qt.ItemDataRole.UserRole + 1, "Starting...")

        self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "...", parse_size_to_bytes)

        new_ts = str(time.time())
        item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_ts)
        self._set_timestamp_item(row, 5, format_timestamp_relative(new_ts, max_relative_seconds=300))
        self._set_row_bold(row, True)

        from core.config import load_category_config
        config = load_category_config()
        temp_dir = config.get("temp_dir")
        saved_path = item_ref.data(Qt.ItemDataRole.UserRole + 1)
        custom_save_dir = os.path.dirname(saved_path) if saved_path else None

        # Clean all existing partial or target files on disk
        dirs_to_clean = [d for d in [custom_save_dir, temp_dir] if d and os.path.exists(d)]
        for d in dirs_to_clean:
            for ext_pattern in ["", ".aria2", ".tmpbdm", ".tmpbdm.bdmx"]:
                fp = os.path.join(d, filename + ext_pattern)
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

        # Start worker with allow_resume=False for clean restart
        self._start_download_worker(
            url, item_ref, resume_filename=filename,
            custom_save_dir=custom_save_dir,
            user_agent=user_agent, cookies=cookies,
            allow_resume=False
        )
        self.save_data()

    def _start_duplicate_copy(self, url, user_agent=None, cookies=None):
        """Initiates a new duplicate download copy for an existing URL."""
        data = f"{url}|{user_agent or ''}|{cookies or ''}"
        self.process_incoming_url(data, allow_duplicate=True)


    def _handle_fetch_complete(self, file_info, fetcher):
        # Remove the finished thread from memory
        if fetcher in self.active_fetchers:
            self.active_fetchers.remove(fetcher)
            
        # Trigger existing popup dialog!
        self.on_file_info_fetched(file_info)

    def on_file_info_fetched(self, file_info):
        silent = getattr(self, "settings", {}).get("silent_download", False)
        show_start = getattr(self, "settings", {}).get("show_start_dialog", True)
        if silent or not show_start:
            # Bypass FileInfoDialog: auto-start immediately
            filename = file_info.get("filename") or resolve_filename(file_info.get("url"), {})
            show_prog = False if silent else getattr(self, "settings", {}).get("show_progress_dialog", True)
            self.start_download(
                url=file_info["url"], 
                custom_filename=filename,
                size_data=(file_info.get("size_str", "?"), file_info.get("size_bytes", 0)),
                start_paused=False,
                show_dialog=show_prog,
                user_agent=file_info.get("user_agent"),
                cookies=file_info.get("cookies"),
                referer=file_info.get("referer") or file_info.get("url")
            )
            return

        from ui.dialogs import DownloadFileInfoDialog

        def _canonical_fn(target_url):
            if not target_url: return ""
            clean = target_url.split("?")[0].split("#")[0]
            seg = [s for s in clean.split("/") if s]
            if not seg: return ""
            last = seg[-1].lower()
            if last == "download" and len(seg) > 1:
                last = seg[-2].lower()
            return last

        # Deduplicate: if a popup dialog for this URL or canonical filename is ALREADY open, bring it to front
        target_url = file_info.get("url") if isinstance(file_info, dict) else None
        canon_name = _canonical_fn(target_url) if target_url else ""
        if target_url:
            for dialog in getattr(self, 'active_file_info_dialogs', {}).values():
                if hasattr(dialog, 'file_info') and isinstance(dialog.file_info, dict):
                    existing_d_url = dialog.file_info.get("url")
                    if existing_d_url == target_url or (_canonical_fn(existing_d_url) == canon_name and canon_name):
                        dialog.show()
                        dialog.raise_()
                        dialog.activateWindow()
                        return

        existing_filenames = set()
        existing_paths = set()
        for r in range(self.download_table.rowCount()):
            it = self.download_table.item(r, 0)
            if it:
                existing_filenames.add(it.text())
                sp = it.data(Qt.ItemDataRole.UserRole + 1)
                if sp:
                    existing_paths.add(os.path.normpath(sp))

        # Top-level window (parent=None) sharing app WM_CLASS so it stacks under single app launcher icon
        dialog = DownloadFileInfoDialog(
            file_info,
            parent=None,
            existing_paths=existing_paths,
            existing_names=existing_filenames
        )
        
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
            cookies=file_info.get("cookies"),
            referer=file_info.get("referer") or file_info.get("url")
        )
        
        # Track the dialog to prevent garbage collection and allow cleanup
        dialog_id = self._get_item_key(item_ref)
        self.active_file_info_dialogs[dialog_id] = dialog
        dialog.finished.connect(lambda *_, d_id=dialog_id: self.active_file_info_dialogs.pop(d_id, None))

        # Connect signals to handle the dialog result
        dialog.accepted.connect(lambda: self._handle_download_dialog_accepted(dialog, file_info, item_ref))
        dialog.rejected.connect(lambda: self._handle_download_dialog_rejected(item_ref))
        dialog.size_updated_signal.connect(lambda sz_str, sz_bytes, ref=item_ref: self._on_dialog_size_updated(ref, sz_str, sz_bytes))
        
        # Show and bring to foreground without stealing focus for the main app
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_dialog_size_updated(self, item_ref, size_str, size_bytes):
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            row = -1
        if row != -1:
            self._set_sortable_item(row, 1, size_str, parse_size_to_bytes)
            self.save_data()

    def _handle_download_dialog_accepted(self, dialog, file_info, item_ref):
        results = dialog.get_results()
        key = self._get_item_key(item_ref)
        if key:
            self.active_file_info_dialogs.pop(key, None)
        
        # Update filename and path in case user changed them in the dialog
        item_ref.setText(results["filename"])
        item_ref.setToolTip(results["filename"])
        item_ref.setData(Qt.ItemDataRole.UserRole + 1, results["save_path"])
        
        # Ensure it's in the table
        row = self.download_table.row(item_ref)
        if row == -1: return

        # If "Start Download" was clicked, initiate the worker
        if results["action"] == 'start':
            self._set_status_text(row, "Starting...")
            show_prog = getattr(self, "settings", {}).get("show_progress_dialog", True)
            self._start_download_worker(
                file_info["url"], 
                item_ref, 
                resume_filename=results["filename"],
                custom_save_dir=os.path.dirname(results["save_path"]),
                show_dialog=show_prog,
                user_agent=file_info.get("user_agent"),
                cookies=file_info.get("cookies"),
                referrer=file_info.get("referer") or item_ref.data(Qt.ItemDataRole.UserRole + 15)
            )
        elif results["action"] == 'later':
            self._set_status_text(row, "Paused")

    def _handle_download_dialog_rejected(self, item_ref):
        key = self._get_item_key(item_ref)
        if key:
            self.active_file_info_dialogs.pop(key, None)
        # User cancelled - remove the proposed download from the table
        row = self.download_table.row(item_ref)
        if row != -1:
            self.download_table.removeRow(row)
        self.save_data()

    def start_download(self, url, custom_filename=None, custom_save_dir=None, size_data=None, start_paused=False, show_dialog=True, user_agent=None, cookies=None, referer=None):
        sorting_was_enabled = self.download_table.isSortingEnabled()
        self.download_table.setSortingEnabled(False)

        # Insert new downloads at the top of the table
        row = 0
        self.download_table.insertRow(row)
        
        try:
             filename_guess = resolve_filename(url, {})
        except:
             filename_guess = "file"
             
        if custom_filename:
             filename_guess = custom_filename
        
        current_ts = str(time.time())

        item_name = QTableWidgetItem(filename_guess)
        item_name.setToolTip(filename_guess)
        item_name.setData(Qt.ItemDataRole.UserRole, url)
        item_name.setIcon(get_file_icon(filename_guess))
        
        # Store raw timestamp data, cookies, and referer in the item
        item_name.setData(Qt.ItemDataRole.UserRole + 3, current_ts) # Date Added
        item_name.setData(Qt.ItemDataRole.UserRole + 2, current_ts) # Last Try
        item_name.setData(Qt.ItemDataRole.UserRole + 4, user_agent) # User-Agent
        item_name.setData(Qt.ItemDataRole.UserRole + 5, cookies)    # Cookies
        item_name.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")  # Queue
        item_name.setData(Qt.ItemDataRole.UserRole + 15, referer or url)  # Referer
        
        # Determine explicit metadata bindings
        size_str = size_data[0] if size_data else "?"
        
        self.download_table.setItem(row, 0, item_name)
        self._set_sortable_item(row, 1, size_str, parse_size_to_bytes)
        
        status_txt = "Paused" if start_paused else "Pending..."
        self._set_status_text(row, status_txt)
        
        self._set_sortable_item(row, 3, "", parse_time_to_sec) if start_paused else self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "", parse_size_to_bytes) if start_paused else self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        
        # Display formatted timestamp
        self._set_timestamp_item(row, 5, format_timestamp_relative(current_ts, max_relative_seconds=300))
        self._set_timestamp_item(row, 6, format_timestamp_relative(current_ts, max_relative_seconds=30))
        self._set_row_bold(row, not start_paused)

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
            if len(self.active_downloads) < self.MAX_CONCURRENT_DOWNLOADS:
                self._start_download_worker(url, item_name, resume_filename=filename_guess, custom_save_dir=save_dir, show_dialog=show_dialog, user_agent=user_agent, cookies=cookies, referrer=referer or url)
            else:
                # Slot full — mark as queued; _try_start_queued will pick it up
                self._set_status_text(row, "Queued")
            
        self.save_data()
        return item_name

    def _start_download_worker(self, url, item_ref, resume_filename=None, custom_save_dir=None, show_dialog=True, user_agent=None, cookies=None, referrer=None, allow_resume=True):
        if not user_agent:
            user_agent = item_ref.data(Qt.ItemDataRole.UserRole + 4)
        if not cookies:
            cookies = item_ref.data(Qt.ItemDataRole.UserRole + 5)
        if not referrer:
            referrer = item_ref.data(Qt.ItemDataRole.UserRole + 15) or url
        
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
            except: save_dir = get_user_downloads_dir()

        temp_dir = config.get("temp_dir")

        # SMART ROUTING: Use Aria2 as the primary engine.
        # Fallback to internal downloader only if Aria2 binary is missing or daemon failed.
        use_aria2 = True
        try:
            is_aria2_live = False
            if hasattr(self, 'aria2_process') and self.aria2_process and self.aria2_process.poll() is None:
                is_aria2_live = True
            else:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.15)
                    ext_data = load_extension_config()
                    r_port = ext_data.get("port", 56800)
                    if s.connect_ex(("127.0.0.1", r_port)) == 0:
                        is_aria2_live = True
            if not is_aria2_live:
                use_aria2 = False
        except Exception:
            use_aria2 = False

        if use_aria2:
            worker = Aria2Worker(
                url, item_ref.row(), save_dir, resume_filename,
                user_agent=user_agent, cookies=cookies, temp_dir=temp_dir,
                referrer=referrer,
                allow_resume=allow_resume
            )
        else:
            worker = DownloadWorker(
                url, item_ref.row(), save_dir, resume_filename,
                user_agent=user_agent, cookies=cookies, temp_dir=temp_dir,
                referrer=referrer,
                allow_resume=allow_resume
            )

        
        gen = (item_ref.data(Qt.ItemDataRole.UserRole + 13) or 0) + 1
        item_ref.setData(Qt.ItemDataRole.UserRole + 13, gen)
        item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Normal")
        worker.generation = gen

        item_ref.setData(Qt.ItemDataRole.UserRole + 1, worker.target_path)
        item_ref.setText(worker.filename)
        item_ref.setToolTip(worker.filename)
        
        worker.main_progress_signal.connect(lambda _, data: self.update_download_row(item_ref, data))
        worker.finished_signal.connect(lambda _, status: self.download_finished(item_ref, status))

        # Top-level window (parent=None) sharing app WM_CLASS so it stacks under single app launcher icon
        progress_dialog = DownloadProgressDialog(worker, None)
        if show_dialog:
            progress_dialog.show()
        else:
            progress_dialog.hide()

        # Connect to the dialog's finished signal to update the main UI/toolbar
        progress_dialog.finished.connect(self.refresh_toolbar_state_on_dialog_close)

        # Use persistent item key to manage active dialogs
        key = self._get_item_key(item_ref)
        self.active_downloads[key] = progress_dialog
        progress_dialog.finished.connect(lambda *_, k=key: self.active_downloads.pop(k, None))
        progress_dialog.finished.connect(self._try_start_queued)

        # Trigger UI Update for Stop Buttons
        self.update_ui_states()

    def resume_selected_download(self):
        selected_items = self.download_table.selectedItems()
        if not selected_items:
            return
        
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            rows = set(item.row() for item in selected_items)
            for row in rows:
                item_name = self.download_table.item(row, 0)
                if not item_name:
                    continue
                # If already active, bring dialog to front (or create/restore if silent/hidden) and resume if paused
                key = self._get_item_key(item_name)
                if key in self.active_downloads or self._is_download_active(item_name):
                    dialog = self.show_download_progress_dialog(item_name)
                    status_item = self.download_table.item(row, 2)
                    logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
                    
                    worker = None
                    if dialog:
                        worker = getattr(dialog, 'worker', None)
                    elif key in self.active_downloads:
                        entry = self.active_downloads[key]
                        worker = getattr(entry, 'worker', entry)

                    if worker and (getattr(worker, 'is_paused', False) or getattr(worker, 'is_pause_requested', False) or logic_status in ["Paused", "Cancelled", "Error"]):
                        gen = (item_name.data(Qt.ItemDataRole.UserRole + 13) or 0) + 1
                        item_name.setData(Qt.ItemDataRole.UserRole + 13, gen)
                        item_name.setData(Qt.ItemDataRole.UserRole + 11, "Normal")
                        worker.generation = gen
                        # Forward resume to existing worker
                        try:
                            if hasattr(worker, 'resume'):
                                worker.resume()
                        except (RuntimeError, Exception):
                            pass
                        if dialog and hasattr(dialog, 'lbl_main_status'):
                            try:
                                dialog.lbl_main_status.setText("Resuming...")
                                dialog.btn_pause.setText("Pause")
                                dialog.btn_cancel.setText("Cancel")
                            except Exception:
                                pass
                        self._set_status_text(row, "Resuming...", logic_status="Resuming...")
                        if status_item:
                            status_item.setData(Qt.ItemDataRole.UserRole + 1, "Resuming...")
                        self._set_row_bold(row, True)
                    continue
                
                # Start/Resume download
                url = item_name.data(Qt.ItemDataRole.UserRole)
                filename = item_name.text()
                
                if url:
                    self._set_status_text(row, "Resuming...", logic_status="Resuming...")
                    status_item = self.download_table.item(row, 2)
                    if status_item:
                        status_item.setData(Qt.ItemDataRole.UserRole + 1, "Resuming...")
                    # Update last try timestamp before resuming
                    new_timestamp = str(time.time())
                    item_name.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                    self._set_timestamp_item(row, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                    self._set_row_bold(row, True)
                    
                    self._start_download_worker(url, item_name, resume_filename=filename)
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self.download_table.viewport().update()
        
        self.update_ui_states()

    def stop_selected_download(self):
        selected_items = self.download_table.selectedItems()
        if not selected_items:
            return
        
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            rows = set(item.row() for item in selected_items)
            for r in rows:
                item = self.download_table.item(r, 0)
                if not item:
                    continue
                item.setData(Qt.ItemDataRole.UserRole + 11, "Paused")
                key = self._get_item_key(item)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    worker = getattr(dialog, 'worker', dialog)
                    if worker is not None and hasattr(worker, 'pause'):
                        try:
                            worker.pause()
                        except Exception:
                            pass
                    
                    if hasattr(dialog, 'lbl_main_status'):
                        try:
                            dialog.lbl_main_status.setText("Paused")
                            dialog.btn_pause.setText("Resume")
                            dialog.btn_cancel.setText("Close")
                            dialog.lbl_speed.setText("0.00 B/s")
                            dialog.lbl_time.setText("-")
                        except Exception:
                            pass

                    # Update status preserving percentage string
                    status_item = self.download_table.item(r, 2)
                    if status_item:
                        current_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
                        if current_status == "Complete" or status_item.text() == "Complete":
                            continue
                    if not status_item:
                        status_item = QTableWidgetItem()
                        self.download_table.setItem(r, 2, status_item)
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
                    pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                    final_display = pct_data if pct_data and "%" in str(pct_data) else "Paused"
                    self._set_status_text(r, final_display, logic_status="Paused")

                    # Reset Time Left and Rate on pause
                    self._set_sortable_item(r, 3, "", parse_time_to_sec)
                    self._set_sortable_item(r, 4, "", parse_size_to_bytes)

                    # Update last try timestamp on pause
                    new_timestamp = str(time.time())
                    item.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                    self._set_timestamp_item(r, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                    self._set_row_bold(r, False)
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self.download_table.viewport().update()
        
        self.update_ui_states()

    def _get_display_state(self, item_ref, worker_status, comp_bytes=0, tot_bytes=0):
        """
        Central IDM-style State Resolver.
        User Intent State (item_ref UserRole+11) is the supreme authority.
        Engine State (worker_status) is only considered when User Intent is Normal/Active.
        """
        user_state = item_ref.data(Qt.ItemDataRole.UserRole + 11) # "Complete", "Paused", "Cancelled", "Normal"
        row = self.download_table.row(item_ref) if hasattr(self, "download_table") else -1
        status_item = self.download_table.item(row, 2) if (row >= 0 and hasattr(self, "download_table")) else None
        prev_pct_str = status_item.data(Qt.ItemDataRole.UserRole) if status_item else None
        
        # Calculate percentage string
        pct_str = ""
        if tot_bytes > 0:
            pct_val = min(100.0, (comp_bytes / tot_bytes) * 100.0)
            if prev_pct_str and "%" in str(prev_pct_str) and pct_val == 0.0:
                try:
                    prev_val = float(str(prev_pct_str).replace("%", "").strip())
                    if prev_val > 0:
                        pct_val = prev_val
                except ValueError:
                    pass
            pct_str = f"{pct_val:.2f}%"
        elif prev_pct_str and "%" in str(prev_pct_str):
            pct_str = str(prev_pct_str)

        # 1. User Intent: Complete
        if user_state == "Complete" or worker_status == "Complete" or (tot_bytes > 0 and comp_bytes >= tot_bytes):
            item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Complete")
            return "Complete", "Complete", pct_str or "100.00%", False

        # 2. Worker reports active/resuming states -> sync user intent to Normal
        if worker_status.startswith("Receiving data") or worker_status.startswith("Downloading") or worker_status in ["Resuming...", "Resume GET...", "Connecting..."]:
            item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Normal")
            user_state = "Normal"

        # 3. User Intent / Progress Dialog Paused
        if user_state == "Paused" or worker_status == "Paused":
            item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Paused")
            final_display = pct_str if pct_str else "Paused"
            return final_display, "Paused", pct_str, False

        # 4. User Intent: Cancelled
        if user_state == "Cancelled" or worker_status == "Cancelled":
            item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Cancelled")
            final_display = pct_str if pct_str else "Cancelled"
            return final_display, "Cancelled", pct_str, False

        # 5. User Intent: Normal / Active -> Interpret Engine Status
        if worker_status.startswith("Receiving data") or worker_status.startswith("Downloading"):
            engine_status = "Downloading"
            final_display = pct_str if pct_str else "Downloading"
            is_active = True
        elif worker_status in ["Resuming...", "Resume GET..."]:
            engine_status = "Resuming..."
            final_display = pct_str if pct_str else "Resuming..."
            is_active = True
        elif worker_status == "Connecting...":
            engine_status = "Connecting..."
            final_display = pct_str if pct_str else "Connecting..."
            is_active = True
        elif worker_status == "Error":
            engine_status = "Error"
            final_display = "Error"
            is_active = False
        else:
            engine_status = worker_status if worker_status else "Downloading"
            final_display = pct_str if pct_str else engine_status
            is_active = True

        return final_display, engine_status, pct_str, is_active

    def _apply_download_row_data(self, item_ref, data):
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            return # object has been deleted by remove
        if row == -1: return 

        # Freshness guard: Discard stale callbacks from older sessions
        if len(data) > 8 and data[8] is not None:
            callback_gen = data[8]
            current_gen = item_ref.data(Qt.ItemDataRole.UserRole + 13)
            if current_gen is not None and callback_gen < current_gen:
                return

        status_item = self.download_table.item(row, 2)
        old_status = status_item.text() if status_item else ""
        old_logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""

        # --- PROTECTION GUARD ---
        # If the row is already marked as Complete, ignore any late progress signals unless actively downloading (e.g. redownload)
        key = self._get_item_key(item_ref)
        if item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Complete" and key not in getattr(self, "active_downloads", {}):
            return
        
        # --- Update Last Try Timestamp ---
        new_timestamp = str(time.time())
        item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)

        new_name = data[0]
        if item_ref.text() != new_name:
            item_ref.setText(new_name)
            item_ref.setToolTip(new_name)
            item_ref.setIcon(get_file_icon(new_name))
        
        # Col 1: Size (Display total file size if known)
        tot_bytes = data[6] if len(data) > 6 else 0
        comp_bytes = data[5] if len(data) > 5 else 0

        if tot_bytes > 0:
            size_display = format_bytes(tot_bytes)
        elif comp_bytes > 0:
            size_display = format_bytes(comp_bytes)
        else:
            size_display = data[1] if len(data) > 1 and data[1] else "Unknown"

        self._set_sortable_item(row, 1, size_display, parse_size_to_bytes)
        
        # Col 2: Status (Resolved centrally via IDM State Architecture)
        worker_status = data[2] if len(data) > 2 else ""
        final_display, display_status, pct_str, is_active = self._get_display_state(item_ref, worker_status, comp_bytes, tot_bytes)

        if pct_str and pct_str != "Complete" and status_item:
            status_item.setData(Qt.ItemDataRole.UserRole, pct_str)
        
        if final_display != old_status or display_status != old_logic_status:
            self._set_status_text(row, final_display, logic_status=display_status)
            status_item = self.download_table.item(row, 2)
            if status_item:
                status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            if display_status != old_logic_status:
                self.update_ui_states()
        
        # Col 3 & 4: Time Left & Rate
        if display_status in ["Complete", "Error", "Paused", "Cancelled", "Queued"]:
            self._set_sortable_item(row, 3, "", parse_time_to_sec)
            self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            if hasattr(self, "active_speeds"):
                self.active_speeds.pop(key, None)
        else:
            time_val = data[3] if len(data) > 3 else ""
            rate_val = data[4] if len(data) > 4 else ""
            self._set_sortable_item(row, 3, time_val, parse_time_to_sec)
            self._set_sortable_item(row, 4, rate_val, parse_size_to_bytes)
            if hasattr(self, "active_speeds"):
                raw_speed = data[7] if len(data) > 7 and isinstance(data[7], (int, float)) else None
                if raw_speed is not None:
                    self.active_speeds[key] = float(raw_speed)
                elif rate_val:
                    self.active_speeds[key] = parse_size_to_bytes(str(rate_val).replace("/s", "").strip())
        self.update_status_bar_speed()
        
        # Col 5: Last Try
        formatted_last_try = format_timestamp_relative(new_timestamp, max_relative_seconds=300)
        last_try_item = self.download_table.item(row, 5)
        if not last_try_item:
            self._set_timestamp_item(row, 5, formatted_last_try)
        elif last_try_item.text() != formatted_last_try:
            last_try_item.setText(formatted_last_try)
        
        self._set_row_bold(row, is_active)

    def _stop_worker_entry(self, entry):
        """Stop either a ProgressDialog (has .worker) or a bare YtDlpDownloadWorker thread."""
        if entry is None:
            return
        try:
            from core.media_downloader import YtDlpDownloadWorker
            if isinstance(entry, YtDlpDownloadWorker):
                try:
                    entry.stop()
                    entry.requestInterruption()
                    entry.quit()
                    entry.wait(2000)
                    if entry.isRunning():
                        entry.terminate()
                        entry.wait(2000)
                except Exception:
                    pass
            else:
                # ProgressDialog path - protect against deleted C++ object
                worker = None
                try:
                    worker = getattr(entry, 'worker', None)
                except (RuntimeError, AttributeError, Exception):
                    pass

                if worker:
                    try:
                        worker.main_progress_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        worker.finished_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        worker.stop()
                    except Exception:
                        pass
                    try:
                        worker.quit()
                        worker.wait(1000)
                    except Exception:
                        pass

                try:
                    if hasattr(entry, 'finished'):
                        entry.finished.disconnect()
                except (RuntimeError, AttributeError, Exception):
                    pass

                try:
                    entry.reject()
                except (RuntimeError, AttributeError, Exception):
                    pass
        except (RuntimeError, Exception):
            pass

    def stop_all_downloads(self):
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            for key, entry in list(self.active_downloads.items()):
                worker = getattr(entry, 'worker', entry)
                if worker is not None and hasattr(worker, 'pause'):
                    try:
                        worker.pause()
                    except Exception:
                        pass
                
                if hasattr(entry, 'lbl_main_status'):
                    try:
                        entry.lbl_main_status.setText("Paused")
                        entry.btn_pause.setText("Resume")
                        entry.btn_cancel.setText("Close")
                        entry.lbl_speed.setText("0.00 B/s")
                        entry.lbl_time.setText("-")
                    except Exception:
                        pass

                # Find the corresponding table item and update status/timestamp
                for r in range(self.download_table.rowCount()):
                    item_ref = self.download_table.item(r, 0)
                    if item_ref and self._get_item_key(item_ref) == key:
                        status_item = self.download_table.item(r, 2)
                        if status_item:
                            current_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
                            if current_status == "Complete" or status_item.text() == "Complete" or item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Complete":
                                continue
                        if not status_item:
                            status_item = QTableWidgetItem()
                            self.download_table.setItem(r, 2, status_item)
                        status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")
                        pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                        final_display = pct_data if pct_data and "%" in str(pct_data) else "Paused"
                        self._set_status_text(r, final_display, logic_status="Paused")

                        self._set_sortable_item(r, 3, "", parse_time_to_sec)
                        self._set_sortable_item(r, 4, "", parse_size_to_bytes)

                        new_timestamp = str(time.time())
                        item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                        self._set_timestamp_item(r, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                        self._set_row_bold(r, False)
                        break
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self.download_table.viewport().update()
        if hasattr(self, "active_speeds"):
            self.active_speeds.clear()
        self.update_status_bar_speed()
        self.update_ui_states()

    def remove_from_list(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
        
        for row in rows:
            item_name = self.download_table.item(row, 0)
            if item_name:
                key = self._get_item_key(item_name)
                if key in self.active_downloads:
                    dialog = self.active_downloads.pop(key, None)
                    self._stop_worker_entry(dialog)
                if hasattr(self, "active_speeds"):
                    self.active_speeds.pop(key, None)
                if hasattr(self, "active_file_info_dialogs"):
                    self.active_file_info_dialogs.pop(key, None)
                if hasattr(self, "active_complete_dialogs"):
                    self.active_complete_dialogs.pop(key, None)
            self.download_table.removeRow(row)
        self.save_data()
        self.update_ui_states()
        self.update_status_bar_items()
        self.update_status_bar_speed()
        MemoryGuard.clean_and_trim()

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
                if item_name:
                    key = self._get_item_key(item_name)
                    if key in self.active_downloads:
                        dlg = self.active_downloads.pop(key, None)
                        self._stop_worker_entry(dlg)
                    if hasattr(self, "active_speeds"):
                        self.active_speeds.pop(key, None)
                    if hasattr(self, "_pending_tray_updates"):
                        self._pending_tray_updates.pop(key, None)
                    if hasattr(self, "active_file_info_dialogs"):
                        self.active_file_info_dialogs.pop(key, None)
                    if hasattr(self, "active_complete_dialogs"):
                        self.active_complete_dialogs.pop(key, None)
                
                if delete_disk and item_name:
                    path = item_name.data(Qt.ItemDataRole.UserRole + 1)
                    if path and os.path.exists(path):
                        try: os.remove(path)
                        except: pass

                # --- ALWAYS CLEAR CACHE/TEMP FILES ---
                if item_name:
                    self._clear_cache_files(item_name, config)

                self.download_table.removeRow(row)
            self.save_data()
            self.update_ui_states()
            self.update_status_bar_items()
            self.update_status_bar_speed()
            MemoryGuard.clean_and_trim()

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
                key = self._get_item_key(item_name)
                if key in self.active_downloads:
                    dlg = self.active_downloads.pop(key, None)
                    self._stop_worker_entry(dlg)
                if hasattr(self, "active_speeds"):
                    self.active_speeds.pop(key, None)
                if hasattr(self, "_pending_tray_updates"):
                    self._pending_tray_updates.pop(key, None)
                if hasattr(self, "active_file_info_dialogs"):
                    self.active_file_info_dialogs.pop(key, None)
                if hasattr(self, "active_complete_dialogs"):
                    self.active_complete_dialogs.pop(key, None)
                
                # Clear cache files for finished items too
                self._clear_cache_files(item_name, config)

            self.download_table.removeRow(row)

        self.save_data()
        self.update_ui_states()
        self.update_status_bar_items()
        self.update_status_bar_speed()
        MemoryGuard.clean_and_trim()
    def update_download_row(self, item_ref, data):
        # FAST PATH: When window is hibernating in tray, buffer state and avoid all UI/DOM mutations
        key = self._get_item_key(item_ref)
        if getattr(self, "_is_in_tray", False):
            if not hasattr(self, "_pending_tray_updates"):
                self._pending_tray_updates = {}
            self._pending_tray_updates[key] = (item_ref, data)
            if hasattr(self, "active_speeds"):
                worker_status = data[2] if len(data) > 2 else ""
                if worker_status in ["Complete", "Error", "Paused", "Cancelled", "Queued"]:
                    self.active_speeds.pop(key, None)
                else:
                    raw_speed = data[7] if len(data) > 7 and isinstance(data[7], (int, float)) else None
                    if raw_speed is not None:
                        self.active_speeds[key] = float(raw_speed)
                    elif len(data) > 4 and data[4]:
                        self.active_speeds[key] = parse_size_to_bytes(str(data[4]).replace("/s", "").strip())
            self.update_status_bar_speed()
            return

        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            self._apply_download_row_data(item_ref, data)
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self._notify_views_changed()
    def download_finished(self, item_ref, status_text):
        key = self._get_item_key(item_ref)
        if hasattr(self, "active_speeds"):
            self.active_speeds.pop(key, None)
        if hasattr(self, "_pending_tray_updates"):
            self._pending_tray_updates.pop(key, None)
        self.update_status_bar_speed()

        # Ignore spurious Paused/Cancelled signals if already Complete
        if item_ref.data(Qt.ItemDataRole.UserRole + 11) == "Complete" and status_text in ["Paused", "Cancelled"]:
            return

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

        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            return 
            
        try:
            if row != -1:
                status_item = self.download_table.item(row, 2)
                if not status_item:
                    self._set_status_text(row, "")
                    status_item = self.download_table.item(row, 2)
                
                # Formatting final display text and updating logical status
                status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
                
                if display_status == "Complete":
                    final_display = "Complete"
                    status_item.setData(Qt.ItemDataRole.UserRole, "Complete")
                    path = item_ref.data(Qt.ItemDataRole.UserRole + 1)
                    if path and os.path.exists(path) and os.path.isfile(path):
                        try:
                            actual_sz = os.path.getsize(path)
                            if actual_sz > 0:
                                self._set_sortable_item(row, 1, format_bytes(actual_sz), parse_size_to_bytes)
                        except Exception:
                            pass
                elif display_status in ["Paused", "Cancelled"]:
                    pct = status_item.data(Qt.ItemDataRole.UserRole)
                    final_display = pct if pct else "0.00%"
                else:
                    final_display = display_status
                
                self._set_status_text(row, final_display, logic_status=display_status)
                
                if display_status in ["Complete", "Error"]:
                     self._set_sortable_item(row, 3, "", parse_time_to_sec)
                     self._set_sortable_item(row, 4, "", parse_size_to_bytes)
                elif display_status in ["Paused", "Cancelled"]:
                     self._set_sortable_item(row, 4, "", parse_size_to_bytes)

                final_timestamp = str(time.time())
                item_ref.setData(Qt.ItemDataRole.UserRole + 2, final_timestamp)
                self._set_timestamp_item(row, 5, format_timestamp_relative(final_timestamp, max_relative_seconds=300))
                self._set_row_bold(row, False)
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)
            self.download_table.viewport().update()

        # Handle UI Popups / Dialogs
        if key in self.active_downloads:
            dlg = self.active_downloads.pop(key, None)
            if hasattr(dlg, 'is_completed') and display_status == "Complete":
                dlg.is_completed = True
            if hasattr(dlg, 'close'):
                dlg.close()
            MemoryGuard.safe_delete_later(dlg)
        if hasattr(self, "active_speeds"):
            self.active_speeds.pop(key, None)

        if display_status == "Complete":
            # Dispatch XDG system notification if enabled
            if getattr(self, "system_notifications", False) or (isinstance(getattr(self, "settings", {}), dict) and self.settings.get("system_notifications", False)):
                try:
                    from core.notifications import send_system_notification
                    filename = item_ref.text() if item_ref else "File"
                    size_str = self.download_table.item(row, 1).text() if (row != -1 and self.download_table.item(row, 1)) else ""
                    save_path = item_ref.data(Qt.ItemDataRole.UserRole + 1) if item_ref else ""
                    body = f"{filename} ({size_str})" if size_str and size_str != "?" else filename
                    send_system_notification(
                        title="Download Complete",
                        message=body,
                        app_name="Bengal Download Manager",
                        icon_name="io.github.tazihad.bengal-download-manager",
                        file_path=save_path,
                        tray_icon=getattr(self, "tray_icon", None)
                    )
                except Exception:
                    pass

            # If File Info dialog is still open, return and wait for confirmed action
            if key in self.active_file_info_dialogs:
                return

            # Determine whether to show Download Complete Dialog (IDM style: suppressed in queues by default)
            silent = getattr(self, "settings", {}).get("silent_download", False)
            is_queue_run = bool(item_ref.data(Qt.ItemDataRole.UserRole + 14)) if item_ref else False
            show_comp = getattr(self, "settings", {}).get("show_complete_dialog", True)
            show_q_comp = getattr(self, "settings", {}).get("show_queue_complete_dialog", False)
            should_show_complete = False if silent else (show_q_comp if is_queue_run else show_comp)

            if should_show_complete:
                # Show IDM-style Download Complete Dialog
                file_data = {
                    "url": item_ref.data(Qt.ItemDataRole.UserRole),
                    "path": item_ref.data(Qt.ItemDataRole.UserRole + 1),
                    "size": self.download_table.item(row, 1).text() if row != -1 else "?"
                }
                # Top-level window (parent=None) sharing app WM_CLASS so it stacks under single app launcher icon
                dialog = DownloadCompleteDialog(file_data, parent=None, main_window=self)
                self.active_complete_dialogs[key] = dialog
                dialog.finished.connect(lambda *_, k=key: self.active_complete_dialogs.pop(k, None))
                dialog.show()
            
            if hasattr(self, "download_retry_counts"):
                self.download_retry_counts.pop(key, None)

        elif display_status == "Error":
            queue_name = item_ref.data(Qt.ItemDataRole.UserRole + 8) or "Main download queue"
            queues = getattr(self, "_queues_data", [])
            if not queues:
                db_queues = get_all_queues()
                queues = db_queues if db_queues else []
            q_config = next((q for q in queues if isinstance(q, dict) and q.get("name") == queue_name), None)
            if q_config and q_config.get("retries_enabled", False):
                max_retries = q_config.get("retries_count", 10)
                if not hasattr(self, "download_retry_counts"):
                    self.download_retry_counts = {}
                current_retries = self.download_retry_counts.get(key, 0)
                if current_retries < max_retries:
                    self.download_retry_counts[key] = current_retries + 1
                    url = item_ref.data(Qt.ItemDataRole.UserRole)
                    if url:
                        self._set_status_text(row, f"Retrying ({current_retries + 1}/{max_retries})...")
                        QTimer.singleShot(3000, lambda ref=item_ref, u=url: self._start_download_worker(u, ref, show_dialog=False))
                        return

        self.update_status_bar_speed()
        self.update_status_bar_items()
        self.update_ui_states()
        self.save_data()
        MemoryGuard.clean_and_trim()
        # Explicit repaint
        self.download_table.viewport().update()
    
    def open_options(self):
        from ui.dialogs import OptionsDialog
        if MemoryGuard.is_widget_alive(getattr(self, "_options_dlg", None)):
            self._options_dlg.raise_()
            self._options_dlg.activateWindow()
            return
        # Top-level window (parent=None) sharing app WM_CLASS so it appears as a separate icon in taskbar panel
        self._options_dlg = OptionsDialog(main_window=self)
        self._options_dlg.accepted.connect(self._handle_options_accepted)
        self._options_dlg.finished.connect(lambda *_: setattr(self, "_options_dlg", None))
        self._options_dlg.show()
        self._options_dlg.raise_()
        self._options_dlg.activateWindow()

    def open_media_downloader(self, url=None, auto_analyze=False, auto_start=False, target_preset=""):
        from ui.dialogs import MediaDownloaderDialog
        if MemoryGuard.is_widget_alive(getattr(self, "_media_downloader_dlg", None)):
            if not auto_start:
                self._media_downloader_dlg.show()
                self._media_downloader_dlg.raise_()
                self._media_downloader_dlg.activateWindow()
            if url:
                if auto_start:
                    self._media_downloader_dlg.analyze_and_download(url, auto_start=True, target_preset=target_preset)
                else:
                    self._media_downloader_dlg.txt_url.setText(url)
                    if auto_analyze:
                        self._media_downloader_dlg._on_analyze_or_stop_clicked()
            return
        self._media_downloader_dlg = MediaDownloaderDialog(main_window=self)
        self._media_downloader_dlg.finished.connect(lambda *_: setattr(self, "_media_downloader_dlg", None))
        if not auto_start:
            self._media_downloader_dlg.show()
            self._media_downloader_dlg.raise_()
            self._media_downloader_dlg.activateWindow()
        if url:
            if auto_start:
                self._media_downloader_dlg.analyze_and_download(url, auto_start=True, target_preset=target_preset)
            else:
                self._media_downloader_dlg.txt_url.setText(url)
                if auto_analyze:
                    self._media_downloader_dlg._on_analyze_or_stop_clicked()

    def open_scheduler(self):
        from ui.dialogs import SchedulerDialog
        if MemoryGuard.is_widget_alive(getattr(self, "_scheduler_dlg", None)):
            self._scheduler_dlg.raise_()
            self._scheduler_dlg.activateWindow()
            return
        # Pass the persistent queue list so reopening the dialog preserves all queues
        self._scheduler_dlg = SchedulerDialog(main_window=self, initial_queues=self._queues_data)
        self._scheduler_dlg.finished.connect(self._sync_sidebar_queues)
        self._scheduler_dlg.finished.connect(lambda *_: setattr(self, "_scheduler_dlg", None))
        self._scheduler_dlg.show()
        self._scheduler_dlg.raise_()
        self._scheduler_dlg.activateWindow()

    def start_media_download(self, url, filename="media.mp4", format_spec="bestvideo+bestaudio/best", is_audio_only=False, custom_save_dir=None, cookies_browser=None, cookies_file=None, total_size_bytes=0):
        from core.media_downloader import YtDlpDownloadWorker

        config = load_category_config()
        categories = config.get("categories", {})
        
        final_category = "Video" if not is_audio_only else "Music"
        if final_category not in categories:
            final_category = "General"
            
        save_dir = custom_save_dir if custom_save_dir else categories[final_category]["path"]
        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception:
                save_dir = get_user_downloads_dir()

        from core.utils import sanitize_media_filename, get_unique_media_filepath
        base_name, ext = os.path.splitext(filename)
        sanitized_filename = sanitize_media_filename(base_name, ext=ext)
        target_path = get_unique_media_filepath(save_dir, sanitized_filename)
        filename = os.path.basename(target_path)

        self.download_table.setSortingEnabled(False)
        row = 0
        self.download_table.insertRow(row)

        current_ts = str(time.time())

        item_name = QTableWidgetItem(filename)
        item_name.setIcon(get_file_icon(filename))
        item_name.setToolTip(filename)
        item_name.setData(Qt.ItemDataRole.UserRole, url)
        item_name.setData(Qt.ItemDataRole.UserRole + 1, target_path)
        item_name.setData(Qt.ItemDataRole.UserRole + 2, current_ts)
        item_name.setData(Qt.ItemDataRole.UserRole + 3, current_ts)
        item_name.setData(Qt.ItemDataRole.UserRole + 6, format_spec)      # for _try_start_queued
        item_name.setData(Qt.ItemDataRole.UserRole + 7, is_audio_only)    # for _try_start_queued
        item_name.setData(Qt.ItemDataRole.UserRole + 8, "Main download queue")  # Queue
        item_name.setData(Qt.ItemDataRole.UserRole + 9, cookies_browser)
        item_name.setData(Qt.ItemDataRole.UserRole + 10, cookies_file)

        init_size_str = format_bytes(total_size_bytes) if total_size_bytes > 0 else "Calculating..."
        self.download_table.setItem(row, 0, item_name)
        self._set_sortable_item(row, 1, init_size_str, parse_size_to_bytes)
        self._set_status_text(row, "Downloading...")
        self._set_sortable_item(row, 3, "--", parse_time_to_sec)
        self._set_sortable_item(row, 4, "--", parse_size_to_bytes)
        self._set_timestamp_item(row, 5, format_timestamp_relative(current_ts, max_relative_seconds=300))
        self._set_timestamp_item(row, 6, format_timestamp_relative(current_ts, max_relative_seconds=30))

        is_active = len(self.active_downloads) < self.MAX_CONCURRENT_DOWNLOADS
        self._set_row_bold(row, is_active)

        # Respect concurrent download cap
        if not is_active:
            # Mark as queued; _try_start_queued will start it when a slot opens
            self._set_status_text(row, "Queued")
            self._set_sortable_item(row, 3, "", parse_time_to_sec)
            self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            self._set_row_bold(row, False)
            self.download_table.setSortingEnabled(True)
            self.update_ui_states()
            self._sync_sidebar_queues()
            self.save_data()
            return item_name

        worker = YtDlpDownloadWorker(
            url=url,
            row_index=row,
            save_dir=save_dir,
            filename=filename,
            format_spec=format_spec,
            is_audio_only=is_audio_only,
            cookies_browser=cookies_browser,
            cookies_file=cookies_file
        )

        key = self._get_item_key(item_name)
        self.active_downloads[key] = worker

        worker.main_progress_signal.connect(lambda _, data, ref=item_name: self.update_download_row(ref, data))
        worker.finished_signal.connect(lambda _, path, ref=item_name, k=key: self._on_media_download_finished(k, ref, path))

        worker.start()
        self.download_table.setSortingEnabled(True)
        self.update_ui_states()
        self._sync_sidebar_queues()
        self.save_data()
        return item_name

    def _on_media_download_finished(self, key, item_ref, path):
        if key in self.active_downloads:
            self.active_downloads.pop(key, None)
        if hasattr(self, "active_speeds"):
            self.active_speeds.pop(key, None)
        self.update_status_bar_speed()
        try:
            row = self.download_table.row(item_ref)
        except RuntimeError:
            row = -1

        if row != -1:
            if path and os.path.exists(path):
                filename = os.path.basename(path)
                item_ref.setText(filename)
                item_ref.setToolTip(filename)
                item_ref.setData(Qt.ItemDataRole.UserRole + 1, path)
                item_ref.setData(Qt.ItemDataRole.UserRole + 11, "Complete")
                actual_size = os.path.getsize(path)
                self._set_sortable_item(row, 1, format_bytes(actual_size), parse_size_to_bytes)
                self._set_status_text(row, "Complete")
                status_item = self.download_table.item(row, 2)
                if status_item:
                    status_item.setData(Qt.ItemDataRole.UserRole, "Complete")
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
                self._set_sortable_item(row, 3, "", parse_time_to_sec)
                self._set_sortable_item(row, 4, "", parse_size_to_bytes)

                # Dispatch XDG system notification if enabled
                if getattr(self, "system_notifications", False) or (isinstance(getattr(self, "settings", {}), dict) and self.settings.get("system_notifications", False)):
                    try:
                        from core.notifications import send_system_notification
                        size_str = self.download_table.item(row, 1).text() if self.download_table.item(row, 1) else ""
                        body = f"{filename} ({size_str})" if size_str and size_str != "?" else filename
                        send_system_notification(
                            title="Download Complete",
                            message=body,
                            app_name="Bengal Download Manager",
                            icon_name="io.github.tazihad.bengal-download-manager",
                            file_path=path,
                            tray_icon=getattr(self, "tray_icon", None)
                        )
                    except Exception:
                        pass

                # Determine whether to show Download Complete Dialog (IDM style: suppressed in queues by default)
                silent = getattr(self, "settings", {}).get("silent_download", False)
                is_queue_run = bool(item_ref.data(Qt.ItemDataRole.UserRole + 14)) if item_ref else False
                show_comp = getattr(self, "settings", {}).get("show_complete_dialog", True)
                show_q_comp = getattr(self, "settings", {}).get("show_queue_complete_dialog", False)
                should_show_complete = False if silent else (show_q_comp if is_queue_run else show_comp)

                if should_show_complete:
                    # Show IDM-style Download Complete Dialog
                    file_data = {
                        "url": item_ref.data(Qt.ItemDataRole.UserRole),
                        "path": path,
                        "size": self.download_table.item(row, 1).text() if row != -1 else "?"
                    }
                    dialog = DownloadCompleteDialog(file_data, parent=None, main_window=self)
                    self.active_complete_dialogs[key] = dialog
                    dialog.finished.connect(lambda *_, k=key: self.active_complete_dialogs.pop(k, None))
                    dialog.show()
            else:
                status_item = self.download_table.item(row, 2)
                if status_item:
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, "Error")
                self._set_status_text(row, "Error")
            self._set_row_bold(row, False)

        self.update_ui_states()
        self.save_data()
        MemoryGuard.clean_and_trim()
        self._try_start_queued()

    def _try_start_queued(self, *_):
        """Start the next Queued row if a concurrent slot is available."""
        while len(self.active_downloads) < self.MAX_CONCURRENT_DOWNLOADS:
            started = False
            for r in range(self.download_table.rowCount()):
                status_item = self.download_table.item(r, 2)
                if status_item and status_item.text() == "Queued":
                    item_ref = self.download_table.item(r, 0)
                    key = self._get_item_key(item_ref) if item_ref else None
                    if item_ref and key not in self.active_downloads:
                        url = item_ref.data(Qt.ItemDataRole.UserRole)
                        # Determine if this is a media (yt-dlp) row by checking stored format_spec data
                        format_spec = item_ref.data(Qt.ItemDataRole.UserRole + 6)
                        if format_spec is not None:
                            # Media download row — re-launch via start_media_download path
                            from core.media_downloader import YtDlpDownloadWorker
                            save_dir = os.path.dirname(item_ref.data(Qt.ItemDataRole.UserRole + 1) or "")
                            filename = item_ref.text()
                            is_audio_only = bool(item_ref.data(Qt.ItemDataRole.UserRole + 7))
                            cookies_browser = item_ref.data(Qt.ItemDataRole.UserRole + 9)
                            cookies_file = item_ref.data(Qt.ItemDataRole.UserRole + 10)
                            worker = YtDlpDownloadWorker(
                                url=url,
                                row_index=r,
                                save_dir=save_dir,
                                filename=filename,
                                format_spec=format_spec,
                                is_audio_only=is_audio_only,
                                cookies_browser=cookies_browser,
                                cookies_file=cookies_file
                            )
                            self.active_downloads[key] = worker
                            worker.main_progress_signal.connect(lambda _, data, ref=item_ref: self.update_download_row(ref, data))
                            worker.finished_signal.connect(lambda _, path, ref=item_ref, k=key: self._on_media_download_finished(k, ref, path))
                            self._set_status_text(r, "Downloading...")
                            worker.start()
                        else:
                            # Regular HTTP download row
                            self._start_download_worker(url, item_ref)
                        started = True
                        break
            if not started:
                break


    def _handle_options_accepted(self):
        # Restart aria2 daemon to apply new port/token
        if hasattr(self, 'aria2_process') and self.aria2_process:
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
        from core.version import VERSION
        QMessageBox.about(
            self,
            "About Bengal Download Manager",
            f"""
            <h2>Bengal Download Manager</h2>

            <p>
            Lightweight open-source download manager built with PyQt6 and Aria2
            featuring multi-threaded downloading.
            </p>

            <p>
            <b>Version:</b> {VERSION}<br>
            <b>License:</b> MIT License<br>
            © 2026 <a>tazihad</a> <a href='https://zihad.com.bd'>https://zihad.com.bd</a><br>
            Contact: <a href='mailto:tazihad@gmail.com'>tazihad@gmail.com</a>
            </p>

            <p>
            <b>Project Site:</b><br>
            <a href='https://github.com/tazihad/bengal-download-manager'>https://github.com/tazihad/bengal-download-manager</a>
            </p>
            """
        )

