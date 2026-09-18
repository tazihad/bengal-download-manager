import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, pyqtProperty, pyqtSlot
from core.utils import open_file_generic, show_in_folder

class DownloadBridge(QObject):
    downloadsChanged = pyqtSignal()
    statusMessageChanged = pyqtSignal(str)

    def __init__(self, main_window=None, store=None, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self._store = store
        if self._store:
            self._store.downloadsChanged.connect(self.downloadsChanged.emit)
        self._downloads_data = []
        self._status_message = "Ready"

    @pyqtProperty(list, notify=downloadsChanged)
    def downloads(self):
        if self._store:
            return self._store.get_all_items()
        if self._main_window:
            return self._main_window.get_qml_downloads_data()
        return self._downloads_data

    @pyqtProperty(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

    @pyqtProperty(str, notify=downloadsChanged)
    def memoryUsage(self):
        from core.utils import get_process_memory, format_bytes
        return format_bytes(get_process_memory())

    @pyqtProperty(bool, notify=downloadsChanged)
    def aria2Running(self):
        try:
            from core.aria2_daemon import get_aria2_daemon_manager
            return get_aria2_daemon_manager().is_running()
        except Exception:
            return False

    @pyqtProperty(str, notify=downloadsChanged)
    def totalSpeed(self):
        try:
            from core.download_controller import get_download_controller
            from core.utils import format_bytes
            ctrl = get_download_controller()
            total = ctrl.get_total_speed()
            if total <= 0.0 and self._main_window and hasattr(self._main_window, 'active_speeds') and self._main_window.active_speeds:
                total = sum(self._main_window.active_speeds.values())
            return f"{format_bytes(total)}/s" if total > 0 else "0 B/s"
        except Exception:
            return "0 B/s"

    @pyqtProperty(int, notify=downloadsChanged)
    def itemCount(self):
        if self._store:
            return self._store.count()
        if self._main_window and hasattr(self._main_window, 'download_table'):
            return self._main_window.download_table.rowCount()
        return len(self._downloads_data)

    @pyqtSlot(str, str, str)
    def addDownload(self, url, category="General", save_path=""):
        if self._main_window:
            self._main_window.add_new_download(url=url, category=category, save_path=save_path)
            self.downloadsChanged.emit()

    @pyqtSlot(int)
    def pauseDownload(self, index):
        if self._main_window:
            self._main_window.qml_pause_download(index)
            self.downloadsChanged.emit()

    @pyqtSlot(int)
    def resumeDownload(self, index):
        if self._main_window:
            self._main_window.qml_resume_download(index)
            self.downloadsChanged.emit()

    @pyqtSlot(int)
    def deleteDownload(self, index):
        if self._main_window:
            self._main_window.qml_delete_download(index)
            self.downloadsChanged.emit()

    @pyqtSlot(int)
    def moveDownload(self, index):
        if self._main_window:
            self._main_window.qml_move_download(index)
            self.downloadsChanged.emit()

    @pyqtSlot(int)
    def renameDownload(self, index):
        if self._main_window:
            self._main_window.qml_rename_download(index)
            self.downloadsChanged.emit()

    @pyqtSlot(str)
    def openFile(self, path):
        if path and os.path.exists(path):
            open_file_generic(path)

    @pyqtSlot(str)
    def openFolder(self, path):
        if path:
            show_in_folder(path)

    @pyqtSlot()
    def refresh(self):
        if self._main_window and hasattr(self._main_window, 'isVisible') and not self._main_window.isVisible():
            return
        self.downloadsChanged.emit()
