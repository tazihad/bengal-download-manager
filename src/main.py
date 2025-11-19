import sys
import os
import time
import json
import shutil
import subprocess
from urllib.parse import urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar, QStyle,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QMenu,
    QFileIconProvider, QInputDialog, QFileDialog
)
from PyQt6.QtGui import QAction, QFont, QCloseEvent, QIcon, QColor, QPalette, QDesktopServices
from PyQt6.QtCore import Qt, QByteArray, QFileInfo, QSize, QMimeDatabase, QUrl

from workers import DownloadWorker
from dialogs import AddUrlDialog, OptionsDialog, DownloadProgressDialog, PropertiesDialog, load_category_config
from utils import get_data_dir, get_config_dir, get_unique_filepath

# --- HELPER FOR SORTING ---
class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        v1 = self.data(Qt.ItemDataRole.UserRole)
        v2 = other.data(Qt.ItemDataRole.UserRole)
        if v1 is not None and v2 is not None:
            try:
                return float(v1) < float(v2)
            except:
                pass
        return self.text() < other.text()

def parse_size_to_bytes(text):
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
    try:
        if not text or text == "...": return 0
        parts = text.split()
        val = float(parts[0])
        unit = parts[1].lower() if len(parts) > 1 else ""
        if 'hr' in unit: return val * 3600
        if 'min' in unit: return val * 60
        return val 
    except:
        return 0

def get_file_icon(filename):
    db = QMimeDatabase()
    mime = db.mimeTypeForFile(filename, QMimeDatabase.MatchMode.MatchExtension)
    if mime.isValid():
        icon_name = mime.iconName()
        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            return icon
    info = QFileInfo(filename)
    provider = QFileIconProvider()
    icon = provider.icon(info)
    if icon.isNull():
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
    return icon

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bengal Download Manager")
        self.setGeometry(200, 150, 1000, 600)
        
        self.settings = self.load_settings()
        
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_central_widget()
        
        self.active_downloads = {} 
        self.load_data()
        
        # Initial UI State Update
        self.update_ui_states()

    def closeEvent(self, event: QCloseEvent):
        self.stop_all_downloads()
        self.save_data()
        self.save_settings()
        event.accept()

    def setup_actions(self):
        self.action_add_url = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "Add URL", self)
        self.action_add_url.triggered.connect(self.open_add_url)

        self.action_exit = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "Exit", self)
        self.action_exit.triggered.connect(self.close)

        self.action_stop = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop), "Stop", self)
        self.action_stop.triggered.connect(self.stop_selected_download)
        self.action_stop.setEnabled(False)

        self.action_stop_all = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), "Stop All", self)
        self.action_stop_all.triggered.connect(self.stop_all_downloads)
        self.action_stop_all.setEnabled(False)

        self.action_resume = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Resume", self)
        self.action_resume.triggered.connect(self.resume_selected_download)
        self.action_resume.setEnabled(False)
        
        self.action_download_now = QAction("Download Now", self)
        self.action_download_now.triggered.connect(self.resume_selected_download) 
        
        self.action_redownload = QAction("Redownload", self)
        self.action_redownload.triggered.connect(self.redownload_selected)

        self.action_remove = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Remove", self)
        self.action_remove.triggered.connect(self.remove_from_list)
        self.action_remove.setEnabled(False)

        self.action_delete = QAction("Delete from disk", self)
        self.action_delete.triggered.connect(self.delete_selected_download)
        self.action_delete.setEnabled(False)

        self.action_delete_completed = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton), "Delete Completed", self)
        self.action_delete_completed.triggered.connect(self.delete_completed_downloads)
        
        self.action_options = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Options", self)
        self.action_options.triggered.connect(self.open_options)

        self.action_open_folder = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), "Open Downloads Folder", self)
        self.action_open_folder.triggered.connect(self.open_downloads_folder_generic)

    def setup_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        # 1. Tasks
        tasks_menu = menu_bar.addMenu("&Tasks")
        tasks_menu.addAction(self.action_add_url)
        tasks_menu.addSeparator()
        tasks_menu.addAction(self.action_exit)

        # 2. File
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.action_stop)
        file_menu.addAction(self.action_remove)
        file_menu.addAction(self.action_download_now)
        file_menu.addAction(self.action_redownload)
        file_menu.addSeparator()
        file_menu.addAction(self.action_open_folder)

        # 3. Downloads
        downloads_menu = menu_bar.addMenu("&Downloads")
        downloads_menu.addAction(self.action_resume)
        downloads_menu.addAction(self.action_stop)
        downloads_menu.addAction(self.action_stop_all)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_delete)
        downloads_menu.addAction(self.action_delete_completed)
        downloads_menu.addSeparator()
        downloads_menu.addAction(self.action_options)

        # 4. View
        view_menu = menu_bar.addMenu("&View")
        
        sort_menu = view_menu.addMenu("Sort by")
        sort_fields = [
            ("File Name", 0), ("Size", 1), ("Status", 2), ("Time Left", 3), 
            ("Transfer Rate", 4), ("Last Try", 5), ("Date Added", 6)
        ]
        for name, col_idx in sort_fields:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=col_idx: self.download_table.sortItems(c, Qt.SortOrder.AscendingOrder))
            sort_menu.addAction(action)

        view_menu.addSeparator()
        toolbar_toggle = QAction("&Toolbar", self)
        toolbar_toggle.setCheckable(True)
        toolbar_toggle.setChecked(True)
        toolbar_toggle.triggered.connect(lambda checked: self.findChild(QToolBar, "MainToolbar").setVisible(checked))
        view_menu.addAction(toolbar_toggle)

        # 5. Help
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About Bengal DM", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_toolbar(self):
        toolbar = self.findChild(QToolBar, "MainToolbar")
        if toolbar is None:
            toolbar = QToolBar("Main Toolbar", self)
            toolbar.setObjectName("MainToolbar")
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        else:
            for action in toolbar.actions():
                toolbar.removeAction(action)
        
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(24, 24))

        toolbar.addAction(self.action_add_url)
        toolbar.addAction(self.action_resume)
        toolbar.addAction(self.action_stop)
        toolbar.addAction(self.action_stop_all)
        toolbar.addAction(self.action_remove) 
        toolbar.addAction(self.action_delete_completed)
        toolbar.addAction(self.action_options)

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
        self.download_table.setIconSize(QSize(16, 16))
        self.download_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.download_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.download_table.setSortingEnabled(True)
        
        self.download_table.itemSelectionChanged.connect(self.update_ui_states)
        
        self.download_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self.show_context_menu)
        
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

    def update_ui_states(self):
        selected_rows = self.download_table.selectedItems()
        has_selection = len(selected_rows) > 0
        
        has_active_downloads = len(self.active_downloads) > 0
        
        selection_has_active = False
        selection_has_paused = False
        
        if has_selection:
            rows = set(item.row() for item in selected_rows)
            for r in rows:
                item = self.download_table.item(r, 0)
                key = id(item)
                if key in self.active_downloads:
                    selection_has_active = True
                else:
                    status = self.download_table.item(r, 2).text()
                    if status != "Completed":
                        selection_has_paused = True
        
        self.action_stop.setEnabled(selection_has_active)
        self.action_stop_all.setEnabled(has_active_downloads)
        
        self.action_remove.setEnabled(has_selection)
        self.action_delete.setEnabled(has_selection)
        
        self.action_resume.setEnabled(selection_has_paused) 
        self.action_download_now.setEnabled(selection_has_paused)
        
        self.action_redownload.setEnabled(has_selection)

    def redownload_selected(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()))
        for row in rows:
            item = self.download_table.item(row, 0)
            self.ctx_redownload(item)

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

    def save_data(self):
        try:
            downloads = []
            for row in range(self.download_table.rowCount()):
                item_name = self.download_table.item(row, 0)
                if not item_name: continue
                
                url = item_name.data(Qt.ItemDataRole.UserRole)
                path = item_name.data(Qt.ItemDataRole.UserRole + 1) 
                filename = item_name.text()
                size = self.download_table.item(row, 1).text()
                status = self.download_table.item(row, 2).text()
                
                if status in ["Receiving data...", "Connecting...", "Pending..."]:
                    status = "Paused"
                
                dl_data = {
                    "url": url,
                    "filename": filename,
                    "path": path,
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
            
            self.download_table.setSortingEnabled(False)
                
            for d in downloads:
                row = self.download_table.rowCount()
                self.download_table.insertRow(row)
                
                filename = d.get("filename", "Unknown")
                item_name = QTableWidgetItem(filename)
                item_name.setData(Qt.ItemDataRole.UserRole, d.get("url", ""))
                item_name.setData(Qt.ItemDataRole.UserRole + 1, d.get("path", "")) 
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
        item = SortableTableWidgetItem(text)
        raw_val = parser_func(text)
        item.setData(Qt.ItemDataRole.UserRole, raw_val)
        self.download_table.setItem(row, col, item)

    def save_settings(self):
        try:
            config_dir = get_config_dir()
            settings = {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "windowState": self.saveState().toHex().data().decode(),
            }
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        settings = {}
        config_dir = get_config_dir()
        path = os.path.join(config_dir, "settings.json")
        if not os.path.exists(path):
            return settings
        try:
            with open(path, "r") as f:
                settings = json.load(f)
                if "geometry" in settings:
                    self.restoreGeometry(QByteArray.fromHex(settings["geometry"].encode()))
                if "windowState" in settings:
                    self.restoreState(QByteArray.fromHex(settings["windowState"].encode()))
        except Exception as e:
            print(f"Error loading settings: {e}")
        return settings

    def show_context_menu(self, pos):
        item = self.download_table.itemAt(pos)
        if not item: return

        self.download_table.selectRow(item.row())
        
        status = self.download_table.item(item.row(), 2).text()
        is_completed = (status == "Completed")

        menu = QMenu(self)
        
        act_open = QAction("Open", self)
        act_open_with = QAction("Open with...", self)
        act_open_folder = QAction("Open folder", self)
        act_move = QAction("Move/Rename", self)
        
        act_move.setEnabled(is_completed)
        act_open.setEnabled(is_completed)
        act_open_with.setEnabled(is_completed)
        
        menu.addActions([act_open, act_open_with, act_open_folder, act_move])
        menu.addSeparator()
        
        act_redownload = QAction("Redownload", self)
        act_resume = QAction("Resume download", self)
        act_refresh = QAction("Refresh download address", self)
        
        act_resume.setEnabled(not is_completed)

        menu.addActions([act_redownload, act_resume, act_refresh])
        menu.addSeparator()
        
        act_remove = QAction("Remove", self)
        menu.addAction(act_remove)
        menu.addSeparator()
        
        act_props = QAction("Properties", self)
        menu.addAction(act_props)

        act_open.triggered.connect(lambda: self.ctx_open_file(item))
        act_open_with.triggered.connect(lambda: self.ctx_open_with(item))
        act_open_folder.triggered.connect(lambda: self.ctx_open_folder(item))
        act_move.triggered.connect(lambda: self.ctx_move_rename(item))
        act_redownload.triggered.connect(lambda: self.ctx_redownload(item))
        act_resume.triggered.connect(self.resume_selected_download)
        act_refresh.triggered.connect(lambda: self.ctx_refresh_address(item))
        act_remove.triggered.connect(self.remove_from_list) 
        act_props.triggered.connect(lambda: self.ctx_properties(item))

        menu.exec(self.download_table.viewport().mapToGlobal(pos))

    def ctx_open_file(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "Error", "File does not exist.")

    def ctx_open_with(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not path or not os.path.exists(path):
             QMessageBox.warning(self, "Error", "File does not exist.")
             return
        app_path, _ = QFileDialog.getOpenFileName(self, "Select Application", "/usr/bin", "Executables (*)")
        if app_path:
            subprocess.Popen([app_path, path])

    def ctx_open_folder(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                if os.name == 'nt':
                    os.startfile(folder)
                else:
                    subprocess.Popen(['xdg-open', folder])

    def open_downloads_folder_generic(self):
        path = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(path):
             if os.name == 'nt':
                 os.startfile(path)
             else:
                 subprocess.Popen(['xdg-open', path])

    def ctx_move_rename(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        old_path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "Error", "File not found to move.")
            return

        new_path, _ = QFileDialog.getSaveFileName(self, "Move/Rename File", old_path)
        if new_path and new_path != old_path:
            try:
                shutil.move(old_path, new_path)
                new_filename = os.path.basename(new_path)
                item_0.setText(new_filename)
                item_0.setData(Qt.ItemDataRole.UserRole + 1, new_path)
                self.save_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to move file: {e}")

    def ctx_redownload(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        path = item_0.data(Qt.ItemDataRole.UserRole + 1)
        url = item_0.data(Qt.ItemDataRole.UserRole)
        
        if path and os.path.exists(path):
            try: os.remove(path)
            except: pass
        
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        self._start_download_worker(url, item_0)

    def ctx_refresh_address(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        url = item_0.data(Qt.ItemDataRole.UserRole)
        new_url, ok = QInputDialog.getText(self, "Refresh Address", "Enter new URL:", text=url)
        if ok and new_url:
            item_0.setData(Qt.ItemDataRole.UserRole, new_url)
            self.save_data()

    def ctx_properties(self, item):
        row = item.row()
        item_0 = self.download_table.item(row, 0)
        data = {
            "row": row,
            "item": item_0,
            "url": item_0.data(Qt.ItemDataRole.UserRole),
            "path": item_0.data(Qt.ItemDataRole.UserRole + 1),
            "filename": item_0.text(),
            "status": self.download_table.item(row, 2).text(),
            "size": self.download_table.item(row, 1).text(),
            "date_added": self.download_table.item(row, 6).text(),
            "last_try": self.download_table.item(row, 5).text()
        }
        dlg = PropertiesDialog(data, self)
        dlg.exec()

    def open_add_url(self):
        dialog = AddUrlDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            if url:
                self.start_download(url)

    def start_download(self, url):
        sorting_was_enabled = self.download_table.isSortingEnabled()
        self.download_table.setSortingEnabled(False)

        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
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
        self._set_sortable_item(row, 1, "...", parse_size_to_bytes)
        self.download_table.setItem(row, 2, QTableWidgetItem("Pending..."))
        self._set_sortable_item(row, 3, "...", parse_time_to_sec)
        self._set_sortable_item(row, 4, "...", parse_size_to_bytes)
        self.download_table.setItem(row, 5, QTableWidgetItem("Just now"))
        self.download_table.setItem(row, 6, QTableWidgetItem(time.strftime("%Y-%m-%d")))

        self.download_table.setSortingEnabled(sorting_was_enabled)
        self._start_download_worker(url, item_name)
        self.save_data()

    def _start_download_worker(self, url, item_ref, resume_filename=None):
        config = load_category_config()
        categories = config.get("categories", {})
        
        target_filename = resume_filename if resume_filename else item_ref.text()
        ext = os.path.splitext(target_filename)[1].replace(".", "").lower()
        
        final_category = "General"
        for cat_name, cat_data in categories.items():
            if ext in cat_data.get("extensions", "").split():
                final_category = cat_name
                break
        
        save_dir = categories[final_category]["path"]
        if not os.path.exists(save_dir):
            try: os.makedirs(save_dir)
            except: save_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        worker = DownloadWorker(url, item_ref.row(), save_dir, resume_filename)
        
        item_ref.setData(Qt.ItemDataRole.UserRole + 1, worker.target_path)
        item_ref.setText(worker.filename)
        
        worker.main_progress_signal.connect(lambda _, data: self.update_download_row(item_ref, data))
        worker.finished_signal.connect(lambda _, status: self.download_finished(item_ref, status))
        
        progress_dialog = DownloadProgressDialog(worker, self)
        progress_dialog.show()
        
        self.active_downloads[id(item_ref)] = progress_dialog
        progress_dialog.finished.connect(lambda: self.active_downloads.pop(id(item_ref), None))
        
        # Trigger UI Update for Stop Buttons
        self.update_ui_states()

    def resume_selected_download(self):
        selected_items = self.download_table.selectedItems()
        if not selected_items: return
        
        rows = set(item.row() for item in selected_items)
        for row in rows:
            item_name = self.download_table.item(row, 0)
            if id(item_name) in self.active_downloads:
                self.active_downloads[id(item_name)].activateWindow()
                self.active_downloads[id(item_name)].raise_()
                continue
            
            url = item_name.data(Qt.ItemDataRole.UserRole)
            filename = item_name.text()
            
            if url:
                self.download_table.setItem(row, 2, QTableWidgetItem("Resuming..."))
                self._start_download_worker(url, item_name, resume_filename=filename)

    def stop_selected_download(self):
        for item in self.download_table.selectedItems():
            if item.column() == 0:
                key = id(item)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop()
                    dialog.reject()
                    self.download_table.setItem(item.row(), 2, QTableWidgetItem("Cancelled"))

    def stop_all_downloads(self):
        for dialog in list(self.active_downloads.values()):
            dialog.worker.stop()
            dialog.reject()

    def remove_from_list(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
        
        for row in rows:
            item_name = self.download_table.item(row, 0)
            key = id(item_name)
            if key in self.active_downloads:
                dialog = self.active_downloads[key]
                dialog.worker.stop()
                dialog.reject()
            self.download_table.removeRow(row)
        self.save_data()
        self.update_ui_states()

    def delete_selected_download(self):
        rows = sorted(set(item.row() for item in self.download_table.selectedItems()), reverse=True)
        if not rows: return
            
        confirm = QMessageBox.question(self, "Delete", "Are you sure you want to delete selected download(s)?\nThis will delete the files from disk.", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if confirm == QMessageBox.StandardButton.Yes:
            for row in rows:
                item_name = self.download_table.item(row, 0)
                key = id(item_name)
                if key in self.active_downloads:
                    dialog = self.active_downloads[key]
                    dialog.worker.stop()
                    dialog.reject()
                
                path = item_name.data(Qt.ItemDataRole.UserRole + 1)
                if path and os.path.exists(path):
                    try: os.remove(path)
                    except: pass
                if path and os.path.exists(path + ".tmpbdm"):
                    try: os.remove(path + ".tmpbdm")
                    except: pass
                
                self.download_table.removeRow(row)
            self.save_data()
            self.update_ui_states()

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
            self.update_ui_states()

    def update_download_row(self, item_ref, data):
        row = self.download_table.row(item_ref)
        if row == -1: return 
        
        new_name = data[0]
        if item_ref.text() != new_name:
            item_ref.setText(new_name)
            item_ref.setIcon(get_file_icon(new_name))
        
        self._set_sortable_item(row, 1, data[1], parse_size_to_bytes)
        
        status_item = self.download_table.item(row, 2)
        if not status_item:
             status_item = QTableWidgetItem()
             self.download_table.setItem(row, 2, status_item)
        status_item.setText(data[2])
        
        self._set_sortable_item(row, 3, data[3], parse_time_to_sec)
        self._set_sortable_item(row, 4, data[4], parse_size_to_bytes)

    def download_finished(self, item_ref, status_text):
        row = self.download_table.row(item_ref)
        if row != -1:
            self.download_table.setItem(row, 2, QTableWidgetItem(status_text))
            self.save_data()
        
        # Update UI to reflect that a download finished (e.g. Stop button disabled)
        self.update_ui_states()
    
    def open_options(self):
        dialog = OptionsDialog(self)
        dialog.exec()

    def show_about(self):
        QMessageBox.about(self, "About Bengal DM", 
            "<h2>Bengal Download Manager</h2>"
            "<p>A simple, multi-threaded download manager built with PyQt6 for fast, resumable downloads.</p>"
            "<p>Version: 1.0</p>"
            "<p>Built for the XDG standard on Linux.</p>"
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())