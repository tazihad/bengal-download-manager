from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
)

class DeleteDialog(QDialog):
    def __init__(self, count, is_completed=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Completed Downloads" if is_completed else "Delete")
        self.setFixedWidth(420)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Message Label
        message = QLabel(f"Are you sure you want to delete {count} {'completed ' if is_completed else 'selected '}download(s)?")
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Checkbox for Disk Deletion
        self.chk_delete_disk = QCheckBox("Also delete files from disk (permanently)")
        self.chk_delete_disk.setChecked(False) # Default to false for safety
        layout.addWidget(self.chk_delete_disk)
        
        layout.addSpacing(5)
        
        # Button Layout
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_yes = QPushButton("Yes")
        self.btn_yes.setFixedWidth(80)
        self.btn_yes.setFixedHeight(30)
        self.btn_yes.setDefault(True)
        self.btn_yes.clicked.connect(self.accept)
        
        self.btn_no = QPushButton("No")
        self.btn_no.setFixedWidth(80)
        self.btn_no.setFixedHeight(30)
        self.btn_no.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        
        layout.addLayout(btn_layout)

    def should_delete_from_disk(self):
        return self.chk_delete_disk.isChecked()
