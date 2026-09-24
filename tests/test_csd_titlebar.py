"""
Tests for Client-Side Decoration (CSD) titlebar component and GNOME custom titlebar theme.
"""

from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from ui.components.csd_titlebar import CsdTitleBar, attach_csd, detach_csd
from ui.dialogs.options import OptionsDialog
from ui.dialogs.batch_download import BatchDownloadDialog


def test_csd_titlebar_flat_corners(qapp):
    """Verify CSD titlebar has 0px top-border radius to eliminate dark corner cutouts."""
    win = QMainWindow()
    titlebar = CsdTitleBar(win, is_dark=True)
    assert "border-top-left-radius: 0px;" in titlebar.styleSheet()
    assert "border-top-right-radius: 0px;" in titlebar.styleSheet()

    titlebar.apply_style(is_dark=False)
    assert "border-top-left-radius: 0px;" in titlebar.styleSheet()
    assert "border-top-right-radius: 0px;" in titlebar.styleSheet()


def test_attach_csd_main_window(qapp):
    """Verify CSD attaches to QMainWindow with full-width container and 0 margins."""
    win = QMainWindow()
    win.setWindowTitle("Main Window")
    attach_csd(win, is_dark=True)

    assert getattr(win, "_csd_titlebar", None) is not None
    assert getattr(win, "_csd_container", None) is not None
    assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint)

    detach_csd(win)
    assert getattr(win, "_csd_titlebar", None) is None
    assert getattr(win, "_csd_container", None) is None
    assert not bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint)


def test_attach_csd_dialog_full_width_wrapping(qapp):
    """Verify CSD wraps dialog contents so titlebar spans full width with 0 margins."""
    dlg = QDialog()
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(15, 15, 15, 15)
    lay.setSpacing(10)
    lbl = QLabel("Content", dlg)
    btn = QPushButton("OK", dlg)
    lay.addWidget(lbl)
    lay.addWidget(btn)

    attach_csd(dlg, is_dark=False)

    assert getattr(dlg, "_csd_titlebar", None) is not None
    assert getattr(dlg, "_csd_content_widget", None) is not None

    # Dialog root layout should have 0 margins so titlebar spans 100% full window width
    m = dlg.layout().contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (0, 0, 0, 0)
    assert dlg.layout().spacing() == 0

    # Titlebar is the very first child in root layout
    assert dlg.layout().indexOf(dlg._csd_titlebar) == 0
    assert dlg.layout().indexOf(dlg._csd_content_widget) == 1

    # Content container preserves original margins (15, 15, 15, 15) and items
    cw_m = dlg._csd_content_widget.layout().contentsMargins()
    assert (cw_m.left(), cw_m.top(), cw_m.right(), cw_m.bottom()) == (15, 15, 15, 15)
    assert dlg._csd_content_widget.layout().spacing() == 10
    assert dlg._csd_content_widget.layout().count() == 2

    # Detach and verify restoration
    detach_csd(dlg)
    assert getattr(dlg, "_csd_titlebar", None) is None
    assert getattr(dlg, "_csd_content_widget", None) is None

    restored_m = dlg.layout().contentsMargins()
    assert (restored_m.left(), restored_m.top(), restored_m.right(), restored_m.bottom()) == (15, 15, 15, 15)
    assert dlg.layout().spacing() == 10
    assert dlg.layout().count() == 2


def test_attach_csd_options_and_batch_dialogs(qapp):
    """Verify CSD attachment on real OptionsDialog and BatchDownloadDialog."""
    opt = OptionsDialog()
    attach_csd(opt, is_dark=True)
    assert getattr(opt, "_csd_titlebar", None) is not None
    assert opt.layout().indexOf(opt._csd_titlebar) == 0
    m_opt = opt.layout().contentsMargins()
    assert (m_opt.left(), m_opt.top(), m_opt.right(), m_opt.bottom()) == (0, 0, 0, 0)

    batch = BatchDownloadDialog(urls_or_items=[{"url": "https://example.com/file.zip"}])
    attach_csd(batch, is_dark=False)
    assert getattr(batch, "_csd_titlebar", None) is not None
    assert batch.layout().indexOf(batch._csd_titlebar) == 0
    m_batch = batch.layout().contentsMargins()
    assert (m_batch.left(), m_batch.top(), m_batch.right(), m_batch.bottom()) == (0, 0, 0, 0)


def test_download_progress_title_formatting(qapp):
    """Verify progress dialog formats long filenames with clean middle elision."""
    class DummyWorker:
        def __init__(self, fn):
            self.filename = fn
            self.url = "http://example.com/" + fn

    from ui.dialogs.progress import DownloadProgressDialog

    # Short filename
    w1 = DummyWorker("sample.mp4")
    dlg1 = DownloadProgressDialog.__new__(DownloadProgressDialog)
    dlg1.worker = w1
    assert dlg1._format_window_title() == "sample.mp4"
    assert dlg1._format_window_title("45%") == "45% - sample.mp4"

    # Very long filename
    w2 = DummyWorker("videoplayback_1080p_60fps_hdr_audio_ultra_high_quality.mp4")
    dlg2 = DownloadProgressDialog.__new__(DownloadProgressDialog)
    dlg2.worker = w2
    formatted = dlg2._format_window_title("75%")
    assert len(formatted) <= 45
    assert formatted.startswith("75% - videoplayback_1080p_")
    assert formatted.endswith(".mp4")
    assert "..." in formatted
