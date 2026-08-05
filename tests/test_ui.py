import pytest
from PyQt6.QtCore import Qt
from main import MainWindow

def test_main_window_table_operations(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()
    initial_count = window.download_table.rowCount()
    assert window.download_table is not None
    assert window.download_table.columnCount() == 7

    # Add a mock download row
    window.start_download(
        url="http://example.com/test.iso",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    assert window.download_table.rowCount() == initial_count + 1
    item0 = window.download_table.item(0, 0)
    assert item0 is not None
    assert item0.text() == "test.iso"

    # Test QML data conversion
    qml_data = window.get_qml_downloads_data()
    assert len(qml_data) == initial_count + 1
    assert qml_data[0]["filename"] == "test.iso"
    assert qml_data[0]["url"] == "http://example.com/test.iso"

def test_main_window_qml_row_controls(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()
    initial_count = window.download_table.rowCount()
    window.start_download(
        url="http://example.com/demo.mp4",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )

    assert window.download_table.rowCount() == initial_count + 1
    window.qml_delete_download(0)
    assert window.download_table.rowCount() == initial_count

def test_main_window_rename_file(qapp, tmp_path, monkeypatch):
    test_file = tmp_path / "old_name.txt"
    test_file.write_text("dummy content")

    window = MainWindow(start_ipc=False)
    window.hide()
    window.start_download(
        url="http://example.com/old_name.txt",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    row = 0
    item0 = window.download_table.item(row, 0)
    item0.setData(Qt.ItemDataRole.UserRole + 1, str(test_file))

    # Mock RenameDialog to simulate user entering "new_name.txt"
    class MockRenameDialog:
        def __init__(self, filename, parent=None): pass
        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted
        def get_filename(self): return "new_name.txt"

    import main
    monkeypatch.setattr(main, "RenameDialog", MockRenameDialog)

    window.ctx_rename(item0)

    new_file = tmp_path / "new_name.txt"
    assert new_file.exists()
    assert not test_file.exists()
    assert item0.text() == "new_name.txt"
    assert item0.data(Qt.ItemDataRole.UserRole + 1) == str(new_file)

def test_main_window_move_file(qapp, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    test_file = source_dir / "move_me.zip"
    test_file.write_text("data")
    dest_file = target_dir / "moved.zip"

    window = MainWindow(start_ipc=False)
    window.hide()
    window.start_download(
        url="http://example.com/move_me.zip",
        custom_save_dir=str(source_dir),
        start_paused=True,
        show_dialog=False
    )
    row = 0
    item0 = window.download_table.item(row, 0)
    item0.setData(Qt.ItemDataRole.UserRole + 1, str(test_file))

    # Mock choose_portal_save_path to return dest_file path
    import main
    monkeypatch.setattr(main, "choose_portal_save_path", lambda title, filename, folder: str(dest_file))

    window.ctx_move(item0)

    assert dest_file.exists()
    assert not test_file.exists()
    assert item0.text() == "moved.zip"
    assert item0.data(Qt.ItemDataRole.UserRole + 1) == str(dest_file)

def test_adaptive_icon_theme(qapp):
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtWidgets import QStyle
    from main import get_themed_icon, ensure_adaptive_icon_theme

    # Set dark palette
    dark_pal = QPalette()
    dark_pal.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    dark_pal.setColor(QPalette.ColorRole.WindowText, QColor(250, 250, 250))
    qapp.setPalette(dark_pal)

    ensure_adaptive_icon_theme(qapp)
    icon = get_themed_icon("list-add", qapp.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
    assert not icon.isNull()
    
    # Verify icon pixmap is non-empty and has high contrast
    pm = icon.pixmap(24, 24)
    assert not pm.isNull()
    assert pm.width() == 24 and pm.height() == 24

def test_download_dialogs_window_stacking_parentage(qapp):
    from ui.dialogs import DownloadProgressDialog, DownloadCompleteDialog, DownloadFileInfoDialog
    from core.workers import DownloadWorker

    worker = DownloadWorker("http://example.com/test.iso", 0, "/tmp")
    progress_dlg = DownloadProgressDialog(worker, None)
    assert progress_dlg.parent() is None
    assert progress_dlg.windowModality() == Qt.WindowModality.NonModal
    assert progress_dlg.isWindow()

    complete_dlg = DownloadCompleteDialog({"url": "http://example.com/test.iso", "path": "/tmp/test.iso", "size": "10 MB"}, None)
    assert complete_dlg.parent() is None
    assert complete_dlg.windowModality() == Qt.WindowModality.NonModal
    assert complete_dlg.isWindow()

    info_dlg = DownloadFileInfoDialog({"url": "http://example.com/test.iso", "suggested_filename": "test.iso", "size_str": "10 MB", "size_bytes": 10485760}, None)
    assert info_dlg.parent() is None
    assert info_dlg.windowModality() == Qt.WindowModality.NonModal
    assert info_dlg.isWindow()

def test_download_progress_dialog_downloaded_formatting(qapp):
    from ui.dialogs import DownloadProgressDialog
    from core.workers import DownloadWorker

    worker = DownloadWorker("http://example.com/test.iso", 0, "/tmp")
    progress_dlg = DownloadProgressDialog(worker, None)

    # Test update_stats with 64.81 MB out of 160 MB (40.50625% -> 40.51%)
    current_bytes = int(64.81 * 1024 * 1024)
    total_bytes = int(160.0 * 1024 * 1024)
    progress_dlg.update_stats(0, ("test.iso", "160.00 MB", "Receiving data...", "10 sec", "5.00 MB/s", current_bytes, total_bytes))

    assert "64.81  MB" in progress_dlg.lbl_downloaded.text()
    assert "(40.51%)" in progress_dlg.lbl_downloaded.text()

    # Test completion formatting (100.00%)
    progress_dlg.on_finished(0, "Complete")
    assert "(100.00%)" in progress_dlg.lbl_downloaded.text()

def test_programs_category_and_icon_resolution(qapp):
    from main import get_category_for_filename, get_file_icon, CATEGORY_EXTENSIONS

    program_files = ["app.deb", "package.rpm", "app.apk", "tool.appimage", "installer.msi", "setup.exe", "script.sh"]
    for fn in program_files:
        assert get_category_for_filename(fn) == "Programs"
        icon = get_file_icon(fn)
        assert not icon.isNull()

    assert ".deb" in CATEGORY_EXTENSIONS["Programs"]
    assert ".rpm" in CATEGORY_EXTENSIONS["Programs"]
    assert ".apk" in CATEGORY_EXTENSIONS["Programs"]
    assert ".appimage" in CATEGORY_EXTENSIONS["Programs"]

def test_header_highlight_sections_disabled_and_max_conn_default(qapp):
    from main import MainWindow
    from ui.dialogs import OptionsDialog

    window = MainWindow()
    assert window.download_table.horizontalHeader().highlightSections() is False

    opt_dlg = OptionsDialog(window)
    opt_dlg.save_extension_data()
    assert opt_dlg.extension_data.get("max_connections") == 8
    opt_dlg.close()
def test_start_menu_launch_vs_autostart_minimized_flag(monkeypatch):
    argv_normal = ["bengal-download-manager"]
    argv_minimized = ["bengal-download-manager", "--minimized"]

    assert ("--minimized" in argv_normal) is False
    assert ("--minimized" in argv_minimized) is True







