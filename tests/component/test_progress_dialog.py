"""Component tests for DownloadProgressDialog, including CSD mode sizing."""

import os
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from ui.dialogs.progress import DownloadProgressDialog
from ui.components.csd_titlebar import attach_csd, detach_csd


class MockWorker(QObject):
    log_signal = pyqtSignal(str)
    main_bar_signal = pyqtSignal(int, int)
    main_progress_signal = pyqtSignal(int, tuple)
    finished_signal = pyqtSignal(int, str)
    init_segments_signal = pyqtSignal(int)
    segment_update_signal = pyqtSignal(int, int, int, int, str)
    url = "https://mirror.del.albony.in/videolan-ftp/vlc/3.0.24/win64/vlc-3.0.24-win64.exe"
    filename = "vlc-3.0.24-win64.exe"
    target_path = "/tmp/vlc-3.0.24-win64.exe"
    total_bytes = 44 * 1024 * 1024
    row_index = 0

    def format_bytes(self, b, precision=2, pad=False):
        return f"{b} B"

    def isRunning(self):
        return False

    def start(self):
        pass


class TestDownloadProgressDialog:
    def test_native_collapsed_and_expanded_size(self, qapp):
        worker = MockWorker()
        dlg = DownloadProgressDialog(worker)

        # In native mode, base height is 236
        assert dlg.width() == 520
        assert dlg.height() == 236
        assert not dlg.is_expanded

        # Expand details
        dlg.btn_details.click()
        assert dlg.is_expanded
        assert dlg.height() == 465

        # Collapse details
        dlg.btn_details.click()
        assert not dlg.is_expanded
        assert dlg.height() == 236
        dlg.close()

    def test_csd_mode_collapsed_and_expanded_size(self, qapp):
        worker = MockWorker()
        dlg = DownloadProgressDialog(worker)

        # Attach CSD (46px headerbar)
        attach_csd(dlg, is_dark=True, mode="Dark")

        # In CSD mode, collapsed height must be 236 + 46 = 282 so content is not cramped
        assert dlg.height() == 282
        assert not dlg.is_expanded

        # Expand details: 236 + 229 + 46 = 511
        dlg.btn_details.click()
        assert dlg.is_expanded
        assert dlg.height() == 511

        # Collapse details: returns to 282
        dlg.btn_details.click()
        assert not dlg.is_expanded
        assert dlg.height() == 282

        # Detach CSD: returns to native 236
        detach_csd(dlg)
        assert dlg.height() == 236
        dlg.close()

    def test_csd_show_event_integration(self, qapp, monkeypatch):
        from core.services.theme_service import apply_titlebar_theme
        monkeypatch.setenv("BDM_FORCE_CSD", "1")

        worker = MockWorker()
        dlg = DownloadProgressDialog(worker)
        apply_titlebar_theme("Light", window=dlg)
        dlg.show()
        qapp.processEvents()

        # Check that after show, CSD is attached and height is 282
        assert dlg.height() == 282
        assert hasattr(dlg, "_csd_titlebar") and dlg._csd_titlebar is not None
        assert dlg._csd_titlebar.height() == 46
        assert dlg._csd_content_widget.height() == 236

        # Toggle details
        dlg.btn_details.click()
        qapp.processEvents()
        assert dlg.height() == 511

        dlg.btn_details.click()
        qapp.processEvents()
        assert dlg.height() == 282

        dlg.close()
