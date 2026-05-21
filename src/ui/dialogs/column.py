from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSpinBox,
    QApplication
)
from PyQt6.QtCore import Qt

class ColumnDialog(QDialog):
    def __init__(self, columns_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Columns")
        self.setWindowIcon(QApplication.windowIcon())
        self.setFixedWidth(400)
        self.columns = columns_data # List of dicts: {"name": str, "visible": bool, "width": int, "logical_index": int}
        
        layout = QVBoxLayout(self)
        
        main_layout = QHBoxLayout()
        
        # List widget for columns
        self.list_widget = QTableWidget(len(self.columns), 1)
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.verticalHeader().setVisible(False)
        self.list_widget.horizontalHeader().setVisible(False)
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        for i, col in enumerate(self.columns):
            item = QTableWidgetItem(col["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if col["visible"] else Qt.CheckState.Unchecked)
            self.list_widget.setItem(i, 0, item)
            
        main_layout.addWidget(self.list_widget)
        
        # Buttons layout
        btn_vbox = QVBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_up.setFixedWidth(100)
        self.btn_up.setFixedHeight(30)
        
        self.btn_down = QPushButton("Move Down")
        self.btn_down.setFixedWidth(100)
        self.btn_down.setFixedHeight(30)
        
        btn_vbox.addWidget(self.btn_up)
        btn_vbox.addWidget(self.btn_down)
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
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.list_widget.itemSelectionChanged.connect(self.update_width_spin)
        self.spin_width.valueChanged.connect(self.update_width_data)

    def update_width_spin(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.spin_width.setValue(self.columns[row]["width"])

    def update_width_data(self, val):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.columns[row]["width"] = val

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            self.columns[row], self.columns[row-1] = self.columns[row-1], self.columns[row]
            self.refresh_list()
            self.list_widget.selectRow(row - 1)

    def move_down(self):
        row = self.list_widget.currentRow()
        if row < len(self.columns) - 1:
            self.columns[row], self.columns[row+1] = self.columns[row+1], self.columns[row]
            self.refresh_list()
            self.list_widget.selectRow(row + 1)

    def refresh_list(self):
        for i, col in enumerate(self.columns):
            item = self.list_widget.item(i, 0)
            item.setText(col["name"])
            item.setCheckState(Qt.CheckState.Checked if col["visible"] else Qt.CheckState.Unchecked)

    def get_results(self):
        for i in range(len(self.columns)):
            self.columns[i]["visible"] = self.list_widget.item(i, 0).checkState() == Qt.CheckState.Checked
        return self.columns
