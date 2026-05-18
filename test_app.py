import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Add src to path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from main import MainWindow
from core.utils import get_config_dir, get_data_dir

@pytest.fixture
def app(qtbot):
    """Fixture to initialize the main window."""
    window = MainWindow()
    # Clear any loaded data to ensure tests start from 0
    while window.download_table.rowCount() > 0:
        window.download_table.removeRow(0)
    qtbot.addWidget(window)
    return window

def test_window_title(app):
    """Verify the main window title."""
    assert app.windowTitle() == "Bengal Download Manager"

def test_initial_ui_state(app):
    """Verify initial UI states."""
    assert app.download_table.rowCount() == 0
    # Check if some actions are disabled by default
    assert not app.action_resume.isEnabled()
    assert not app.action_stop.isEnabled()

def test_add_url_dialog_opens(app, qtbot):
    """Verify the Add URL dialog opens and returns a URL."""
    from ui.dialogs import AddUrlDialog
    
    dialog = AddUrlDialog(app)
    qtbot.addWidget(dialog)
    
    # Simulate entering a URL
    test_url = "http://example.com/file.zip"
    dialog.url_input.setText(test_url)
    assert dialog.get_url() == test_url

def test_config_paths():
    """Verify that configuration and data paths are reachable."""
    config_dir = get_config_dir()
    data_dir = get_data_dir()
    
    assert os.path.exists(config_dir)
    assert os.path.exists(data_dir)

def test_start_download_logic(app):
    """Verify the start_download method correctly inserts a row."""
    test_url = "http://speedtest.tele2.net/1MB.zip"
    
    # Use start_paused=True to avoid spawning actual threads during test
    item = app.start_download(
        url=test_url,
        custom_filename="test_file.zip",
        start_paused=True,
        show_dialog=False
    )
    
    assert app.download_table.rowCount() == 1
    assert app.download_table.item(0, 0).text() == "test_file.zip"
    assert app.download_table.item(0, 2).text() == "Paused"

if __name__ == "__main__":
    # If run directly, show instructions
    print("Test script created. To run tests, please install dev dependencies:")
    print("pip install -r requirements-dev.txt")
    print("\nThen run:")
    print("PYTHONPATH=src pytest test_app.py")
