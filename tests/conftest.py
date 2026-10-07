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
from PyQt6.QtCore import QEvent


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    yield app
    app.processEvents()
    app.sendPostedEvents()


@pytest.fixture(autouse=True)
def _flush_deferred_deletes(qapp):
    """Process pending deleteLater() calls after every test.

    Without this, widgets created by dialogs/windows accumulate in
    QApplication.allWidgets() across tests, making app.setStyleSheet()
    (which re-polishes every live widget) progressively slower and
    eventually appearing to hang the suite.
    """
    yield
    flush_deferred_deletes(qapp)


def flush_deferred_deletes(app):
    import gc
    for w in app.topLevelWidgets():
        try:
            if hasattr(w, "listener_thread") and w.listener_thread:
                w.listener_thread.stop(timeout_ms=500)
                w.listener_thread = None
        except Exception:
            pass
    gc.collect()
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()


@pytest.fixture(scope="session")
def destroy_widget(qapp):
    """Return a callable that closes and fully destroys a Qt widget."""
    def _destroy(widget):
        try:
            if hasattr(widget, "is_quitting"):
                widget.is_quitting = True
            widget.close()
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass
        flush_deferred_deletes(qapp)
    return _destroy
