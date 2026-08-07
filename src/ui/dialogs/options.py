import os
import subprocess
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QWidget, QGroupBox, QComboBox, QCheckBox, QSpinBox,
    QRadioButton, QButtonGroup, QFrame, QStyle, QGridLayout, QMessageBox,
    QApplication
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG
from core.utils import (
    load_proxy_config, save_proxy_config, 
    load_extension_config, save_extension_config, call_aria2_rpc,
    find_aria2, choose_portal_save_path, choose_portal_folder_path,
    is_autostart_enabled, set_autostart_enabled
)
from core.config import load_category_config, save_category_config

class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedSize(500, 520)
        
        # Remove maximize button and prevent resizing via window flags
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)
        
        self.config_data = load_category_config()
        self.proxy_data = load_proxy_config()
        self.extension_data = load_extension_config()
        self.current_category = "General"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
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
        self.btn_ok.setFixedWidth(80)
        self.btn_ok.setFixedHeight(30)
        self.btn_ok.setDefault(True)
        self.btn_ok.setToolTip("Save configuration changes and close dialog")
        self.btn_ok.clicked.connect(self.save_and_accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip("Discard changes and close dialog")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def setup_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # 1. Theme & Appearance
        grp_theme = QGroupBox("Theme & Appearance")
        vbox_theme = QVBoxLayout()
        vbox_theme.setContentsMargins(10, 15, 10, 10)
        vbox_theme.setSpacing(10)

        # Row 1: Theme & Accent
        row_theme_accent = QHBoxLayout()
        lbl_theme = QLabel("Theme:")
        lbl_theme.setToolTip("Select application visual theme")
        self.combo_theme = QComboBox()
        self.combo_theme.setToolTip("Select application visual theme")
        theme_options = [
            "Automatic", "Light", "Dark", 
            "Ubuntu Light", "Ubuntu Dark",
            "IDM Classic", "Kirigami Light", "Kirigami Dark",
            "Breeze Light", "Breeze Dark",
            "Dracula", "Nord", "One Dark", "Catppuccin",
            "Solarized Light", "Solarized Dark"
        ]
        self.combo_theme.addItems(theme_options)

        lbl_accent = QLabel("Accent:")
        lbl_accent.setToolTip("Select accent/highlight color")
        self.combo_accent = QComboBox()
        self.combo_accent.setToolTip("Select accent/highlight color")
        accent_options = [
            "Default / Auto", "Breeze Blue", "Ubuntu Orange", 
            "Windows Blue", "Dracula Purple", "Nord Frost", 
            "Emerald Green", "Crimson Red", "Amethyst Violet"
        ]
        self.combo_accent.addItems(accent_options)

        row_theme_accent.addWidget(lbl_theme)
        row_theme_accent.addWidget(self.combo_theme)
        row_theme_accent.addSpacing(15)
        row_theme_accent.addWidget(lbl_accent)
        row_theme_accent.addWidget(self.combo_accent)
        row_theme_accent.addStretch()
        vbox_theme.addLayout(row_theme_accent)

        # Row 2: Toolbar Icons Theme
        row_icons = QHBoxLayout()
        lbl_icon_theme = QLabel("Toolbar Icons:")
        lbl_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        self.combo_icon_theme = QComboBox()
        self.combo_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        icon_theme_options = ["Automatic", "Breeze", "Breeze Dark", "Ubuntu", "Adwaita", "HighColor"]
        self.combo_icon_theme.addItems(icon_theme_options)

        row_icons.addWidget(lbl_icon_theme)
        row_icons.addWidget(self.combo_icon_theme)
        row_icons.addStretch()
        vbox_theme.addLayout(row_icons)

        # Initial values & restore state for Cancel
        current_theme = "Automatic"
        current_accent = "Default / Auto"
        current_icon_theme = "Automatic"
        if self.parent() and hasattr(self.parent(), "settings") and isinstance(self.parent().settings, dict):
            current_theme = self.parent().settings.get("theme", "Automatic")
            current_accent = self.parent().settings.get("accent", "Default / Auto")
            current_icon_theme = self.parent().settings.get("icon_theme", "Automatic")

        self.initial_theme = current_theme
        self.initial_accent = current_accent
        self.initial_icon_theme = current_icon_theme

        idx_t = self.combo_theme.findText(current_theme)
        if idx_t != -1: self.combo_theme.setCurrentIndex(idx_t)
        idx_a = self.combo_accent.findText(current_accent)
        if idx_a != -1: self.combo_accent.setCurrentIndex(idx_a)
        idx_i = self.combo_icon_theme.findText(current_icon_theme)
        if idx_i != -1: self.combo_icon_theme.setCurrentIndex(idx_i)

        # Connect live preview signals
        self.combo_theme.currentIndexChanged.connect(self.on_appearance_preview)
        self.combo_accent.currentIndexChanged.connect(self.on_appearance_preview)
        self.combo_icon_theme.currentIndexChanged.connect(self.on_appearance_preview)

        grp_theme.setLayout(vbox_theme)
        layout.addWidget(grp_theme)

        # 2. Startup & Integration
        grp_startup = QGroupBox("Startup & Integration")
        vbox_startup = QVBoxLayout()
        vbox_startup.setContentsMargins(10, 15, 10, 10)
        vbox_startup.setSpacing(10)
        
        self.chk_startup = QCheckBox("Launch Bengal DM on system startup")
        self.chk_startup.setChecked(is_autostart_enabled())
        self.chk_startup.setToolTip("Automatically launch Bengal Download Manager on system boot")
        vbox_startup.addWidget(self.chk_startup)
        
        self.chk_start_minimized = QCheckBox("Start minimized in system tray on system startup")
        # Load from parent (MainWindow) settings
        self.chk_start_minimized.setChecked(getattr(self.parent(), "start_minimized_on_autostart", False))
        self.chk_start_minimized.setToolTip("Launch hidden in system tray when autostarting")
        vbox_startup.addWidget(self.chk_start_minimized)
        
        grp_startup.setLayout(vbox_startup)
        layout.addWidget(grp_startup)
        
        # 2. Engine Settings
        grp_engine = QGroupBox("Engine Settings")
        vbox_engine = QVBoxLayout()
        vbox_engine.setContentsMargins(10, 15, 10, 10)
        vbox_engine.setSpacing(12)
        
        # Engine status label
        self.lbl_engine = QLabel("Active Engine: Checking...")
        self.lbl_engine.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_engine.setToolTip("Connection status of backend Aria2 download engine")
        vbox_engine.addWidget(self.lbl_engine)
        
        # Initial check
        self.refresh_engine_status()
        
        grp_engine.setLayout(vbox_engine)
        layout.addWidget(grp_engine)

        # 3. UI Settings
        grp_ui = QGroupBox("UI Settings")
        vbox_ui = QVBoxLayout()
        vbox_ui.setContentsMargins(10, 15, 10, 10)
        vbox_ui.setSpacing(10)

        row_scale = QHBoxLayout()
        lbl_scale = QLabel("Scale:")
        lbl_scale.setToolTip("Set user interface scale factor")
        self.combo_scale = QComboBox()
        self.combo_scale.setToolTip("Set user interface scale factor")
        scale_options = [
            "50%", "75%", "90%", "100%", "110%", "115%", "125%", 
            "135%", "150%", "175%", "200%", "225%", "250%", "275%", "300%"
        ]
        self.combo_scale.addItems(scale_options)

        # Load saved scale setting from parent if available
        current_scale = "100%"
        if self.parent() and hasattr(self.parent(), "settings"):
            current_scale = self.parent().settings.get("ui_scale", "100%")
        self.initial_scale = current_scale

        idx = self.combo_scale.findText(current_scale)
        if idx != -1:
            self.combo_scale.setCurrentIndex(idx)
        else:
            def_idx = self.combo_scale.findText("100%")
            if def_idx != -1:
                self.combo_scale.setCurrentIndex(def_idx)

        row_scale.addWidget(lbl_scale)
        row_scale.addWidget(self.combo_scale)
        row_scale.addStretch()
        vbox_ui.addLayout(row_scale)

        grp_ui.setLayout(vbox_ui)
        layout.addWidget(grp_ui)

        layout.addStretch()

    def refresh_engine_status(self):
        """Re-tests the Aria2 RPC connection and updates the label in background."""
        if not hasattr(self, 'lbl_engine'): return
        
        token = self.txt_aria_token.text().strip() if hasattr(self, 'txt_aria_token') else self.extension_data.get("token", "")
        rpc_port = self.spin_aria_port.value() if hasattr(self, 'spin_aria_port') else self.extension_data.get("port", 56800)
        
        self.lbl_engine.setText("Active Engine: <span style='color: #3498db;'>●</span> Checking...")
        
        def check():
            proxy = load_proxy_config()
            engine_status = "<span style='color: orange;'>●</span> Fallback (Custom Python)"
            try:
                # This is a blocking network call (3s timeout)
                result = call_aria2_rpc("aria2.getVersion", port=rpc_port, token=token)
                if result:
                    version = result.get('version', 'Unknown')
                    engine_status = f"<span style='color: #00ca00;'>●</span> Aria2 Connected (v{version})"
                elif proxy.get("mode") == "manual":
                    engine_status = "<span style='color: #3498db;'>●</span> Aria2 Starting (via Proxychains)..."
            except:
                pass
            
            aria2_bin = find_aria2() or "Not found"
            final_text = f"Active Engine: {engine_status}<br><small>Binary: {aria2_bin}</small>"
            
            # Update UI safely from background thread
            QMetaObject.invokeMethod(self.lbl_engine, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, final_text))

        threading.Thread(target=check, daemon=True).start()

    def setup_saveto_tab(self):
        layout = QVBoxLayout(self.saveto_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
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
        grp_layout.setContentsMargins(10, 15, 10, 15)
        grp_layout.setSpacing(10)
        
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Category"))
        cat_row.addStretch()
        grp_layout.addLayout(cat_row)
        
        self.combo_cat = QComboBox()
        self.combo_cat.addItems(sorted(self.config_data["categories"].keys()))
        idx = self.combo_cat.findText("General")
        if idx != -1: self.combo_cat.setCurrentIndex(idx)
        self.combo_cat.setToolTip("Select category to configure download routing rules")
        self.combo_cat.currentTextChanged.connect(self.on_category_changed)
        grp_layout.addWidget(self.combo_cat)

        grp_layout.addWidget(QLabel('Automatically put in above category the following file types:'))
        self.txt_extensions = QLineEdit()
        self.txt_extensions.setToolTip("Space-separated file extensions automatically assigned to this category")
        self.txt_extensions.textChanged.connect(self.on_extensions_changed)
        grp_layout.addWidget(self.txt_extensions)
        
        self.lbl_def_dir = QLabel('Default download directory for "General" category')
        grp_layout.addWidget(self.lbl_def_dir)
        
        dir_row = QHBoxLayout()
        self.txt_save_path = QLineEdit()
        self.txt_save_path.setToolTip("Default save directory for files in selected category")
        self.txt_save_path.textChanged.connect(self.on_path_changed)
        dir_row.addWidget(self.txt_save_path)
        
        btn_browse_save = QPushButton("Browse")
        btn_browse_save.setToolTip("Browse folder to set category save directory")
        btn_browse_save.clicked.connect(lambda: self.browse_folder(self.txt_save_path))
        dir_row.addWidget(btn_browse_save)
        grp_layout.addLayout(dir_row)
        
        self.chk_last_selected = QCheckBox('Change folder for selected category on last selected')
        self.chk_last_selected.setChecked(True)
        self.chk_last_selected.setToolTip("Automatically update category directory when selecting a custom folder")
        grp_layout.addWidget(self.chk_last_selected)

        layout.addWidget(grp_save)
        
        grp_temp = QGroupBox("Temporary directory")
        temp_layout = QVBoxLayout(grp_temp)
        temp_layout.setContentsMargins(10, 15, 10, 15)
        temp_layout.setSpacing(10)
        
        temp_dir_row = QHBoxLayout()
        self.txt_temp_path = QLineEdit()
        self.txt_temp_path.setText(self.config_data.get("temp_dir", ""))
        self.txt_temp_path.setToolTip("Temporary directory used for downloading chunks before merging")
        temp_dir_row.addWidget(self.txt_temp_path)
        
        btn_browse_temp = QPushButton("Browse")
        btn_browse_temp.setToolTip("Browse folder for temporary chunk storage")
        btn_browse_temp.clicked.connect(lambda: self.browse_folder(self.txt_temp_path))
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
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
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
        manual_layout.setContentsMargins(10, 15, 10, 15)
        manual_layout.setSpacing(12)
        
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
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # Header with App Icon
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.windowIcon().pixmap(32, 32))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("<b>Bengal Download Manager Integration Module</b>"))
        header_layout.addStretch()
        layout.addLayout(header_layout)

        
        grp_aria = QGroupBox("Aria2 RPC Settings")
        aria_layout = QGridLayout(grp_aria)
        aria_layout.setContentsMargins(10, 15, 10, 15)
        aria_layout.setSpacing(12)
        
        # Protocol
        aria_layout.addWidget(QLabel("Protocol:"), 0, 0)
        self.combo_aria_proto = QComboBox()
        self.combo_aria_proto.setToolTip("Communication protocol for connecting to Aria2 RPC daemon")
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
             idx_text = self.combo_aria_proto.findText(current_proto)
             if idx_text >= 0:
                 self.combo_aria_proto.setCurrentIndex(idx_text)
             else:
                 self.combo_aria_proto.setCurrentIndex(2)

        aria_layout.addWidget(self.combo_aria_proto, 0, 1)
        
        # Port
        aria_layout.addWidget(QLabel("Port:"), 1, 0)
        self.spin_aria_port = QSpinBox()
        self.spin_aria_port.setRange(1, 65535)
        self.spin_aria_port.setValue(self.extension_data.get("port", 56800))
        self.spin_aria_port.setToolTip("Port number for Aria2 RPC daemon (default 56800)")
        aria_layout.addWidget(self.spin_aria_port, 1, 1)
        
        # Token
        aria_layout.addWidget(QLabel("Secret Token:"), 2, 0)
        self.txt_aria_token = QLineEdit()
        self.txt_aria_token.setPlaceholderText("Optional secret token")
        self.txt_aria_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_aria_token.setText(self.extension_data.get("token", ""))
        self.txt_aria_token.setToolTip("Secret authentication token for Aria2 RPC requests")
        aria_layout.addWidget(self.txt_aria_token, 2, 1)
        
        # Show Token Checkbox
        self.chk_show_token = QCheckBox("Show Token")
        self.chk_show_token.setToolTip("Toggle secret token text visibility")
        self.chk_show_token.toggled.connect(self.on_toggle_show_token)
        aria_layout.addWidget(self.chk_show_token, 3, 1)
        
        layout.addWidget(grp_aria)

        # Get Browser Extension Section
        grp_get_ext = QGroupBox("Get Browser Extension")
        get_ext_layout = QHBoxLayout(grp_get_ext)
        get_ext_layout.setContentsMargins(10, 15, 10, 15)
        get_ext_layout.setSpacing(10)

        from ui.icons import get_monochrome_icon
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        self.btn_ext_github = QPushButton(" GitHub")
        self.btn_ext_github.setIcon(get_monochrome_icon("github", size=18))
        self.btn_ext_github.setToolTip("Open GitHub Releases page to download extension package")
        self.btn_ext_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/tazihad/bengal-download-manager/releases")))

        self.btn_ext_firefox = QPushButton(" Firefox Store")
        self.btn_ext_firefox.setIcon(get_monochrome_icon("firefox", size=18))
        self.btn_ext_firefox.setToolTip("Open Mozilla Firefox Add-ons Store page")
        self.btn_ext_firefox.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://addons.mozilla.org/en-US/firefox/addon/bengal-dm-integration-module")))

        self.btn_ext_chrome = QPushButton(" Chrome (Coming Soon)")
        self.btn_ext_chrome.setIcon(get_monochrome_icon("chrome", size=18))
        self.btn_ext_chrome.setEnabled(False)
        self.btn_ext_chrome.setToolTip("Chrome Web Store integration is coming soon")

        get_ext_layout.addWidget(self.btn_ext_github)
        get_ext_layout.addWidget(self.btn_ext_firefox)
        get_ext_layout.addWidget(self.btn_ext_chrome)
        
        layout.addWidget(grp_get_ext)
        
        layout.addStretch()

    def on_toggle_show_token(self, checked):
        """Toggles the echo mode of the token field."""
        if checked:
            self.txt_aria_token.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.txt_aria_token.setEchoMode(QLineEdit.EchoMode.Password)

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
            "protocol": self.combo_aria_proto.currentData(), 
            "host": "localhost",
            "port": self.spin_aria_port.value(),
            "token": self.txt_aria_token.text().strip(),
            "max_connections": 8
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
        current_path = line_edit.text().strip()
        folder = current_path if os.path.exists(current_path) else os.path.expanduser("~/Downloads")
        path = choose_portal_folder_path("Select Directory", folder)
        if path:
            line_edit.setText(path)

    def on_appearance_preview(self):
        t = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "Automatic"
        a = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "Default / Auto"
        i = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "Automatic"
        if self.parent():
            preview_fn = getattr(self.parent(), "preview_appearance", None)
            if callable(preview_fn):
                preview_fn(t, a, i)

    def reject(self):
        if self.parent():
            preview_fn = getattr(self.parent(), "preview_appearance", None)
            if callable(preview_fn):
                t = getattr(self, 'initial_theme', 'Automatic')
                a = getattr(self, 'initial_accent', 'Default / Auto')
                i = getattr(self, 'initial_icon_theme', 'Automatic')
                preview_fn(t, a, i)
        super().reject()

    def save_and_accept(self):
        self.config_data["temp_dir"] = self.txt_temp_path.text()
        save_category_config(self.config_data)
        
        new_scale = self.combo_scale.currentText()
        new_theme = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "Automatic"
        new_accent = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "Default / Auto"
        new_icon_theme = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "Automatic"
        scale_changed = hasattr(self, 'initial_scale') and (self.initial_scale != new_scale)

        # Save start_minimized_on_autostart, ui_scale, theme, accent, and icon_theme to parent (MainWindow)
        if self.parent():
            setattr(self.parent(), "start_minimized_on_autostart", self.chk_start_minimized.isChecked())
            if hasattr(self.parent(), "settings") and isinstance(self.parent().settings, dict):
                self.parent().settings["ui_scale"] = new_scale
                self.parent().settings["theme"] = new_theme
                self.parent().settings["accent"] = new_accent
                self.parent().settings["icon_theme"] = new_icon_theme
            apply_fn = getattr(self.parent(), "apply_appearance_setting", None)
            if callable(apply_fn):
                apply_fn(new_theme, new_accent, new_icon_theme)
            else:
                save_fn = getattr(self.parent(), "save_settings", None)
                if callable(save_fn):
                    save_fn()

        set_autostart_enabled(self.chk_startup.isChecked(), self.chk_start_minimized.isChecked())
        self.save_proxy_data()
        self.save_extension_data()

        if scale_changed:
            QMessageBox.information(
                self,
                "Restart Required",
                "UI Scale setting has been changed. Please restart Bengal Download Manager to apply the changes."
            )

        self.accept()

    def get_theme(self):
        return self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "Automatic"

    def get_accent(self):
        return self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "Default / Auto"

    def get_icon_theme(self):
        return self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "Automatic"
