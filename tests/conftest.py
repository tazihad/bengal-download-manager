import sys
import os
import pytest

# Enforce offscreen Qt rendering to save CPU/GPU/RAM resources on older systems
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Mute noisy Qt QPA debug outputs
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false"

# Ensure 'src' is in sys.path for test discovery
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import tempfile
_test_temp_dir = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = os.path.join(_test_temp_dir.name, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_test_temp_dir.name, "cache")
os.environ["XDG_DATA_HOME"] = os.path.join(_test_temp_dir.name, "data")

from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    yield app
    app.processEvents()
    app.sendPostedEvents()
