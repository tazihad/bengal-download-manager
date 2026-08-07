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
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu,
    QFileIconProvider, QInputDialog, QDialog, 
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit,
    QSystemTrayIcon, QRubberBand
)
from PyQt6.QtGui import QAction, QFont, QCloseEvent, QIcon, QColor, QPalette, QDesktopServices, QKeySequence, QPixmap, QImage
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase, QUrl, QTimer, QThread, pyqtSignal, QObject, QEvent, QPoint, QRect, QItemSelectionModel, QItemSelection
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


from core.workers import DownloadWorker, Aria2Worker
from ui.dialogs import (
    AddUrlDialog, OptionsDialog, DownloadProgressDialog, 
    PropertiesDialog, DownloadCompleteDialog, ColumnDialog, DeleteDialog, RenameDialog
)
from core.config import load_category_config
from core.utils import (
    get_data_dir, get_config_dir, get_unique_filepath, ensure_aria2, 
    load_proxy_config, load_extension_config, generate_proxychains_config, get_proxychains_bin,
    show_in_folder, resolve_filename, open_file_generic, open_with, choose_portal_save_path
)

# Default TCP port for extension communication
DM_CONNECTOR_PORT = 9000 

# --- IPC HELPER THREAD ---
class SignalEmitter(QObject):
    """Utility to emit signals safely to the GUI thread."""
    new_download_signal = pyqtSignal(str)

class IPCRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):

        ext_data = load_extension_config()
        config_json = json.dumps({
            "status": "Bengal DM is running",
            "aria2": {
                "port": ext_data.get("port", 56800),
                "token": ext_data.get("token", "")
            }
        })
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(config_json.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        url = ""
        user_agent = ""
        cookies = ""
        
        try:
            payload = json.loads(body)
            url = payload.get("url", "")
            user_agent = payload.get("userAgent", "")
            cookies = payload.get("cookies", "")
        except json.JSONDecodeError:
            url = body
            
        if url and url.startswith("http"):
            # self.server.emitter is passed when initializing the server
            self.server.emitter.new_download_signal.emit(f"{url}|{user_agent}|{cookies}")
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
    def log_message(self, format, *args):
        pass # Suppress default logging to stderr

class TcpListenerThread(QThread):
    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.server = None

    def run(self):
        try:
            self.server = HTTPServer(('127.0.0.1', self.port), IPCRequestHandler)
            # Attach emitter to server so handler can access it
            self.server.emitter = self.emitter 
            self.server.serve_forever()
        except Exception as e:
            pass

    def stop(self):
        if self.server:
            # shutdown() must be called from another thread
            def cleanup():
                self.server.shutdown()
                self.server.server_close()
            threading.Thread(target=cleanup, daemon=True).start()

# --- SINGLE INSTANCE IPC HELPERS ---
def get_single_instance_key():
    import getpass
    user_identifier = str(os.getuid()) if hasattr(os, 'getuid') else getpass.getuser()
    return f"bengal-download-manager-single-instance-{user_identifier}"

class SingleInstanceServer(QObject):
    messageReceived = pyqtSignal(dict)

    def __init__(self, key=None, parent=None):
        super().__init__(parent)
        self.key = key or get_single_instance_key()
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_new_connection)

    def start(self):
        QLocalServer.removeServer(self.key)
        if not self.server.listen(self.key):
            print(f"Warning: SingleInstanceServer could not listen on key '{self.key}': {self.server.errorString()}")

    def stop(self):
        if self.server and self.server.isListening():
            self.server.close()
            QLocalServer.removeServer(self.key)

    def _on_new_connection(self):
        client = self.server.nextPendingConnection()
        if client:
            client.readyRead.connect(lambda c=client: self._read_client(c))

    def _read_client(self, client):
        try:
            data = client.readAll().data()
            if data:
                payload = json.loads(data.decode('utf-8'))
                self.messageReceived.emit(payload)
        except Exception as e:
            print(f"SingleInstanceServer read error: {e}")
        finally:
            client.deleteLater()

def check_single_instance(key=None, timeout_ms=500):
    """
    Attempts to connect to an existing running instance of Bengal Download Manager.
    If connected, sends invocation arguments to the primary instance and returns True.
    Otherwise returns False.
    """
    target_key = key or get_single_instance_key()
    socket = QLocalSocket()
    socket.connectToServer(target_key)
    if socket.waitForConnected(timeout_ms):
        msg_payload = {
            "command": "show",
            "args": sys.argv[1:]
        }
        data = json.dumps(msg_payload).encode('utf-8')
        socket.write(data)
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return True
    return False


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

ACCENT_COLORS = {
    "BDM (Default)": "#3daee9",
    "BDM": "#3daee9",
    "Default / Auto": None,
    "Breeze Blue": "#3daee9",
    "Ubuntu Orange": "#e95420",
    "Windows Blue": "#0078d4",
    "Dracula Purple": "#bd93f9",
    "Nord Frost": "#88c0d0",
    "Emerald Green": "#2ecc71",
    "Crimson Red": "#e74c3c",
    "Amethyst Violet": "#9b59b6"
}

def _build_palette(bg, text, base, alt, btn, link, hl, hl_text, accent=None):
    if accent and accent in ACCENT_COLORS and ACCENT_COLORS[accent]:
        hl = ACCENT_COLORS[accent]
        link = ACCENT_COLORS[accent]
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(text))
    pal.setColor(QPalette.ColorRole.Base, QColor(base))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(alt))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(alt))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(text))
    pal.setColor(QPalette.ColorRole.Text, QColor(text))
    pal.setColor(QPalette.ColorRole.Button, QColor(btn))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ff5555"))
    pal.setColor(QPalette.ColorRole.Link, QColor(link))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(hl))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(hl_text))
    return pal


def normalize_theme_name(name, default="BDM Dark (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm dark", "bdmdark", "dark", "bdm dark (default)"):
        return "BDM Dark (Default)"
    if s_lower in ("bdm light", "bdmlight", "light"):
        return "BDM Light"
    if s_lower in ("automatic", "auto"):
        return "Automatic"
    return s


def normalize_accent_name(name, default="BDM (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm", "bdm (default)", "default"):
        return "BDM (Default)"
    return s


def normalize_icon_theme_name(name, default="BDM (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("bdm", "bdm (default)", "default"):
        return "BDM (Default)"
    return s


def normalize_tray_icon_name(name, default="App Icon (Default)"):
    if not name:
        return default
    s = str(name).strip()
    s_lower = s.lower()
    if s_lower in ("app icon", "app_icon", "app icon (default)", "default", "bdm app icon"):
        return "App Icon (Default)"
    return s


CURRENT_TRAY_ICON = "App Icon (Default)"


def apply_app_theme(theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None, app=None):
    """
    Applies application theme ('Automatic', 'BDM Light', 'BDM Dark', 'Ubuntu Light', 'Ubuntu Dark',
    'IDM Classic', 'Kirigami Light', 'Kirigami Dark', 'Breeze Light', 'Breeze Dark',
    'Dracula', 'Nord', 'One Dark', 'Catppuccin', 'Solarized Light', 'Solarized Dark'),
    custom accent color, custom toolbar icon set, and custom system tray icon set.
    """
    if app is None:
        app = QApplication.instance()
    if not app:
        return

    sh = app.styleHints()
    theme_lower = str(theme_name).strip().lower()

    if theme_lower in ("ubuntu light", "ubuntulight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#f7f7f7", "#333333", "#ffffff", "#e8e8e8", "#e8e8e8", "#e95420", "#e95420", "#ffffff", accent=accent_name))
    elif theme_lower in ("ubuntu dark", "ubuntudark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#300a24", "#ffffff", "#1e0617", "#3c102d", "#3c102d", "#e95420", "#e95420", "#ffffff", accent=accent_name))
    elif theme_lower in ("idm classic", "idm", "windows classic"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#f0f0f0", "#000000", "#ffffff", "#f7f7f7", "#e1e1e1", "#0066cc", "#0078d4", "#ffffff", accent=accent_name))
    elif theme_lower in ("kirigami light", "kirigamilight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#fcfcfc", "#232629", "#ffffff", "#f5f5f5", "#f5f5f5", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("kirigami dark", "kirigamidark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#232629", "#fcfcfc", "#1b1e20", "#2a2e32", "#31363b", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower == "dracula":
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#282a36", "#f8f8f2", "#1e1f29", "#44475a", "#44475a", "#8be9fd", "#bd93f9", "#282a36", accent=accent_name))
    elif theme_lower == "nord":
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#2e3440", "#eceff4", "#242933", "#3b4252", "#3b4252", "#88c0d0", "#88c0d0", "#2e3440", accent=accent_name))
    elif theme_lower in ("one dark", "onedark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#21252b", "#abb2bf", "#1b1d23", "#282c34", "#282c34", "#61afef", "#61afef", "#1b1d23", accent=accent_name))
    elif theme_lower in ("catppuccin", "catppuccin mocha"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#1e1e2e", "#cdd6f4", "#181825", "#313244", "#313244", "#89b4fa", "#cba6f7", "#1e1e2e", accent=accent_name))
    elif theme_lower in ("solarized light", "solarizedlight"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#fdf6e3", "#657b83", "#eee8d5", "#fdf6e3", "#eee8d5", "#268bd2", "#268bd2", "#ffffff", accent=accent_name))
    elif theme_lower in ("solarized dark", "solarizeddark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#002b36", "#839496", "#073642", "#002b36", "#073642", "#268bd2", "#268bd2", "#ffffff", accent=accent_name))
    elif theme_lower in ("breeze dark", "breezedark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#2a2e32", "#eff0f1", "#232629", "#31363b", "#31363b", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("breeze light", "breezelight", "breeze white", "breezewhite"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#eff0f1", "#232629", "#fcfcfc", "#eef0f2", "#eef0f2", "#2980b9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("bdm light", "bdmlight", "light"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Light)
        app.setPalette(_build_palette("#eff0f1", "#232629", "#ffffff", "#f8f9fa", "#eef0f2", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))
    elif theme_lower in ("bdm dark (default)", "bdm dark", "bdmdark", "dark"):
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Dark)
        app.setPalette(_build_palette("#202326", "#eff0f1", "#141618", "#1c1e20", "#2a2e32", "#3daee9", "#3daee9", "#ffffff", accent=accent_name))
    else:  # Automatic
        if hasattr(sh, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            sh.setColorScheme(Qt.ColorScheme.Unknown)
        app.setPalette(app.style().standardPalette())
        if accent_name and accent_name in ACCENT_COLORS and ACCENT_COLORS[accent_name]:
            p = QPalette(app.palette())
            p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_COLORS[accent_name]))
            p.setColor(QPalette.ColorRole.Link, QColor(ACCENT_COLORS[accent_name]))
            app.setPalette(p)

    # Icon theme handling
    global CURRENT_ICON_THEME, CURRENT_TRAY_ICON
    if icon_theme_name:
        CURRENT_ICON_THEME = str(icon_theme_name).strip()
    else:
        CURRENT_ICON_THEME = "BDM (Default)"

    if tray_icon_name:
        CURRENT_TRAY_ICON = str(tray_icon_name).strip()
    else:
        CURRENT_TRAY_ICON = "App Icon (Default)"

    if icon_theme_name and str(icon_theme_name).lower() not in ("automatic", "bdm", "bdm (default)"):
        icon_lower = str(icon_theme_name).strip().lower()
        icon_map = {
            "breeze": "breeze",
            "breeze dark": "breeze-dark",
            "ubuntu": "ubuntu-mono-dark",
            "adwaita": "Adwaita",
            "highcolor": "hicolor"
        }
        if icon_lower in icon_map:
            QIcon.setThemeName(icon_map[icon_lower])
        else:
            QIcon.setThemeName(str(icon_theme_name))
    else:
        ensure_adaptive_icon_theme(app)

    if not app.styleSheet():
        app.setStyleSheet("""
            QMenuBar {
                background-color: palette(window);
                color: palette(window-text);
            }
            QMenuBar::item {
                background-color: transparent;
                color: palette(window-text);
                padding: 4px 10px;
            }
            QMenuBar::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            QMenu {
                background-color: palette(window);
                color: palette(window-text);
                border: 1px solid palette(mid);
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: palette(window-text);
                padding: 5px 24px 5px 12px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            QMenu::separator {
                height: 1px;
                background-color: palette(mid);
                margin: 4px 6px;
            }
        """)

    for w in app.allWidgets():
        try:
            w.setPalette(app.palette())
            app.style().unpolish(w)
            app.style().polish(w)
            w.update()
        except Exception:
            pass

    for top in app.topLevelWidgets():
        try:
            refresh_fn = getattr(top, "refresh_theme_ui", None)
            if callable(refresh_fn):
                refresh_fn()
            top.update()
            top.repaint()
        except Exception:
            pass


def ensure_adaptive_icon_theme(app=None):
    """
    Ensures icon search paths and active icon theme adapt cleanly to system/app
    light and dark themes (specifically resolving dark toolbar icons in Flatpak mode).
    """
    search_paths = QIcon.themeSearchPaths()
    for p in ["/app/share/icons", "/usr/share/icons", os.path.expanduser("~/.local/share/icons")]:
        if os.path.exists(p) and p not in search_paths:
            search_paths.append(p)
    QIcon.setThemeSearchPaths(search_paths)

    if app is None:
        app = QApplication.instance()
    if not app:
        return

    window_color = app.palette().color(QPalette.ColorRole.Window)
    text_color = app.palette().color(QPalette.ColorRole.WindowText)
    is_dark = window_color.value() < 128 or text_color.value() > 128

    current_theme = QIcon.themeName()
    if is_dark:
        if not (current_theme.endswith("-dark") or "dark" in current_theme.lower()):
            dark_candidates = [f"{current_theme}-dark", "breeze-dark", "ubuntu-mono-dark", "Adwaita-dark"]
            for candidate in dark_candidates:
                found = False
                for sp in search_paths:
                    if os.path.exists(os.path.join(sp, candidate)):
                        QIcon.setThemeName(candidate)
                        found = True
                        break
                if found:
                    break


def _get_pixmap_luminance(pm):
    img = pm.toImage()
    if img.isNull() or img.width() == 0 or img.height() == 0:
        return None
    r, g, b, count = 0, 0, 0, 0
    for x in range(img.width()):
        for y in range(img.height()):
            c = img.pixelColor(x, y)
            if c.alpha() > 50:
                r += c.red()
                g += c.green()
                b += c.blue()
                count += 1
    if count == 0:
        return None
    avg_r, avg_g, avg_b = r / count, g / count, b / count
    return 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b


def _invert_pixmap(pm):
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for x in range(img.width()):
        for y in range(img.height()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                img.setPixelColor(x, y, QColor(255 - c.red(), 255 - c.green(), 255 - c.blue(), c.alpha()))
    return QPixmap.fromImage(img)


CURRENT_ICON_THEME = "Automatic"

FREEDESKTOP_MAP = {
    "add_url": ["list-add", "document-new", "add"],
    "resume": ["media-playback-start", "go-down", "start"],
    "stop": ["process-stop", "media-playback-stop", "stop"],
    "stop_all": ["process-stop", "media-playback-stop", "stop"],
    "delete": ["user-trash", "edit-delete", "delete"],
    "clear_completed": ["edit-clear-all", "edit-clear", "clear"],
    "options": ["preferences-system", "configure", "settings"],
    "open_folder": ["folder-open", "folder-download", "folder"],
    "all_downloads": ["folder-download", "emblem-downloads", "download", "folder"],
    "compressed": ["package-x-generic", "application-x-archive", "archive"],
    "documents": ["x-office-document", "document", "text-x-generic"],
    "music": ["audio-x-generic", "audio", "sound"],
    "programs": ["system-run", "application-x-executable", "system"],
    "video": ["video-x-generic", "video", "media-video"],
    "unfinished": ["emblem-synchronizing", "process-working", "sync"],
    "finished": ["emblem-default", "dialog-ok", "check"],
    "exit": ["application-exit", "system-log-out", "exit"],
    "show_hide": ["window-new", "view-restore", "go-home"]
}


def get_themed_icon(name, fallback=None):
    """
    Returns an icon for the given symbol name.
    If a custom system icon theme is active (e.g. Breeze, Ubuntu, Adwaita), resolves from system icons.
    Otherwise, returns the clean minimal vector stroke monochrome icon from ui/icons.py.
    """
    global CURRENT_ICON_THEME

    if CURRENT_ICON_THEME and str(CURRENT_ICON_THEME).lower() not in ("automatic", "bdm", "bdm (default)"):
        aliases = FREEDESKTOP_MAP.get(name, [name])
        for alias in aliases:
            ic = QIcon.fromTheme(alias)
            if not ic.isNull() and ic.name() != "":
                return ic

    if name in ("tray", "app_icon"):
        return get_monochrome_app_icon()

    from ui.icons import get_monochrome_icon
    icon = get_monochrome_icon(name)
    if not icon.isNull():
        return icon
    
    ensure_adaptive_icon_theme()
    icon = QIcon.fromTheme(name)
    if (icon.isNull() or icon.name() == "") and fallback:
        icon = fallback if isinstance(fallback, QIcon) else QIcon(fallback)
    return icon


def get_themed_tray_icon(tray_option=None):
    """
    Resolves system tray icon based on tray icon theme selection.
    Options: 'App Icon (Default)', 'Automatic', 'Monochrome Light', 'Monochrome Dark'.
    """
    global CURRENT_TRAY_ICON
    if tray_option is None:
        tray_option = CURRENT_TRAY_ICON if CURRENT_TRAY_ICON else "App Icon (Default)"

    opt_lower = str(tray_option).strip().lower()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)

    light_path = os.path.join(root_dir, "assets", "tray_monochrome_light.png")
    dark_path = os.path.join(root_dir, "assets", "tray_monochrome_dark.png")
    if not os.path.exists(light_path):
        light_path = os.path.join(current_dir, "assets", "tray_monochrome_light.png")
    if not os.path.exists(dark_path):
        dark_path = os.path.join(current_dir, "assets", "tray_monochrome_dark.png")

    if opt_lower in ("app icon (default)", "app icon", "app_icon", "bdm app icon"):
        icon = get_app_icon()
        if not icon.isNull():
            return icon
    elif opt_lower in ("monochrome light", "monochromelight"):
        if os.path.exists(light_path):
            ic = QIcon(light_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon(color=QColor("#ffffff"))
    elif opt_lower in ("monochrome dark", "monochromedark"):
        if os.path.exists(dark_path):
            ic = QIcon(dark_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon(color=QColor("#232629"))
    elif opt_lower == "automatic":
        app = QApplication.instance()
        text_val = app.palette().color(QPalette.ColorRole.WindowText).value() if app else 255
        target_path = light_path if text_val > 128 else dark_path
        if os.path.exists(target_path):
            ic = QIcon(target_path)
            if not ic.isNull():
                return ic
        return get_monochrome_app_icon()

    icon = get_app_icon()
    if not icon.isNull():
        return icon
    app = QApplication.instance()
    if app:
        return app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    return QIcon()


CATEGORY_EXTENSIONS = {
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt"],
    "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"],
    "Programs": [".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"]
}

def get_category_for_filename(filename):
    if not filename:
        return "General"
    fn = filename.lower()
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if any(fn.endswith(ext) for ext in exts):
            return cat
    return "General"

def get_file_icon(filename):
    if not filename:
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    ext = os.path.splitext(filename)[1].lower()

    # Prioritize specific vector stroke icons for binary executables & installer packages
    if ext in [".exe", ".msi"]:
        return get_themed_icon("exe")
    elif ext == ".appimage":
        return get_themed_icon("appimage")
    elif ext == ".flatpak":
        return get_themed_icon("flatpak")
    elif ext in [".deb", ".rpm", ".apk", ".snap", ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"]:
        return get_themed_icon("programs")

    db = QMimeDatabase()
    mime = db.mimeTypeForFile(filename, QMimeDatabase.MatchMode.MatchExtension)
    if mime.isValid():
        icon_name = mime.iconName()
        icon = get_themed_icon(icon_name)
        if not icon.isNull() and icon.name() != "":
            return icon
        generic_name = mime.genericIconName()
        if generic_name:
            g_icon = get_themed_icon(generic_name)
            if not g_icon.isNull() and g_icon.name() != "":
                return g_icon

    info = QFileInfo(filename)
    provider = QFileIconProvider()
    icon = provider.icon(info)
    if not icon.isNull():
        return icon

    cat = get_category_for_filename(filename)
    fallbacks = {
        "Programs": get_themed_icon("system-run", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMenuButton)),
        "Compressed": get_themed_icon("package-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DriveFDIcon)),
        "Documents": get_themed_icon("x-office-document", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)),
        "Music": get_themed_icon("audio-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)),
        "Video": get_themed_icon("video-x-generic", QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)),
    }
    return fallbacks.get(cat, QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

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
    """Robustly finds and returns the application icon across local, AppImage, and Flatpak environments."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    icon_locations = [
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "logo.png"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "logo.svg"),
        # Flatpak specific icon paths
        "/app/share/icons/hicolor/256x256/apps/io.github.tazihad.bengal-download-manager.png",
        "/app/share/icons/hicolor/scalable/apps/io.github.tazihad.bengal-download-manager.svg",
        "/app/share/icons/hicolor/256x256/apps/bengal-download-manager.png",
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/io.github.tazihad.bengal-download-manager.png"),
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

    # Theme icon fallbacks (Flatpak / Desktop theme name)
    for theme_name in ["io.github.tazihad.bengal-download-manager", "bengal-download-manager"]:
        icon = QIcon.fromTheme(theme_name)
        if not icon.isNull():
            return icon
                
    # Fallback to system icon if nothing found
    return QIcon.fromTheme("system-run", QIcon(":/icons/fallback.png")) # Just a safe fallback


def get_monochrome_app_icon(color=None, size=24):
    """
    Converts the Bengal Download Manager application logo into a clean, sharp
    monochrome icon adapting to light/dark window text colors for system tray.
    """
    app = QApplication.instance()
    if color is None:
        if app:
            color = app.palette().color(QPalette.ColorRole.WindowText)
        else:
            color = QColor("#ffffff")

    app_ic = get_app_icon()
    if app_ic.isNull():
        return app_ic
    
    pm = app_ic.pixmap(size * 2, size * 2)
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    
    r, g, b, _ = color.getRgb()
    for x in range(img.width()):
        for y in range(img.height()):
            pixel_color = img.pixelColor(x, y)
            alpha = pixel_color.alpha()
            if alpha > 0:
                img.setPixelColor(x, y, QColor(r, g, b, alpha))
                
    mono_pm = QPixmap.fromImage(img)
    ic = QIcon()
    ic.addPixmap(mono_pm)
    return ic

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
        
        self.settings = self.load_settings()
        
        # FEATURE: Start Minimized logic
        if getattr(self, "start_minimized", False):
            # We use a timer to hide because some window managers might show it briefly otherwise
            QTimer.singleShot(0, self.hide)
            # Update tray icon action to "Show"
            QTimer.singleShot(0, self.update_tray_action)
        
        self.active_downloads = {} 
        self.active_file_info_dialogs = {}
        self.active_complete_dialogs = {}
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

        if self.start_ipc:
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
        
        if hasattr(self, 'single_instance_server') and self.single_instance_server:
            self.single_instance_server.stop()

        
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

    def changeEvent(self, event):
        if event and event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            ensure_adaptive_icon_theme(QApplication.instance())
            self.setup_actions()
            self.setup_toolbar()
        super().changeEvent(event)

    # --- DRAG AND DROP HANDLERS ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.process_incoming_url(url.toString())

    def setup_actions(self):
        self.action_add_url = QAction(get_themed_icon("add_url"), "Add URL", self)
        self.action_add_url.setShortcut(QKeySequence("Ctrl+V"))
        self.action_add_url.setToolTip("Add a new download URL address (Ctrl+V)")
        self.action_add_url.triggered.connect(self.open_add_url)

        self.action_exit = QAction(get_themed_icon("exit"), "Exit", self)
        self.action_exit.setToolTip("Exit Bengal Download Manager")
        self.action_exit.triggered.connect(self.quit_app)

        self.action_stop = QAction(get_themed_icon("stop"), "Stop/Pause", self)
        self.action_stop.setToolTip("Pause or stop selected download(s)")
        self.action_stop.triggered.connect(self.stop_selected_download)
        self.action_stop.setEnabled(False)

        self.action_stop_all = QAction(get_themed_icon("stop_all"), "Stop All", self)
        self.action_stop_all.setToolTip("Pause or stop all currently active downloads")
        self.action_stop_all.triggered.connect(self.stop_all_downloads)
        self.action_stop_all.setEnabled(False)

        self.action_resume = QAction(get_themed_icon("resume"), "Resume", self)
        self.action_resume.setToolTip("Resume downloading selected file(s)")
        self.action_resume.triggered.connect(self.resume_selected_download)
        self.action_resume.setEnabled(False)
        
        self.action_download_now = QAction(get_themed_icon("resume"), "Download Now", self)
        self.action_download_now.setToolTip("Start downloading selected file immediately")
        self.action_download_now.triggered.connect(self.resume_selected_download) 
        
        self.action_redownload = QAction(get_themed_icon("unfinished"), "Redownload", self)
        self.action_redownload.setToolTip("Restart download from the beginning")
        self.action_redownload.triggered.connect(self.redownload_selected)

        self.action_delete = QAction(get_themed_icon("delete"), "Delete", self)
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

        self.action_open_folder = QAction(get_themed_icon("open_folder"), "Open Downloads Folder", self)
        self.action_open_folder.setToolTip("Open default downloads directory")
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
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
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
        self.category_tree.setRootIsDecorated(False)
        self.category_tree.setIconSize(QSize(18, 18))
        self.category_tree.setIndentation(10)
        self.category_tree.setAnimated(True)
        self.category_tree.itemClicked.connect(self.filter_downloads)

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
                color: palette(highlighted-text);
            }
            QTreeWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                font-weight: 600;
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

        all_downloads = QTreeWidgetItem(self.category_tree, ["All Downloads"])
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

        item_unfinished = QTreeWidgetItem(self.category_tree, ["Unfinished"])
        item_unfinished.setIcon(0, get_themed_icon("unfinished"))
        item_unfinished.setToolTip(0, "Show active, paused, or pending downloads")

        item_finished = QTreeWidgetItem(self.category_tree, ["Finished"])
        item_finished.setIcon(0, get_themed_icon("finished"))
        item_finished.setToolTip(0, "Show completed downloads")

        self.category_tree.setCurrentItem(all_downloads)
        
        self.download_table = QTableWidget()
        self.download_table.setIconSize(QSize(16, 16))
        self.download_table.setColumnCount(7)
        self.download_table.verticalHeader().setVisible(False)
        
        # Ensure row selection is correctly set up
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Install event filter to clear selection on empty area click
        self.empty_area_filter = EmptyAreaClickFilter(self.download_table, self)
        self.download_table.viewport().installEventFilter(self.empty_area_filter)

        # FIX: Remove blue cell highlight (focus rectangle) on selection

        self.download_table.setStyleSheet("""
            QTableWidget::item:focus { 
                border: none; 
                outline: 0; 
                background: transparent; 
            }
            QHeaderView::section {
                font-weight: normal;
            }
        """)

        self.download_table.itemSelectionChanged.connect(self.update_ui_states)
        
        self.download_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self.show_context_menu)
        
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

    def setup_tray_icon(self):
        """Sets up the system tray icon and its context menu safely."""
        self.tray_icon = None
        self.action_tray_toggle = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        try:
            self.tray_icon = QSystemTrayIcon(self)

            # Set monochrome app icon for tray
            icon = get_monochrome_app_icon()
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
            tray_menu.addAction(self.action_options)
            tray_menu.addSeparator()
            tray_menu.addAction(self.action_exit)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
            
            # Double click to show/hide
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
        except Exception as e:
            print(f"Warning: System tray icon initialization failed ({e})")
            self.tray_icon = None

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def restore_window(self):
        """Restores the window from minimized or hidden state and brings it to the foreground."""
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_tray_action()

    def toggle_window(self):
        """Toggles the visibility of the main window."""
        if self.isVisible() and not self.isMinimized():
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
        # Logic fix: Allow resume even if active (window open) if the status is logically paused
        self.action_resume.setEnabled(selection_has_resumable)
        self.action_download_now.setEnabled(selection_has_resumable)
        
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
        ext_map = CATEGORY_EXTENSIONS

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
                item_name.setToolTip(filename)
                
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
                raw_status = d.get("status", "0.00%")
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

            self.download_table.setSortingEnabled(True)
            
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

        # Apply font/styling only if needed or newly created
        if col in [1, 2, 3, 4, 5, 6]:
            # Use UserRole+10 as a flag to avoid redundant font applications
            if created or not item.data(Qt.ItemDataRole.UserRole + 10):
                font = QFont(QApplication.font())
                font.setFeature(QFont.Tag.fromString('tnum'), 1)
                if col in [1, 2, 3, 4]:
                    font.setBold(True)
                item.setFont(font)
                item.setData(Qt.ItemDataRole.UserRole + 10, True)
            
        raw_val = parser_func(text)
        if item.data(Qt.ItemDataRole.UserRole) != raw_val:
            item.setData(Qt.ItemDataRole.UserRole, raw_val)

    def _set_status_text(self, row, text):
        item = self.download_table.item(row, 2)
        created = False
        if not item:
            item = QTableWidgetItem(text)
            self.download_table.setItem(row, 2, item)
            created = True
        elif item.text() != text:
            item.setText(text)
            
        item.setToolTip(f"Status: {text}" if text else "Status: N/A")

        # Apply bold font with tabular figures only if needed
        if created or not item.data(Qt.ItemDataRole.UserRole + 10):
            font = QFont(QApplication.font())
            font.setFeature(QFont.Tag.fromString('tnum'), 1)
            font.setBold(True)
            item.setFont(font)
            item.setData(Qt.ItemDataRole.UserRole + 10, True)

    def _set_timestamp_item(self, row, col, text):
        item = self.download_table.item(row, col)
        if not item:
            item = QTableWidgetItem(text)
            self.download_table.setItem(row, col, item)
        elif item.text() != text:
            item.setText(text)
            
        col_name = "Last Attempt" if col == 5 else "Date Added"
        item.setToolTip(f"{col_name}: {text}" if text else f"{col_name}: N/A")

        if not item.data(Qt.ItemDataRole.UserRole + 10):
            font = QFont(QApplication.font())
            font.setFeature(QFont.Tag.fromString('tnum'), 1)
            item.setFont(font)
            item.setData(Qt.ItemDataRole.UserRole + 10, True)
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
                key = id(item)
                if key in self.active_downloads:
                    self.active_downloads[key].worker.stop()

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
                "icon_theme": getattr(self, "settings", {}).get("icon_theme", "BDM (Default)"),
                "tray_icon": getattr(self, "settings", {}).get("tray_icon", "App Icon (Default)")
            }
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def apply_appearance_setting(self, theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None):
        if not hasattr(self, "settings") or not isinstance(self.settings, dict):
            self.settings = {}
        self.settings["theme"] = theme_name
        self.settings["accent"] = accent_name
        self.settings["icon_theme"] = icon_theme_name
        self.settings["tray_icon"] = tray_icon_name
        apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name)
        self.save_settings()
        self.refresh_theme_ui()

    def preview_appearance(self, theme_name, accent_name=None, icon_theme_name=None, tray_icon_name=None):
        apply_app_theme(theme_name, accent_name, icon_theme_name, tray_icon_name)
        self.refresh_theme_ui()

    def apply_theme_setting(self, theme_name):
        accent_name = getattr(self, "settings", {}).get("accent", "BDM (Default)")
        icon_theme_name = getattr(self, "settings", {}).get("icon_theme", "BDM (Default)")
        tray_icon_name = getattr(self, "settings", {}).get("tray_icon", "App Icon (Default)")
        self.apply_appearance_setting(theme_name, accent_name, icon_theme_name, tray_icon_name)

    def refresh_theme_ui(self):
        # Refresh category tree style & icons
        if hasattr(self, "category_tree"):
            self.style().unpolish(self.category_tree)
            self.style().polish(self.category_tree)
            self.category_tree.update()
            root = self.category_tree.topLevelItem(0)
            if root:
                root.setIcon(0, get_themed_icon("all_downloads"))
                cat_icons = {
                    "Compressed": get_themed_icon("compressed"),
                    "Documents": get_themed_icon("documents"),
                    "Music": get_themed_icon("music"),
                    "Programs": get_themed_icon("programs"),
                    "Video": get_themed_icon("video")
                }
                for i in range(root.childCount()):
                    child = root.child(i)
                    if child and child.text(0) in cat_icons:
                        child.setIcon(0, cat_icons[child.text(0)])

            item_unfin = self.category_tree.topLevelItem(1)
            if item_unfin:
                item_unfin.setIcon(0, get_themed_icon("unfinished"))
            item_fin = self.category_tree.topLevelItem(2)
            if item_fin:
                item_fin.setIcon(0, get_themed_icon("finished"))

        # Refresh action icons
        action_icon_map = {
            "action_add_url": "add_url",
            "action_exit": "exit",
            "action_stop": "stop",
            "action_stop_all": "stop_all",
            "action_resume": "resume",
            "action_download_now": "resume",
            "action_redownload": "unfinished",
            "action_delete": "delete",
            "action_clear": "clear_completed",
            "action_options": "options",
            "action_open_folder": "open_folder"
        }
        for attr, icon_name in action_icon_map.items():
            if hasattr(self, attr):
                getattr(self, attr).setIcon(get_themed_icon(icon_name))

        if hasattr(self, "update_tray_action"):
            self.update_tray_action()

        if hasattr(self, "tray_icon") and self.tray_icon:
            global CURRENT_TRAY_ICON
            tray_opt = CURRENT_TRAY_ICON if CURRENT_TRAY_ICON else getattr(self, "settings", {}).get("tray_icon", "App Icon (Default)")
            tray_ic = get_themed_tray_icon(tray_opt)
            if not tray_ic.isNull():
                self.tray_icon.setIcon(tray_ic)

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

        self.update()
        self.repaint()

    def load_settings(self):
        settings = {
            "theme": "BDM Dark (Default)",
            "accent": "BDM (Default)",
            "icon_theme": "BDM (Default)",
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

        apply_app_theme(
            settings["theme"],
            settings["accent"],
            settings["icon_theme"],
            settings["tray_icon"]
        )
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
        
        act_open = QAction(get_themed_icon("documents"), "Open", self)
        act_open_with = QAction(get_themed_icon("documents"), "Open with...", self)
        act_open_folder = QAction(get_themed_icon("open_folder"), "Open folder", self)
        act_move = QAction(get_themed_icon("open_folder"), "Move...", self)
        act_rename = QAction(get_themed_icon("documents"), "Rename...", self)
        
        act_move.setEnabled(is_completed)
        act_rename.setEnabled(is_completed)
        act_open.setEnabled(is_completed)
        act_open_with.setEnabled(is_completed)
        
        menu.addActions([act_open, act_open_with, act_open_folder, act_move, act_rename])
        menu.addSeparator()
        
        # Enhanced State Logic for Context Menu
        act_stop = QAction(get_themed_icon("stop"), "Stop/Pause Download", self)
        act_stop.triggered.connect(self.stop_selected_download)
        act_stop.setEnabled(is_active and is_pausable)
        
        act_resume = QAction(get_themed_icon("resume"), "Resume download", self)
        act_resume.triggered.connect(self.resume_selected_download)
        act_resume.setEnabled(is_resumable and not is_active)
        
        act_redownload = QAction(get_themed_icon("unfinished"), "Redownload", self)
        act_refresh = QAction(get_themed_icon("clear_completed"), "Refresh download address", self)
        
        menu.addActions([act_resume, act_stop])
        menu.addSeparator()
        menu.addActions([act_redownload, act_refresh])
        menu.addSeparator()
        
        act_delete = QAction(get_themed_icon("delete"), "Delete", self)
        act_delete.triggered.connect(self.delete_selected_download)
        menu.addAction(act_delete)
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
        path = os.path.join(os.path.expanduser("~"), "Downloads")
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

        new_path = choose_portal_save_path("Move File", filename, folder)

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

        dialog = RenameDialog(old_filename, self)
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
        
        self._set_status_text(row, "Pending...")
        
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
        self._add_url_dialog = AddUrlDialog(self)
        if self._add_url_dialog.exec():
            self._handle_add_url_accepted(self._add_url_dialog)

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

        if not url:
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
                    return

        # 4. Start the fetcher
        from core.workers import FileInfoFetcherWorker
        fetcher = FileInfoFetcherWorker(url, user_agent=user_agent, cookies=cookies)
        self.active_fetchers.append(fetcher)
        
        # Connect to a wrapper that cleans up the thread memory when done
        fetcher.finished_signal.connect(lambda info, f=fetcher: self._handle_fetch_complete(info, f))
        fetcher.start()

    def _handle_fetch_complete(self, file_info, fetcher):
        # Remove the finished thread from memory
        if fetcher in self.active_fetchers:
            self.active_fetchers.remove(fetcher)
            
        # Trigger existing popup dialog!
        self.on_file_info_fetched(file_info)

    def on_file_info_fetched(self, file_info):
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

        # Top-level window (parent=None) sharing app WM_CLASS so it stacks under single app launcher icon
        dialog = DownloadFileInfoDialog(file_info, None)
        
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
        
        # Track the dialog to prevent garbage collection and allow cleanup
        dialog_id = id(item_ref)
        self.active_file_info_dialogs[dialog_id] = dialog
        dialog.finished.connect(lambda: self.active_file_info_dialogs.pop(dialog_id, None))

        # Connect signals to handle the dialog result
        dialog.accepted.connect(lambda: self._handle_download_dialog_accepted(dialog, file_info, item_ref))
        dialog.rejected.connect(lambda: self._handle_download_dialog_rejected(item_ref))
        
        # Show and bring to foreground without stealing focus for the main app
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _handle_download_dialog_accepted(self, dialog, file_info, item_ref):
        results = dialog.get_results()
        key = id(item_ref)
        
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
            self._start_download_worker(
                file_info["url"], 
                item_ref, 
                resume_filename=results["filename"],
                custom_save_dir=os.path.dirname(results["save_path"]),
                user_agent=file_info.get("user_agent")
            )
        elif results["action"] == 'later':
            self._set_status_text(row, "Paused")

    def _handle_download_dialog_rejected(self, item_ref):
        # User cancelled - remove the proposed download from the table
        row = self.download_table.row(item_ref)
        if row != -1:
            self.download_table.removeRow(row)
        self.save_data()

    def start_download(self, url, custom_filename=None, custom_save_dir=None, size_data=None, start_paused=False, show_dialog=True, user_agent=None, cookies=None):
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
        self._set_status_text(row, status_txt)
        
        self._set_sortable_item(row, 3, "", parse_time_to_sec) if start_paused else self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "", parse_size_to_bytes) if start_paused else self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        
        # Display formatted timestamp
        self._set_timestamp_item(row, 5, format_timestamp_relative(current_ts, max_relative_seconds=300))
        self._set_timestamp_item(row, 6, format_timestamp_relative(current_ts, max_relative_seconds=30))

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
            
            # If already active, bring dialog to front or resume if paused
            if id(item_name) in self.active_downloads:
                dialog = self.active_downloads[id(item_name)]
                status_item = self.download_table.item(row, 2)
                logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
                
                if logic_status in ["Paused", "Cancelled", "Error"]:
                    # Forward resume to existing worker
                    dialog.worker.resume()
                
                dialog.activateWindow()
                dialog.raise_()
                continue
            
            # Start/Resume download
            url = item_name.data(Qt.ItemDataRole.UserRole)
            filename = item_name.text()
            
            if url:
                self._set_status_text(row, "Resuming...")                
                # Update last try timestamp before resuming
                new_timestamp = str(time.time())
                item_name.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)
                self._set_timestamp_item(row, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                
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
                    self._set_timestamp_item(item.row(), 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
                    
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
                    self._set_timestamp_item(r, 5, format_timestamp_relative(new_timestamp, max_relative_seconds=300))
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
        
        # --- FIX: Block signals and disable sorting during update to prevent flickering ---
        sorting_was_enabled = self.download_table.isSortingEnabled()
        if sorting_was_enabled:
            self.download_table.setSortingEnabled(False)
        self.download_table.blockSignals(True)
        
        try:
            # --- Update Last Try Timestamp ---
            # Update the stored raw timestamp whenever progress is made
            new_timestamp = str(time.time())
            item_ref.setData(Qt.ItemDataRole.UserRole + 2, new_timestamp)

            new_name = data[0]
            if item_ref.text() != new_name:
                item_ref.setText(new_name)
                item_ref.setToolTip(new_name)
                item_ref.setIcon(get_file_icon(new_name))
            
            # Col 1: Size
            self._set_sortable_item(row, 1, data[1], parse_size_to_bytes)
            
            # Col 2: Status
            status_item = self.download_table.item(row, 2)
            old_status = ""
            if not status_item:
                 self._set_status_text(row, "")
                 status_item = self.download_table.item(row, 2)
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
                        self._set_status_text(row, "Complete")
                        status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            
            if display_status == "Downloading":
                final_display = pct_str if pct_str else "Downloading"
            elif display_status in ["Paused", "Cancelled"]:
                pct_data = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct_data if pct_data else display_status
            
            # CRITICAL: Always force "Complete" if that's the determined status
            if display_status == "Complete":
                final_display = "Complete"
                self._set_status_text(row, "Complete")
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
                
            # Check if internal logical status changed to trigger UI update
            old_logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1)
            
            if final_display != old_status or display_status != old_logic_status:
                self._set_status_text(row, final_display)
                
                # Update logical status and trigger UI states only if logical status changed
                if display_status != old_logic_status:
                    status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
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
            formatted_last_try = format_timestamp_relative(new_timestamp, max_relative_seconds=300)
            last_try_item = self.download_table.item(row, 5)
            if not last_try_item:
                self._set_timestamp_item(row, 5, formatted_last_try)
            elif last_try_item.text() != formatted_last_try:
                last_try_item.setText(formatted_last_try)
            
        finally:
            self.download_table.blockSignals(False)
            if sorting_was_enabled:
                self.download_table.setSortingEnabled(True)

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
                self._set_status_text(row, "")
                status_item = self.download_table.item(row, 2)
            
            # Formatting final display text and updating logical status
            status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            
            if display_status == "Complete":
                final_display = "Complete"
            elif display_status in ["Paused", "Cancelled"]:
                pct = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct if pct else "0.00%"
            else:
                final_display = display_status
            
            self._set_status_text(row, final_display)
            
            if display_status in ["Complete", "Error"]:
                 self._set_sortable_item(row, 3, "", parse_time_to_sec)
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)
            elif display_status in ["Paused", "Cancelled"]:
                 self._set_sortable_item(row, 4, "", parse_size_to_bytes)

            final_timestamp = str(time.time())
            item_ref.setData(Qt.ItemDataRole.UserRole + 2, final_timestamp)
            self._set_timestamp_item(row, 5, format_timestamp_relative(final_timestamp, max_relative_seconds=300))

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
            # Top-level window (parent=None) sharing app WM_CLASS so it stacks under single app launcher icon
            dialog = DownloadCompleteDialog(file_data, None)
            self.active_complete_dialogs[key] = dialog
            dialog.finished.connect(lambda: self.active_complete_dialogs.pop(key, None))
            dialog.show()
            
        self.update_ui_states()
        self.save_data()
        # Explicit repaint
        self.download_table.viewport().update()
    
    def open_options(self):
        from ui.dialogs import OptionsDialog
        if hasattr(self, "_options_dlg") and self._options_dlg and self._options_dlg.isVisible():
            self._options_dlg.raise_()
            self._options_dlg.activateWindow()
            return
        # Top-level window (parent=None) sharing app WM_CLASS so it appears as a separate icon in taskbar panel
        self._options_dlg = OptionsDialog(main_window=self)
        self._options_dlg.accepted.connect(self._handle_options_accepted)
        self._options_dlg.show()
        self._options_dlg.raise_()
        self._options_dlg.activateWindow()


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

if __name__ == "__main__":

    from PyQt6.QtCore import Qt

    try:
        from core.utils import get_config_dir
        _cfg_path = os.path.join(get_config_dir(), "settings.json")
        if os.path.exists(_cfg_path):
            with open(_cfg_path, "r") as _f:
                _s_data = json.load(_f)
                _scale_str = _s_data.get("ui_scale", "100%")
                if _scale_str and _scale_str != "100%":
                    _num_str = _scale_str.replace("%", "").strip()
                    _factor = float(_num_str) / 100.0
                    os.environ["QT_SCALE_FACTOR"] = str(_factor)
    except Exception:
        pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("bengal-download-manager")
    app.setApplicationName("bengal-download-manager")
    app.setDesktopFileName("io.github.tazihad.bengal-download-manager")
    app.setQuitOnLastWindowClosed(False)

    # --- SINGLE INSTANCE ENFORCEMENT ---
    if "--no-single-instance" not in sys.argv:
        if check_single_instance():
            print("Bengal Download Manager is already running. Primary instance brought to focus.")
            sys.exit(0)

    _saved_theme = "BDM Dark (Default)"
    _saved_accent = "BDM (Default)"
    _saved_icon_theme = "BDM (Default)"
    _saved_tray_icon = "App Icon (Default)"
    try:
        if os.path.exists(_cfg_path):
            with open(_cfg_path, "r") as _f:
                _s_data = json.load(_f)
                _saved_theme = normalize_theme_name(_s_data.get("theme"))
                _saved_accent = normalize_accent_name(_s_data.get("accent"))
                _saved_icon_theme = normalize_icon_theme_name(_s_data.get("icon_theme"))
                _saved_tray_icon = normalize_tray_icon_name(_s_data.get("tray_icon"))
    except Exception:
        pass

    apply_app_theme(_saved_theme, _saved_accent, _saved_icon_theme, _saved_tray_icon, app)

    app_font = QFont("Segoe UI", 9)
    app_font.setFeature(QFont.Tag.fromString('tnum'), 1)
    app.setFont(app_font)
    
    # Initialize and set global application icon
    app_icon = get_app_icon()
    if app_icon.isNull():
        # Last resort fallback to standard Qt icon
        app_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    app.setWindowIcon(app_icon)
    
    window = MainWindow()

    use_qml = "--qml" in sys.argv or "--kirigami" in sys.argv or os.environ.get("USE_KIRIGAMI") == "1"

    # Start single instance server on primary instance if enabled
    if "--no-single-instance" not in sys.argv:
        single_instance_server = SingleInstanceServer()
        def handle_single_instance_msg(payload):
            cmd = payload.get("command", "show")
            args = payload.get("args", [])
            if "--minimized" not in args:
                window.restore_window()
                if use_qml and 'qml_engine' in locals() and qml_engine.rootObjects():
                    for root in qml_engine.rootObjects():
                        if hasattr(root, "show"):
                            root.show()
                        if hasattr(root, "showNormal"):
                            root.showNormal()
                        if hasattr(root, "raise_"):
                            root.raise_()
                        if hasattr(root, "requestActivate"):
                            root.requestActivate()
            for arg in args:
                if isinstance(arg, str) and (arg.startswith("http://") or arg.startswith("https://")):
                    window.process_incoming_url(arg)

        single_instance_server.messageReceived.connect(handle_single_instance_msg)
        single_instance_server.start()
        window.single_instance_server = single_instance_server

    if "--minimized" in sys.argv:
        window.start_minimized = True
        QTimer.singleShot(0, window.hide)
        QTimer.singleShot(0, window.update_tray_action)
    else:
        window.start_minimized = False

    if use_qml:
        try:
            from PyQt6.QtQml import QQmlApplicationEngine
            from PyQt6.QtCore import QUrl
            from core.bridge import DownloadBridge

            qml_engine = QQmlApplicationEngine()
            qml_engine.addImportPath("/usr/lib/x86_64-linux-gnu/qt6/qml")
            bridge = DownloadBridge(main_window=window)
            qml_engine.rootContext().setContextProperty("downloadBridge", bridge)

            qml_file = os.path.join(os.path.dirname(__file__), "ui", "qml", "Main.qml")
            qml_engine.load(QUrl.fromLocalFile(qml_file))

            if qml_engine.rootObjects():
                sys.exit(app.exec())
            else:
                print("Failed to initialize QML root object. Falling back to native UI.")
        except Exception as e:
            print(f"Kirigami QML initialization skipped ({e}). Falling back to native UI.")

    if not getattr(window, "start_minimized", False):
        window.show()
    sys.exit(app.exec())