import pytest
from core.bridge import DownloadBridge
from main import MainWindow

def test_download_bridge_initialization(qapp):
    bridge = DownloadBridge()
    assert bridge.downloads == []
    assert bridge.statusMessage == "Ready"

def test_download_bridge_slots(qapp):
    window = MainWindow(start_ipc=False)
    initial_count = len(window.get_qml_downloads_data())
    bridge = DownloadBridge(main_window=window)
    
    signal_received = False
    def on_changed():
        nonlocal signal_received
        signal_received = True

    bridge.downloadsChanged.connect(on_changed)
    bridge.addDownload("http://example.com/file.zip", "General", "/tmp")
    assert signal_received
    assert len(bridge.downloads) == initial_count + 1
    assert bridge.downloads[0]["filename"] == "file.zip"
    assert "B" in bridge.memoryUsage
    assert isinstance(bridge.aria2Running, bool)
    assert "B/s" in bridge.totalSpeed
    assert bridge.itemCount == initial_count + 1
