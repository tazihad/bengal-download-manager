import os
import json
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QWidget, QGroupBox, QProgressBar, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QGridLayout, 
    QMessageBox, QStyle, QLayout, QComboBox, QCheckBox, QSpinBox, QFileDialog,
    QRadioButton, QButtonGroup
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from utils import get_config_dir, load_proxy_config, save_proxy_config, load_extension_config, save_extension_config

# --- CONFIGURATION HELPERS ---
DEFAULT_CATEGORIES = {
    "General": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads"),
        "extensions": ""
    },
    "Compressed": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Compressed"),
        "extensions": "zip rar 7z tar gz iso"
    },
    "Documents": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Documents"),
        "extensions": "pdf doc docx txt ppt pptx xls xlsx"
    },
    "Music": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Music"),
        "extensions": "mp3 wav aac flac ogg"
    },
    "Programs": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Programs"),
        "extensions": "exe msi sh bin deb bat"
    },
    "Video": {
        "path": os.path.join(os.path.expanduser("~"), "Downloads", "Video"),
        "extensions": "mp4 mkv avi mov wmv flv"
    }
}

def load_category_config():
    path = os.path.join(get_config_dir(), "categories.json")
    data = {"categories": DEFAULT_CATEGORIES, "temp_dir": os.path.join(os.path.expanduser("~"), ".cache", "bengal-dm")}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
                for cat, defaults in DEFAULT_CATEGORIES.items():
                    if cat not in loaded["categories"]:
                        loaded["categories"][cat] = defaults
                return loaded
        except:
            pass
    return data

def save_category_config(data):
    path = os.path.join(get_config_dir(), "categories.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

# --- ADD URL DIALOG ---
class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new address to download")
        self.setMinimumWidth(500)
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


# --- DOWNLOAD FILE INFO DIALOG ---
class DownloadFileInfoDialog(QDialog):
    def __init__(self, file_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download File Info")
        self.setFixedWidth(550)
        self.file_info = file_info
        
        self.layout = QVBoxLayout(self)
        
        # Determine category automatically
        self.ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
            "Programs": [".exe", ".msi", ".sh", ".bin", ".deb", ".bat"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }
        
        from PyQt6.QtWidgets import QFormLayout
        form_layout = QFormLayout()
        
        self.url_input = QLineEdit(file_info.get("url", ""))
        self.url_input.setReadOnly(True)
        form_layout.addRow("URL:", self.url_input)
        
        self.category_combo = QComboBox()
        categories = ["General", "Compressed", "Documents", "Music", "Programs", "Video"]
        self.category_combo.addItems(categories)
        form_layout.addRow("Category:", self.category_combo)
        
        save_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.clicked.connect(self.browse_save_path)
        save_layout.addWidget(self.save_input)
        save_layout.addWidget(self.btn_browse)
        form_layout.addRow("Save As:", save_layout)
        
        self.lbl_size = QLabel(file_info.get("size_str", "Unknown"))
        self.lbl_size.setStyleSheet("font-weight: bold;")
        form_layout.addRow("File Size:", self.lbl_size)
        
        self.layout.addLayout(form_layout)
        
        self.auto_detect_category()
        self.update_save_path()
        self.category_combo.currentTextChanged.connect(self.update_save_path)
        
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Download")
        self.btn_later = QPushButton("Download Later")
        self.btn_cancel = QPushButton("Cancel")
        
        self.btn_start.clicked.connect(self.on_start)
        self.btn_later.clicked.connect(self.on_later)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_later)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(btn_layout)
        
        self.action_result = None 
        
    def auto_detect_category(self):
        filename = self.file_info.get("filename", "").lower()
        detected = "General"
        for cat, exts in self.ext_map.items():
            if any(filename.endswith(ext) for ext in exts):
                detected = cat
                break
        self.category_combo.setCurrentText(detected)
        
    def update_save_path(self):
        cat = self.category_combo.currentText()
        if cat == "General":
            base_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Bengal DM")
        else:
            base_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Bengal DM", cat)
        
        try: os.makedirs(base_dir, exist_ok=True)
        except: pass
        
        target_path = os.path.join(base_dir, self.file_info.get("filename", "file"))
        from utils import get_unique_filepath
        target_path = get_unique_filepath(target_path)
        self.save_input.setText(target_path)
        
    def browse_save_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File As", self.save_input.text())
        if path:
            self.save_input.setText(path)
            
    def get_results(self):
        return {
            "action": self.action_result,
            "save_path": self.save_input.text(),
            "category": self.category_combo.currentText(),
            "filename": os.path.basename(self.save_input.text()),
            "size_str": self.file_info.get("size_str", "Unknown"),
            "size_bytes": self.file_info.get("size_bytes", 0)
        }
        
    def on_start(self):
        self.action_result = 'start'
        self.accept()
        
    def on_later(self):
        self.action_result = 'later'
        self.accept()

# --- OPTIONS DIALOG ---
class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumSize(500, 400)
        
        self.config_data = load_category_config()
        self.proxy_data = load_proxy_config()
        self.extension_data = load_extension_config()
        self.current_category = "General"
        
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        self.general_tab = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.general_tab, "General")

        self.saveto_tab = QWidget()
        self.setup_saveto_tab()
        self.tabs.addTab(self.saveto_tab, "Save To")
        
        self.proxy_tab = QWidget()
        self.setup_proxy_tab()
        self.tabs.addTab(self.proxy_tab, "Proxy / Socks")

        self.extension_tab = QWidget()
        self.setup_extension_tab()
        self.tabs.addTab(self.extension_tab, "Extensions")
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.save_and_accept)
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
        
        # Engine status label
        self.lbl_engine = QLabel("Active Engine: Checking...")
        self.lbl_engine.setTextFormat(Qt.TextFormat.RichText)
        vbox_settings.addWidget(self.lbl_engine)
        
        # Initial check
        self.refresh_engine_status()
        
        vbox_settings.addWidget(QLabel("Default Connections: 8"))
        
        version_info = "Not found"
        aria2_path = os.path.expanduser("~/bin/aria2c")
        if os.path.exists(aria2_path):
            try:
                out = subprocess.check_output([aria2_path, "--version"], text=True).splitlines()[0]
                version_info = f"{out} ({aria2_path})"
            except: pass
        else:
            try:
                out = subprocess.check_output(["aria2c", "--version"], text=True).splitlines()[0]
                version_info = f"{out} (System Path)"
            except: pass
                
        vbox_settings.addWidget(QLabel(f"Aria2 Binary: {version_info}"))
        grp_settings.setLayout(vbox_settings)
        layout.addWidget(grp_settings)
        layout.addStretch()

    def refresh_engine_status(self):
        """Re-tests the Aria2 RPC connection and updates the label."""
        token = self.txt_aria_token.text().strip() if hasattr(self, 'txt_aria_token') else self.extension_data.get("token", "")
        rpc_port = self.spin_aria_port.value() if hasattr(self, 'spin_aria_port') else self.extension_data.get("port", 56800)
        
        from utils import call_aria2_rpc, load_proxy_config
        proxy = load_proxy_config()
        
        # Default status
        engine_status = "<span style='color: orange; font-weight: bold;'>Fallback (Custom Python)</span>"
        
        try:
            # Force local check via raw socket
            result = call_aria2_rpc("aria2.getVersion", port=rpc_port, token=token)
            if result:
                version = result.get('version', 'Unknown')
                engine_status = f"<span style='color: green; font-weight: bold;'>Aria2 Connected (v{version})</span>"
            elif proxy.get("mode") == "manual":
                # If manual proxy is on, aria2 might be starting or taking time through proxychains
                engine_status = "<span style='color: blue; font-weight: bold;'>Aria2 Starting (via Proxychains)...</span>"
        except:
            pass
        
        if hasattr(self, 'lbl_engine'):
            self.lbl_engine.setText(f"Active Engine: {engine_status}")

    def setup_saveto_tab(self):
        layout = QVBoxLayout(self.saveto_tab)
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.style().standardPixmap(QStyle.StandardPixmap.SP_DirIcon)) 
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("Categories, file types, folders"))
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        grp_save = QGroupBox("Save To...")
        grp_layout = QVBoxLayout(grp_save)
        grp_layout.setSpacing(8)
        
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Category"))
        cat_row.addStretch()
        btn_new = QPushButton("New")
        btn_new.setFixedWidth(60)
        cat_row.addWidget(btn_new)
        grp_layout.addLayout(cat_row)
        
        self.combo_cat = QComboBox()
        self.combo_cat.addItems(sorted(self.config_data["categories"].keys()))
        idx = self.combo_cat.findText("General")
        if idx != -1: self.combo_cat.setCurrentIndex(idx)
        self.combo_cat.currentTextChanged.connect(self.on_category_changed)
        grp_layout.addWidget(self.combo_cat)

        grp_layout.addWidget(QLabel('Automatically put in above category the following file types:'))
        self.txt_extensions = QLineEdit()
        self.txt_extensions.textChanged.connect(self.on_extensions_changed)
        grp_layout.addWidget(self.txt_extensions)
        
        self.lbl_def_dir = QLabel('Default download directory for "General" category')
        grp_layout.addWidget(self.lbl_def_dir)
        
        dir_row = QHBoxLayout()
        self.txt_save_path = QLineEdit()
        self.txt_save_path.textChanged.connect(self.on_path_changed)
        dir_row.addWidget(self.txt_save_path)
        
        btn_browse_save = QPushButton("Browse")
        btn_browse_save.clicked.connect(lambda: self.browse_folder(self.txt_save_path))
        dir_row.addWidget(btn_browse_save)
        grp_layout.addLayout(dir_row)
        
        self.chk_last_selected = QCheckBox('Change folder for selected category on last selected')
        self.chk_last_selected.setChecked(True)
        grp_layout.addWidget(self.chk_last_selected)

        grp_save.setLayout(grp_layout)
        layout.addWidget(grp_save)
        
        grp_temp = QGroupBox("Temporary directory")
        temp_layout = QVBoxLayout(grp_temp)
        
        temp_dir_row = QHBoxLayout()
        self.txt_temp_path = QLineEdit()
        self.txt_temp_path.setText(self.config_data.get("temp_dir", ""))
        temp_dir_row.addWidget(self.txt_temp_path)
        
        btn_browse_temp = QPushButton("Browse")
        btn_browse_temp.clicked.connect(lambda: self.browse_folder(self.txt_temp_path))
        temp_dir_row.addWidget(btn_browse_temp)
        temp_layout.addLayout(temp_dir_row)
        
        grp_temp.setLayout(temp_layout)
        layout.addWidget(grp_temp)
        layout.addStretch()
        self.on_category_changed(self.combo_cat.currentText())

    def on_proxy_toggle(self, checked):
        if checked:
            self.update_proxy_ui()
            self.save_proxy_data()
            self.refresh_engine_status()

    def setup_proxy_tab(self):
        layout = QVBoxLayout(self.proxy_tab)
        
        self.bg_mode = QButtonGroup(self)
        
        self.rb_no_proxy = QRadioButton("No proxy / Get from system")
        self.rb_no_proxy.toggled.connect(self.on_proxy_toggle)
        layout.addWidget(self.rb_no_proxy)
        self.bg_mode.addButton(self.rb_no_proxy)
        
        self.rb_manual = QRadioButton("Manual proxy configuration")
        self.rb_manual.toggled.connect(self.on_proxy_toggle)
        layout.addWidget(self.rb_manual)
        self.bg_mode.addButton(self.rb_manual)
        
        # Manual Settings Group
        self.grp_manual = QGroupBox()
        manual_layout = QVBoxLayout(self.grp_manual)
        
        # Type
        type_layout = QHBoxLayout()
        self.bg_type = QButtonGroup(self)
        
        self.rb_http = QRadioButton("HTTP")
        self.rb_http.toggled.connect(self.on_proxy_toggle)
        self.rb_socks4 = QRadioButton("SOCKS4")
        self.rb_socks4.toggled.connect(self.on_proxy_toggle)
        self.rb_socks5 = QRadioButton("SOCKS5")
        self.rb_socks5.toggled.connect(self.on_proxy_toggle)
        
        self.bg_type.addButton(self.rb_http)
        self.bg_type.addButton(self.rb_socks4)
        self.bg_type.addButton(self.rb_socks5)
        
        type_layout.addWidget(QLabel("Type:"))
        type_layout.addWidget(self.rb_http)
        type_layout.addWidget(self.rb_socks4)
        type_layout.addWidget(self.rb_socks5)
        type_layout.addStretch()
        manual_layout.addLayout(type_layout)
        
        # Host / Port
        addr_layout = QHBoxLayout()
        addr_layout.addWidget(QLabel("Proxy/Socks host:"))
        self.txt_host = QLineEdit()
        self.txt_host.textChanged.connect(self.save_proxy_data)
        self.txt_host.textChanged.connect(self.refresh_engine_status)
        addr_layout.addWidget(self.txt_host)
        
        addr_layout.addWidget(QLabel("Port:"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(8080)
        self.spin_port.valueChanged.connect(self.save_proxy_data)
        self.spin_port.valueChanged.connect(self.refresh_engine_status)
        addr_layout.addWidget(self.spin_port)
        manual_layout.addLayout(addr_layout)
        
        # Auth
        self.chk_auth = QCheckBox("Authentication required")
        self.chk_auth.toggled.connect(self.update_proxy_ui)
        self.chk_auth.toggled.connect(self.save_proxy_data)
        self.chk_auth.toggled.connect(self.refresh_engine_status)
        manual_layout.addWidget(self.chk_auth)
        
        auth_layout = QGridLayout()
        auth_layout.addWidget(QLabel("Username:"), 0, 0)
        self.txt_user = QLineEdit()
        self.txt_user.textChanged.connect(self.save_proxy_data)
        self.txt_user.textChanged.connect(self.refresh_engine_status)
        auth_layout.addWidget(self.txt_user, 0, 1)
        
        auth_layout.addWidget(QLabel("Password:"), 1, 0)
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.textChanged.connect(self.save_proxy_data)
        self.txt_pass.textChanged.connect(self.refresh_engine_status)
        auth_layout.addWidget(self.txt_pass, 1, 1)
        
        manual_layout.addLayout(auth_layout)
        
        layout.addWidget(self.grp_manual)
        layout.addStretch()
        
        # Load Values (Block signals to prevent auto-save-defaults during init)
        self.rb_manual.blockSignals(True)
        self.rb_no_proxy.blockSignals(True)
        self.rb_http.blockSignals(True)
        self.rb_socks4.blockSignals(True)
        self.rb_socks5.blockSignals(True)
        self.txt_host.blockSignals(True)
        self.spin_port.blockSignals(True)
        self.chk_auth.blockSignals(True)
        self.txt_user.blockSignals(True)
        self.txt_pass.blockSignals(True)
        
        if self.proxy_data["mode"] == "manual":
            self.rb_manual.setChecked(True)
        else:
            self.rb_no_proxy.setChecked(True)
            
        ptype = self.proxy_data.get("type", "http")
        if ptype == "socks4": self.rb_socks4.setChecked(True)
        elif ptype == "socks5": self.rb_socks5.setChecked(True)
        else: self.rb_http.setChecked(True)
        
        self.txt_host.setText(self.proxy_data.get("host", ""))
        self.spin_port.setValue(self.proxy_data.get("port", 8080))
        self.chk_auth.setChecked(self.proxy_data.get("auth", False))
        self.txt_user.setText(self.proxy_data.get("user", ""))
        self.txt_pass.setText(self.proxy_data.get("password", ""))

        self.rb_manual.blockSignals(False)
        self.rb_no_proxy.blockSignals(False)
        self.rb_http.blockSignals(False)
        self.rb_socks4.blockSignals(False)
        self.rb_socks5.blockSignals(False)
        self.txt_host.blockSignals(False)
        self.spin_port.blockSignals(False)
        self.chk_auth.blockSignals(False)
        self.txt_user.blockSignals(False)
        self.txt_pass.blockSignals(False)
        
        self.update_proxy_ui()

    def setup_extension_tab(self):
        layout = QVBoxLayout(self.extension_tab)
        layout.setSpacing(15)
        
        desc = QLabel("Configure connection settings for Aria2 RPC integration.")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        grp_aria = QGroupBox("Aria2 RPC Settings")
        form_layout = QGridLayout(grp_aria)
        form_layout.setSpacing(10)
        
        # Protocol
        form_layout.addWidget(QLabel("Protocol:"), 0, 0)
        self.combo_aria_proto = QComboBox()
        # Add items with user data to map display text to protocol code
        self.combo_aria_proto.addItem("http", "http")
        self.combo_aria_proto.addItem("https", "https")
        self.combo_aria_proto.addItem("websocket", "ws")
        self.combo_aria_proto.addItem("websocket (security)", "wss")
        
        current_proto = self.extension_data.get("protocol", "ws") # Default to ws
        index = self.combo_aria_proto.findData(current_proto)
        if index >= 0:
            self.combo_aria_proto.setCurrentIndex(index)
        else:
             # Fallback if legacy value matches text instead of data, or just default
             idx_text = self.combo_aria_proto.findText(current_proto)
             if idx_text >= 0:
                 self.combo_aria_proto.setCurrentIndex(idx_text)
             else:
                 # Default to websocket (index 2)
                 self.combo_aria_proto.setCurrentIndex(2)

        form_layout.addWidget(self.combo_aria_proto, 0, 1)
        
        # Port
        form_layout.addWidget(QLabel("Port:"), 1, 0)
        self.spin_aria_port = QSpinBox()
        self.spin_aria_port.setRange(1, 65535)
        self.spin_aria_port.setValue(self.extension_data.get("port", 56800))
        form_layout.addWidget(self.spin_aria_port, 1, 1)
        
        # Token
        form_layout.addWidget(QLabel("Secret Token:"), 2, 0)
        self.txt_aria_token = QLineEdit()
        self.txt_aria_token.setPlaceholderText("Optional secret token")
        self.txt_aria_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_aria_token.setText(self.extension_data.get("token", ""))
        form_layout.addWidget(self.txt_aria_token, 2, 1)
        
        # Show Token Checkbox
        self.chk_show_token = QCheckBox("Show Token")
        self.chk_show_token.toggled.connect(
            lambda checked: self.txt_aria_token.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        form_layout.addWidget(self.chk_show_token, 3, 1)
        
        layout.addWidget(grp_aria)
        layout.addStretch()

    def update_proxy_ui(self):
        manual = self.rb_manual.isChecked()
        self.grp_manual.setEnabled(manual)
        
        auth = self.chk_auth.isChecked() and manual
        self.txt_user.setEnabled(auth)
        self.txt_pass.setEnabled(auth)

    def save_proxy_data(self):
        mode = "manual" if self.rb_manual.isChecked() else "no_proxy"
        ptype = "http"
        if self.rb_socks4.isChecked(): ptype = "socks4"
        if self.rb_socks5.isChecked(): ptype = "socks5"
        
        self.proxy_data = {
            "mode": mode,
            "type": ptype,
            "host": self.txt_host.text().strip(),
            "port": self.spin_port.value(),
            "auth": self.chk_auth.isChecked(),
            "user": self.txt_user.text(),
            "password": self.txt_pass.text()
        }
        save_proxy_config(self.proxy_data)

    def save_extension_data(self):
        self.extension_data = {
            "protocol": self.combo_aria_proto.currentData(), # Save the protocol code (http, ws), not the display text
            "host": "localhost",
            "port": self.spin_aria_port.value(),
            "token": self.txt_aria_token.text().strip()
        }
        save_extension_config(self.extension_data)

    def on_category_changed(self, category):
        self.current_category = category
        cat_data = self.config_data["categories"].get(category, {})
        self.txt_extensions.blockSignals(True)
        self.txt_save_path.blockSignals(True)
        self.txt_extensions.setText(cat_data.get("extensions", ""))
        self.txt_save_path.setText(cat_data.get("path", ""))
        self.lbl_def_dir.setText(f'Default download directory for "{category}" category')
        self.txt_extensions.blockSignals(False)
        self.txt_save_path.blockSignals(False)

    def on_extensions_changed(self, text):
        if self.current_category in self.config_data["categories"]:
            self.config_data["categories"][self.current_category]["extensions"] = text

    def on_path_changed(self, text):
        if self.current_category in self.config_data["categories"]:
            self.config_data["categories"][self.current_category]["path"] = text

    def browse_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", line_edit.text())
        if folder:
            line_edit.setText(folder)

    def save_and_accept(self):
        self.config_data["temp_dir"] = self.txt_temp_path.text()
        save_category_config(self.config_data)
        self.save_proxy_data()
        self.save_extension_data()
        self.accept()

    def get_theme(self):
        return None


# --- PROPERTIES DIALOG ---
class PropertiesDialog(QDialog):
    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Properties - {file_data.get('filename', 'Unknown')}")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        grp_file = QGroupBox("File Information")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setSpacing(10)
        
        labels = [
            ("File Name:", file_data.get('filename', '')),
            ("Type:", os.path.splitext(file_data.get('filename', ''))[1].upper() + " File"),
            ("Status:", file_data.get('status', 'Unknown')),
            ("Size:", file_data.get('size', 'Unknown')),
            ("Saved To:", os.path.dirname(file_data.get('path', 'Unknown'))),
            ("Address:", file_data.get('url', '')),
            ("Date Added:", file_data.get('date_added', '')),
            ("Last Try:", file_data.get('last_try', ''))
        ]
        
        for i, (label_text, value) in enumerate(labels):
            lbl_widget = QLabel(label_text)
            lbl_widget.setStyleSheet("font-weight: bold;")
            
            val_widget = QLineEdit(str(value))
            val_widget.setReadOnly(True)
            val_widget.setCursorPosition(0) 
            val_widget.setStyleSheet("""
                QLineEdit { 
                    background: transparent; 
                    color: white; 
                    border: none; 
                }
            """)
            
            grid.addWidget(lbl_widget, i, 0)
            grid.addWidget(val_widget, i, 1)
            
        grp_file.setLayout(grid)
        layout.addWidget(grp_file)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_open = QPushButton("Open")
        self.btn_open.clicked.connect(self.accept) 
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)


# --- DOWNLOAD PROGRESS DIALOG ---
class DownloadProgressDialog(QDialog):
    def __init__(self, worker, parent=None):
        # Passing parent=None allows the window to be a separate top-level window
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle(f"{self.worker.filename}")
        
        # Ensure it behaves like a separate window in the OS
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(Qt.WindowType.Window) 
        
        self.fixed_width = 500
        self.base_height = 280
        self.setMinimumWidth(450)
        self.setMinimumHeight(self.base_height)
        
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        url_text = self.worker.url
        
        self.lbl_url = QLabel(url_text)
        self.lbl_url.setToolTip(url_text)
        self.lbl_url.setStyleSheet("color: #666;")
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
    
    def setup_limiter_tab(self):
        layout = QVBoxLayout(self.limiter_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        lbl_desc = QLabel("You can limit the download speed to avoid slowing down your internet browsing.")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)
        
        control_layout = QHBoxLayout()
        self.chk_limit = QCheckBox("Use Speed Limiter")
        self.chk_limit.setStyleSheet("font-weight: bold;")
        self.chk_limit.toggled.connect(self.apply_speed_limit)
        control_layout.addWidget(self.chk_limit)
        
        control_layout.addSpacing(20)
        layout.addLayout(control_layout)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Maximum download speed:"))
        
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 100000)
        self.spin_limit.setValue(512)
        self.spin_limit.setSuffix("") 
        self.spin_limit.setEnabled(False) 
        self.spin_limit.valueChanged.connect(self.apply_speed_limit)
        input_layout.addWidget(self.spin_limit)
        
        input_layout.addWidget(QLabel("KB/sec"))
        
        input_layout.addStretch()
        layout.addLayout(input_layout)
        layout.addStretch()


    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.status_tab = QWidget()
        self.setup_status_tab()
        self.tabs.addTab(self.status_tab, "Download status")
        
        self.limiter_tab = QWidget()
        self.setup_limiter_tab()
        self.tabs.addTab(self.limiter_tab, "Speed Limiter")

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
            import subprocess, os
            try:
                target_dir = os.path.dirname(self.worker.target_path)
                if os.path.exists(target_dir):
                    subprocess.Popen(['xdg-open', target_dir])
            except Exception:
                pass 

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
            self.resize(self.width(), self.base_height + details_extra)
        else:
            self.details_frame.hide()
            self.btn_details.setText("Show Details >>")
            self.resize(self.width(), self.base_height)

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
                 display_status = "Completed"
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
        self.lbl_size.setText(data[1])
        self.lbl_speed.setText(data[4])
        self.lbl_time.setText(data[3])
        
        current_bytes = self.current_bytes
        total_bytes = self.total_bytes
        
        # Calculate percentage properly based on progress bar values
        if total_bytes > 0:
            percent = f"{(current_bytes / total_bytes) * 100:.1f}%"
        else:
            percent = "Unknown %" if current_bytes > 0 else "0.0%"
            
        self.lbl_downloaded.setText(f"{self.worker.format_bytes(current_bytes)} ({percent})")
        
        main_status_text = self.lbl_main_status.text()
        if main_status_text in ["Downloading", "Resuming...", "Connecting..."]:
            self.btn_pause.setText("Pause")
            self.btn_cancel.setText("Cancel")
            self.btn_pause.setEnabled(True)
            self.btn_cancel.setEnabled(True)
        elif main_status_text == "Paused":
            self.btn_pause.setText("Resume")
            self.btn_cancel.setText("Close")
            self.btn_pause.setEnabled(True)
            self.btn_cancel.setEnabled(True)
        elif main_status_text in ["Cancelled", "Error"]:
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
        if status == "Completed":
            display_status = "Completed"
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
        
        if display_status == "Completed":
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
            self.btn_pause.clicked.connect(lambda: os.startfile(os.path.dirname(self.worker.target_path)) if os.name == 'nt' else subprocess.Popen(['xdg-open', os.path.dirname(self.worker.target_path)]))
        elif display_status in ["Cancelled", "Paused", "Error"]:
            self.btn_cancel.setText("Close")
            self.btn_pause.setText("Resume")
            self.btn_pause.setEnabled(True)
            
            
    def closeEvent(self, event):
        if self.btn_cancel.text() == "Cancel":
            self.worker.stop()
            self.worker.finished_signal.emit(self.worker.row_index, "Paused")
        self.reject()