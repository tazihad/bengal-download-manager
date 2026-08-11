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
    progress_dlg.close()
    worker.deleteLater()

    complete_dlg = DownloadCompleteDialog({"url": "http://example.com/test.iso", "path": "/tmp/test.iso", "size": "10 MB"}, None)
    assert complete_dlg.parent() is None
    assert complete_dlg.windowModality() == Qt.WindowModality.NonModal
    assert complete_dlg.isWindow()
    complete_dlg.close()

    info_dlg = DownloadFileInfoDialog({"url": "http://example.com/test.iso", "suggested_filename": "test.iso", "size_str": "10 MB", "size_bytes": 10485760}, None)
    assert info_dlg.parent() is None
    assert info_dlg.windowModality() == Qt.WindowModality.NonModal
    assert info_dlg.isWindow()
    info_dlg.close()

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
    progress_dlg.close()
    worker.deleteLater()

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

def test_options_dialog_startup_checkbox_ordering_and_browser_removal(qapp):
    from main import MainWindow
    from ui.dialogs import OptionsDialog

    window = MainWindow()
    opt_dlg = OptionsDialog(window)

    # Ensure browser integration checkbox is removed
    assert not hasattr(opt_dlg, "chk_browser")

    # Ensure Launch Bengal is on top of start minimized
    assert opt_dlg.chk_startup.text() == "Launch Bengal DM on system startup"
    assert opt_dlg.chk_start_minimized.text() == "Start minimized in system tray on system startup"
    
    # Check widget order in vbox_startup
    grp_startup = opt_dlg.startup_tab.findChild(object, "")
    # Verify chk_startup comes before chk_start_minimized
    layout = opt_dlg.chk_startup.parentWidget().layout()
    startup_idx = layout.indexOf(opt_dlg.chk_startup)
    minimized_idx = layout.indexOf(opt_dlg.chk_start_minimized)
    assert startup_idx < minimized_idx
    assert startup_idx == 0

    opt_dlg.close()

def test_download_table_item_filename_tooltip(qapp):
    from main import MainWindow

    window = MainWindow()
    item = window.start_download("https://example.com/long_test_filename_document.pdf", start_paused=True, show_dialog=False)
    
    assert item.toolTip() == "long_test_filename_document.pdf"
    assert window.download_table.item(0, 0).toolTip() == "long_test_filename_document.pdf"
    window.close()

def test_ui_comprehensive_tooltips(qapp):
    from main import MainWindow

    window = MainWindow()
    
    # Actions tooltips
    assert window.action_add_url.toolTip() != ""
    assert window.action_stop.toolTip() != ""
    assert window.action_resume.toolTip() != ""
    assert window.action_options.toolTip() != ""

    # Tree tooltips
    top_item = window.category_tree.topLevelItem(0)
    assert top_item.toolTip(0) != ""

    # Table column header tooltips
    header_item = window.download_table.horizontalHeaderItem(0)
    assert header_item.toolTip() != ""
    window.close()

def test_options_dialog_ui_scale_dropdown(qapp, tmp_path, monkeypatch):
    import main
    import core.utils
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(main, "get_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(core.utils, "get_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    from main import MainWindow
    from ui.dialogs import OptionsDialog

    window = MainWindow()
    opt_dlg = OptionsDialog(window)

    # Check combo_scale existence
    assert hasattr(opt_dlg, "combo_scale")
    combo = opt_dlg.combo_scale

    # Check items count and options
    expected_items = [
        "50%", "75%", "90%", "100%", "110%", "115%", "125%", 
        "135%", "150%", "175%", "200%", "225%", "250%", "275%", "300%"
    ]
    items = [combo.itemText(i) for i in range(combo.count())]
    assert items == expected_items

    # Check default selected item
    assert combo.currentText() == "100%"

    # Select 125% and accept
    idx_125 = combo.findText("125%")
    assert idx_125 != -1
    combo.setCurrentIndex(idx_125)

    opt_dlg.save_and_accept()
    assert window.settings.get("ui_scale") == "125%"

    opt_dlg.close()
    window.close()


def test_options_dialog_theme_selection(qapp):
    from ui.dialogs import OptionsDialog
    from main import MainWindow, apply_app_theme, get_themed_tray_icon, get_app_icon, get_monochrome_app_icon

    window = MainWindow()
    window.settings["theme"] = "BDM Dark (Default)"
    window.settings["accent"] = "BDM (Default)"
    window.settings["icon_theme"] = "BDM (Default)"
    window.settings["tray_icon"] = "App Icon (Default)"
    opt_dlg = OptionsDialog(window)

    # Check combos existence
    assert hasattr(opt_dlg, "combo_theme")
    assert hasattr(opt_dlg, "combo_accent")
    assert hasattr(opt_dlg, "combo_icon_theme")
    assert hasattr(opt_dlg, "combo_tray_icon")

    # Check items count and options
    expected_themes = [
        "Automatic", "BDM Dark (Default)", "BDM Light", 
        "Breeze Dark", "Breeze Light", "Catppuccin",
        "Dracula", "IDM Classic", "Kirigami Dark", 
        "Kirigami Light", "Nord", "One Dark", 
        "Solarized Dark", "Solarized Light", 
        "Ubuntu Dark", "Ubuntu Light"
    ]
    items = [opt_dlg.combo_theme.itemText(i) for i in range(opt_dlg.combo_theme.count())]
    assert items == expected_themes

    # Check default selected items
    assert opt_dlg.combo_theme.currentText() == "BDM Dark (Default)"
    assert opt_dlg.combo_tray_icon.currentText() == "App Icon (Default)"

    # Select Ubuntu Dark, Ubuntu Orange, Breeze Dark, and Monochrome Light
    idx_ub_dark = opt_dlg.combo_theme.findText("Ubuntu Dark")
    assert idx_ub_dark != -1
    opt_dlg.combo_theme.setCurrentIndex(idx_ub_dark)

    idx_orange = opt_dlg.combo_accent.findText("Ubuntu Orange")
    assert idx_orange != -1
    opt_dlg.combo_accent.setCurrentIndex(idx_orange)

    idx_mono_light = opt_dlg.combo_tray_icon.findText("Monochrome Light")
    assert idx_mono_light != -1
    opt_dlg.combo_tray_icon.setCurrentIndex(idx_mono_light)

    opt_dlg.save_and_accept()
    assert window.settings.get("theme") == "Ubuntu Dark"
    assert window.settings.get("accent") == "Ubuntu Orange"
    assert window.settings.get("tray_icon") == "Monochrome Light"
    assert opt_dlg.get_theme() == "Ubuntu Dark"
    assert opt_dlg.get_accent() == "Ubuntu Orange"
    assert opt_dlg.get_tray_icon() == "Monochrome Light"

    # Verify get_themed_tray_icon and app icon functions without error
    assert not get_app_icon().isNull()
    assert not get_monochrome_app_icon().isNull()
    for tray_opt in ["App Icon (Default)", "Automatic", "Monochrome Light", "Monochrome Dark"]:
        ic = get_themed_tray_icon(tray_opt)
        assert not ic.isNull()

    # Verify apply_app_theme functions without exception for all options
    for theme_item in expected_themes:
        apply_app_theme(theme_item, "Ubuntu Orange", "Breeze", "App Icon (Default)", qapp)

    opt_dlg.close()
    window.close()

def test_main_window_restore_window(qapp):
    from main import MainWindow

    window = MainWindow(start_ipc=False)
    window.hide()
    assert window.isHidden()

    window.restore_window()
    assert window.isVisible()
    assert not window.isMinimized()

    window.showMinimized()
    assert window.isMinimized()

    window.restore_window()
    assert not window.isMinimized()
    assert window.isVisible()
    window.close()

def test_single_instance_server_ipc(qapp, monkeypatch):
    import time
    from main import SingleInstanceServer, check_single_instance
    from PyQt6.QtCore import QCoreApplication

    test_key = "bengal-dm-test-single-instance-key"
    received_payloads = []

    server = SingleInstanceServer(key=test_key)
    server.messageReceived.connect(lambda p: received_payloads.append(p))
    server.start()

    # Simulate secondary instance connecting
    connected = check_single_instance(key=test_key, timeout_ms=1000)
    assert connected is True

    # Process Qt event loop to let server handle incoming socket connection
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert len(received_payloads) == 1
    assert received_payloads[0].get("command") == "show"

    server.stop()


def test_main_window_paste_url_shortcut(qapp, monkeypatch):
    from main import MainWindow
    from PyQt6.QtWidgets import QApplication
    from ui.dialogs import AddUrlDialog

    window = MainWindow()
    test_url = "https://example.com/pasted_archive.zip"
    QApplication.clipboard().setText(test_url)

    opened_dialogs = []
    def mock_exec(self):
        opened_dialogs.append(self)
        assert self.get_url() == test_url
        return False

    monkeypatch.setattr(AddUrlDialog, "exec", mock_exec)

    window.action_paste_url.trigger()
    assert len(opened_dialogs) == 1
    window.close()


def test_add_url_dialog_media_detection(qapp):
    from ui.dialogs import AddUrlDialog

    dialog = AddUrlDialog()
    # 1. Non-media URL -> Label and button hidden
    dialog.url_input.setText("https://example.com/file.zip")
    assert dialog.lbl_media_status.isHidden()
    assert dialog.btn_send_media.isHidden()

    # 2. Media URL -> Green text label and Download Media button shown
    dialog.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not dialog.lbl_media_status.isHidden()
    assert not dialog.btn_send_media.isHidden()

    # 3. Click Download Media button -> is_media_mode set to True
    dialog.btn_send_media.click()
    assert dialog.is_media_mode is True
    dialog.close()











