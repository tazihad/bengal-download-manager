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
    load_proxy_config, save_proxy_config, get_aria2_proxy_url,
    load_extension_config, save_extension_config, call_aria2_rpc,
    find_aria2, choose_portal_save_path, choose_portal_folder_path, choose_portal_open_file_path,
    is_autostart_enabled, set_autostart_enabled
)
from core.config import load_category_config, save_category_config
from core.memory_guard import MemoryGuard

class OptionsDialog(QDialog):
    def __init__(self, main_window=None, parent=None):
        # Pass parent=None to QDialog superclass so it is initialized as an independent top-level window in taskbar panels while sharing WM_CLASS
        super().__init__(None)
        self._main_window = main_window or parent
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Options")
        self.setWindowIcon(QApplication.windowIcon())
        
        target_height = 520
        if self._main_window and hasattr(self._main_window, "height"):
            main_h = self._main_window.height()
            if main_h > 200:
                target_height = main_h
        self.setFixedWidth(520)
        self.setFixedHeight(target_height)
        
        # Set window flags so Options dialog appears as an independent top-level window in taskbar panels
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

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

        self.startup_tab = QWidget()
        self.setup_startup_tab()
        self.tabs.addTab(self.startup_tab, "Startup")

        self.saveto_tab = QWidget()
        self.setup_saveto_tab()
        self.tabs.addTab(self.saveto_tab, "Save To")

        self.downloads_tab = QWidget()
        self.setup_downloads_tab()
        self.tabs.addTab(self.downloads_tab, "Downloads")
        
        self.proxy_tab = QWidget()
        self.setup_proxy_tab()
        self.tabs.addTab(self.proxy_tab, "Proxy")

        self.extension_tab = QWidget()
        self.setup_extension_tab()
        self.tabs.addTab(self.extension_tab, "Extensions")

        self.media_tab = QWidget()
        self.setup_media_tab()
        self.tabs.addTab(self.media_tab, "Media")
        
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

    @property
    def main_win(self):
        return getattr(self, "_main_window", None) or self.parent()

    def setup_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # 1. Theme and Appearance
        grp_theme = QGroupBox("Theme and Appearance")
        # Use QGridLayout for Theme & Appearance to ensure perfect 2D alignment across all 4 dropdowns
        grid_theme = QGridLayout()
        grid_theme.setContentsMargins(10, 8, 10, 8)
        grid_theme.setSpacing(10)

        lbl_theme = QLabel("Theme:")
        lbl_theme.setToolTip("Select application visual theme")
        self.combo_theme = QComboBox()
        self.combo_theme.setToolTip("Select application visual theme")
        theme_options = [
            "System", "BDM Auto", "BDM Dark (Default)", "BDM Light",
            "Breeze Dark", "Breeze Light", "Catppuccin",
            "Dracula", "IDM Classic", "Kirigami Dark", 
            "Kirigami Light", "Material You Dark", "Material You Light",
            "Nord", "Obsidian Flow", "One Dark", 
            "Solarized Dark", "Solarized Light", 
            "Twilight", "Ubuntu Dark", "Ubuntu Light"
        ]
        self.combo_theme.addItems(theme_options)

        lbl_accent = QLabel("Accent:")
        lbl_accent.setToolTip("Select accent/highlight color")
        self.combo_accent = QComboBox()
        self.combo_accent.setToolTip("Select accent/highlight color")
        accent_options = [
            "System", "BDM (Default)", "Amethyst Violet", "Breeze Blue", 
            "Crimson Red", "Dracula Purple", "Emerald Green", 
            "Material Cobalt", "Material Violet", "Nord Frost", 
            "Obsidian Purple", "Twilight", "Ubuntu Orange", "Windows Blue"
        ]
        self.combo_accent.addItems(accent_options)

        lbl_icon_theme = QLabel("Icons:")
        lbl_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        self.combo_icon_theme = QComboBox()
        self.combo_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        icon_theme_options = ["BDM Auto (Default)", "BDM Dark", "BDM Light", "Adwaita", "Breeze", "Breeze Dark", "HighColor", "Modern Color", "Yaru"]
        self.combo_icon_theme.addItems(icon_theme_options)

        lbl_tray_icon = QLabel("Tray Icon:")
        lbl_tray_icon.setToolTip("Select system tray icon style")
        self.combo_tray_icon = QComboBox()
        self.combo_tray_icon.setToolTip("Select system tray icon style")
        tray_icon_options = [
            "App Icon (Default)", "Automatic", "Monochrome Dark", "Monochrome Light"
        ]
        self.combo_tray_icon.addItems(tray_icon_options)

        grid_theme.addWidget(lbl_theme, 0, 0)
        grid_theme.addWidget(self.combo_theme, 0, 1)
        grid_theme.addWidget(lbl_accent, 0, 2)
        grid_theme.addWidget(self.combo_accent, 0, 3)

        grid_theme.addWidget(lbl_icon_theme, 1, 0)
        grid_theme.addWidget(self.combo_icon_theme, 1, 1)
        grid_theme.addWidget(lbl_tray_icon, 1, 2)
        grid_theme.addWidget(self.combo_tray_icon, 1, 3)

        grp_theme.setLayout(grid_theme)

        current_theme = "BDM Dark (Default)"
        current_accent = "BDM (Default)"
        current_icon_theme = "BDM Auto (Default)"
        current_tray_icon = "App Icon (Default)"
        if self.main_win and hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
            current_theme = self.main_win.settings.get("theme", "BDM Dark (Default)")
            current_accent = self.main_win.settings.get("accent", "BDM (Default)")
            current_icon_theme = self.main_win.settings.get("icon_theme", "BDM (Default)")
            current_tray_icon = self.main_win.settings.get("tray_icon", "App Icon (Default)")


        try:
            from main import normalize_theme_name, normalize_accent_name, normalize_icon_theme_name, normalize_tray_icon_name
            current_theme = normalize_theme_name(current_theme)
            current_accent = normalize_accent_name(current_accent)
            current_icon_theme = normalize_icon_theme_name(current_icon_theme)
            current_tray_icon = normalize_tray_icon_name(current_tray_icon)
        except Exception:
            pass

        self.initial_theme = current_theme
        self.initial_accent = current_accent
        self.initial_icon_theme = current_icon_theme
        self.initial_tray_icon = current_tray_icon

        idx_t = self.combo_theme.findText(current_theme)
        if idx_t == -1: idx_t = self.combo_theme.findText("BDM Dark (Default)")
        if idx_t != -1: self.combo_theme.setCurrentIndex(idx_t)

        idx_a = self.combo_accent.findText(current_accent)
        if idx_a == -1: idx_a = self.combo_accent.findText("BDM (Default)")
        if idx_a != -1: self.combo_accent.setCurrentIndex(idx_a)

        idx_i = self.combo_icon_theme.findText(current_icon_theme)
        if idx_i == -1: idx_i = self.combo_icon_theme.findText("BDM Auto (Default)")
        if idx_i != -1: self.combo_icon_theme.setCurrentIndex(idx_i)

        idx_tr = self.combo_tray_icon.findText(current_tray_icon)
        if idx_tr == -1: idx_tr = self.combo_tray_icon.findText("App Icon (Default)")
        if idx_tr != -1: self.combo_tray_icon.setCurrentIndex(idx_tr)

        # Connect live preview signals
        self.combo_theme.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_accent.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_icon_theme.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_tray_icon.currentTextChanged.connect(self.on_appearance_preview)

        layout.addWidget(grp_theme)

        # 2. UI Settings (Right after Theme)
        grp_ui = QGroupBox("UI Settings")
        vbox_ui = QVBoxLayout()
        vbox_ui.setContentsMargins(10, 8, 10, 8)
        vbox_ui.setSpacing(8)

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
        if self.main_win and hasattr(self.main_win, "settings"):
            current_scale = self.main_win.settings.get("ui_scale", "100%")

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

    def setup_downloads_tab(self):
        layout = QVBoxLayout(self.downloads_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        def _get_setting(key, default):
            if self.main_win and hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
                return self.main_win.settings.get(key, default)
            return default

        # 1. Dialog and Popup Windows (IDM-style)
        grp_dialogs = QGroupBox("Download Dialogs")
        vbox_dialogs = QVBoxLayout()
        vbox_dialogs.setContentsMargins(10, 10, 10, 10)
        vbox_dialogs.setSpacing(8)

        self.chk_silent_download = QCheckBox("Silent download mode (start immediately without showing any dialogs)")
        self.chk_silent_download.setToolTip("When enabled, downloads start and finish silently in the background without showing Start, Progress, or Complete popup dialogs")
        self.chk_silent_download.setChecked(_get_setting("silent_download", False))
        vbox_dialogs.addWidget(self.chk_silent_download)

        line_silent = QFrame()
        line_silent.setFrameShape(QFrame.Shape.HLine)
        line_silent.setFrameShadow(QFrame.Shadow.Sunken)
        vbox_dialogs.addWidget(line_silent)

        self.chk_show_start_dialog = QCheckBox("Show start download dialog")
        self.chk_show_start_dialog.setToolTip("Show confirmation and destination dialog before starting a download")
        self.chk_show_start_dialog.setChecked(_get_setting("show_start_dialog", True))
        vbox_dialogs.addWidget(self.chk_show_start_dialog)

        self.chk_show_progress_dialog = QCheckBox("Show download progress dialog")
        self.chk_show_progress_dialog.setToolTip("Show popup progress dialog during active file transfer")
        self.chk_show_progress_dialog.setChecked(_get_setting("show_progress_dialog", True))
        vbox_dialogs.addWidget(self.chk_show_progress_dialog)

        self.chk_show_complete_dialog = QCheckBox("Show download complete dialog")
        self.chk_show_complete_dialog.setToolTip("Show popup completion window when a file finishes downloading")
        self.chk_show_complete_dialog.setChecked(_get_setting("show_complete_dialog", True))
        vbox_dialogs.addWidget(self.chk_show_complete_dialog)

        self.chk_show_queue_complete_dialog = QCheckBox("Show download complete dialog for downloads in queues")
        self.chk_show_queue_complete_dialog.setToolTip("Show completion dialog for individual files inside download queues (Default: Disabled to prevent popup spam)")
        self.chk_show_queue_complete_dialog.setChecked(_get_setting("show_queue_complete_dialog", False))
        vbox_dialogs.addWidget(self.chk_show_queue_complete_dialog)

        def _on_silent_toggled(checked):
            if checked:
                self.chk_show_start_dialog.setChecked(False)
                self.chk_show_progress_dialog.setChecked(False)
                self.chk_show_complete_dialog.setChecked(False)
            self.chk_show_start_dialog.setEnabled(not checked)
            self.chk_show_progress_dialog.setEnabled(not checked)
            self.chk_show_complete_dialog.setEnabled(not checked)
            self.chk_show_queue_complete_dialog.setEnabled(not checked)

        self.chk_silent_download.toggled.connect(_on_silent_toggled)
        if self.chk_silent_download.isChecked():
            _on_silent_toggled(True)

        grp_dialogs.setLayout(vbox_dialogs)
        layout.addWidget(grp_dialogs)

        # 2. Desktop Notifications
        grp_notif = QGroupBox("Notifications")
        vbox_notif = QVBoxLayout()
        vbox_notif.setContentsMargins(10, 10, 10, 10)
        vbox_notif.setSpacing(8)

        self.chk_system_notifications = QCheckBox("Show system notification when download completes")
        current_notif = False
        if self.main_win and hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
            current_notif = self.main_win.settings.get("system_notifications", False)
        elif self.main_win and hasattr(self.main_win, "system_notifications"):
            current_notif = bool(getattr(self.main_win, "system_notifications", False))
        self.chk_system_notifications.setChecked(current_notif)
        self.chk_system_notifications.setToolTip("Send an XDG standard desktop notification when a download completes")
        vbox_notif.addWidget(self.chk_system_notifications)

        grp_notif.setLayout(vbox_notif)
        layout.addWidget(grp_notif)

        # 3. Engine Settings
        grp_engine = QGroupBox("Engine and Connection Settings")
        vbox_engine = QVBoxLayout()
        vbox_engine.setContentsMargins(10, 10, 10, 10)
        vbox_engine.setSpacing(8)
        
        # Engine status label
        self.lbl_engine = QLabel("Active Engine: Checking...")
        self.lbl_engine.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_engine.setToolTip("Connection status and backend binary for Aria2 download engine")
        vbox_engine.addWidget(self.lbl_engine)
        
        # Max Split Connections (threads)
        row_conn = QHBoxLayout()
        lbl_conn = QLabel("Max Split Connections (threads):")
        lbl_conn.setToolTip("Default number of parallel split connections / threads per download (1-32). Default: 8")
        self.spin_max_conn = QSpinBox()
        self.spin_max_conn.setRange(1, 32)
        init_conn = 8
        if hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            init_conn = self.extension_data.get("max_connections", 8)
        self.spin_max_conn.setValue(int(init_conn) if isinstance(init_conn, (int, float, str)) and str(init_conn).isdigit() else 8)
        self.spin_max_conn.setFixedWidth(70)
        self.spin_max_conn.setToolTip("Default number of parallel split connections / threads per download (1-32). Default: 8")
        row_conn.addWidget(lbl_conn)
        row_conn.addWidget(self.spin_max_conn)
        row_conn.addStretch()
        vbox_engine.addLayout(row_conn)

        # Initial check
        self.refresh_engine_status()
        
        grp_engine.setLayout(vbox_engine)
        layout.addWidget(grp_engine)

        layout.addStretch()

    def setup_startup_tab(self):
        layout = QVBoxLayout(self.startup_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        # Startup and Integration
        grp_startup = QGroupBox("Startup and Integration")
        vbox_startup = QVBoxLayout()
        vbox_startup.setContentsMargins(10, 15, 10, 10)
        vbox_startup.setSpacing(10)
        
        self.chk_startup = QCheckBox("Launch Bengal DM on system startup")
        self.chk_startup.setChecked(is_autostart_enabled())
        self.chk_startup.setToolTip("Automatically launch Bengal Download Manager on system boot")
        vbox_startup.addWidget(self.chk_startup)
        
        self.chk_start_minimized = QCheckBox("Start minimized in system tray on system startup")
        self.chk_start_minimized.setChecked(getattr(self.main_win, "start_minimized_on_autostart", False))
        self.chk_start_minimized.setEnabled(self.chk_startup.isChecked())
        self.chk_startup.toggled.connect(self.chk_start_minimized.setEnabled)
        self.chk_start_minimized.setToolTip("Launch hidden in system tray when autostarting")
        vbox_startup.addWidget(self.chk_start_minimized)
        
        grp_startup.setLayout(vbox_startup)
        layout.addWidget(grp_startup)
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
                    engine_status = "<span style='color: #3498db;'>●</span> Aria2 Starting..."
            except:
                pass
            
            aria2_bin = find_aria2() or "Not found"
            final_text = f"Active Engine: {engine_status}<br><small>Binary: {aria2_bin}</small>"
            
            # Update UI safely from background thread
            try:
                import sip
                if hasattr(self, 'lbl_engine') and not sip.isdeleted(self.lbl_engine):
                    QMetaObject.invokeMethod(self.lbl_engine, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, final_text))
            except Exception:
                pass

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
        self.rb_no_proxy.setToolTip("Connect directly to the internet without using a custom proxy")
        self.rb_no_proxy.toggled.connect(self.on_proxy_toggle)
        layout.addWidget(self.rb_no_proxy)
        self.bg_mode.addButton(self.rb_no_proxy)
        
        self.rb_manual = QRadioButton("Manual proxy configuration")
        self.rb_manual.setToolTip("Route all download traffic through a custom HTTP or HTTPS proxy server")
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
        self.rb_http.setToolTip("Use HTTP proxy protocol")
        self.rb_http.toggled.connect(self.on_proxy_toggle)
        self.rb_https = QRadioButton("HTTPS")
        self.rb_https.setToolTip("Use secure HTTPS proxy protocol")
        self.rb_https.toggled.connect(self.on_proxy_toggle)
        
        self.bg_type.addButton(self.rb_http)
        self.bg_type.addButton(self.rb_https)
        
        lbl_type = QLabel("Type:")
        lbl_type.setToolTip("Select proxy protocol type")
        type_layout.addWidget(lbl_type)
        type_layout.addWidget(self.rb_http)
        type_layout.addWidget(self.rb_https)
        type_layout.addStretch()
        manual_layout.addLayout(type_layout)
        
        # Host / Port
        addr_layout = QHBoxLayout()
        lbl_host = QLabel("Proxy host:")
        lbl_host.setToolTip("Hostname or IP address of the proxy server")
        addr_layout.addWidget(lbl_host)
        self.txt_host = QLineEdit()
        self.txt_host.setToolTip("Hostname or IP address of proxy server (e.g. 127.0.0.1 or proxy.example.com)")
        self.txt_host.textChanged.connect(self.save_proxy_data)
        self.txt_host.textChanged.connect(self.refresh_engine_status)
        addr_layout.addWidget(self.txt_host)
        
        lbl_port = QLabel("Port:")
        lbl_port.setToolTip("Port number of the proxy server (1-65535)")
        addr_layout.addWidget(lbl_port)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(8080)
        self.spin_port.setToolTip("Port number of proxy server (1-65535)")
        self.spin_port.valueChanged.connect(self.save_proxy_data)
        self.spin_port.valueChanged.connect(self.refresh_engine_status)
        addr_layout.addWidget(self.spin_port)
        manual_layout.addLayout(addr_layout)
        
        # Auth
        self.chk_auth = QCheckBox("Authentication required")
        self.chk_auth.setToolTip("Enable username and password credentials for proxy authentication")
        self.chk_auth.toggled.connect(self.update_proxy_ui)
        self.chk_auth.toggled.connect(self.save_proxy_data)
        self.chk_auth.toggled.connect(self.refresh_engine_status)
        manual_layout.addWidget(self.chk_auth)
        
        auth_layout = QGridLayout()
        lbl_user = QLabel("Username:")
        lbl_user.setToolTip("Username for proxy authentication")
        auth_layout.addWidget(lbl_user, 0, 0)
        self.txt_user = QLineEdit()
        self.txt_user.setToolTip("Username for proxy server authentication")
        self.txt_user.textChanged.connect(self.save_proxy_data)
        self.txt_user.textChanged.connect(self.refresh_engine_status)
        auth_layout.addWidget(self.txt_user, 0, 1)
        
        lbl_pass = QLabel("Password:")
        lbl_pass.setToolTip("Password for proxy authentication")
        auth_layout.addWidget(lbl_pass, 1, 0)
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setToolTip("Password for proxy server authentication")
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
        self.rb_https.blockSignals(True)
        self.txt_host.blockSignals(True)
        self.spin_port.blockSignals(True)
        self.chk_auth.blockSignals(True)
        self.txt_user.blockSignals(True)
        self.txt_pass.blockSignals(True)
        
        if self.proxy_data["mode"] == "manual":
            self.rb_manual.setChecked(True)
        else:
            self.rb_no_proxy.setChecked(True)
            
        ptype = str(self.proxy_data.get("type", "http")).lower()
        if ptype == "https":
            self.rb_https.setChecked(True)
        else:
            self.rb_http.setChecked(True)
        
        self.txt_host.setText(self.proxy_data.get("host", ""))
        self.spin_port.setValue(self.proxy_data.get("port", 8080))
        self.chk_auth.setChecked(self.proxy_data.get("auth", False))
        self.txt_user.setText(self.proxy_data.get("user", ""))
        self.txt_pass.setText(self.proxy_data.get("password", ""))

        self.rb_manual.blockSignals(False)
        self.rb_no_proxy.blockSignals(False)
        self.rb_http.blockSignals(False)
        self.rb_https.blockSignals(False)
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

    def setup_media_tab(self):
        layout = QVBoxLayout(self.media_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        media_defaults = self.config_data.get("media_downloader_defaults", {})

        # 1. Browser Integration and Auto-Start
        grp_browser = QGroupBox("Browser Integration and Auto-Start")
        vbox_browser = QVBoxLayout(grp_browser)
        vbox_browser.setContentsMargins(10, 15, 10, 15)
        vbox_browser.setSpacing(10)

        self.chk_auto_start_media = QCheckBox("Auto-start media downloads when sent from browser")
        self.chk_auto_start_media.setToolTip("Automatically analyze and start downloading media streams sent from browser without extra confirmation")
        self.chk_auto_start_media.setChecked(bool(media_defaults.get("auto_start_media", False)))
        vbox_browser.addWidget(self.chk_auto_start_media)

        row_media_q = QHBoxLayout()
        row_media_q.addWidget(QLabel("Preselected Quality Target:"))
        self.cmb_media_quality = QComboBox()
        self.cmb_media_quality.setToolTip("Default quality preset to select when auto-starting media downloads")
        self.cmb_media_quality.addItems([
            "Best Quality (Video + Audio merged)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "360p Low Quality",
            "Audio Only (MP3)"
        ])
        saved_q = media_defaults.get("auto_media_quality_preset", "1080p Full HD")
        idx_q = self.cmb_media_quality.findText(saved_q)
        if idx_q != -1:
            self.cmb_media_quality.setCurrentIndex(idx_q)
        else:
            self.cmb_media_quality.setCurrentIndex(3)  # 1080p Full HD
        
        row_media_q.addWidget(self.cmb_media_quality, stretch=1)
        vbox_browser.addLayout(row_media_q)
        layout.addWidget(grp_browser)

        # 2. Authentication and Cookie Vault Defaults
        grp_cookies = QGroupBox("Authentication and Cookie Vault Defaults")
        vbox_cookies = QVBoxLayout(grp_cookies)
        vbox_cookies.setContentsMargins(10, 15, 10, 15)
        vbox_cookies.setSpacing(10)

        row_cookies_config = QHBoxLayout()
        lbl_cookie = QLabel("Cookie:")
        lbl_cookie.setToolTip("Select cookie authentication strategy for media sites")
        row_cookies_config.addWidget(lbl_cookie)
        self.cmb_opt_cookies_mode = QComboBox()
        self.cmb_opt_cookies_mode.setToolTip("Select cookie authentication source (Netscape file, browser auto-extract, or none)")
        self.cmb_opt_cookies_mode.addItems([
            "Netscape File (cookies.txt)",
            "Browser Auto-Extraction",
            "None (Anonymous / Public)"
        ])
        saved_cmode = media_defaults.get("cookies_mode_idx", 0)
        self.cmb_opt_cookies_mode.setCurrentIndex(min(max(0, saved_cmode), 2))
        row_cookies_config.addWidget(self.cmb_opt_cookies_mode, stretch=1)

        self.lbl_opt_cookies_browser = QLabel("Browser:")
        self.lbl_opt_cookies_browser.setToolTip("Select installed web browser to extract cookies from")
        row_cookies_config.addWidget(self.lbl_opt_cookies_browser)
        self.cmb_opt_cookies_browser = QComboBox()
        self.cmb_opt_cookies_browser.setToolTip("Select web browser to automatically extract authenticated cookies")
        self.cmb_opt_cookies_browser.addItems(["Chrome", "Firefox", "Brave", "Edge", "Chromium", "Vivaldi", "Opera"])
        saved_cbrowser = self.config_data.get("media_downloader_cookies_browser", media_defaults.get("cookies_browser", "Chrome"))
        idx_cb = self.cmb_opt_cookies_browser.findText(saved_cbrowser, Qt.MatchFlag.MatchFixedString)
        if idx_cb != -1:
            self.cmb_opt_cookies_browser.setCurrentIndex(idx_cb)
        row_cookies_config.addWidget(self.cmb_opt_cookies_browser, stretch=1)
        vbox_cookies.addLayout(row_cookies_config)

        # Full-width cookies path input with Browse / Clear buttons below
        self.lbl_opt_cookies_path = QLabel("Netscape cookies.txt Path:")
        self.lbl_opt_cookies_path.setToolTip("File path to exported Netscape format cookies.txt")
        vbox_cookies.addWidget(self.lbl_opt_cookies_path)

        self.txt_opt_cookies_path = QLineEdit()
        self.txt_opt_cookies_path.setPlaceholderText("Path to exported Netscape cookies.txt file...")
        self.txt_opt_cookies_path.setToolTip("Path to exported Netscape format cookies.txt file on disk")
        saved_cpath = self.config_data.get("media_downloader_cookies_path", media_defaults.get("cookies_path", ""))
        self.txt_opt_cookies_path.setText(saved_cpath)
        vbox_cookies.addWidget(self.txt_opt_cookies_path)

        row_cbuttons = QHBoxLayout()
        row_cbuttons.addStretch()

        self.btn_opt_browse_c = QPushButton("Browse...")
        self.btn_opt_browse_c.setFixedWidth(90)
        self.btn_opt_browse_c.setToolTip("Browse filesystem for exported cookies.txt file")
        self.btn_opt_browse_c.clicked.connect(self._browse_opt_cookies_file)
        row_cbuttons.addWidget(self.btn_opt_browse_c)

        self.btn_opt_clear_c = QPushButton("Clear")
        self.btn_opt_clear_c.setFixedWidth(80)
        self.btn_opt_clear_c.setToolTip("Clear current cookies.txt file path")
        self.btn_opt_clear_c.clicked.connect(self.txt_opt_cookies_path.clear)
        row_cbuttons.addWidget(self.btn_opt_clear_c)

        vbox_cookies.addLayout(row_cbuttons)

        self.cmb_opt_cookies_mode.currentIndexChanged.connect(self._update_opt_cookies_ui)
        self._update_opt_cookies_ui()

        layout.addWidget(grp_cookies)

        # 3. YouTube Extractor & Player Client Settings
        grp_extractor = QGroupBox("YouTube Extractor Engine Settings")
        vbox_extractor = QVBoxLayout(grp_extractor)
        vbox_extractor.setContentsMargins(10, 15, 10, 15)
        vbox_extractor.setSpacing(10)

        row_client = QHBoxLayout()
        row_client.addWidget(QLabel("YouTube Player Client:"))
        self.txt_opt_youtube_client = QLineEdit()
        self.txt_opt_youtube_client.setPlaceholderText("e.g. default, android, web, ios, tv, android_vr, mweb...")
        self.txt_opt_youtube_client.setToolTip("YouTube player client(s) passed to yt-dlp via --extractor-args youtube:player_client=...\nDefault is 'default'. Multiple clients can be comma-separated (e.g. 'default', 'android', 'web').")
        saved_client = media_defaults.get("youtube_player_client", "default")
        self.txt_opt_youtube_client.setText(saved_client)
        row_client.addWidget(self.txt_opt_youtube_client, stretch=1)

        self.btn_opt_reset_youtube_client = QPushButton("Reset")
        self.btn_opt_reset_youtube_client.setFixedWidth(80)
        self.btn_opt_reset_youtube_client.setToolTip("Reset YouTube player client to default ('default')")
        self.btn_opt_reset_youtube_client.clicked.connect(lambda: self.txt_opt_youtube_client.setText("default"))
        row_client.addWidget(self.btn_opt_reset_youtube_client)

        vbox_extractor.addLayout(row_client)
        layout.addWidget(grp_extractor)

        layout.addStretch()

    def _update_opt_cookies_ui(self):
        mode_idx = self.cmb_opt_cookies_mode.currentIndex() if hasattr(self, "cmb_opt_cookies_mode") else 0
        # 0 = Netscape File, 1 = Browser Auto-Extraction, 2 = None
        is_file_mode = (mode_idx == 0)
        is_browser_mode = (mode_idx == 1)

        if hasattr(self, "lbl_opt_cookies_browser"):
            self.lbl_opt_cookies_browser.setEnabled(is_browser_mode)
        if hasattr(self, "cmb_opt_cookies_browser"):
            self.cmb_opt_cookies_browser.setEnabled(is_browser_mode)

        if hasattr(self, "lbl_opt_cookies_path"):
            self.lbl_opt_cookies_path.setEnabled(is_file_mode)
        if hasattr(self, "txt_opt_cookies_path"):
            self.txt_opt_cookies_path.setEnabled(is_file_mode)
        if hasattr(self, "btn_opt_browse_c"):
            self.btn_opt_browse_c.setEnabled(is_file_mode)
        if hasattr(self, "btn_opt_clear_c"):
            self.btn_opt_clear_c.setEnabled(is_file_mode)

    def _browse_opt_cookies_file(self):
        current_path = self.txt_opt_cookies_path.text().strip()
        folder = os.path.dirname(current_path) if (current_path and os.path.exists(current_path)) else os.path.expanduser("~")
        file_path = choose_portal_open_file_path(title="Select Netscape Cookies File", folder=folder)
        if file_path is None:
            from PyQt6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Netscape Cookies File",
                folder,
                "Text Files (*.txt);;All Files (*)"
            )
        if file_path:
            self.txt_opt_cookies_path.setText(file_path)

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
        ptype = "https" if self.rb_https.isChecked() else "http"
        
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

        # Dynamically update running Aria2 daemon proxy settings via RPC
        proxy_url = get_aria2_proxy_url(self.proxy_data)
        token = self.txt_aria_token.text().strip() if hasattr(self, 'txt_aria_token') else self.extension_data.get("token", "")
        rpc_port = self.spin_aria_port.value() if hasattr(self, 'spin_aria_port') else self.extension_data.get("port", 56800)
        try:
            call_aria2_rpc("aria2.changeGlobalOption", [{"all-proxy": proxy_url}], port=rpc_port, token=token)
        except Exception:
            pass

    def save_extension_data(self):
        max_c = 8
        if hasattr(self, "spin_max_conn"):
            max_c = self.spin_max_conn.value()
        elif hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            max_c = self.extension_data.get("max_connections", 8)

        proto = "ws"
        if hasattr(self, "combo_aria_proto"):
            proto = self.combo_aria_proto.currentData()
        elif hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            proto = self.extension_data.get("protocol", "ws")

        port = 56800
        if hasattr(self, "spin_aria_port"):
            port = self.spin_aria_port.value()
        elif hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            port = self.extension_data.get("port", 56800)

        token = ""
        if hasattr(self, "txt_aria_token"):
            token = self.txt_aria_token.text().strip()
        elif hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            token = self.extension_data.get("token", "")

        self.extension_data = {
            "protocol": proto, 
            "host": "localhost",
            "port": port,
            "token": token,
            "max_connections": max_c
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

    def on_appearance_preview(self, text=None):
        t = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Dark (Default)"
        a = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"
        i = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"
        tr = self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"
        if self.main_win:
            preview_fn = getattr(self.main_win, "preview_appearance", None)
            if callable(preview_fn):
                preview_fn(t, a, i, tr)

    def reject(self):
        if self.main_win:
            preview_fn = getattr(self.main_win, "preview_appearance", None)
            if callable(preview_fn):
                t = getattr(self, 'initial_theme', 'BDM Dark (Default)')
                a = getattr(self, 'initial_accent', 'BDM (Default)')
                i = getattr(self, 'initial_icon_theme', 'BDM Auto')
                tr = getattr(self, 'initial_tray_icon', 'App Icon (Default)')
                preview_fn(t, a, i, tr)
        super().reject()

    def save_and_accept(self):
        self.config_data["temp_dir"] = self.txt_temp_path.text()

        # Save Media Downloader defaults
        media_defaults = self.config_data.get("media_downloader_defaults", {})
        if hasattr(self, "chk_auto_start_media"):
            media_defaults["auto_start_media"] = self.chk_auto_start_media.isChecked()
        if hasattr(self, "cmb_media_quality"):
            media_defaults["auto_media_quality_preset"] = self.cmb_media_quality.currentText()
        if hasattr(self, "cmb_opt_cookies_mode"):
            media_defaults["cookies_mode_idx"] = self.cmb_opt_cookies_mode.currentIndex()
        if hasattr(self, "cmb_opt_cookies_browser"):
            b_name = self.cmb_opt_cookies_browser.currentText()
            media_defaults["cookies_browser"] = b_name
            self.config_data["media_downloader_cookies_browser"] = b_name
        if hasattr(self, "txt_opt_cookies_path"):
            c_path = self.txt_opt_cookies_path.text().strip()
            media_defaults["cookies_path"] = c_path
            self.config_data["media_downloader_cookies_path"] = c_path
        if hasattr(self, "txt_opt_youtube_client"):
            media_defaults["youtube_player_client"] = self.txt_opt_youtube_client.text().strip() or "default"
        self.config_data["media_downloader_defaults"] = media_defaults

        save_category_config(self.config_data)
        
        new_scale = self.combo_scale.currentText()
        new_theme = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Dark (Default)"
        new_accent = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"
        new_icon_theme = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"
        new_tray_icon = self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"
        scale_changed = hasattr(self, 'initial_scale') and (self.initial_scale != new_scale)

        # Save start_minimized_on_autostart, ui_scale, theme, accent, icon_theme, tray_icon, system_notifications, and dialog visibility to parent (MainWindow)
        if self.main_win:
            setattr(self.main_win, "start_minimized_on_autostart", self.chk_start_minimized.isChecked())
            is_notif = self.chk_system_notifications.isChecked() if hasattr(self, "chk_system_notifications") else False
            setattr(self.main_win, "system_notifications", is_notif)
            
            silent_dl = self.chk_silent_download.isChecked() if hasattr(self, "chk_silent_download") else False
            show_start = self.chk_show_start_dialog.isChecked() if hasattr(self, "chk_show_start_dialog") else True
            show_prog = self.chk_show_progress_dialog.isChecked() if hasattr(self, "chk_show_progress_dialog") else True
            show_comp = self.chk_show_complete_dialog.isChecked() if hasattr(self, "chk_show_complete_dialog") else True
            show_q_comp = self.chk_show_queue_complete_dialog.isChecked() if hasattr(self, "chk_show_queue_complete_dialog") else False

            setattr(self.main_win, "silent_download", silent_dl)
            setattr(self.main_win, "show_start_dialog", show_start)
            setattr(self.main_win, "show_progress_dialog", show_prog)
            setattr(self.main_win, "show_complete_dialog", show_comp)
            setattr(self.main_win, "show_queue_complete_dialog", show_q_comp)

            if hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
                self.main_win.settings["ui_scale"] = new_scale
                self.main_win.settings["theme"] = new_theme
                self.main_win.settings["accent"] = new_accent
                self.main_win.settings["icon_theme"] = new_icon_theme
                self.main_win.settings["tray_icon"] = new_tray_icon
                self.main_win.settings["system_notifications"] = is_notif
                self.main_win.settings["silent_download"] = silent_dl
                self.main_win.settings["show_start_dialog"] = show_start
                self.main_win.settings["show_progress_dialog"] = show_prog
                self.main_win.settings["show_complete_dialog"] = show_comp
                self.main_win.settings["show_queue_complete_dialog"] = show_q_comp

            apply_fn = getattr(self.main_win, "apply_appearance_setting", None)
            if callable(apply_fn):
                apply_fn(new_theme, new_accent, new_icon_theme, new_tray_icon)
            else:
                save_fn = getattr(self.main_win, "save_settings", None)
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
        return self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Dark (Default)"

    def get_accent(self):
        return self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"

    def get_icon_theme(self):
        return self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"

    def get_tray_icon(self):
        return self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"

    def get_silent_download(self) -> bool:
        return self.chk_silent_download.isChecked() if hasattr(self, "chk_silent_download") else False

    def get_show_start_dialog(self) -> bool:
        return self.chk_show_start_dialog.isChecked() if hasattr(self, "chk_show_start_dialog") else True

    def get_show_progress_dialog(self) -> bool:
        return self.chk_show_progress_dialog.isChecked() if hasattr(self, "chk_show_progress_dialog") else True

    def get_show_complete_dialog(self) -> bool:
        return self.chk_show_complete_dialog.isChecked() if hasattr(self, "chk_show_complete_dialog") else True

    def get_show_queue_complete_dialog(self) -> bool:
        return self.chk_show_queue_complete_dialog.isChecked() if hasattr(self, "chk_show_queue_complete_dialog") else False
