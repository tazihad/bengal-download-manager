"""
Scheduler Dialog for Bengal Download Manager.
Provides a queue management interface with scheduling options
modeled after IDM's Scheduler functionality.
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGroupBox, QCheckBox, QSpinBox, QRadioButton,
    QButtonGroup, QFrame, QGridLayout, QApplication,
    QListWidget, QListWidgetItem, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QSplitter, QComboBox, QLineEdit, QFileDialog, QTimeEdit,
    QDateEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QTime, QDate
from PyQt6.QtGui import QFont, QAction
from core.memory_guard import MemoryGuard


# Default queue definitions
DEFAULT_QUEUES = [
    {
        "name": "Main download queue",
        "default": True,
        "mode": "onetime",          # locked to "onetime" for this queue
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",   # "once" or "daily"
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],  # Sun-Sat
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "open_file_enabled": False,
        "open_file_path": "",
        "exit_app_when_done": False,
        "turn_off_enabled": False,
        "turn_off_action": "Shut down",
        "force_terminate": False,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    },
    {
        "name": "Synchronization queue",
        "default": True,
        "mode": "sync",             # locked to "sync" for this queue
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "open_file_enabled": False,
        "open_file_path": "",
        "exit_app_when_done": False,
        "turn_off_enabled": False,
        "turn_off_action": "Shut down",
        "force_terminate": False,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    },
]


def _make_default_queue(name):
    """Creates a new queue dict with default values (same as Main download queue)."""
    return {
        "name": name,
        "default": False,
        "mode": "onetime",
        "start_on_startup": False,
        "start_at_enabled": False,
        "start_at_time": "23:00:00",
        "schedule_type": "daily",
        "once_date": None,
        "daily_days": [True, True, True, True, True, True, True],
        "stop_at_enabled": False,
        "stop_at_time": "07:30:00",
        "retries_enabled": False,
        "retries_count": 10,
        "open_file_enabled": False,
        "open_file_path": "",
        "exit_app_when_done": False,
        "turn_off_enabled": False,
        "turn_off_action": "Shut down",
        "force_terminate": False,
        "sync_interval_enabled": False,
        "sync_hours": 2,
        "sync_minutes": 0,
        "max_concurrent": 4,
        "files": [],
    }


class SchedulerDialog(QDialog):
    """Queue scheduler dialog providing IDM-style download queue management."""

    def __init__(self, main_window=None, parent=None, initial_queues=None):
        super().__init__(None)
        self._main_window = main_window or parent
        MemoryGuard.auto_manage_dialog(self)
        self.setWindowTitle("Scheduler")
        self.setWindowIcon(QApplication.windowIcon())
        self.setMinimumSize(750, 530)
        self.resize(750, 530)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

        self.setStyleSheet("""
            QCheckBox:disabled,
            QRadioButton:disabled,
            QLabel:disabled {
                color: #888888;
            }
            QSpinBox:disabled,
            QTimeEdit:disabled,
            QDateEdit:disabled,
            QLineEdit:disabled,
            QComboBox:disabled {
                color: #888888;
                background-color: palette(disabled, base);
                border: 1px solid palette(disabled, mid);
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
            QMenu::item:selected, QMenu::item:hover {
                background-color: palette(highlight);
                color: #000000;
            }
            QMenu::item:disabled {
                color: #888888;
                background-color: transparent;
            }
            QMenu::item:disabled:selected, QMenu::item:disabled:hover {
                color: #888888;
                background-color: transparent;
            }
            QMenu::separator {
                height: 1px;
                background-color: palette(mid);
                margin: 4px 6px;
            }
        """)

        # Queue data storage — use caller-supplied list or fall back to defaults
        source = initial_queues if initial_queues is not None else DEFAULT_QUEUES
        self.queues = [dict(q) for q in source]
        for q in self.queues:
            q["daily_days"] = list(q["daily_days"])
        self._selected_index = -1

        self._build_ui()
        self._populate_queue_list()

    # ---------------------------------------------------------------
    # UI Construction
    # ---------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ---- Left panel ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        lbl = QLabel("Queues")
        fnt = lbl.font()
        fnt.setBold(True)
        lbl.setFont(fnt)
        left_layout.addWidget(lbl)

        self.queue_list = QListWidget()
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._show_queue_context_menu)
        self.queue_list.currentRowChanged.connect(self._on_queue_selected)
        left_layout.addWidget(self.queue_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_new_queue = QPushButton("New queue")
        self.btn_new_queue.clicked.connect(self._add_new_queue)
        btn_row.addWidget(self.btn_new_queue)
        self.btn_delete_queue = QPushButton("Delete")
        self.btn_delete_queue.clicked.connect(self._delete_selected_queue)
        self.btn_delete_queue.setEnabled(False)
        btn_row.addWidget(self.btn_delete_queue)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # ---- Right panel ----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.queue_title_label = QLabel("")
        title_font = self.queue_title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        self.queue_title_label.setFont(title_font)
        self.queue_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.queue_title_label)

        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs, 1)

        # Schedule tab
        self.schedule_tab = QWidget()
        self._build_schedule_tab()
        self.tabs.addTab(self.schedule_tab, "Schedule")

        # Files tab
        self.files_tab = QWidget()
        self._build_files_tab()
        self.tabs.addTab(self.files_tab, "Files in the queue")

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([200, 550])

        # ---- Bottom buttons ----
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.btn_start = QPushButton("Start now")
        self.btn_start.clicked.connect(self._on_start_now)
        bottom.addWidget(self.btn_start)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._on_stop)
        bottom.addWidget(self.btn_stop)
        bottom.addStretch()
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self._apply_changes)
        bottom.addWidget(self.btn_apply)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)

    def _build_schedule_tab(self):
        layout = QVBoxLayout(self.schedule_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Mode selection
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.radio_onetime = QRadioButton("One-time downloading")
        self.radio_sync = QRadioButton("Periodic synchronization")
        self.mode_group.addButton(self.radio_onetime, 0)
        self.mode_group.addButton(self.radio_sync, 1)
        self.radio_onetime.setChecked(True)
        mode_row.addWidget(self.radio_onetime)
        mode_row.addStretch()
        mode_row.addWidget(self.radio_sync)
        layout.addLayout(mode_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Start on startup
        self.chk_startup = QCheckBox("Start download on application startup")
        layout.addWidget(self.chk_startup)

        # Start download at
        start_row = QHBoxLayout()
        self.chk_start_at = QCheckBox("Start download at")
        start_row.addWidget(self.chk_start_at)
        self.time_start_at = QTimeEdit()
        self.time_start_at.setDisplayFormat("hh:mm:ss AP")
        self.time_start_at.setTime(QTime(23, 0, 0))
        self._apply_tabular_font(self.time_start_at)
        self.time_start_at.setEnabled(False)
        start_row.addWidget(self.time_start_at)
        start_row.addStretch()
        layout.addLayout(start_row)

        # Schedule type container (switches between once/daily and sync interval)
        # All schedule sub-controls are enabled only when chk_start_at is checked.
        self.schedule_container = QWidget()
        self.schedule_layout = QVBoxLayout(self.schedule_container)
        self.schedule_layout.setContentsMargins(20, 0, 0, 0)
        self.schedule_layout.setSpacing(4)

        # -- One-time sub-options --
        self.onetime_widget = QWidget()
        onetime_layout = QVBoxLayout(self.onetime_widget)
        onetime_layout.setContentsMargins(0, 0, 0, 0)
        onetime_layout.setSpacing(4)

        self.schedule_type_group = QButtonGroup(self)
        once_row = QHBoxLayout()
        self.radio_once = QRadioButton("Once at")
        self.schedule_type_group.addButton(self.radio_once, 0)
        once_row.addWidget(self.radio_once)
        self.date_once = QDateEdit()
        self.date_once.setCalendarPopup(True)
        self.date_once.setDate(QDate.currentDate())
        self._apply_tabular_font(self.date_once)
        self.date_once.setEnabled(False)
        once_row.addWidget(self.date_once)
        once_row.addStretch()
        onetime_layout.addLayout(once_row)

        daily_row = QHBoxLayout()
        self.radio_daily = QRadioButton("Daily")
        self.schedule_type_group.addButton(self.radio_daily, 1)
        self.radio_daily.setChecked(True)
        daily_row.addWidget(self.radio_daily)

        self.day_checks = []
        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        days_grid = QGridLayout()
        days_grid.setSpacing(4)
        for i, day in enumerate(day_names):
            chk = QCheckBox(day)
            chk.setChecked(True)
            self.day_checks.append(chk)
            row_idx = i // 3
            col_idx = i % 3
            days_grid.addWidget(chk, row_idx, col_idx)
        onetime_layout.addLayout(days_grid)

        self.schedule_layout.addWidget(self.onetime_widget)

        # -- Sync sub-options --
        self.sync_widget = QWidget()
        sync_layout = QVBoxLayout(self.sync_widget)
        sync_layout.setContentsMargins(0, 0, 0, 0)
        sync_layout.setSpacing(4)

        sync_interval_row = QHBoxLayout()
        self.chk_sync_interval = QCheckBox("Start again every")
        sync_interval_row.addWidget(self.chk_sync_interval)
        self.spin_sync_hours = QSpinBox()
        self.spin_sync_hours.setRange(0, 99)
        self.spin_sync_hours.setValue(2)
        self.spin_sync_hours.setEnabled(False)
        self._apply_tabular_font(self.spin_sync_hours)
        sync_interval_row.addWidget(self.spin_sync_hours)
        sync_interval_row.addWidget(QLabel("hours"))
        self.spin_sync_mins = QSpinBox()
        self.spin_sync_mins.setRange(0, 59)
        self.spin_sync_mins.setValue(0)
        self.spin_sync_mins.setEnabled(False)
        self._apply_tabular_font(self.spin_sync_mins)
        sync_interval_row.addWidget(self.spin_sync_mins)
        sync_interval_row.addWidget(QLabel("min"))
        sync_interval_row.addStretch()
        sync_layout.addLayout(sync_interval_row)

        # Daily weekday checkboxes for sync mode
        sync_daily_label = QLabel("Daily")
        sync_daily_label.setIndent(20)
        sync_layout.addWidget(sync_daily_label)
        self.sync_day_checks = []
        sync_days_grid = QGridLayout()
        sync_days_grid.setSpacing(4)
        for i, day in enumerate(day_names):
            chk = QCheckBox(day)
            chk.setChecked(True)
            self.sync_day_checks.append(chk)
            sync_days_grid.addWidget(chk, i // 3, i % 3)
        sync_layout.addLayout(sync_days_grid)

        self.sync_widget.setVisible(False)
        self.schedule_layout.addWidget(self.sync_widget)

        layout.addWidget(self.schedule_container)

        # Connect chk_start_at → enable/disable time field + all schedule sub-controls
        self.chk_start_at.toggled.connect(self._on_start_at_toggled)
        # Connect schedule type radio → date_once enabled only when radio_once + start_at checked
        self.radio_once.toggled.connect(self._refresh_schedule_controls)
        # Connect mode toggle
        self.mode_group.idToggled.connect(self._on_mode_changed)
        # Connect sync interval checkbox
        self.chk_sync_interval.toggled.connect(self._on_sync_interval_toggled)

        # Stop download at
        stop_row = QHBoxLayout()
        self.chk_stop_at = QCheckBox("Stop download at")
        stop_row.addWidget(self.chk_stop_at)
        self.time_stop_at = QTimeEdit()
        self.time_stop_at.setDisplayFormat("hh:mm:ss AP")
        self.time_stop_at.setTime(QTime(7, 30, 0))
        self._apply_tabular_font(self.time_stop_at)
        self.time_stop_at.setEnabled(False)
        stop_row.addWidget(self.time_stop_at)
        stop_row.addStretch()
        layout.addLayout(stop_row)
        self.chk_stop_at.toggled.connect(self.time_stop_at.setEnabled)

        # Retries
        retries_row = QHBoxLayout()
        self.chk_retries = QCheckBox("Number of retries for each file if downloading failed:")
        retries_row.addWidget(self.chk_retries)
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 999)
        self.spin_retries.setValue(10)
        self._apply_tabular_font(self.spin_retries)
        self.spin_retries.setEnabled(False)
        retries_row.addWidget(self.spin_retries)
        retries_row.addStretch()
        layout.addLayout(retries_row)
        self.chk_retries.toggled.connect(self.spin_retries.setEnabled)

        # Open file when done
        open_row = QHBoxLayout()
        self.chk_open_file = QCheckBox("Open the following file when done:")
        open_row.addWidget(self.chk_open_file)
        layout.addLayout(open_row)

        file_row = QHBoxLayout()
        file_row.setContentsMargins(20, 0, 0, 0)
        self.txt_open_file = QLineEdit()
        self.txt_open_file.setEnabled(False)
        file_row.addWidget(self.txt_open_file, 1)
        self.btn_browse_file = QPushButton("...")
        self.btn_browse_file.setFixedWidth(30)
        self.btn_browse_file.setEnabled(False)
        self.btn_browse_file.clicked.connect(self._browse_open_file)
        file_row.addWidget(self.btn_browse_file)
        layout.addLayout(file_row)
        self.chk_open_file.toggled.connect(self.txt_open_file.setEnabled)
        self.chk_open_file.toggled.connect(self.btn_browse_file.setEnabled)

        # Exit app when done
        self.chk_exit_app = QCheckBox("Exit Bengal Download Manager when done")
        layout.addWidget(self.chk_exit_app)

        # Turn off computer when done
        turnoff_row = QHBoxLayout()
        self.chk_turn_off = QCheckBox("Turn off computer when done")
        turnoff_row.addWidget(self.chk_turn_off)
        self.combo_turn_off = QComboBox()
        self.combo_turn_off.addItems(["Shut down", "Hibernate", "Sleep", "Stand by"])
        self.combo_turn_off.setEnabled(False)
        turnoff_row.addWidget(self.combo_turn_off)
        turnoff_row.addStretch()
        layout.addLayout(turnoff_row)

        # Force terminate — child of turn_off, disabled when turn_off is unchecked
        self.chk_force = QCheckBox("Force processes to terminate")
        self.chk_force.setEnabled(False)
        self.chk_force.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(self.chk_force)

        self.chk_turn_off.toggled.connect(self.combo_turn_off.setEnabled)
        self.chk_turn_off.toggled.connect(self.chk_force.setEnabled)
        # When turn_off is unchecked, also uncheck force
        self.chk_turn_off.toggled.connect(lambda checked: self.chk_force.setChecked(False) if not checked else None)

        layout.addStretch()

    def _build_files_tab(self):
        layout = QVBoxLayout(self.files_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # "Download N files at the same time" row
        concurrent_row = QHBoxLayout()
        concurrent_row.addWidget(QLabel("Download"))
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 20)
        self.spin_concurrent.setValue(4)
        self._apply_tabular_font(self.spin_concurrent)
        concurrent_row.addWidget(self.spin_concurrent)
        concurrent_row.addWidget(QLabel("files at the same time"))
        concurrent_row.addStretch()
        layout.addLayout(concurrent_row)

        # Files table: File Name | Size | Status | Time Left
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["File Name", "Size", "Status", "Time left"])
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files_table.setAlternatingRowColors(True)
        self.files_table.verticalHeader().setVisible(False)
        layout.addWidget(self.files_table, 1)

        # Connect tab change to refresh files when switching to Files tab
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------
    @staticmethod
    def _apply_tabular_font(widget):
        """Applies tabular (monospaced-numeral) font to a widget for aligned numeric display."""
        font = widget.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
        widget.setFont(font)

    def _populate_queue_list(self):
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for q in self.queues:
            item = QListWidgetItem(q["name"])
            self.queue_list.addItem(item)
        self.queue_list.blockSignals(False)
        if self.queues:
            self.queue_list.setCurrentRow(0)

    def _load_queue_to_ui(self, index):
        """Loads the queue at the given index into the right panel controls."""
        if index < 0 or index >= len(self.queues):
            return

        q = self.queues[index]
        self.queue_title_label.setText(q["name"])

        # --- Mode radio locking ---
        # Main download queue: only onetime; Synchronization queue: only sync
        is_main = q.get("name") == "Main download queue"
        is_sync_q = q.get("name") == "Synchronization queue"

        if q["mode"] == "sync":
            self.radio_sync.setChecked(True)
        else:
            self.radio_onetime.setChecked(True)

        # Lock mode radios for the two built-in queues
        self.radio_onetime.setEnabled(not is_sync_q)
        self.radio_sync.setEnabled(not is_main)

        self.chk_startup.setChecked(q.get("start_on_startup", False))

        # Start at
        self.chk_start_at.setChecked(q.get("start_at_enabled", False))
        t_parts = q.get("start_at_time", "23:00:00").split(":")
        self.time_start_at.setTime(QTime(int(t_parts[0]), int(t_parts[1]), int(t_parts[2]) if len(t_parts) > 2 else 0))

        # Schedule type
        if q.get("schedule_type") == "once":
            self.radio_once.setChecked(True)
        else:
            self.radio_daily.setChecked(True)

        if q.get("once_date"):
            self.date_once.setDate(QDate.fromString(q["once_date"], "yyyy-MM-dd"))
        else:
            self.date_once.setDate(QDate.currentDate())

        days = q.get("daily_days", [True] * 7)
        for i, chk in enumerate(self.day_checks):
            chk.setChecked(days[i] if i < len(days) else True)
        for i, chk in enumerate(self.sync_day_checks):
            chk.setChecked(days[i] if i < len(days) else True)

        # Sync interval
        self.chk_sync_interval.setChecked(q.get("sync_interval_enabled", False))
        self.spin_sync_hours.setValue(q.get("sync_hours", 2))
        self.spin_sync_mins.setValue(q.get("sync_minutes", 0))

        # Stop at
        self.chk_stop_at.setChecked(q.get("stop_at_enabled", False))
        st_parts = q.get("stop_at_time", "07:30:00").split(":")
        self.time_stop_at.setTime(QTime(int(st_parts[0]), int(st_parts[1]), int(st_parts[2]) if len(st_parts) > 2 else 0))

        # Retries
        self.chk_retries.setChecked(q.get("retries_enabled", False))
        self.spin_retries.setValue(q.get("retries_count", 10))

        # Open file
        self.chk_open_file.setChecked(q.get("open_file_enabled", False))
        self.txt_open_file.setText(q.get("open_file_path", ""))

        # Post-completion
        self.chk_exit_app.setChecked(q.get("exit_app_when_done", False))
        self.chk_turn_off.setChecked(q.get("turn_off_enabled", False))
        idx = self.combo_turn_off.findText(q.get("turn_off_action", "Shut down"))
        self.combo_turn_off.setCurrentIndex(max(0, idx))
        self.chk_force.setChecked(q.get("force_terminate", False))

        # Concurrent downloads spinbox
        self.spin_concurrent.setValue(q.get("max_concurrent", 4))

        # Refresh all dependent-field enabled states
        self._on_start_at_toggled(self.chk_start_at.isChecked())
        self._on_mode_changed(self.mode_group.checkedId(), True)

        # Files table — populate if on that tab
        if self.tabs.currentIndex() == 1:
            self._refresh_files_table(index)

    def _save_ui_to_queue(self, index):
        """Saves current right panel state back into the queue dict at index."""
        if index < 0 or index >= len(self.queues):
            return

        q = self.queues[index]
        q["mode"] = "sync" if self.radio_sync.isChecked() else "onetime"
        q["start_on_startup"] = self.chk_startup.isChecked()
        q["start_at_enabled"] = self.chk_start_at.isChecked()
        t = self.time_start_at.time()
        q["start_at_time"] = f"{t.hour():02d}:{t.minute():02d}:{t.second():02d}"

        q["schedule_type"] = "once" if self.radio_once.isChecked() else "daily"
        q["once_date"] = self.date_once.date().toString("yyyy-MM-dd")

        if q["mode"] == "sync":
            q["daily_days"] = [chk.isChecked() for chk in self.sync_day_checks]
        else:
            q["daily_days"] = [chk.isChecked() for chk in self.day_checks]

        q["sync_interval_enabled"] = self.chk_sync_interval.isChecked()
        q["sync_hours"] = self.spin_sync_hours.value()
        q["sync_minutes"] = self.spin_sync_mins.value()

        st = self.time_stop_at.time()
        q["stop_at_enabled"] = self.chk_stop_at.isChecked()
        q["stop_at_time"] = f"{st.hour():02d}:{st.minute():02d}:{st.second():02d}"

        q["retries_enabled"] = self.chk_retries.isChecked()
        q["retries_count"] = self.spin_retries.value()

        q["open_file_enabled"] = self.chk_open_file.isChecked()
        q["open_file_path"] = self.txt_open_file.text()

        q["exit_app_when_done"] = self.chk_exit_app.isChecked()
        q["turn_off_enabled"] = self.chk_turn_off.isChecked()
        q["turn_off_action"] = self.combo_turn_off.currentText()
        q["force_terminate"] = self.chk_force.isChecked()

        q["max_concurrent"] = self.spin_concurrent.value()

    def _refresh_files_table(self, queue_index=None):
        """Populates the Files in the queue table from the main window's download table."""
        self.files_table.setRowCount(0)

        mw = self._main_window
        if mw is None:
            return

        dt = getattr(mw, "download_table", None)
        if dt is None:
            return

        for r in range(dt.rowCount()):
            name_item = dt.item(r, 0)
            size_item = dt.item(r, 1)
            status_item = dt.item(r, 2)
            time_item = dt.item(r, 3)

            if not name_item:
                continue

            row = self.files_table.rowCount()
            self.files_table.insertRow(row)
            self.files_table.setItem(row, 0, QTableWidgetItem(name_item.text()))
            self.files_table.setItem(row, 1, QTableWidgetItem(size_item.text() if size_item else ""))

            # Prefer the raw percentage stored in UserRole over the display text
            # (display text can be "Downloading..." while UserRole holds "45.23%")
            if status_item:
                pct = status_item.data(Qt.ItemDataRole.UserRole)
                status_display = pct if pct else status_item.text()
            else:
                status_display = ""
            self.files_table.setItem(row, 2, QTableWidgetItem(status_display))
            self.files_table.setItem(row, 3, QTableWidgetItem(time_item.text() if time_item else ""))

    def _refresh_schedule_controls(self):
        """Re-applies enabled state for all schedule sub-controls based on chk_start_at."""
        self._on_start_at_toggled(self.chk_start_at.isChecked())

    def _on_start_at_toggled(self, checked: bool):
        """Enable/disable the time field and all schedule sub-controls."""
        self.time_start_at.setEnabled(checked)

        # Onetime sub-controls
        self.radio_once.setEnabled(checked)
        self.radio_daily.setEnabled(checked)
        # date_once only when both start_at checked AND radio_once selected
        self.date_once.setEnabled(checked and self.radio_once.isChecked())
        for chk in self.day_checks:
            chk.setEnabled(checked)

        # Sync sub-controls — only if also in sync mode
        in_sync = self.radio_sync.isChecked()
        self.chk_sync_interval.setEnabled(checked and in_sync)
        sync_interval_on = self.chk_sync_interval.isChecked()
        self.spin_sync_hours.setEnabled(checked and in_sync and sync_interval_on)
        self.spin_sync_mins.setEnabled(checked and in_sync and sync_interval_on)
        for chk in self.sync_day_checks:
            chk.setEnabled(checked and in_sync)

    def _on_sync_interval_toggled(self, checked: bool):
        """Enable/disable sync hour/min spinboxes based on chk_sync_interval."""
        start_at_on = self.chk_start_at.isChecked()
        self.spin_sync_hours.setEnabled(start_at_on and checked)
        self.spin_sync_mins.setEnabled(start_at_on and checked)

    def _on_tab_changed(self, tab_index: int):
        if tab_index == 1:
            self._refresh_files_table(self._selected_index)

    # ---------------------------------------------------------------
    # Slots
    # ---------------------------------------------------------------
    def _on_queue_selected(self, row):
        if self._selected_index >= 0:
            self._save_ui_to_queue(self._selected_index)

        self._selected_index = row
        if 0 <= row < len(self.queues):
            self._load_queue_to_ui(row)
            self.btn_delete_queue.setEnabled(not self.queues[row].get("default", False))
        else:
            self.btn_delete_queue.setEnabled(False)

    def _on_mode_changed(self, mode_id, checked=True):
        if not checked:
            return
        is_sync = (mode_id == 1)
        self.onetime_widget.setVisible(not is_sync)
        self.sync_widget.setVisible(is_sync)
        # Refresh start-at dependent enables after mode switch
        self._on_start_at_toggled(self.chk_start_at.isChecked())

    def _add_new_queue(self):
        # Generate unique name
        base = "Queue"
        existing = {q["name"] for q in self.queues}
        i = 1
        while f"{base} # {i}" in existing:
            i += 1
        name = f"{base} # {i}"

        new_q = _make_default_queue(name)
        self.queues.append(new_q)
        item = QListWidgetItem(name)
        self.queue_list.addItem(item)
        self.queue_list.setCurrentRow(len(self.queues) - 1)

    def _delete_selected_queue(self):
        row = self.queue_list.currentRow()
        if row < 0 or row >= len(self.queues):
            return
        if self.queues[row].get("default", False):
            return

        self._selected_index = -1
        del self.queues[row]
        self.queue_list.takeItem(row)
        if self.queues:
            self.queue_list.setCurrentRow(min(row, len(self.queues) - 1))

    def _browse_open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select file to open when done")
        if path:
            self.txt_open_file.setText(path)

    def _apply_changes(self):
        if self._selected_index >= 0:
            self._save_ui_to_queue(self._selected_index)
            # Propagate max_concurrent back to main window if possible
            mw = self._main_window
            if mw is not None:
                q = self.queues[self._selected_index]
                if q.get("name") == "Main download queue":
                    mw.MAX_CONCURRENT_DOWNLOADS = q.get("max_concurrent", 4)
            # Update the list item name if changed
            q = self.queues[self._selected_index]
            item = self.queue_list.item(self._selected_index)
            if item:
                item.setText(q["name"])

    def _on_start_now(self):
        """Placeholder: start the selected queue's downloads immediately."""
        pass

    def _on_stop(self):
        """Placeholder: stop the selected queue's downloads."""
        pass

    def _show_queue_context_menu(self, pos):
        item = self.queue_list.itemAt(pos)
        if not item:
            return

        row = self.queue_list.row(item)
        q = self.queues[row] if row < len(self.queues) else None
        if not q:
            return

        menu = QMenu(self)

        act_start = menu.addAction("Start now")
        act_start.triggered.connect(self._on_start_now)

        act_stop = menu.addAction("Stop")
        act_stop.triggered.connect(self._on_stop)

        menu.addSeparator()

        act_edit = menu.addAction("Edit queue")
        act_edit.triggered.connect(lambda: self.queue_list.setCurrentRow(row))

        act_schedule = menu.addAction("Schedule")
        act_schedule.triggered.connect(lambda: (self.queue_list.setCurrentRow(row), self.tabs.setCurrentIndex(0)))

        menu.addSeparator()

        act_delete = menu.addAction("Delete")
        _is_default = q.get("default", False)
        try:
            from main import make_faded_icon, get_themed_icon as _gti
            act_delete.setIcon(make_faded_icon(_gti("delete")) if _is_default else _gti("delete"))
        except Exception:
            pass
        act_delete.setEnabled(not _is_default)
        act_delete.triggered.connect(lambda: self._delete_queue_at(row))

        act_new = menu.addAction("Create new queue")
        act_new.triggered.connect(self._add_new_queue)

        menu.exec(self.queue_list.viewport().mapToGlobal(pos))

    def _delete_queue_at(self, row):
        if row < 0 or row >= len(self.queues):
            return
        if self.queues[row].get("default", False):
            return
        if self._selected_index == row:
            self._selected_index = -1
        del self.queues[row]
        self.queue_list.takeItem(row)
        if self.queues:
            self.queue_list.setCurrentRow(min(row, len(self.queues) - 1))
