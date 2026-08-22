from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QSpinBox,
    QApplication
)
from PyQt6.QtCore import Qt

class ColumnDialog(QDialog):
    def __init__(self, columns_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Columns")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(420)
        self.setMinimumHeight(400)
        self.resize(420, 400)
        self.columns = [dict(c) for c in columns_data]  # List of dicts: {"name": str, "visible": bool, "width": int, "logical_index": int}
        self._is_refreshing = False
        
        layout = QVBoxLayout(self)
        
        main_layout = QHBoxLayout()
        
        # List widget for columns
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(240)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        self.refresh_list()
            
        main_layout.addWidget(self.list_widget)
        
        # Buttons layout
        btn_vbox = QVBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_up.setFixedWidth(100)
        self.btn_up.setFixedHeight(30)
        
        self.btn_down = QPushButton("Move Down")
        self.btn_down.setFixedWidth(100)
        self.btn_down.setFixedHeight(30)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setFixedWidth(100)
        self.btn_select_all.setFixedHeight(30)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setFixedWidth(100)
        self.btn_deselect_all.setFixedHeight(30)
        
        btn_vbox.addWidget(self.btn_up)
        btn_vbox.addWidget(self.btn_down)
        btn_vbox.addSpacing(10)
        btn_vbox.addWidget(self.btn_select_all)
        btn_vbox.addWidget(self.btn_deselect_all)
        btn_vbox.addStretch()
        main_layout.addLayout(btn_vbox)
        
        layout.addLayout(main_layout)
        
        # Width control
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Column width (pixels):"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(10, 1000)
        self.spin_width.setFixedHeight(25)
        width_layout.addWidget(self.spin_width)
        width_layout.addStretch()
        layout.addLayout(width_layout)
        
        # OK/Cancel
        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setFixedWidth(80)
        self.btn_ok.setFixedHeight(30)
        self.btn_ok.setDefault(True)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(30)
        
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)
        
        # Connections
        self.btn_up.clicked.connect(self.move_up)
        self.btn_down.clicked.connect(self.move_down)
        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_deselect_all.clicked.connect(self.deselect_all)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.list_widget.currentRowChanged.connect(self.update_width_spin)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.spin_width.valueChanged.connect(self.update_width_data)

    def _on_item_changed(self, item):
        if self._is_refreshing or not item:
            return
        row = self.list_widget.row(item)
        if 0 <= row < len(self.columns):
            self.columns[row]["visible"] = (item.checkState() == Qt.CheckState.Checked)

    def select_all(self):
        for col in self.columns:
            col["visible"] = True
        self.refresh_list()

    def deselect_all(self):
        for i, col in enumerate(self.columns):
            col["visible"] = (i == 0)
        self.refresh_list()

    def update_width_spin(self, row: int):
        if 0 <= row < len(self.columns):
            self.spin_width.blockSignals(True)
            self.spin_width.setValue(self.columns[row]["width"])
            self.spin_width.blockSignals(False)

    def update_width_data(self, val):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.columns):
            self.columns[row]["width"] = val

    def move_up(self):
        self._sync_from_widgets()
        row = self.list_widget.currentRow()
        if row > 0:
            self.columns[row], self.columns[row-1] = self.columns[row-1], self.columns[row]
            self.refresh_list()
            self.list_widget.setCurrentRow(row - 1)

    def move_down(self):
        self._sync_from_widgets()
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.columns) - 1:
            self.columns[row], self.columns[row+1] = self.columns[row+1], self.columns[row]
            self.refresh_list()
            self.list_widget.setCurrentRow(row + 1)

    def refresh_list(self):
        self._is_refreshing = True
        try:
            curr_row = self.list_widget.currentRow()
            self.list_widget.clear()
            for col in self.columns:
                item = QListWidgetItem(col["name"])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if col.get("visible", True) else Qt.CheckState.Unchecked)
                self.list_widget.addItem(item)
            if 0 <= curr_row < len(self.columns):
                self.list_widget.setCurrentRow(curr_row)
            elif len(self.columns) > 0:
                self.list_widget.setCurrentRow(0)
        finally:
            self._is_refreshing = False

    def _sync_from_widgets(self):
        try:
            for i in range(len(self.columns)):
                item = self.list_widget.item(i)
                if item:
                    self.columns[i]["visible"] = (item.checkState() == Qt.CheckState.Checked)
        except Exception:
            pass
        if not any(c.get("visible", False) for c in self.columns) and self.columns:
            self.columns[0]["visible"] = True

    def accept(self):
        self._sync_from_widgets()
        super().accept()

    def get_results(self):
        return [dict(c) for c in self.columns]
