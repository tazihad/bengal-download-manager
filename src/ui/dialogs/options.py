import os
import subprocess
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QWidget, QGroupBox, QComboBox, QCheckBox, QSpinBox,
    QRadioButton, QButtonGroup, QFrame, QStyle, QGridLayout, QMessageBox,
    QApplication, QStackedWidget, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from core.utils import (
    load_proxy_config, save_proxy_config, get_aria2_proxy_url,
    load_extension_config, save_extension_config, call_aria2_rpc,
    find_aria2, choose_portal_save_path, choose_portal_folder_path, choose_portal_open_file_path,
    is_autostart_enabled, set_autostart_enabled, get_user_downloads_dir, get_user_home_dir
)
from core.config import load_category_config, save_category_config
from core.memory_guard import MemoryGuard

class TwoRowTabWidget(QWidget):
    """Two-row tab bar widget matching IDM design aesthetics across themes."""
    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = []
        self._buttons = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.idClicked.connect(self._on_button_clicked)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 2-Row Tab Bars
        tabs_layout = QVBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(2)

        self.row1_layout = QHBoxLayout()
        self.row1_layout.setContentsMargins(0, 0, 0, 0)
        self.row1_layout.setSpacing(2)

        self.row2_layout = QHBoxLayout()
        self.row2_layout.setContentsMargins(0, 0, 0, 0)
        self.row2_layout.setSpacing(2)

        tabs_layout.addLayout(self.row1_layout)
        tabs_layout.addLayout(self.row2_layout)
        main_layout.addLayout(tabs_layout)

        # Content container
        self.container_frame = QFrame()
        self.container_frame.setObjectName("twoRowTabContainer")
        self.container_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.stack = QStackedWidget(self.container_frame)

        container_layout = QVBoxLayout(self.container_frame)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.addWidget(self.stack)

        main_layout.addWidget(self.container_frame, 1)

        self.setStyleSheet("""
            QFrame#twoRowTabContainer {
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: palette(window);
            }
            QPushButton.twoRowTabBtn {
                border: 1px solid palette(mid);
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 4px 6px;
                font-size: 12px;
                background-color: palette(button);
                color: palette(button-text);
                min-height: 20px;
            }
            QPushButton.twoRowTabBtn:hover {
                background-color: palette(light);
            }
            QPushButton.twoRowTabBtn:checked {
                font-weight: bold;
                background-color: palette(window);
                border-top: 2px solid palette(highlight);
                color: palette(window-text);
            }
        """)

    def addTab(self, widget, label, row=2):
        idx = len(self._widgets)
        self._widgets.append((widget, label, row))
        self.stack.addWidget(widget)

        btn = QPushButton(label)
        btn.setProperty("class", "twoRowTabBtn")
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons.append(btn)
        self._button_group.addButton(btn, idx)

        if row == 1:
            self.row1_layout.addWidget(btn)
        else:
            self.row2_layout.addWidget(btn)

        if idx == 0:
            btn.setChecked(True)
            self.stack.setCurrentIndex(0)
        return idx

    def _on_button_clicked(self, idx):
        self.setCurrentIndex(idx)

    def setCurrentIndex(self, idx):
        if 0 <= idx < len(self._widgets):
            self.stack.setCurrentIndex(idx)
            btn = self._button_group.button(idx)
            if btn and not btn.isChecked():
                btn.setChecked(True)
            self.currentChanged.emit(idx)

    def setCurrentWidget(self, widget):
        for idx, (w, _, _) in enumerate(self._widgets):
            if w == widget:
                self.setCurrentIndex(idx)
                break

    def currentIndex(self):
        return self.stack.currentIndex()

    def currentWidget(self):
        return self.stack.currentWidget()

    def widget(self, idx):
        return self.stack.widget(idx)

    def indexOf(self, widget):
        for idx, (w, _, _) in enumerate(self._widgets):
            if w == widget:
                return idx
        return -1

    def count(self):
        return len(self._widgets)

    def tabText(self, idx):
        if 0 <= idx < len(self._widgets):
            return self._widgets[idx][1]
        return ""

    def setTabText(self, idx, text):
        if 0 <= idx < len(self._widgets):
            w, _, r = self._widgets[idx]
            self._widgets[idx] = (w, text, r)
            if idx < len(self._buttons):
                self._buttons[idx].setText(text)

class OptionsDialog(QDialog):
    def __init__(self, main_window=None, parent=None, initial_tab=None):
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

        self.tabs = TwoRowTabWidget()
        layout.addWidget(self.tabs)
        
        # Row 1 (Top: Core Settings)
        self.general_tab = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.general_tab, "General", row=1)

        self.downloads_tab = QWidget()
        self.setup_downloads_tab()
        self.tabs.addTab(self.downloads_tab, "Downloads", row=1)

        self.saveto_tab = QWidget()
        self.setup_saveto_tab()
        self.tabs.addTab(self.saveto_tab, "Save To", row=1)

        self.startup_tab = QWidget()
        self.setup_startup_tab()
        self.tabs.addTab(self.startup_tab, "Startup", row=1)

        # Row 2 (Bottom: Integrations & Network)
        self.extension_tab = QWidget()
        self.setup_extension_tab()
        self.tabs.addTab(self.extension_tab, "Extensions", row=2)

        self.media_tab = QWidget()
        self.setup_media_tab()
        self.tabs.addTab(self.media_tab, "Media", row=2)

        self.aria2_tab = QWidget()
        self.setup_aria2_tab()
        self.tabs.addTab(self.aria2_tab, "Aria2 / RPC", row=2)

        self.proxy_tab = QWidget()
        self.setup_proxy_tab()
        self.tabs.addTab(self.proxy_tab, "Proxy / Socks", row=2)

        # Default to General tab in Row 1 or initial_tab if specified
        if initial_tab is not None:
            self.select_tab(initial_tab)
        else:
            self.tabs.setCurrentWidget(self.general_tab)

        self.tabs.currentChanged.connect(lambda idx: self.refresh_engine_status() if any(k in self.tabs.tabText(idx) for k in ("Downloads", "Aria2", "RPC")) else None)
        if hasattr(self, 'spin_aria_port'):
            self.spin_aria_port.valueChanged.connect(self.refresh_engine_status)
        if hasattr(self, 'txt_aria_token'):
            self.txt_aria_token.textChanged.connect(self.refresh_engine_status)
        
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

    def select_tab(self, target):
        """Switches to the tab specified by QWidget, index (int), or name string (e.g. 'media')."""
        if isinstance(target, QWidget):
            self.tabs.setCurrentWidget(target)
            return
        if isinstance(target, int):
            self.tabs.setCurrentIndex(target)
            return
        if isinstance(target, str):
            target_lower = target.strip().lower()
            for idx, (_, label, _) in enumerate(self.tabs._widgets):
                if target_lower in label.lower():
                    self.tabs.setCurrentIndex(idx)
                    return

    @property
    def main_win(self):
        return getattr(self, "_main_window", None) or self.parent()

    def setup_general_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
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
        self.combo_theme.setMaxVisibleItems(10)
        self.combo_theme.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_theme = self.combo_theme.view()
        if view_theme:
            view_theme.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        theme_options = [
            "BDM Auto (Default)", "System", "BDM Dark", "BDM Light",
            "Breeze Dark", "Breeze Light", "Catppuccin",
            "Dracula", "IDM Classic", "Kirigami Dark", 
            "Kirigami Light", "Material You Dark", "Material You Light",
            "Nord", "Obsidian Flow", "One Dark", 
            "Solarized Dark", "Solarized Light", 
            "Stellar Dark", "Stellar Light",
            "Twilight", "Ubuntu Dark", "Ubuntu Light"
        ]
        self.combo_theme.addItems(theme_options)

        lbl_accent = QLabel("Accent:")
        lbl_accent.setToolTip("Select accent/highlight color")
        self.combo_accent = QComboBox()
        self.combo_accent.setToolTip("Select accent/highlight color")
        self.combo_accent.setMaxVisibleItems(10)
        self.combo_accent.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_accent = self.combo_accent.view()
        if view_accent:
            view_accent.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        accent_options = [
            "System", "BDM (Default)", "Amethyst Violet", "Breeze Blue", 
            "Crimson Red", "Dracula Purple", "Emerald Green", 
            "Material Cobalt", "Material Violet", "Nord Frost", 
            "Obsidian Purple", "Stellar Blue", "Twilight", "Ubuntu Orange", "Windows Blue"
        ]
        self.combo_accent.addItems(accent_options)

        lbl_icon_theme = QLabel("Icons:")
        lbl_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        self.combo_icon_theme = QComboBox()
        self.combo_icon_theme.setToolTip("Select icon theme set for toolbar and sidebar")
        self.combo_icon_theme.setMaxVisibleItems(10)
        self.combo_icon_theme.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_icons = self.combo_icon_theme.view()
        if view_icons:
            view_icons.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        icon_theme_options = ["BDM Auto (Default)", "BDM Dark", "BDM Light", "Adwaita", "Breeze", "Breeze Dark", "HighColor", "Modern Color", "Stellar", "Yaru"]
        self.combo_icon_theme.addItems(icon_theme_options)

        lbl_tray_icon = QLabel("Tray Icon:")
        lbl_tray_icon.setToolTip("Select system tray icon style")
        self.combo_tray_icon = QComboBox()
        self.combo_tray_icon.setToolTip("Select system tray icon style")
        self.combo_tray_icon.setMaxVisibleItems(10)
        self.combo_tray_icon.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_tray = self.combo_tray_icon.view()
        if view_tray:
            view_tray.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tray_icon_options = [
            "App Icon (Default)", "Automatic", "Monochrome Dark", "Monochrome Light"
        ]
        self.combo_tray_icon.addItems(tray_icon_options)

        lbl_titlebar = QLabel("Title bar:")
        lbl_titlebar.setToolTip("Select title bar theme: follow system theme, system light, or system dark")
        self.combo_titlebar = QComboBox()
        self.combo_titlebar.setToolTip("Select title bar theme: Automatic (follow system theme), Light, or Dark")
        self.combo_titlebar.setMaxVisibleItems(10)
        self.combo_titlebar.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_titlebar = self.combo_titlebar.view()
        if view_titlebar:
            view_titlebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        titlebar_options = ["Automatic", "Light", "Dark"]
        self.combo_titlebar.addItems(titlebar_options)

        grid_theme.addWidget(lbl_theme, 0, 0)
        grid_theme.addWidget(self.combo_theme, 0, 1)
        grid_theme.addWidget(lbl_accent, 0, 2)
        grid_theme.addWidget(self.combo_accent, 0, 3)

        grid_theme.addWidget(lbl_icon_theme, 1, 0)
        grid_theme.addWidget(self.combo_icon_theme, 1, 1)
        grid_theme.addWidget(lbl_tray_icon, 1, 2)
        grid_theme.addWidget(self.combo_tray_icon, 1, 3)

        grid_theme.addWidget(lbl_titlebar, 2, 0)
        grid_theme.addWidget(self.combo_titlebar, 2, 1)

        grp_theme.setLayout(grid_theme)

        current_theme = "BDM Auto (Default)"
        current_accent = "BDM (Default)"
        current_icon_theme = "BDM Auto (Default)"
        current_tray_icon = "App Icon (Default)"
        current_titlebar = "Automatic"
        if self.main_win and hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
            current_theme = self.main_win.settings.get("theme", "BDM Auto (Default)")
            current_accent = self.main_win.settings.get("accent", "BDM (Default)")
            current_icon_theme = self.main_win.settings.get("icon_theme", "BDM (Default)")
            current_tray_icon = self.main_win.settings.get("tray_icon", "App Icon (Default)")
            current_titlebar = self.main_win.settings.get("title_bar", "Automatic")

        try:
            from core.services.theme_service import (
                normalize_theme_name, normalize_accent_name,
                normalize_icon_theme_name, normalize_tray_icon_name,
                normalize_titlebar_name
            )
            current_theme = normalize_theme_name(current_theme)
            current_accent = normalize_accent_name(current_accent)
            current_icon_theme = normalize_icon_theme_name(current_icon_theme)
            current_tray_icon = normalize_tray_icon_name(current_tray_icon)
            current_titlebar = normalize_titlebar_name(current_titlebar)
        except Exception:
            pass

        self.initial_theme = current_theme
        self.initial_accent = current_accent
        self.initial_icon_theme = current_icon_theme
        self.initial_tray_icon = current_tray_icon
        self.initial_titlebar = current_titlebar

        idx_t = self.combo_theme.findText(current_theme)
        if idx_t == -1: idx_t = self.combo_theme.findText("BDM Auto (Default)")
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

        idx_tb = self.combo_titlebar.findText(current_titlebar)
        if idx_tb == -1: idx_tb = self.combo_titlebar.findText("Automatic")
        if idx_tb != -1: self.combo_titlebar.setCurrentIndex(idx_tb)

        # Connect live preview signals
        self.combo_theme.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_accent.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_icon_theme.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_tray_icon.currentTextChanged.connect(self.on_appearance_preview)
        self.combo_titlebar.currentTextChanged.connect(self.on_appearance_preview)

        layout.addWidget(grp_theme)

        # 2. UI Settings (Scale & Language)
        grp_ui = QGroupBox("UI Settings")
        grid_ui = QGridLayout()
        grid_ui.setContentsMargins(10, 8, 10, 8)
        grid_ui.setSpacing(10)

        lbl_scale = QLabel("Scale:")
        lbl_scale.setToolTip("Set user interface scale factor")
        self.combo_scale = QComboBox()
        self.combo_scale.setToolTip("Set user interface scale factor")
        self.combo_scale.setMaxVisibleItems(10)
        self.combo_scale.setStyleSheet("QComboBox { combobox-popup: 0; }")
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

        lbl_language = QLabel("Language:")
        lbl_language.setToolTip("Select user interface language")
        self.combo_language = QComboBox()
        self.combo_language.setToolTip("Select interface language (Restart recommended to apply changes to all windows)")
        self.combo_language.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo_language.setMinimumContentsLength(18)
        self.combo_language.setMaxVisibleItems(10)
        self.combo_language.setStyleSheet("QComboBox { combobox-popup: 0; }")
        view_lang = self.combo_language.view()
        if view_lang:
            view_lang.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            view_lang.setUniformItemSizes(True)

        from core.services.language_service import (
            get_available_languages, get_language_display
        )
        self.combo_language.addItems(get_available_languages())

        current_language = "system"
        if self.main_win and hasattr(self.main_win, "settings") and isinstance(self.main_win.settings, dict):
            current_language = self.main_win.settings.get("language", "system")

        current_lang_display = get_language_display(current_language)
        idx_lang = self.combo_language.findText(current_lang_display)
        if idx_lang != -1:
            self.combo_language.setCurrentIndex(idx_lang)
        else:
            self.combo_language.setCurrentIndex(0)

        self.initial_language = self.combo_language.currentText()

        grid_ui.addWidget(lbl_scale, 0, 0)
        grid_ui.addWidget(self.combo_scale, 0, 1)
        grid_ui.addWidget(lbl_language, 0, 2)
        grid_ui.addWidget(self.combo_language, 0, 3)
        grid_ui.setColumnStretch(4, 1)

        grp_ui.setLayout(grid_ui)
        layout.addWidget(grp_ui)
        layout.addStretch()

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.general_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def setup_downloads_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
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

        default_progress_tooltip = "Show popup progress dialog during active file transfer"
        disabled_by_start_tooltip = "Show popup progress dialog during active file transfer (Requires 'Show start download dialog' to be enabled)"
        disabled_by_silent_tooltip = "Show popup progress dialog during active file transfer (Disabled when Silent Download is enabled)"

        def _update_dialog_checkbox_states():
            silent = self.chk_silent_download.isChecked()
            start_enabled = not silent
            self.chk_show_start_dialog.setEnabled(start_enabled)

            prog_enabled = start_enabled and self.chk_show_start_dialog.isChecked()
            self.chk_show_progress_dialog.setEnabled(prog_enabled)
            if silent:
                self.chk_show_progress_dialog.setToolTip(disabled_by_silent_tooltip)
            elif not self.chk_show_start_dialog.isChecked():
                self.chk_show_progress_dialog.setToolTip(disabled_by_start_tooltip)
            else:
                self.chk_show_progress_dialog.setToolTip(default_progress_tooltip)

            self.chk_show_complete_dialog.setEnabled(not silent)
            self.chk_show_queue_complete_dialog.setEnabled(not silent)

        self.chk_silent_download.toggled.connect(lambda _: _update_dialog_checkbox_states())
        self.chk_show_start_dialog.toggled.connect(lambda _: _update_dialog_checkbox_states())
        _update_dialog_checkbox_states()

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

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.downloads_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def setup_startup_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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
        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.startup_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)


    def refresh_engine_status(self):
        """Re-tests the Aria2 RPC connection and updates the label in background."""
        if not hasattr(self, 'lbl_engine'): return
        
        token = self.txt_aria_token.text().strip() if hasattr(self, 'txt_aria_token') else self.extension_data.get("token", "")
        rpc_port = self.spin_aria_port.value() if hasattr(self, 'spin_aria_port') else self.extension_data.get("port", 56800)
        
        self.lbl_engine.setText("Active Engine: <span style='color: #3498db;'>●</span> Checking...")
        
        def check():
            engine_status = "<span style='color: orange;'>●</span> Fallback (Custom Python)"
            try:
                result = call_aria2_rpc("aria2.getVersion", port=rpc_port, token=token)
                if result and isinstance(result, dict) and "version" in result:
                    version = result.get('version', 'Unknown')
                    engine_status = f"<span style='color: #00ca00;'>●</span> Aria2 Connected (v{version})"
                else:
                    aria2_bin = find_aria2()
                    if not aria2_bin:
                        engine_status = "<span style='color: red;'>●</span> Aria2 Not Installed (Python Engine Active)"
                    else:
                        engine_status = "<span style='color: orange;'>●</span> Offline (Python Fallback Active)"
            except Exception:
                pass
            
            aria2_bin = find_aria2() or "Not found"
            final_text = f"Active Engine: {engine_status}<br><small>Binary: {aria2_bin}</small>"
            
            # Update UI safely from background thread
            try:
                from PyQt6 import sip
                if hasattr(self, 'lbl_engine') and not sip.isdeleted(self.lbl_engine):
                    QMetaObject.invokeMethod(self.lbl_engine, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, final_text))
            except Exception:
                pass

        threading.Thread(target=check, daemon=True).start()

    def setup_saveto_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
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
        
        grp_temp = QGroupBox("Temporary / Cache directory")
        temp_layout = QVBoxLayout(grp_temp)
        temp_layout.setContentsMargins(10, 15, 10, 15)
        temp_layout.setSpacing(10)
        
        temp_dir_row = QHBoxLayout()
        self.txt_temp_path = QLineEdit()
        self.txt_temp_path.setText(self.config_data.get("temp_dir", ""))
        self.txt_temp_path.setToolTip("Temporary and cache directory used for downloading chunks, video stream fragments, and incomplete downloads before merging")
        temp_dir_row.addWidget(self.txt_temp_path)
        
        btn_browse_temp = QPushButton("Browse")
        btn_browse_temp.setToolTip("Browse folder for temporary chunk and cache storage")
        btn_browse_temp.clicked.connect(lambda: self.browse_folder(self.txt_temp_path))
        temp_layout.addLayout(temp_dir_row)
        
        grp_temp.setLayout(temp_layout)
        layout.addWidget(grp_temp)
        layout.addStretch()

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.saveto_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)
        self.on_category_changed(self.combo_cat.currentText())

    def on_proxy_toggle(self, checked):
        if checked:
            self.update_proxy_ui()
            self.save_proxy_data()
            self.refresh_engine_status()

    def setup_proxy_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
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
        self.rb_socks5 = QRadioButton("SOCKS5")
        self.rb_socks5.setToolTip("Use SOCKS5 proxy protocol (with optional user/password authentication)")
        self.rb_socks5.toggled.connect(self.on_proxy_toggle)
        self.rb_socks4 = QRadioButton("SOCKS4")
        self.rb_socks4.setToolTip("Use SOCKS4 proxy protocol (user identity only)")
        self.rb_socks4.toggled.connect(self.on_proxy_toggle)

        self.bg_type.addButton(self.rb_http)
        self.bg_type.addButton(self.rb_https)
        self.bg_type.addButton(self.rb_socks5)
        self.bg_type.addButton(self.rb_socks4)

        lbl_type = QLabel("Type:")
        lbl_type.setToolTip("Select proxy protocol type")
        type_layout.addWidget(lbl_type)
        type_layout.addWidget(self.rb_http)
        type_layout.addWidget(self.rb_https)
        type_layout.addWidget(self.rb_socks5)
        type_layout.addWidget(self.rb_socks4)
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
        
        # Status section for auto-detecting proxy connectivity, IP, and country flag
        self.proxy_status_frame = QFrame()
        self.proxy_status_frame.setObjectName("proxy_status_frame")
        self.proxy_status_frame.setStyleSheet("""
            QFrame#proxy_status_frame {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 6px 10px;
                margin-top: 6px;
            }
        """)
        status_hlayout = QHBoxLayout(self.proxy_status_frame)
        status_hlayout.setContentsMargins(8, 6, 8, 6)
        status_hlayout.setSpacing(10)

        self.lbl_proxy_flag = QLabel("🌐")
        self.lbl_proxy_flag.setStyleSheet("font-size: 22px;")
        self.lbl_proxy_flag.setToolTip("Country flag")
        status_hlayout.addWidget(self.lbl_proxy_flag)

        status_text_layout = QVBoxLayout()
        status_text_layout.setContentsMargins(0, 0, 0, 0)
        status_text_layout.setSpacing(2)

        self.lbl_proxy_status = QLabel("Proxy status: Not checked")
        self.lbl_proxy_status.setStyleSheet("font-weight: bold; color: palette(window-text);")
        status_text_layout.addWidget(self.lbl_proxy_status)

        self.lbl_proxy_ip = QLabel("")
        tnum_font = QFont(self.font())
        tnum_font.setPointSize(9)
        tnum_font.setFeature(QFont.Tag.fromString('tnum'), 1)
        self.lbl_proxy_ip.setFont(tnum_font)
        self.lbl_proxy_ip.setStyleSheet("color: palette(window-text);")
        status_text_layout.addWidget(self.lbl_proxy_ip)

        status_hlayout.addLayout(status_text_layout, 1)

        self.btn_test_proxy = QPushButton("Test Proxy")
        self.btn_test_proxy.setFixedHeight(32)
        self.btn_test_proxy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_proxy.setStyleSheet("""
            QPushButton {
                padding: 4px 16px;
                min-width: 95px;
                font-weight: 500;
            }
        """)
        self.btn_test_proxy.setToolTip("Verify connection and detect external IP and country using this proxy")
        self.btn_test_proxy.clicked.connect(lambda: self.trigger_proxy_detection(force=True))
        status_hlayout.addWidget(self.btn_test_proxy)

        manual_layout.addWidget(self.proxy_status_frame)

        # Debounce timer for auto-detecting proxy changes
        self._proxy_debounce_timer = QTimer(self)
        self._proxy_debounce_timer.setSingleShot(True)
        self._proxy_debounce_timer.setInterval(750)
        self._proxy_debounce_timer.timeout.connect(self.trigger_proxy_detection)

        self.txt_host.textChanged.connect(self._schedule_proxy_detection)
        self.spin_port.valueChanged.connect(self._schedule_proxy_detection)
        self.chk_auth.toggled.connect(self._schedule_proxy_detection)
        self.txt_user.textChanged.connect(self._schedule_proxy_detection)
        self.txt_pass.textChanged.connect(self._schedule_proxy_detection)
        self.rb_http.toggled.connect(self._schedule_proxy_detection)
        self.rb_https.toggled.connect(self._schedule_proxy_detection)
        self.rb_socks5.toggled.connect(self._schedule_proxy_detection)
        self.rb_socks4.toggled.connect(self._schedule_proxy_detection)

        layout.addWidget(self.grp_manual)
        layout.addStretch()
        
        # Load Values (Block signals to prevent auto-save-defaults during init)
        self.rb_manual.blockSignals(True)
        self.rb_no_proxy.blockSignals(True)
        self.rb_http.blockSignals(True)
        self.rb_https.blockSignals(True)
        self.rb_socks5.blockSignals(True)
        self.rb_socks4.blockSignals(True)
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
        elif ptype in ("socks5", "socks5h"):
            self.rb_socks5.setChecked(True)
        elif ptype in ("socks4", "socks4a"):
            self.rb_socks4.setChecked(True)
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
        self.rb_socks5.blockSignals(False)
        self.rb_socks4.blockSignals(False)
        self.txt_host.blockSignals(False)
        self.spin_port.blockSignals(False)
        self.chk_auth.blockSignals(False)
        self.txt_user.blockSignals(False)
        self.txt_pass.blockSignals(False)
        
        self.update_proxy_ui()
        if self.rb_manual.isChecked() and self.txt_host.text().strip():
            QTimer.singleShot(200, self.trigger_proxy_detection)

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.proxy_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def setup_extension_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header with App Icon
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.windowIcon().pixmap(32, 32))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("<b>Bengal Download Manager Integration Module</b>"))
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Overview & Features Box
        grp_info = QGroupBox("Browser Integration Overview")
        info_layout = QVBoxLayout(grp_info)
        info_layout.setContentsMargins(12, 14, 12, 14)
        info_layout.setSpacing(8)

        info_text = QLabel(
            "The Bengal DM browser extension captures downloads directly from your browser "
            "and sends them to Bengal Download Manager for high-speed multi-threaded acceleration."
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        features_label = QLabel(
            "• One-click automatic download interception\n"
            "• Media sniffer for online audio and video streams\n"
            "• Right-click context menu to download links or selection\n"
            "• Configurable file type filtering and bypass lists"
        )
        features_label.setStyleSheet("color: gray; font-size: 12px; line-height: 1.4;")
        info_layout.addWidget(features_label)
        layout.addWidget(grp_info)

        # Get Browser Extension Section
        grp_get_ext = QGroupBox("Get Browser Extension")
        get_ext_layout = QVBoxLayout(grp_get_ext)
        get_ext_layout.setContentsMargins(12, 14, 12, 14)
        get_ext_layout.setSpacing(10)

        ext_desc = QLabel("Install the extension directly in your preferred browser:")
        get_ext_layout.addWidget(ext_desc)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        from ui.icons import get_monochrome_icon
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        self.btn_ext_github = QPushButton(" GitHub Releases")
        self.btn_ext_github.setFixedHeight(32)
        self.btn_ext_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ext_github.setIcon(get_monochrome_icon("github", size=18))
        self.btn_ext_github.setToolTip("Open GitHub Releases page to download extension package (.xpi / .zip)")
        self.btn_ext_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/tazihad/bengal-download-manager/releases")))

        self.btn_ext_firefox = QPushButton(" Firefox Store")
        self.btn_ext_firefox.setFixedHeight(32)
        self.btn_ext_firefox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ext_firefox.setIcon(get_monochrome_icon("firefox", size=18))
        self.btn_ext_firefox.setToolTip("Open Mozilla Firefox Add-ons Store page")
        self.btn_ext_firefox.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://addons.mozilla.org/en-US/firefox/addon/bengal-dm-integration-module")))

        self.btn_ext_chrome = QPushButton(" Chrome (Coming Soon)")
        self.btn_ext_chrome.setFixedHeight(32)
        self.btn_ext_chrome.setIcon(get_monochrome_icon("chrome", size=18))
        self.btn_ext_chrome.setEnabled(False)
        self.btn_ext_chrome.setToolTip("Chrome Web Store integration is coming soon")

        buttons_layout.addWidget(self.btn_ext_github)
        buttons_layout.addWidget(self.btn_ext_firefox)
        buttons_layout.addWidget(self.btn_ext_chrome)
        get_ext_layout.addLayout(buttons_layout)

        layout.addWidget(grp_get_ext)

        # Note pointing to Aria2 / RPC tab
        note_label = QLabel("<i>Note: To configure Aria2 RPC authentication token or local IPC port, open the <b>Aria2 / RPC</b> tab.</i>")
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note_label)

        layout.addStretch()

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.extension_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def setup_aria2_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Header with App Icon
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        header_icon.setPixmap(self.windowIcon().pixmap(24, 24))
        header_layout.addWidget(header_icon)
        header_title = QLabel("<b>Aria2 RPC & IPC Connection Settings</b>")
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Aria2 RPC Settings Group
        grp_aria = QGroupBox("Aria2 RPC Daemon Settings")
        aria_layout = QGridLayout(grp_aria)
        aria_layout.setContentsMargins(12, 16, 12, 16)
        aria_layout.setSpacing(12)

        # Protocol
        aria_layout.addWidget(QLabel("Protocol:"), 0, 0)
        self.combo_aria_proto = QComboBox()
        self.combo_aria_proto.setFixedHeight(28)
        self.combo_aria_proto.setToolTip("Communication protocol for connecting to Aria2 RPC daemon")
        self.combo_aria_proto.addItem("http", "http")
        self.combo_aria_proto.addItem("https", "https")
        self.combo_aria_proto.addItem("websocket", "ws")
        self.combo_aria_proto.addItem("websocket (security)", "wss")

        current_proto = self.extension_data.get("protocol", "ws")
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
        self.spin_aria_port.setFixedHeight(28)
        self.spin_aria_port.setRange(1, 65535)
        self.spin_aria_port.setValue(self.extension_data.get("port", 56800))
        self.spin_aria_port.setToolTip("Port number for Aria2 RPC daemon (default 56800)")
        aria_layout.addWidget(self.spin_aria_port, 1, 1)

        # Token
        aria_layout.addWidget(QLabel("Secret Token:"), 2, 0)
        self.txt_aria_token = QLineEdit()
        self.txt_aria_token.setFixedHeight(28)
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

        # Extension IPC Settings Group
        grp_ipc = QGroupBox("Extension IPC Settings")
        ipc_layout = QGridLayout(grp_ipc)
        ipc_layout.setContentsMargins(12, 16, 12, 16)
        ipc_layout.setSpacing(12)

        ipc_layout.addWidget(QLabel("IPC Port:"), 0, 0)
        self.spin_ipc_port = QSpinBox()
        self.spin_ipc_port.setFixedHeight(28)
        self.spin_ipc_port.setRange(1024, 65535)
        configured_port = self.extension_data.get("ipc_port", 56900)
        self.spin_ipc_port.setValue(configured_port)
        self.spin_ipc_port.setToolTip(
            "Local IPC port for browser extension downloads. Change if 56900 is in use."
        )
        ipc_layout.addWidget(self.spin_ipc_port, 0, 1)

        parent_mw = self.parent()
        active_ipc_port = None
        if parent_mw and hasattr(parent_mw, "listener_thread") and parent_mw.listener_thread:
            active_ipc_port = getattr(parent_mw.listener_thread, "port", None)

        if active_ipc_port and active_ipc_port != configured_port:
            ipc_hint = QLabel(
                f"Configured port: {configured_port}. Active fallback listener: Port {active_ipc_port} "
                "(primary port is occupied by another process/socket)."
            )
            ipc_hint.setStyleSheet("color: #e67e22; font-size: 11px; font-weight: 500;")
        else:
            ipc_hint = QLabel("Local TCP port used by browser extensions to transmit downloads. Change if 56900 is in use.")
            ipc_hint.setStyleSheet("color: gray; font-size: 11px;")
        ipc_hint.setWordWrap(True)
        ipc_layout.addWidget(ipc_hint, 1, 0, 1, 2)

        layout.addWidget(grp_ipc)
        layout.addStretch()

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.aria2_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def setup_media_tab(self):
        _scroll_area = QScrollArea()
        _scroll_area.setWidgetResizable(True)
        _scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        _content = QWidget()
        layout = QVBoxLayout(_content)
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

        self.chk_auto_update_engine = QCheckBox("Auto-check and update media engine on startup")
        self.chk_auto_update_engine.setToolTip("Automatically check for missing media engine dependencies (yt-dlp, ffmpeg, deno, AtomicParsley) and update them on application launch")
        self.chk_auto_update_engine.setChecked(bool(media_defaults.get("auto_update_engine_startup", True)))
        vbox_browser.addWidget(self.chk_auto_update_engine)

        grid_media = QGridLayout()
        grid_media.setContentsMargins(0, 6, 0, 0)
        grid_media.setSpacing(10)

        lbl_q = QLabel("Quality preset:")
        lbl_q.setToolTip("Default quality preset to select when auto-starting media downloads")
        self.cmb_media_quality = QComboBox()
        self.cmb_media_quality.setFixedHeight(28)
        self.cmb_media_quality.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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

        grid_media.addWidget(lbl_q, 0, 0)
        grid_media.addWidget(self.cmb_media_quality, 0, 1)

        # Video Container format
        lbl_v = QLabel("Video format:")
        lbl_v.setToolTip(
            "Output container format for downloaded videos.\n"
            "• Auto: Downloads the site's native container (fastest, no extra conversion).\n"
            "• MKV: Universal container, supports all codecs.\n"
            "• MP4 / WebM: Converts to target format via FFmpeg if needed."
        )
        self.cmb_video_container = QComboBox()
        self.cmb_video_container.setFixedHeight(28)
        self.cmb_video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cmb_video_container.setToolTip(
            "Output container format for downloaded videos.\n"
            "• Auto: Downloads the site's native container (fastest, no extra conversion).\n"
            "• MKV: Universal container, supports all codecs.\n"
            "• MP4 / WebM: Converts to target format via FFmpeg if needed."
        )
        self.cmb_video_container.addItems([
            "Auto (Best / Native) (Default)", "MKV", "MP4", "WebM"
        ])
        saved_vc = media_defaults.get("video_container", "Auto (Best / Native) (Default)")
        idx_vc = self.cmb_video_container.findText(saved_vc)
        self.cmb_video_container.setCurrentIndex(idx_vc if idx_vc != -1 else 0)

        grid_media.addWidget(lbl_v, 1, 0)
        grid_media.addWidget(self.cmb_video_container, 1, 1)

        # Audio Format
        lbl_a = QLabel("Audio format:")
        lbl_a.setToolTip(
            "Output format for audio-only downloads.\n"
            "• Auto: Downloads the site's native audio stream (fastest).\n"
            "• Opus / MP3 / AAC / etc.: Converts to target format via FFmpeg if needed."
        )
        self.cmb_audio_format = QComboBox()
        self.cmb_audio_format.setFixedHeight(28)
        self.cmb_audio_format.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cmb_audio_format.setToolTip(
            "Output format for audio-only downloads.\n"
            "• Auto: Downloads the site's native audio stream (fastest).\n"
            "• Opus / MP3 / AAC / etc.: Converts to target format via FFmpeg if needed."
        )
        self.cmb_audio_format.addItems([
            "Auto (Best / Native) (Default)", "Opus", "MP3", "AAC", "FLAC", "M4A", "OGG", "WAV"
        ])
        saved_af = media_defaults.get("audio_format", "Auto (Best / Native) (Default)")
        idx_af = self.cmb_audio_format.findText(saved_af)
        self.cmb_audio_format.setCurrentIndex(idx_af if idx_af != -1 else 0)

        grid_media.addWidget(lbl_a, 2, 0)
        grid_media.addWidget(self.cmb_audio_format, 2, 1)

        grid_media.setColumnStretch(1, 1)

        vbox_browser.addLayout(grid_media)
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
        self.cmb_opt_cookies_mode.setFixedHeight(28)
        self.cmb_opt_cookies_mode.setToolTip("Select cookie authentication source (Netscape file or none)")
        self.cmb_opt_cookies_mode.addItems([
            "Netscape File (cookies.txt)",
            "None (Anonymous / Public)"
        ])
        saved_cmode = media_defaults.get("cookies_mode_idx", 0)
        self.cmb_opt_cookies_mode.setCurrentIndex(min(max(0, saved_cmode), 1))
        row_cookies_config.addWidget(self.cmb_opt_cookies_mode, stretch=1)
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

        lbl_cookies_help = QLabel(
            '<i>Authenticated cookies bypass bot verification ("Sign in to confirm you\'re not a bot"), '
            'rate limits, and unlock premium/member-only streams. '
            'Learn how to export and configure cookies in the '
            '<a href="https://github.com/tazihad/bengal-download-manager/blob/main/docs/COOKIES_GUIDE.md" style="color: #3498db; text-decoration: underline;">How to Use Cookies Guide on GitHub</a>.</i>'
        )
        lbl_cookies_help.setOpenExternalLinks(True)
        lbl_cookies_help.setWordWrap(True)
        lbl_cookies_help.setStyleSheet("color: gray; font-size: 11px;")
        vbox_cookies.addWidget(lbl_cookies_help)

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

        _scroll_area.setWidget(_content)
        _tab_lyt = QVBoxLayout(self.media_tab)
        _tab_lyt.setContentsMargins(0, 0, 0, 0)
        _tab_lyt.setSpacing(0)
        _tab_lyt.addWidget(_scroll_area)

    def _update_opt_cookies_ui(self):
        mode_idx = self.cmb_opt_cookies_mode.currentIndex() if hasattr(self, "cmb_opt_cookies_mode") else 0
        # 0 = Netscape File, 1 = None
        is_file_mode = (mode_idx == 0)

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
        folder = os.path.dirname(current_path) if (current_path and os.path.exists(current_path)) else get_user_home_dir()
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
        if hasattr(self, "proxy_status_frame"):
            self.proxy_status_frame.setEnabled(manual)
        
        is_socks4 = hasattr(self, "rb_socks4") and self.rb_socks4.isChecked()
        auth = self.chk_auth.isChecked() and manual
        self.txt_user.setEnabled(auth)
        self.txt_pass.setEnabled(auth and not is_socks4)
        if is_socks4:
            self.chk_auth.setText("User identity required (SOCKS4)")
        else:
            self.chk_auth.setText("Authentication required")

    def save_proxy_data(self):
        mode = "manual" if self.rb_manual.isChecked() else "no_proxy"
        if hasattr(self, "rb_https") and self.rb_https.isChecked():
            ptype = "https"
        elif hasattr(self, "rb_socks5") and self.rb_socks5.isChecked():
            ptype = "socks5"
        elif hasattr(self, "rb_socks4") and self.rb_socks4.isChecked():
            ptype = "socks4"
        else:
            ptype = "http"
        
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

        # Dynamically coordinate proxy transitions via Aria2DaemonManager
        try:
            from core.aria2_daemon import get_aria2_daemon_manager
            mgr = get_aria2_daemon_manager()
            mgr.update_proxy(self.proxy_data)
        except Exception:
            # Fallback direct RPC call
            proxy_url = get_aria2_proxy_url(self.proxy_data)
            token = self.txt_aria_token.text().strip() if hasattr(self, 'txt_aria_token') else self.extension_data.get("token", "")
            rpc_port = self.spin_aria_port.value() if hasattr(self, 'spin_aria_port') else self.extension_data.get("port", 56800)
            try:
                call_aria2_rpc("aria2.changeGlobalOption", [{"all-proxy": proxy_url}], port=rpc_port, token=token)
            except Exception:
                pass

        # Notify main window to update its proxy status bar
        if hasattr(self, "main_window") and self.main_window and hasattr(self.main_window, "update_status_bar_proxy"):
            try:
                self.main_window.update_status_bar_proxy(force=True)
            except Exception:
                pass

    def _schedule_proxy_detection(self):
        if not hasattr(self, "rb_manual") or not self.rb_manual.isChecked():
            return
        host = self.txt_host.text().strip() if hasattr(self, "txt_host") else ""
        if not host:
            if hasattr(self, "lbl_proxy_status"):
                self.lbl_proxy_status.setText("Proxy status: Host is empty")
                self.lbl_proxy_status.setStyleSheet("color: palette(placeholder-text);")
                self.lbl_proxy_flag.setText("🌐")
                self.lbl_proxy_flag.setToolTip("Enter proxy host to test connection")
                self.lbl_proxy_ip.setText("")
            return
        if hasattr(self, "lbl_proxy_status"):
            self.lbl_proxy_status.setText("Proxy status: Waiting to test...")
            self.lbl_proxy_status.setStyleSheet("color: palette(window-text);")
        if hasattr(self, "_proxy_debounce_timer"):
            self._proxy_debounce_timer.start(750)

    def trigger_proxy_detection(self, force: bool = False):
        if not hasattr(self, "rb_manual") or not self.rb_manual.isChecked():
            return
        host = self.txt_host.text().strip() if hasattr(self, "txt_host") else ""
        if not host:
            return
        if getattr(self, "_proxy_worker", None) and self._proxy_worker.isRunning():
            return

        self.lbl_proxy_status.setText("Testing proxy...")
        self.lbl_proxy_status.setStyleSheet("color: palette(window-text); font-weight: bold;")
        self.lbl_proxy_flag.setText("⏳")
        self.lbl_proxy_flag.setToolTip("Testing connection through configured proxy...")
        if hasattr(self, "btn_test_proxy"):
            self.btn_test_proxy.setEnabled(False)

        cfg = self.get_current_proxy_data()
        from core.services.proxy_service import ProxyDetectorWorker
        self._proxy_worker = ProxyDetectorWorker(cfg, timeout=6.0, parent=None)
        self._proxy_worker.detection_finished.connect(self._on_proxy_detection_finished)
        self._proxy_worker.start()

    def _on_proxy_detection_finished(self, result):
        if hasattr(self, "btn_test_proxy"):
            self.btn_test_proxy.setEnabled(True)
        if not hasattr(self, "lbl_proxy_status"):
            return

        if result.is_working:
            self.lbl_proxy_flag.setText(result.flag_emoji or "🌐")
            tooltip_country = result.country if result.country else "Unknown Country"
            if result.city:
                tooltip_country = f"{result.city}, {tooltip_country}"
            self.lbl_proxy_flag.setToolTip(tooltip_country)
            self.lbl_proxy_status.setText("Proxy is working")
            self.lbl_proxy_status.setStyleSheet("color: #2eb85c; font-weight: bold;")
            self.lbl_proxy_ip.setText(f"IP: {result.ip}")
            if hasattr(self, "main_window") and self.main_window and hasattr(self.main_window, "on_proxy_verified"):
                try:
                    self.main_window.on_proxy_verified(result)
                except Exception:
                    pass
        else:
            self.lbl_proxy_flag.setText("⚠️")
            self.lbl_proxy_flag.setToolTip(result.error_message or "Proxy error")
            self.lbl_proxy_status.setText(f"Connection failed: {result.error_message}")
            self.lbl_proxy_status.setStyleSheet("color: #e55353; font-weight: bold;")
            self.lbl_proxy_ip.setText("")

    def get_current_proxy_data(self) -> dict:
        mode = "manual" if self.rb_manual.isChecked() else "no_proxy"
        if hasattr(self, "rb_https") and self.rb_https.isChecked():
            ptype = "https"
        elif hasattr(self, "rb_socks5") and self.rb_socks5.isChecked():
            ptype = "socks5"
        elif hasattr(self, "rb_socks4") and self.rb_socks4.isChecked():
            ptype = "socks4"
        else:
            ptype = "http"

        return {
            "mode": mode,
            "type": ptype,
            "host": self.txt_host.text().strip() if hasattr(self, "txt_host") else "",
            "port": self.spin_port.value() if hasattr(self, "spin_port") else 8080,
            "auth": self.chk_auth.isChecked() if hasattr(self, "chk_auth") else False,
            "user": self.txt_user.text() if hasattr(self, "txt_user") else "",
            "password": self.txt_pass.text() if hasattr(self, "txt_pass") else "",
        }

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

        ipc_port = 56900
        if hasattr(self, "spin_ipc_port"):
            ipc_port = self.spin_ipc_port.value()
        elif hasattr(self, "extension_data") and isinstance(self.extension_data, dict):
            ipc_port = self.extension_data.get("ipc_port", 56900)

        self.extension_data = {
            "protocol": proto, 
            "host": "localhost",
            "port": port,
            "token": token,
            "max_connections": max_c,
            "ipc_port": ipc_port
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
        folder = current_path if os.path.exists(current_path) else get_user_downloads_dir()
        path = choose_portal_folder_path("Select Directory", folder)
        if path:
            line_edit.setText(path)

    def on_appearance_preview(self, text=None):
        t = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Auto (Default)"
        a = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"
        i = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"
        tr = self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"
        tb = self.combo_titlebar.currentText() if hasattr(self, 'combo_titlebar') else "Automatic"
        if self.main_win:
            preview_fn = getattr(self.main_win, "preview_appearance", None)
            if callable(preview_fn):
                preview_fn(t, a, i, tr, tb)

    def reject(self):
        self.hide()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        if self.main_win:
            preview_fn = getattr(self.main_win, "preview_appearance", None)
            if callable(preview_fn):
                t = getattr(self, 'initial_theme', 'BDM Auto (Default)')
                a = getattr(self, 'initial_accent', 'BDM (Default)')
                i = getattr(self, 'initial_icon_theme', 'BDM Auto')
                tr = getattr(self, 'initial_tray_icon', 'App Icon (Default)')
                tb = getattr(self, 'initial_titlebar', 'Automatic')
                preview_fn(t, a, i, tr, tb)
            setattr(self.main_win, "_is_previewing", False)
        self._cleanup_proxy_worker()
        super().reject()

    def save_and_accept(self):
        self.config_data["temp_dir"] = self.txt_temp_path.text()

        # Save Media Downloader defaults
        media_defaults = self.config_data.get("media_downloader_defaults", {})
        if hasattr(self, "chk_auto_start_media"):
            media_defaults["auto_start_media"] = self.chk_auto_start_media.isChecked()
        if hasattr(self, "chk_auto_update_engine"):
            media_defaults["auto_update_engine_startup"] = self.chk_auto_update_engine.isChecked()
        if hasattr(self, "cmb_media_quality"):
            media_defaults["auto_media_quality_preset"] = self.cmb_media_quality.currentText()
        if hasattr(self, "cmb_video_container"):
            media_defaults["video_container"] = self.cmb_video_container.currentText()
        if hasattr(self, "cmb_audio_format"):
            media_defaults["audio_format"] = self.cmb_audio_format.currentText()
        if hasattr(self, "cmb_opt_cookies_mode"):
            media_defaults["cookies_mode_idx"] = self.cmb_opt_cookies_mode.currentIndex()
        if hasattr(self, "txt_opt_cookies_path"):
            c_path = self.txt_opt_cookies_path.text().strip()
            media_defaults["cookies_path"] = c_path
            self.config_data["media_downloader_cookies_path"] = c_path
        if hasattr(self, "txt_opt_youtube_client"):
            media_defaults["youtube_player_client"] = self.txt_opt_youtube_client.text().strip() or "default"
        self.config_data["media_downloader_defaults"] = media_defaults

        save_category_config(self.config_data)
        
        from core.services.language_service import (
            get_language_code, apply_language
        )

        new_scale = self.combo_scale.currentText()
        new_theme = self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Auto (Default)"
        new_accent = self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"
        new_icon_theme = self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"
        new_tray_icon = self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"
        new_titlebar = self.combo_titlebar.currentText() if hasattr(self, 'combo_titlebar') else "Automatic"
        new_lang_display = self.combo_language.currentText() if hasattr(self, 'combo_language') else "System Default"
        new_lang_code = get_language_code(new_lang_display)

        scale_changed = hasattr(self, 'initial_scale') and (self.initial_scale != new_scale)
        lang_changed = hasattr(self, 'initial_language') and (self.initial_language != new_lang_display)

        # Save start_minimized_on_autostart, ui_scale, theme, accent, icon_theme, tray_icon, language, system_notifications, and dialog visibility to parent (MainWindow)
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
                self.main_win.settings["title_bar"] = new_titlebar
                self.main_win.settings["language"] = new_lang_code
                self.main_win.settings["system_notifications"] = is_notif
                self.main_win.settings["silent_download"] = silent_dl
                self.main_win.settings["show_start_dialog"] = show_start
                self.main_win.settings["show_progress_dialog"] = show_prog
                self.main_win.settings["show_complete_dialog"] = show_comp
                self.main_win.settings["show_queue_complete_dialog"] = show_q_comp

            if lang_changed:
                apply_language(QApplication.instance(), new_lang_code)
                if hasattr(self.main_win, "retranslate_ui"):
                    self.main_win.retranslate_ui()

            apply_fn = getattr(self.main_win, "apply_appearance_setting", None)
            if callable(apply_fn):
                apply_fn(new_theme, new_accent, new_icon_theme, new_tray_icon, new_titlebar)
            else:
                save_fn = getattr(self.main_win, "save_settings", None)
                if callable(save_fn):
                    save_fn()

        set_autostart_enabled(self.chk_startup.isChecked(), self.chk_start_minimized.isChecked())
        self.save_proxy_data()
        self.save_extension_data()

        restart_items = []
        if scale_changed:
            restart_items.append("UI Scale")
        if lang_changed:
            restart_items.append("Language")

        if restart_items:
            items_str = " and ".join(restart_items)
            QMessageBox.information(
                self,
                "Restart Required",
                f"{items_str} setting has been changed. Please restart Bengal Download Manager for all changes to take full effect."
            )

        self.accept()

    def _cleanup_proxy_worker(self):
        if hasattr(self, "_proxy_debounce_timer") and self._proxy_debounce_timer.isActive():
            self._proxy_debounce_timer.stop()
        worker = getattr(self, "_proxy_worker", None)
        if worker:
            try:
                worker.detection_finished.disconnect(self._on_proxy_detection_finished)
            except Exception:
                pass
            if hasattr(worker, "stop") and callable(worker.stop):
                worker.stop()
            if worker.isRunning():
                worker.wait(200)
            self._proxy_worker = None

    def closeEvent(self, event):
        self.hide()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self._cleanup_proxy_worker()
        super().closeEvent(event)

    def accept(self):
        self.hide()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self._cleanup_proxy_worker()
        super().accept()

    def get_language(self) -> str:
        from core.services.language_service import get_language_code
        return get_language_code(self.combo_language.currentText()) if hasattr(self, 'combo_language') else "system"

    def get_theme(self):
        return self.combo_theme.currentText() if hasattr(self, 'combo_theme') else "BDM Auto (Default)"

    def get_accent(self):
        return self.combo_accent.currentText() if hasattr(self, 'combo_accent') else "BDM (Default)"

    def get_icon_theme(self):
        return self.combo_icon_theme.currentText() if hasattr(self, 'combo_icon_theme') else "BDM Auto"

    def get_tray_icon(self):
        return self.combo_tray_icon.currentText() if hasattr(self, 'combo_tray_icon') else "App Icon (Default)"

    def get_titlebar(self):
        return self.combo_titlebar.currentText() if hasattr(self, 'combo_titlebar') else "Automatic"

    def get_silent_download(self) -> bool:
        return self.chk_silent_download.isChecked() if hasattr(self, "chk_silent_download") else False

    def get_show_start_dialog(self) -> bool:
        return self.chk_show_start_dialog.isChecked() if hasattr(self, "chk_show_start_dialog") else True

    def get_show_progress_dialog(self) -> bool:
        if hasattr(self, "chk_show_start_dialog") and not self.chk_show_start_dialog.isChecked():
            return False
        return self.chk_show_progress_dialog.isChecked() if hasattr(self, "chk_show_progress_dialog") else True

    def get_show_complete_dialog(self) -> bool:
        return self.chk_show_complete_dialog.isChecked() if hasattr(self, "chk_show_complete_dialog") else True

    def get_show_queue_complete_dialog(self) -> bool:
        return self.chk_show_queue_complete_dialog.isChecked() if hasattr(self, "chk_show_queue_complete_dialog") else False
