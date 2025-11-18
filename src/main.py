import sys
import os
import time
import json
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu,
    QFileIconProvider
)
from PyQt6.QtGui import QAction, QFont, QCloseEvent, QIcon
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase

from workers import DownloadWorker
from dialogs import AddUrlDialog, OptionsDialog, DownloadProgressDialog
from utils import get_data_dir, get_config_dir

# --- HELPER FOR SORTING ---
class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        # Sort by UserRole data (numeric) if available, else text
        v1 = self.data(Qt.ItemDataRole.UserRole)
        v2 = other.data(Qt.ItemDataRole.UserRole)
        if v1 is not None and v2 is not None:
            try:
                return float(v1) < float(v2)
            except:
                pass # Fallback to string comparison
        return self.text() < other.text()

def parse_size_to_bytes(text):
    """Converts '1.5 MB' to raw bytes for sorting."""
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
    """Converts '1 min' to seconds for sorting."""
    try:
        if not text or text == "...": return 0
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].lower() if len(parts) > 1 else ""
        if 'hr' in unit: return val * 3600
        if 'min' in unit: return val * 60
        return val # seconds
    except:
        return 0

def get_file_icon(filename):
    """
    Returns a robust system icon for the file type.
    Prioritizes MIME type lookup for non-existent files to get accurate extension icons.
    """
    # 1. Try MIME database (Best for Linux/Unix with themes)
    db = QMimeDatabase()
    mime = db.mimeTypeForFile(filename, QMimeDatabase.MatchMode.MatchExtension)
    if mime.isValid():
        icon_name = mime.iconName()
        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            return icon
            
    # 2. Fallback to standard provider
    info = QFileInfo(filename)
    provider = QFileIconProvider()
    icon = provider.icon(info)
    
    # 3. If still generic/null, return a generic file icon
    if icon.isNull():
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
    
    return icon

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        self.setGeometry(200, 150, 1000, 600)
        self.setup_toolbar()
        self.setup_central_widget()
        self.setStatusBar(QStatusBar(self))
        # Key: id(QTableWidgetItem_col0) -> DownloadProgressDialog
        self.active_downloads = {} 
        
        # Load persistence data
        self.load_settings()
        self.load_data()

    def closeEvent(self, event: QCloseEvent):
        """Handle application closure by saving state."""
        self.stop_all_downloads()
        self.save_data()
        self.save_settings()
        event.accept()

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setObjectName("MainToolbar")
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
        self.download_table.setIconSize(QSize(16, 16)) # Fixed: QSize is now imported
        
        # Enable Sorting
        self.download_table.setSortingEnabled(True)
        
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
                if status == "Completed": should_hide = True
            elif category == "Finished":
                if status != "Completed": should_hide = True
            elif category in ext_map:
                extensions = ext_map[category]
                if not any(filename.endswith(ext) for ext in extensions):
                    should_hide = True
            
            if should_hide:
                self.download_table.setRowHidden(row, True)

    # --- PERSISTENCE METHODS ---
    def save_data(self):
        try:
            downloads = []
            for row in range(self.download_table.rowCount()):
                item_name = self.download_table.item(row, 0)
                if not item_name: continue
                
                url = item_name.data(Qt.ItemDataRole.UserRole)
                filename = item_name.text()
                size = self.download_table.item(row, 1).text()
                status = self.download_table.item(row, 2).text()
                
                if status in ["Receiving data...", "Connecting...", "Pending..."]:
                    status = "Paused"
                
                dl_data = {
                    "url": url,
                    "filename": filename,
                    "size": size,
                    "status": status,
                    "time_left": self.download_table.item(row, 3).text(),
                    "rate": self.download_table.item(row, 4).text(),
                    "last_try": self.download_table.item(row, 5).text(),
                    "date_added": self.download_table.item(row, 6).text()
                }
                downloads.append(dl_data)
            
            data_dir = get_data_dir()
            with open(os.path.join(data_dir, "downloads.json"), "w") as f:
                json.dump(downloads, f, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")

    def load_data(self):
        data_dir = get_data_dir()
        path = os.path.join(data_dir, "downloads.json")
        if not os.path.exists(path):
            return

        try:
            with open(path, "r") as f:
                downloads = json.load(f)
            
            # Disable sorting while loading to avoid jumping
            self.download_table.setSortingEnabled(False)
                
            for d in downloads:
                row = self.download_table.rowCount()
                self.download_table.insertRow(row)
                
                filename = d.get("filename", "Unknown")
                item_name = QTableWidgetItem(filename)
                item_name.setData(Qt.ItemDataRole.UserRole, d.get("url", ""))
                # Set icon
                item_name.setIcon(get_file_icon(filename))
                
                self.download_table.setItem(row, 0, item_name)
                
                self._set_sortable_item(row, 1, d.get("size", "..."), parse_size_to_bytes)
                self.download_table.setItem(row, 2, QTableWidgetItem(d.get("status", "Unknown")))
                self._set_sortable_item(row, 3, d.get("time_left", ""), parse_time_to_sec)
                self._set_sortable_item(row, 4, d.get("rate", ""), parse_size_to_bytes)
                self.download_table.setItem(row, 5, QTableWidgetItem(d.get("last_try", "")))
                self.download_table.setItem(row, 6, QTableWidgetItem(d.get("date_added", "")))
            
            self.download_table.setSortingEnabled(True)
            
        except Exception as e:
            print(f"Error loading data: {e}")

    def _set_sortable_item(self, row, col, text, parser_func):
        """Helper to set a sortable item with raw numeric data."""
        item = SortableTableWidgetItem(text)
        raw_val = parser_func(text)
        item.setData(Qt.ItemDataRole.UserRole, raw_val)
        self.download_table.setItem(row, col, item)

    def save_settings(self):
        try:
            config_dir = get_config_dir()
            settings = {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "windowState": self.saveState().toHex().data().decode()
            }
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        config_dir = get_config_dir()
        path = os.path.join(config_dir, "settings.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r") as f:
                settings = json.load(f)
                if "geometry" in settings:
                    self.restoreGeometry(QByteArray.fromHex(settings["geometry"].encode()))
                if "windowState" in settings:
                    self.restoreState(QByteArray.fromHex(settings["windowState"].encode()))
        except Exception as e:
            print(f"Error loading settings: {e}")

    # --------------------------

    def open_add_url(self):
        dialog = AddUrlDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            if url:
                self.start_download(url)

    def start_download(self, url):
        # Disable sorting briefly to insert safely
        sorting_was_enabled = self.download_table.isSortingEnabled()
        self.download_table.setSortingEnabled(False)

        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        # Get filename guess from URL for icon purposes immediately
        # Use unquote so "Google%20Docs.pdf" -> "Google Docs.pdf"
        try:
             parsed = urlparse(url)
             path = unquote(parsed.path)
             filename_guess = os.path.basename(path)
             if not filename_guess: filename_guess = "file"
        except:
             filename_guess = "file"
        
        item_name = QTableWidgetItem(filename_guess)
        item_name.setData(Qt.ItemDataRole.UserRole, url)
        item_name.setIcon(get_file_icon(filename_guess))
        
        self.download_table.setItem(row, 0, item_name)
        
        # Initialize columns with correct item types
        self._set_sortable_item(row, 1, "...", parse_size_to_bytes)
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        self.download_table.setItem(row, 5, QTableWidgetItem("Just now"))
        self.download_table.setItem(row, 6, QTableWidgetItem(time.strftime("%Y-%m-%d")))

        self.download_table.setSortingEnabled(sorting_was_enabled)
        
        # Pass the ITEM reference, not the row index, because sorting changes indices
        self._start_download_worker(url, item_name)
        self.save_data()

    def _start_download_worker(self, url, item_ref, resume_filename=None):
        save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Create worker. Row index passed to worker is for legacy logging mostly.
        # We will use item_ref for UI updates.
        worker = DownloadWorker(url, item_ref.row(), save_dir, resume_filename)
        
        # Connect signals using lambda to capture item_ref
        worker.main_progress_signal.connect(lambda _, data: self.update_download_row(item_ref, data))
        worker.finished_signal.connect(lambda _, status: self.download_finished(item_ref, status))
        
        progress_dialog = DownloadProgressDialog(worker, self)
        progress_dialog.show()
        
        # Key active downloads by the ITEM ID (stable across sorts)
        self.active_downloads[id(item_ref)] = progress_dialog
        progress_dialog.finished.connect(lambda: self.active_downloads.pop(id(item_ref), None))

    def resume_selected_download(self):
        selected_items = self.download_table.selectedItems()
        if not selected_items: return
        
        # Find the selected row's name item (column 0)
        # selectedItems returns items from all columns. We need the one from Col 0.
        item_row = selected_items[0].row()
        item_name = self.download_table.item(item_row, 0)
        
        if id(item_name) in self.active_downloads:
            self.active_downloads[id(item_name)].activateWindow()
            self.active_downloads[id(item_name)].raise_()
            return
        
        url = item_name.data(Qt.ItemDataRole.UserRole)
        filename = item_name.text()
        
        if url:
            self.download_table.setItem(item_row, 2, QTableWidgetItem("Resuming..."))
            self._start_download_worker(url, item_name, resume_filename=filename)
        else:
            QMessageBox.warning(self, "Error", "Could not find download URL.")

    def stop_selected_download(self):
        for item in self.download_table.selectedItems():
            # Only process if it's the key item (column 0)
            if item.column() == 0:
                key = id(item)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop()
                    dialog.reject()
                    self.download_table.setItem(item.row(), 2, QTableWidgetItem("Cancelled"))

    def stop_all_downloads(self):
        for dialog in self.active_downloads.values():
            dialog.worker.stop()
            dialog.reject()
        # Status update is tricky here without item ref mapping, 
        # but closeEvent calls this so UI update matters less.

    def delete_selected_download(self):
        # Get rows from selection
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
            
        confirm = QMessageBox.question(self, "Delete", "Are you sure you want to delete selected download(s)?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if confirm == QMessageBox.StandardButton.Yes:
            for row in rows:
                item_name = self.download_table.item(row, 0)
                key = id(item_name)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop()
                    dialog.reject()
                self.download_table.removeRow(row)
            self.save_data()

    def delete_completed_downloads(self):
        rows_to_delete = []
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() == "Completed":
                rows_to_delete.append(row)
        
        if not rows_to_delete: return

        confirm = QMessageBox.question(self, "Delete Completed", f"Delete {len(rows_to_delete)} completed downloads?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if confirm == QMessageBox.StandardButton.Yes:
            for row in sorted(rows_to_delete, reverse=True):
                self.download_table.removeRow(row)
            self.save_data()

    def update_download_row(self, item_ref, data):
        # Find the current row of the item (it might have moved due to sorting)
        row = self.download_table.row(item_ref)
        if row == -1: return # Item deleted
        
        # data = (filename, size_str, percent_str, time_left, speed_str)
        
        # 0. Name
        new_name = data[0]
        if item_ref.text() != new_name:
            item_ref.setText(new_name)
            # Update icon if name changes (e.g. resolved from URL)
            item_ref.setIcon(get_file_icon(new_name))
        
        # 1. Size
        self._set_sortable_item(row, 1, data[1], parse_size_to_bytes)
        
        # 2. Status (Shows percent during download)
        status_item = self.download_table.item(row, 2)
        if not status_item:
             status_item = QTableWidgetItem()
             self.download_table.setItem(row, 2, status_item)
        status_item.setText(data[2])
        
        # 3. Time
        self._set_sortable_item(row, 3, data[3], parse_time_to_sec)
        
        # 4. Rate
        self._set_sortable_item(row, 4, data[4], parse_size_to_bytes)

    def download_finished(self, item_ref, status_text):
        row = self.download_table.row(item_ref)
        if row != -1:
            self.download_table.setItem(row, 2, QTableWidgetItem(status_text))
            self.save_data()

    def open_options(self):
        dialog = OptionsDialog(self)
        dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())