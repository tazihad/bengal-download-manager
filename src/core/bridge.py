import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, pyqtProperty, pyqtSlot
from core.utils import open_file_generic, show_in_folder

class DownloadBridge(QObject):
    downloadsChanged = pyqtSignal()
    statusMessageChanged = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self._downloads_data = []
        self._status_message = "Ready"

    @pyqtProperty(list, notify=downloadsChanged)
    def downloads(self):
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
        if self._main_window and hasattr(self._main_window, 'aria2_process') and self._main_window.aria2_process:
            return self._main_window.aria2_process.poll() is None
        return False

    @pyqtProperty(str, notify=downloadsChanged)
    def totalSpeed(self):
        if self._main_window and hasattr(self._main_window, 'active_speeds') and self._main_window.active_speeds:
            from core.utils import format_bytes
            return f"{format_bytes(sum(self._main_window.active_speeds.values()))}/s"
        return "0 B/s"

    @pyqtProperty(int, notify=downloadsChanged)
    def itemCount(self):
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
        self.downloadsChanged.emit()
