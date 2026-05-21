import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QFrame, QHBoxLayout

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from ui.dialogs.progress import DownloadProgressDialog

class MockWorker:
    def __init__(self):
        self.filename = "test.zip"
        self.url = "http://example.com/test.zip"
        self.row_index = 0
        from PyQt6.QtCore import pyqtSignal, QObject
        class Signals(QObject):
            log_signal = pyqtSignal(str)
            main_bar_signal = pyqtSignal(int, int)
            main_progress_signal = pyqtSignal(int, list)
            finished_signal = pyqtSignal(int, str)
            init_segments_signal = pyqtSignal(int)
            segment_update_signal = pyqtSignal(int, int, int, int, str)
        self.signals = Signals()
        self.log_signal = self.signals.log_signal
        self.main_bar_signal = self.signals.main_bar_signal
        self.main_progress_signal = self.signals.main_progress_signal
        self.finished_signal = self.signals.finished_signal
        self.init_segments_signal = self.signals.init_segments_signal
        self.segment_update_signal = self.signals.segment_update_signal
    def start(self): pass
    def stop(self): pass
    def format_bytes(self, b): return str(b)

@pytest.fixture
def progress_dialog(qtbot):
    worker = MockWorker()
    dialog = DownloadProgressDialog(worker)
    qtbot.addWidget(dialog)
    return dialog

def test_details_frame_position(progress_dialog):
    layout = progress_dialog.layout()
    assert isinstance(layout, QVBoxLayout)
    
    items = [layout.itemAt(i) for i in range(layout.count())]
    
    details_index = -1
    btn_layout_index = -1
    
    for i, item in enumerate(items):
        if item.widget() == progress_dialog.details_frame:
            details_index = i
        if item.layout() and any(progress_dialog.btn_details == item.layout().itemAt(j).widget() for j in range(item.layout().count()) if item.layout().itemAt(j).widget()):
            btn_layout_index = i
            
    assert btn_layout_index != -1, "Button layout not found"
    assert details_index != -1, "Details frame not found"
    
    # We want btn_layout to be BEFORE details_frame
    assert btn_layout_index < details_index, f"Button layout (index {btn_layout_index}) should be before Details frame (index {details_index})"
