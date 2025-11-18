import sys
import os
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu
)
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtCore import Qt

from workers import DownloadWorker
from dialogs import AddUrlDialog, OptionsDialog, DownloadProgressDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        self.setGeometry(200, 150, 1000, 600)
        self.setup_toolbar()
        self.setup_central_widget()
        self.setStatusBar(QStatusBar(self))
        self.active_downloads = {} 

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        actions_config = [
            ("Add URL", QStyle.StandardPixmap.SP_FileDialogNewFolder),
            ("Resume", QStyle.StandardPixmap.SP_MediaPlay),
            ("Stop", QStyle.StandardPixmap.SP_MediaStop),
            ("Stop All", QStyle.StandardPixmap.SP_DialogCancelButton),
            ("Delete", QStyle.StandardPixmap.SP_TrashIcon),
            ("Delete Completed", QStyle.StandardPixmap.SP_DialogDiscardButton),
            ("Options", QStyle.StandardPixmap.SP_FileDialogDetailedView),
        ]

        for text, icon_type in actions_config:
            icon = self.style().standardIcon(icon_type)
            action = QAction(icon, text, self)
            action.setStatusTip(text)
            toolbar.addAction(action)
            
            if text == "Options":
                action.triggered.connect(self.open_options)
            elif text == "Add URL":
                action.triggered.connect(self.open_add_url)
            elif text == "Resume":
                action.triggered.connect(self.resume_selected_download)
            elif text == "Stop":
                action.triggered.connect(self.stop_selected_download)
            elif text == "Stop All":
                action.triggered.connect(self.stop_all_downloads)
            elif text == "Delete":
                action.triggered.connect(self.delete_selected_download)
            elif text == "Delete Completed":
                action.triggered.connect(self.delete_completed_downloads)

    def setup_central_widget(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.itemClicked.connect(self.filter_downloads) 
        
        all_downloads = QTreeWidgetItem(self.category_tree, ["All Downloads"])
        all_downloads.setExpanded(True)
        categories = ["Compressed", "Documents", "Music", "Programs", "Video"]
        for cat in categories:
            QTreeWidgetItem(all_downloads, [cat])
        QTreeWidgetItem(self.category_tree, ["Unfinished"])
        QTreeWidgetItem(self.category_tree, ["Finished"])
        
        self.download_table = QTableWidget()
        self.download_table.setColumnCount(7)
        self.download_table.verticalHeader().setVisible(False)
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.download_table.setHorizontalHeaderLabels([
            "File Name", "Size", "Status", "Time Left", 
            "Transfer Rate", "Last Try", "Date Added"
        ])
        header = self.download_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.category_tree)
        splitter.addWidget(self.download_table)
        splitter.setSizes([200, 800])
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

    def filter_downloads(self, item, column):
        category = item.text(0)
        
        ext_map = {
            "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
            "Music": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
            "Programs": [".exe", ".msi", ".sh", ".bin", ".deb", ".bat"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }

        for row in range(self.download_table.rowCount()):
            self.download_table.setRowHidden(row, False) 
            
            filename = self.download_table.item(row, 0).text().lower()
            status = self.download_table.item(row, 2).text()
            
            should_hide = False
            
            if category == "All Downloads":
                should_hide = False
            elif category == "Unfinished":
                if status == "Completed":
                    should_hide = True
            elif category == "Finished":
                if status != "Completed":
                    should_hide = True
            elif category in ext_map:
                extensions = ext_map[category]
                if not any(filename.endswith(ext) for ext in extensions):
                    should_hide = True
            
            if should_hide:
                self.download_table.setRowHidden(row, True)

    def open_add_url(self):
        dialog = AddUrlDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            if url:
                self.start_download(url)

    def start_download(self, url):
        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        item = QTableWidgetItem(url)
        item.setData(Qt.ItemDataRole.UserRole, url)
        self.download_table.setItem(row, 0, item)
        
        self.download_table.setItem(row, 1, QTableWidgetItem("..."))
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        self.download_table.setItem(row, 3, QTableWidgetItem("..."))
        self.download_table.setItem(row, 4, QTableWidgetItem("..."))
        self.download_table.setItem(row, 5, QTableWidgetItem("Just now"))
        self.download_table.setItem(row, 6, QTableWidgetItem(time.strftime("%Y-%m-%d")))

        self._start_download_worker(url, row)

    def _start_download_worker(self, url, row, resume_filename=None):
        save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Pass resume_filename to worker to avoid creating new (1), (2) files
        worker = DownloadWorker(url, row, save_dir, resume_filename)
        worker.main_progress_signal.connect(self.update_download_row)
        worker.finished_signal.connect(self.download_finished)
        
        progress_dialog = DownloadProgressDialog(worker, self)
        progress_dialog.show()
        
        self.active_downloads[row] = progress_dialog
        progress_dialog.finished.connect(lambda: self.active_downloads.pop(row, None))

    def resume_selected_download(self):
        selected_rows = self.download_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        
        if row in self.active_downloads:
            self.active_downloads[row].activateWindow()
            self.active_downloads[row].raise_()
            return
        
        item = self.download_table.item(row, 0)
        url = item.data(Qt.ItemDataRole.UserRole)
        filename = item.text() # Get current filename from table
        
        if url:
            self.download_table.setItem(row, 2, QTableWidgetItem("Resuming..."))
            # Pass filename to ensure we resume on the SAME file
            self._start_download_worker(url, row, resume_filename=filename)
        else:
            QMessageBox.warning(self, "Error", "Could not find download URL.")

    def stop_selected_download(self):
        selected_rows = self.download_table.selectionModel().selectedRows()
        for idx in selected_rows:
            row = idx.row()
            if row in self.active_downloads:
                dialog = self.active_downloads[row]
                dialog.worker.stop()
                dialog.reject() 
                self.download_table.setItem(row, 2, QTableWidgetItem("Cancelled"))

    def stop_all_downloads(self):
        active_rows = list(self.active_downloads.keys())
        for row in active_rows:
            if row in self.active_downloads:
                dialog = self.active_downloads[row]
                dialog.worker.stop()
                dialog.reject()
                self.download_table.setItem(row, 2, QTableWidgetItem("Cancelled"))

    def delete_selected_download(self):
        selected_rows = sorted(self.download_table.selectionModel().selectedRows(), key=lambda x: x.row(), reverse=True)
        
        if not selected_rows:
            return
            
        confirm = QMessageBox.question(self, "Delete", "Are you sure you want to delete selected download(s)?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if confirm == QMessageBox.StandardButton.Yes:
            for idx in selected_rows:
                row = idx.row()
                if row in self.active_downloads:
                    dialog = self.active_downloads[row]
                    dialog.worker.stop()
                    dialog.reject()
                
                self.download_table.removeRow(row)

    def delete_completed_downloads(self):
        rows_to_delete = []
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() == "Completed":
                rows_to_delete.append(row)
        
        if not rows_to_delete:
            return

        confirm = QMessageBox.question(self, "Delete Completed", f"Delete {len(rows_to_delete)} completed downloads?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if confirm == QMessageBox.StandardButton.Yes:
            for row in sorted(rows_to_delete, reverse=True):
                self.download_table.removeRow(row)

    def update_download_row(self, row, data):
        if row < self.download_table.rowCount():
            item0 = self.download_table.item(row, 0)
            if not item0: 
                item0 = QTableWidgetItem()
                self.download_table.setItem(row, 0, item0)
            
            item0.setText(data[0]) 
            
            self.download_table.setItem(row, 1, QTableWidgetItem(data[1]))
            self.download_table.setItem(row, 2, QTableWidgetItem(data[2]))
            self.download_table.setItem(row, 3, QTableWidgetItem(data[3]))
            self.download_table.setItem(row, 4, QTableWidgetItem(data[4]))

    def download_finished(self, row, status_text):
        if row < self.download_table.rowCount():
            self.download_table.setItem(row, 2, QTableWidgetItem(status_text))

    def open_options(self):
        dialog = OptionsDialog(self)
        dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())