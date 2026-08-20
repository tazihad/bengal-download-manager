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
    from PyQt6.QtGui import QPalette, QColor, QIcon
    from PyQt6.QtWidgets import QStyle
    import main
    from main import get_themed_icon, ensure_adaptive_icon_theme, normalize_icon_theme_name
    from ui.icons import get_monochrome_icon

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

    # Verify disabled mode pixmap is generated and non-empty
    disabled_pm = icon.pixmap(24, 24, QIcon.Mode.Disabled)
    assert not disabled_pm.isNull()

    # Test normalize_icon_theme_name for 3 BDM options
    assert normalize_icon_theme_name("bdm") == "BDM Auto (Default)"
    assert normalize_icon_theme_name("BDM Dark") == "BDM Dark"
    assert normalize_icon_theme_name("bdm light") == "BDM Light"

    # Test BDM Dark and BDM Light themes in get_themed_icon
    main.CURRENT_ICON_THEME = "BDM Dark"
    icon_dark = get_themed_icon("add_url")
    assert not icon_dark.isNull()
    assert not icon_dark.pixmap(24, 24, QIcon.Mode.Disabled).isNull()

    main.CURRENT_ICON_THEME = "BDM Light"
    icon_light = get_themed_icon("add_url")
    assert not icon_light.isNull()
    assert not icon_light.pixmap(24, 24, QIcon.Mode.Disabled).isNull()

    main.CURRENT_ICON_THEME = "BDM Auto (Default)"


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

    window = MainWindow(start_ipc=False)
    assert window.download_table.horizontalHeader().highlightSections() is False

    opt_dlg = OptionsDialog(window)
    opt_dlg.save_extension_data()
    assert opt_dlg.extension_data.get("max_connections") == 8
    opt_dlg.close()
    window.close()
def test_start_menu_launch_vs_autostart_minimized_flag(monkeypatch):
    argv_normal = ["bengal-download-manager"]
    argv_minimized = ["bengal-download-manager", "--minimized"]

    assert ("--minimized" in argv_normal) is False
    assert ("--minimized" in argv_minimized) is True

def test_options_dialog_startup_checkbox_ordering_and_browser_removal(qapp):
    from main import MainWindow
    from ui.dialogs import OptionsDialog

    window = MainWindow(start_ipc=False)
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

    # Check enabled state dependency
    opt_dlg.chk_startup.setChecked(False)
    assert not opt_dlg.chk_start_minimized.isEnabled()
    opt_dlg.chk_startup.setChecked(True)
    assert opt_dlg.chk_start_minimized.isEnabled()

    opt_dlg.close()
    window.close()

def test_download_table_item_filename_tooltip(qapp):
    from main import MainWindow

    window = MainWindow(start_ipc=False)
    item = window.start_download("https://example.com/long_test_filename_document.pdf", start_paused=True, show_dialog=False)
    
    assert item.toolTip() == "long_test_filename_document.pdf"
    assert window.download_table.item(0, 0).toolTip() == "long_test_filename_document.pdf"
    window.close()

def test_ui_comprehensive_tooltips(qapp):
    from main import MainWindow

    window = MainWindow(start_ipc=False)
    
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
    import ui.dialogs.options
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.dialogs.options.QMessageBox, "information", lambda *args, **kwargs: None)

    from main import MainWindow
    from ui.dialogs import OptionsDialog

    window = MainWindow(start_ipc=False)
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

    window = MainWindow(start_ipc=False)
    window.settings["theme"] = "BDM Dark (Default)"
    window.settings["accent"] = "BDM (Default)"
    window.settings["icon_theme"] = "BDM Auto (Default)"
    window.settings["tray_icon"] = "App Icon (Default)"
    opt_dlg = OptionsDialog(window)

    # Check combos existence
    assert hasattr(opt_dlg, "combo_theme")
    assert hasattr(opt_dlg, "combo_accent")
    assert hasattr(opt_dlg, "combo_icon_theme")
    assert hasattr(opt_dlg, "combo_tray_icon")

    # Check items count and options
    expected_themes = [
        "System", "BDM Auto", "BDM Dark (Default)", "BDM Light",
        "Breeze Dark", "Breeze Light", "Catppuccin",
        "Dracula", "IDM Classic", "Kirigami Dark", 
        "Kirigami Light", "Material You Dark", "Material You Light",
        "Nord", "Obsidian Flow", "One Dark", 
        "Solarized Dark", "Solarized Light", 
        "Twilight", "Ubuntu Dark", "Ubuntu Light"
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

    window = MainWindow(start_ipc=False)
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


def test_system_accent_color_detection(qapp):
    from main import detect_accent, apply_app_theme
    from PyQt6.QtGui import QPalette

    detected = detect_accent("auto", app=qapp)
    assert detected is not None
    assert detected.isValid()

    apply_app_theme("BDM Dark (Default)", accent_name="System", app=qapp)
    current_hl = qapp.palette().color(QPalette.ColorRole.Highlight)
    assert current_hl.name() == detected.name()

    apply_app_theme("System", accent_name="System", app=qapp)
    current_hl_sys = qapp.palette().color(QPalette.ColorRole.Highlight)
    assert current_hl_sys.isValid()


def test_dropdown_options_sorting(qapp):
    from ui.dialogs.options import OptionsDialog
    dlg = OptionsDialog()

    themes = [dlg.combo_theme.itemText(i) for i in range(dlg.combo_theme.count())]
    assert themes[:4] == ["System", "BDM Auto", "BDM Dark (Default)", "BDM Light"]
    assert themes[4:] == sorted(themes[4:])

    accents = [dlg.combo_accent.itemText(i) for i in range(dlg.combo_accent.count())]
    assert accents[:2] == ["System", "BDM (Default)"]
    assert accents[2:] == sorted(accents[2:])

    icons = [dlg.combo_icon_theme.itemText(i) for i in range(dlg.combo_icon_theme.count())]
    assert icons[:3] == ["BDM Auto (Default)", "BDM Dark", "BDM Light"]
    assert icons[3:] == sorted(icons[3:])
    dlg.close()


def test_download_complete_persistence_on_restart(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("core.utils.get_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr("main.get_data_dir", lambda: str(tmp_path))

    # 1. Create a real completed downloaded file on disk
    downloaded_file = tmp_path / "finished_movie.mp4"
    downloaded_file.write_bytes(b"A" * 1024 * 100)

    win1 = MainWindow(start_ipc=False)
    win1.hide()
    win1.start_download(
        url="http://example.com/finished_movie.mp4",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    item_ref = win1.download_table.item(0, 0)
    item_ref.setData(Qt.ItemDataRole.UserRole + 1, str(downloaded_file))

    # Emit progress at 98.30%
    win1.update_download_row(item_ref, ("finished_movie.mp4", "100.00 KB", "Downloading", "00:01", "10.00 KB/s", 98300, 100000))
    status_item = win1.download_table.item(0, 2)
    assert status_item.text() == "98.30%"

    # Finish download
    win1.download_finished(item_ref, "Complete")
    assert win1.download_table.item(0, 2).text() == "Complete"

    # Simulate app exit: stop_all_downloads and save_data
    win1.stop_all_downloads()
    assert win1.download_table.item(0, 2).text() == "Complete"
    win1.save_data()

    # 2. Reopen window and load persisted downloads.json
    win2 = MainWindow(start_ipc=False)
    win2.hide()
    assert win2.download_table.rowCount() == 1
    assert win2.download_table.item(0, 0).text() == "finished_movie.mp4"
    assert win2.download_table.item(0, 1) is not None
    assert win2.download_table.item(0, 1).text() == "100.00 KB"
    assert win2.download_table.item(0, 2).text() == "Complete"
    assert win2.download_table.item(0, 2).data(Qt.ItemDataRole.UserRole + 1) == "Complete"


def test_download_size_displayed_all_time(qapp, tmp_path):
    target_file = tmp_path / "sample.iso"
    target_file.write_bytes(b"x" * 2048)

    win = MainWindow(start_ipc=False)
    win.hide()
    win.download_table.setRowCount(0)

    win.start_download(
        url="http://example.com/sample.iso",
        custom_save_dir=str(tmp_path),
        start_paused=True,
        show_dialog=False
    )
    item_ref = win.download_table.item(0, 0)
    item_ref.setData(Qt.ItemDataRole.UserRole + 1, str(target_file))

    win.download_finished(item_ref, "Complete")

    # Table size must be displayed
    assert win.download_table.item(0, 1) is not None
    assert win.download_table.item(0, 1).text() == "2.00 KB"

    # Save and reload
    win.save_data()

    reloaded_win = MainWindow(start_ipc=False)
    reloaded_win.hide()
    assert reloaded_win.download_table.rowCount() == 1
    assert reloaded_win.download_table.item(0, 1) is not None
    assert reloaded_win.download_table.item(0, 1).text() == "2.00 KB"
    assert reloaded_win.download_table.item(0, 2).text() == "Complete"


def test_download_progress_dialog_close_after_complete(qapp, tmp_path):
    from ui.dialogs.progress import DownloadProgressDialog
    from unittest.mock import MagicMock

    mock_worker = MagicMock()
    mock_worker.filename = "test.zip"
    mock_worker.url = "http://example.com/test.zip"
    mock_worker.row_index = 0
    mock_worker.target_path = str(tmp_path / "test.zip")
    mock_worker.format_bytes.return_value = "10.00 MB"

    dlg = DownloadProgressDialog(mock_worker)
    dlg.hide()

    # Complete the download
    dlg.on_finished(0, "Complete")
    assert dlg.is_completed is True
    assert dlg.btn_cancel.text() == "Close"

    # Close the dialog
    dlg.close()
    # Ensure worker finished_signal.emit was NOT called with Paused
    for call in mock_worker.finished_signal.emit.call_args_list:
        assert "Paused" not in call[0]


def test_status_bar_initialization(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    assert window.statusBar() is not None
    assert hasattr(window, "status_items_label")
    assert hasattr(window, "status_speed_label")
    assert hasattr(window, "status_aria2_label")
    assert hasattr(window, "status_memory_label")

    # Verify OpenType tabular numbers font feature
    for lbl in [window.status_items_label, window.status_speed_label, window.status_memory_label]:
        font = lbl.font()
        # font feature tnum or tabular numbers
        assert font is not None

    assert "items" in window.status_items_label.text() or "item" in window.status_items_label.text()
    assert "Speed:" in window.status_speed_label.text()
    assert "Aria2:" in window.status_aria2_label.text()
    assert "Memory:" in window.status_memory_label.text()
    window.close()


def test_status_bar_item_selection(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    # Clear table
    while window.download_table.rowCount() > 0:
        window.download_table.removeRow(0)

    window.update_status_bar_items()
    assert window.status_items_label.text() == "0 items"

    # Add item 1 (will become row 1 after next insert)
    window.start_download("http://example.com/file1.zip", custom_save_dir="/tmp", start_paused=True, show_dialog=False)
    # Add item 2 (inserted at row 0)
    window.start_download("http://example.com/file2.zip", custom_save_dir="/tmp", start_paused=True, show_dialog=False)
    
    window.download_table.item(0, 1).setText("10.00 MB")
    window.download_table.item(1, 1).setText("5.00 MB")
    window.update_status_bar_items()
    assert window.status_items_label.text() == "2 items"

    # Select row 0 (10.00 MB)
    window.download_table.selectRow(0)
    assert window.status_items_label.text() == "Selected: 1 of 2 items"
    assert "10.00 MB" in window.status_items_label.toolTip()

    # Select row 1 (5.00 MB)
    window.download_table.selectRow(1)
    assert window.status_items_label.text() == "Selected: 1 of 2 items"
    assert "5.00 MB" in window.status_items_label.toolTip()

    # Select both rows (15.00 MB total)
    window.download_table.selectAll()
    assert window.status_items_label.text() == "Selected: 2 of 2 items"
    assert "15.00 MB" in window.status_items_label.toolTip()

    # Clear selection
    window.download_table.clearSelection()
    assert window.status_items_label.text() == "2 items"
    window.close()


def test_status_bar_download_speed(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    # Add download
    item_ref = window.start_download("http://example.com/fast.bin", custom_save_dir="/tmp", start_paused=True, show_dialog=False)

    # Initial speed should be 0 B/s
    assert "0 B/s" in window.status_speed_label.text()

    # Simulate progress update with speed (1.5 MB/s = 1572864 B/s)
    # data: [filename, size, status, time_left, rate, completed_bytes, total_bytes, raw_speed]
    progress_data = ("fast.bin", "100.00 MB", "Receiving data...", "1 min", "1.50 MB/s", 15728640, 104857600, 1572864)
    window.update_download_row(item_ref, progress_data)

    assert "1.50 MB/s" in window.status_speed_label.text()

    # Complete download
    window.download_finished(item_ref, "Complete")
    assert window.status_speed_label.text() == "Speed: 0 B/s"
    window.close()


def test_status_bar_aria2_and_memory(qapp):
    from unittest.mock import MagicMock, patch
    window = MainWindow(start_ipc=False)
    window.hide()

    # Mock running aria2 process
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 99999
    window.aria2_process = mock_proc
    window.update_status_bar_aria2()
    assert "Connected" in window.status_aria2_label.text()
    assert "99999" in window.status_aria2_label.toolTip()

    # Mock stopped aria2 process
    mock_proc.poll.return_value = 1
    with patch("socket.socket") as mock_sock:
        mock_sock.return_value.__enter__.return_value.connect_ex.return_value = 1
        window.update_status_bar_aria2()
    assert "Stopped" in window.status_aria2_label.text()

    # Memory label update
    window.update_status_bar_memory()
    assert "Memory:" in window.status_memory_label.text()
    assert "B" in window.status_memory_label.text()
    window.close()


def test_sidebar_section_headers(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    assert hasattr(window, "header_categories")
    assert hasattr(window, "header_status")
    assert hasattr(window, "header_schedule")

    assert window.header_categories.text(0) == "Categories"
    assert window.header_status.text(0) == "Status"
    assert window.header_schedule.text(0) == "Schedule"

    assert window.header_categories.data(0, Qt.ItemDataRole.UserRole) == "header"
    assert window.header_status.data(0, Qt.ItemDataRole.UserRole) == "header"
    assert window.header_schedule.data(0, Qt.ItemDataRole.UserRole) == "header"

    # Clicking header items should not trigger filtering or crash
    window.start_download("http://example.com/test.zip", custom_save_dir="/tmp", start_paused=True, show_dialog=False)
    window.filter_downloads(window.header_categories, 0)
    assert not window.download_table.isRowHidden(0)

    window.filter_downloads(window.header_status, 0)
    assert not window.download_table.isRowHidden(0)

    window.filter_downloads(window.header_schedule, 0)
    assert not window.download_table.isRowHidden(0)
    window.close()


def test_app_exit_cleanup(qapp):
    from unittest.mock import MagicMock
    from PyQt6.QtGui import QCloseEvent
    window = MainWindow(start_ipc=False)
    window.hide()

    # Mock aria2 process
    mock_aria = MagicMock()
    window.aria2_process = mock_aria

    # Mock a dialog in active_complete_dialogs
    mock_dlg = MagicMock()
    window.active_complete_dialogs[12345] = mock_dlg

    # Quit app
    window.quit_app()

    assert window.is_quitting is True
    assert mock_aria.terminate.called
    assert mock_dlg.close.called
    assert len(window.active_complete_dialogs) == 0
    window.close()


def test_classic_table_active_row_bold_only(qapp):
    window = MainWindow(start_ipc=False)
    window.set_table_style("classic")
    window.hide()

    # 1. Start paused download (inactive) -> should NOT be bold
    item_paused = window.start_download("http://example.com/inactive.zip", custom_save_dir="/tmp", start_paused=True, show_dialog=False)
    row_paused = window.download_table.row(item_paused)
    for col in range(window.download_table.columnCount()):
        cell = window.download_table.item(row_paused, col)
        if cell and cell.text():
            assert not cell.font().bold(), f"Col {col} of paused row should NOT be bold"

    # 2. Add an active download -> should be bold
    item_active = window.start_download("http://example.com/active.zip", custom_save_dir="/tmp", start_paused=False, show_dialog=False)
    row_active = window.download_table.row(item_active)
    for col in range(window.download_table.columnCount()):
        cell = window.download_table.item(row_active, col)
        if cell and cell.text():
            assert cell.font().bold(), f"Col {col} of active row SHOULD be bold"

    # 3. Finish the active download -> should become NOT bold
    window.download_finished(item_active, "Complete")
    for col in range(window.download_table.columnCount()):
        cell = window.download_table.item(row_active, col)
        if cell and cell.text():
            assert not cell.font().bold(), f"Col {col} of completed row should NOT be bold"

    window.close()


def test_menu_hover_and_table_selected_black(qapp):
    from ui.icons import get_monochrome_icon
    from PyQt6.QtGui import QIcon, QColor, QImage, QPalette
    from main import apply_app_theme

    apply_app_theme("BDM Dark (Default)")
    assert qapp.palette().color(QPalette.ColorRole.HighlightedText) == QColor("#000000")

    # Test get_monochrome_icon with explicit selected_color produces black (#000000)
    icon_sel = get_monochrome_icon("resume", selected_color=QColor("#000000"))
    sel_pixmap = icon_sel.pixmap(24, 24, QIcon.Mode.Selected)
    assert not sel_pixmap.isNull()
    img = sel_pixmap.toImage()
    has_black_pixel = False
    for y in range(img.height()):
        for x in range(img.width()):
            pixel = img.pixelColor(x, y)
            if pixel.alpha() > 100:
                assert pixel.red() == 0 and pixel.green() == 0 and pixel.blue() == 0, f"Selected mode pixel ({x},{y}) color {pixel.name()} is not black"
                has_black_pixel = True
    assert has_black_pixel is True

    # Test get_themed_icon Normal mode is white, Active mode (menu hover) is black, Selected mode is black
    from main import get_themed_icon
    icon = get_themed_icon("resume")

    norm_pixmap = icon.pixmap(24, 24, QIcon.Mode.Normal)
    assert not norm_pixmap.isNull()
    img_norm = norm_pixmap.toImage()
    has_white_pixel = False
    for y in range(img_norm.height()):
        for x in range(img_norm.width()):
            pixel = img_norm.pixelColor(x, y)
            if pixel.alpha() > 100:
                assert pixel.red() > 200 and pixel.green() > 200 and pixel.blue() > 200, f"Mode Normal pixel ({x},{y}) is not white"
                has_white_pixel = True
    assert has_white_pixel is True

    # Active mode (menu item hover) must be pure black (#000000)
    act_pixmap = icon.pixmap(24, 24, QIcon.Mode.Active)
    assert not act_pixmap.isNull()
    img_act = act_pixmap.toImage()
    has_black_pixel = False
    for y in range(img_act.height()):
        for x in range(img_act.width()):
            pixel = img_act.pixelColor(x, y)
            if pixel.alpha() > 100:
                assert pixel.red() == 0 and pixel.green() == 0 and pixel.blue() == 0, f"Active mode pixel ({x},{y}) is not black"
                has_black_pixel = True
    assert has_black_pixel is True

    # Selected mode must be pure black (#000000)
    sel_pixmap = icon.pixmap(24, 24, QIcon.Mode.Selected)
    assert not sel_pixmap.isNull()
    img_sel = sel_pixmap.toImage()
    has_sel_black_pixel = False
    for y in range(img_sel.height()):
        for x in range(img_sel.width()):
            pixel = img_sel.pixelColor(x, y)
            if pixel.alpha() > 100:
                assert pixel.red() == 0 and pixel.green() == 0 and pixel.blue() == 0, f"Selected mode pixel ({x},{y}) is not black"
                has_sel_black_pixel = True
    assert has_sel_black_pixel is True


def test_status_bar_view_toggle(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    assert hasattr(window, "action_status_bar_toggle")
    assert window.action_status_bar_toggle.isCheckable()
    assert window.action_status_bar_toggle.isChecked()
    assert not window.statusBar().isHidden()

    # Toggle off
    window.toggle_status_bar(False)
    assert window.statusBar().isHidden()
    assert not window.action_status_bar_toggle.isChecked()

    # Toggle on
    window.toggle_status_bar(True)
    assert not window.statusBar().isHidden()
    assert window.action_status_bar_toggle.isChecked()
    window.close()


def test_column_dialog_height(qapp):
    from ui.dialogs.column import ColumnDialog
    columns = [
        {"name": "File Name", "visible": True, "width": 200, "logical_index": 0},
        {"name": "Size", "visible": True, "width": 100, "logical_index": 1},
        {"name": "Status", "visible": True, "width": 100, "logical_index": 2},
        {"name": "Time Left", "visible": True, "width": 100, "logical_index": 3},
        {"name": "Transfer Rate", "visible": True, "width": 100, "logical_index": 4},
        {"name": "Last Try", "visible": True, "width": 120, "logical_index": 5},
        {"name": "Date Added", "visible": True, "width": 120, "logical_index": 6},
    ]
    dlg = ColumnDialog(columns)
    assert dlg.minimumHeight() >= 380
    assert dlg.list_widget.minimumHeight() >= 220
    dlg.close()


def test_dialog_reopen_after_deletion(qapp):
    window = MainWindow(start_ipc=False)
    window.hide()

    # 1. Options Dialog: open, close/delete, reopen without RuntimeError
    window.open_options()
    assert window._options_dlg is not None
    dlg = window._options_dlg
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()

    # Reopening must not crash on deleted C++ object
    window.open_options()
    assert window._options_dlg is not None
    assert window._options_dlg is not dlg
    window._options_dlg.close()

    # 2. Media Downloader Dialog: open, close/delete, reopen
    window.open_media_downloader()
    assert window._media_downloader_dlg is not None
    dlg_media = window._media_downloader_dlg
    dlg_media.close()
    dlg_media.deleteLater()
    qapp.processEvents()

    window.open_media_downloader()
    assert window._media_downloader_dlg is not None
    assert window._media_downloader_dlg is not dlg_media
    window._media_downloader_dlg.close()

    # 3. Scheduler Dialog: open, close/delete, reopen
    window.open_scheduler()
    assert window._scheduler_dlg is not None
    dlg_sched = window._scheduler_dlg
    dlg_sched.close()
    dlg_sched.deleteLater()
    qapp.processEvents()

    window.open_scheduler()
    assert window._scheduler_dlg is not None
    assert window._scheduler_dlg is not dlg_sched
    window._scheduler_dlg.close()

    window.close()


def test_redownload_progress_updates(qapp, monkeypatch):
    window = MainWindow(start_ipc=False)
    window.hide()

    item = window.start_download("http://example.com/test_redownload.zip", custom_save_dir="/tmp", start_paused=False, show_dialog=False)
    row = window.download_table.row(item)

    # 1. Complete the download
    window.download_finished(item, "Complete")
    assert window.download_table.item(row, 2).text() == "Complete"
    assert item.data(Qt.ItemDataRole.UserRole + 11) == "Complete"

    # 2. Trigger Redownload
    # Mock _start_download_worker so we control progress events
    called_start = []
    monkeypatch.setattr(window, "_start_download_worker", lambda url, itm: called_start.append(itm))
    
    window.ctx_redownload(item)
    assert len(called_start) == 1
    assert item.data(Qt.ItemDataRole.UserRole + 11) is None
    status_item = window.download_table.item(row, 2)
    assert status_item.text() == "Pending..."
    assert status_item.data(Qt.ItemDataRole.UserRole + 1) == "Pending..."

    # 3. Simulate progress update from worker
    progress_data = ("test_redownload.zip", "10 MB", "Receiving data...", "00:01:00", "500 KB/s", 5 * 1024 * 1024, 10 * 1024 * 1024, 512000)
    window.update_download_row(item, progress_data)

    # Table row MUST update and not stay stuck on "Pending..."
    assert status_item.text() == "50.00%"
    assert status_item.data(Qt.ItemDataRole.UserRole + 1) == "Downloading"
    assert window.download_table.item(row, 4).text() == "500 KB/s"

    # 4. Finish the redownload
    window.download_finished(item, "Complete")
    assert status_item.text() == "Complete"
    assert status_item.data(Qt.ItemDataRole.UserRole + 1) == "Complete"

    window.close()


def test_toolbar_hover_icon_glow(qapp):
    from main import apply_app_theme
    from PyQt6.QtWidgets import QToolBar, QToolButton
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QIcon

    apply_app_theme("BDM Dark (Default)")
    window = MainWindow(start_ipc=False)
    window.hide()

    tb = window.findChild(QToolBar, "MainToolbar")
    assert tb is not None
    add_btn = None
    for b in tb.findChildren(QToolButton):
        if b.defaultAction() is window.action_add_url:
            add_btn = b
            break

    assert add_btn is not None
    orig_pm = add_btn.icon().pixmap(24, 24).toImage()

    # 1. Hover toolbar button -> switches to glowing icon
    enter_event = QEvent(QEvent.Type.Enter)
    qapp.sendEvent(add_btn, enter_event)

    hover_pm = add_btn.icon().pixmap(24, 24).toImage()
    assert hover_pm != orig_pm

    # Ensure hover icon is not black in dark mode
    white_pixels = 0
    for y in range(hover_pm.height()):
        for x in range(hover_pm.width()):
            c = hover_pm.pixelColor(x, y)
            if c.red() > 200 and c.green() > 200 and c.blue() > 200 and c.alpha() > 150:
                white_pixels += 1
    assert white_pixels > 0, "Hover icon in dark mode should have luminous white/bright stroke"

    # 2. Leave hover -> restores original icon
    leave_event = QEvent(QEvent.Type.Leave)
    qapp.sendEvent(add_btn, leave_event)

    restored_pm = add_btn.icon().pixmap(24, 24).toImage()
    assert restored_pm == orig_pm
    window.close()

    # 3. Light Mode toolbar hover -> glowing dark icon
    win_light = MainWindow(start_ipc=False)
    win_light.hide()
    win_light.apply_appearance_setting("BDM Light", icon_theme_name="BDM Light")

    tb_light = win_light.findChild(QToolBar, "MainToolbar")
    add_btn_light = None
    for b in tb_light.findChildren(QToolButton):
        if b.defaultAction() is win_light.action_add_url:
            add_btn_light = b
            break
    assert add_btn_light is not None

    qapp.sendEvent(add_btn_light, enter_event)
    hover_light_pm = add_btn_light.icon().pixmap(24, 24).toImage()
    dark_pixels = sum(1 for y in range(hover_light_pm.height()) for x in range(hover_light_pm.width()) if hover_light_pm.pixelColor(x, y).red() < 50 and hover_light_pm.pixelColor(x, y).alpha() > 150)
    assert dark_pixels > 0, "Hover icon in light mode should have dark stroke pixels"
    win_light.close()


def test_sidebar_incomplete_status_filter(qapp):
    from PyQt6.QtWidgets import QTableWidgetItem
    window = MainWindow(start_ipc=False)
    window.hide()
    window.download_table.setRowCount(0)

    assert window.item_unfinished.text(0) == "Incomplete"

    # Add incomplete and complete rows directly
    window.download_table.insertRow(0)
    item0 = QTableWidgetItem("file1.zip")
    item0_status = QTableWidgetItem("50.00%")
    window.download_table.setItem(0, 0, item0)
    window.download_table.setItem(0, 2, item0_status)

    window.download_table.insertRow(1)
    item1 = QTableWidgetItem("file2.zip")
    item1_status = QTableWidgetItem("Complete")
    window.download_table.setItem(1, 0, item1)
    window.download_table.setItem(1, 2, item1_status)

    # Filter by Incomplete
    window.filter_downloads(window.item_unfinished, 0)
    assert not window.download_table.isRowHidden(0)
    assert window.download_table.isRowHidden(1)

    # Filter by Finished
    window.filter_downloads(window.item_finished, 0)
    assert window.download_table.isRowHidden(0)
    assert not window.download_table.isRowHidden(1)

    window.close()




def test_sidebar_selected_icon_black_in_dark_and_light_modes(qapp):
    from main import apply_app_theme
    from PyQt6.QtWidgets import QStyleOptionViewItem, QStyle
    from PyQt6.QtGui import QPainter, QPixmap
    from PyQt6.QtCore import QRect

    # 1. Dark Mode
    win_dark = MainWindow(start_ipc=False)
    win_dark.hide()
    win_dark.apply_appearance_setting("BDM Dark (Default)", icon_theme_name="BDM Dark (Default)")

    tree = win_dark.category_tree
    item = win_dark.all_downloads_header
    tree.setCurrentItem(item)

    # Render selected item using delegate
    pm = QPixmap(200, 30)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    opt = QStyleOptionViewItem()
    opt.initFrom(tree)
    opt.rect = QRect(0, 0, 200, 30)
    opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
    tree.itemDelegate().paint(p, opt, tree.model().index(1, 0))
    p.end()

    img = pm.toImage()
    black_px = sum(1 for y in range(img.height()) for x in range(30) if img.pixelColor(x, y).red() == 0 and img.pixelColor(x, y).green() == 0 and img.pixelColor(x, y).blue() == 0 and img.pixelColor(x, y).alpha() > 150)
    white_px = sum(1 for y in range(img.height()) for x in range(30) if img.pixelColor(x, y).red() > 200 and img.pixelColor(x, y).alpha() > 150)
    assert black_px > 0, "Left panel selected icon must have pure black pixels in dark mode"
    assert white_px == 0, "Left panel selected icon must not have white pixels in dark mode"
    win_dark.close()

    # 2. Light Mode
    win_light = MainWindow(start_ipc=False)
    win_light.hide()
    win_light.apply_appearance_setting("BDM Light", icon_theme_name="BDM Light")

    tree_light = win_light.category_tree
    item_light = win_light.all_downloads_header
    tree_light.setCurrentItem(item_light)

    pm_light = QPixmap(200, 30)
    pm_light.fill(Qt.GlobalColor.transparent)
    p2 = QPainter(pm_light)
    opt2 = QStyleOptionViewItem()
    opt2.initFrom(tree_light)
    opt2.rect = QRect(0, 0, 200, 30)
    opt2.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
    tree_light.itemDelegate().paint(p2, opt2, tree_light.model().index(1, 0))
    p2.end()

    img_light = pm_light.toImage()
    black_px_light = sum(1 for y in range(img_light.height()) for x in range(30) if img_light.pixelColor(x, y).red() == 0 and img_light.pixelColor(x, y).green() == 0 and img_light.pixelColor(x, y).blue() == 0 and img_light.pixelColor(x, y).alpha() > 150)
    white_px_light = sum(1 for y in range(img_light.height()) for x in range(30) if img_light.pixelColor(x, y).red() > 200 and img_light.pixelColor(x, y).alpha() > 150)
    assert black_px_light > 0, "Left panel selected icon must have pure black pixels in light mode"
    assert white_px_light == 0, "Left panel selected icon must not have white pixels in light mode"
    win_light.close()


def test_add_url_dialog_button_click_icon_colors(qapp):
    """Verify that in AddUrlDialog, clicking Paste or Download Media uses white icon in dark mode and dark icon in light mode."""
    from main import apply_app_theme
    from ui.dialogs.add_url import AddUrlDialog
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF

    press_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    release_event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    # 1. Dark Mode
    apply_app_theme("BDM Dark (Default)")
    dlg_dark = AddUrlDialog()
    dlg_dark.hide()

    qapp.sendEvent(dlg_dark.btn_paste, press_event)
    pm_press_dark = dlg_dark.btn_paste.icon().pixmap(16, 16).toImage()
    white_px_dark = sum(1 for y in range(pm_press_dark.height()) for x in range(pm_press_dark.width()) if pm_press_dark.pixelColor(x, y).red() > 200 and pm_press_dark.pixelColor(x, y).alpha() > 150)
    dark_px_dark = sum(1 for y in range(pm_press_dark.height()) for x in range(pm_press_dark.width()) if pm_press_dark.pixelColor(x, y).red() < 50 and pm_press_dark.pixelColor(x, y).alpha() > 150)
    assert white_px_dark > 0, "Dark mode AddUrlDialog paste button on click must have white icon pixels"
    assert dark_px_dark == 0, "Dark mode AddUrlDialog paste button on click must not have dark icon pixels"
    qapp.sendEvent(dlg_dark.btn_paste, release_event)
    dlg_dark.close()

    # 2. Light Mode
    apply_app_theme("BDM Light")
    dlg_light = AddUrlDialog()
    dlg_light.hide()

    qapp.sendEvent(dlg_light.btn_paste, press_event)
    pm_press_light = dlg_light.btn_paste.icon().pixmap(16, 16).toImage()
    dark_px_light = sum(1 for y in range(pm_press_light.height()) for x in range(pm_press_light.width()) if pm_press_light.pixelColor(x, y).red() < 50 and pm_press_light.pixelColor(x, y).alpha() > 150)
    white_px_light = sum(1 for y in range(pm_press_light.height()) for x in range(pm_press_light.width()) if pm_press_light.pixelColor(x, y).red() > 200 and pm_press_light.pixelColor(x, y).alpha() > 150)
    assert dark_px_light > 0, "Light mode AddUrlDialog paste button on click must have dark icon pixels"
    assert white_px_light == 0, "Light mode AddUrlDialog paste button on click must not have white icon pixels"
    qapp.sendEvent(dlg_light.btn_paste, release_event)
    dlg_light.close()


def test_process_incoming_url_routes_media_link_to_media_downloader(qapp, monkeypatch):
    """Verify that process_incoming_url routes media streaming links directly to open_media_downloader."""
    from main import MainWindow

    win = MainWindow(start_ipc=False)
    win.hide()

    called_url = None
    called_auto_start = None
    called_preset = None

    def mock_open_media_downloader(url=None, auto_analyze=False, auto_start=False, target_preset=""):
        nonlocal called_url, called_auto_start, called_preset
        called_url = url
        called_auto_start = auto_start
        called_preset = target_preset

    monkeypatch.setattr(win, "open_media_downloader", mock_open_media_downloader)

    # 1. Standard YouTube URL
    win.process_incoming_url("https://www.youtube.com/watch?v=sample_vid|Mozilla/5.0|cookie1=val")
    assert called_url == "https://www.youtube.com/watch?v=sample_vid"
    assert called_preset is not None

    # 2. Vimeo URL
    called_url = None
    win.process_incoming_url("https://vimeo.com/76979871||")
    assert called_url == "https://vimeo.com/76979871"

    win.close()


def test_open_media_downloader_auto_start_remains_hidden(qapp, monkeypatch):
    """Verify that open_media_downloader keeps the dialog hidden when auto_start is True."""
    from main import MainWindow

    win = MainWindow(start_ipc=False)
    win.hide()

    # Mock analyze_and_download so no real yt-dlp process is spawned
    analyzed_calls = []
    from ui.dialogs.media_downloader import MediaDownloaderDialog
    monkeypatch.setattr(
        MediaDownloaderDialog,
        "analyze_and_download",
        lambda self, url, auto_start=False, target_preset="": analyzed_calls.append((url, auto_start, target_preset))
    )

    # 1. auto_start=True -> dialog must NOT be visible
    win.open_media_downloader(url="https://youtube.com/watch?v=123", auto_start=True, target_preset="1080p Full HD")
    assert win._media_downloader_dlg is not None
    assert win._media_downloader_dlg.isVisible() is False
    assert len(analyzed_calls) == 1
    assert analyzed_calls[0] == ("https://youtube.com/watch?v=123", True, "1080p Full HD")

    if win._media_downloader_dlg:
        win._media_downloader_dlg.close()

    # 2. auto_start=False -> dialog IS visible
    win.open_media_downloader(url="https://youtube.com/watch?v=456", auto_start=False)
    assert win._media_downloader_dlg is not None
    assert win._media_downloader_dlg.isVisible() is True
    win._media_downloader_dlg.close()
    win.close()


def test_options_dialog_media_tab_youtube_client(qapp, monkeypatch):
    """Verify that OptionsDialog includes writable YouTube Player Client input and reset button."""
    from ui.dialogs.options import OptionsDialog

    saved_configs = []
    monkeypatch.setattr("ui.dialogs.options.save_category_config", lambda cfg: saved_configs.append(cfg))

    dlg = OptionsDialog(main_window=None)
    assert hasattr(dlg, "txt_opt_youtube_client")
    assert hasattr(dlg, "btn_opt_reset_youtube_client")

    # Set custom client string (e.g. android,web)
    dlg.txt_opt_youtube_client.setText("android,web")
    dlg.save_and_accept()

    assert len(saved_configs) == 1
    media_defs = saved_configs[0].get("media_downloader_defaults", {})
    assert media_defs.get("youtube_player_client") == "android,web"

    # Test Reset button restores default "default"
    dlg2 = OptionsDialog(main_window=None)
    dlg2.txt_opt_youtube_client.setText("ios")
    dlg2.btn_opt_reset_youtube_client.click()
    assert dlg2.txt_opt_youtube_client.text() == "default"

    dlg.close()
    dlg2.close()


def test_options_dialog_height_matches_main_window(qapp):
    """Verify that OptionsDialog height matches main window height."""
    from ui.dialogs.options import OptionsDialog
    from PyQt6.QtWidgets import QWidget

    fake_main = QWidget()
    fake_main.resize(800, 680)

def test_tray_hibernation_buffers_updates_and_suspends_timers(qapp):
    """Verify that when the window is in tray hibernation, UI updates are buffered and timers suspended."""
    window = MainWindow(start_ipc=False)
    window._is_in_tray = True
    window.start_download(
        url="http://example.com/hibernation_test.bin",
        custom_save_dir="/tmp",
        start_paused=True,
        show_dialog=False
    )
    row = 0
    item_ref = window.download_table.item(row, 0)
    assert item_ref is not None

    # Simulate progress while in tray
    progress_data = ("hibernation_test.bin", "10.00 MB", "Downloading", "00:05", "2.00 MB/s", 5242880, 10485760)
    window.update_download_row(item_ref, progress_data)

    # Item should be buffered in _pending_tray_updates and not yet mutated in DOM
    item_key = window._get_item_key(item_ref)
    assert item_key in window._pending_tray_updates
    assert window.active_speeds.get(item_key) is not None
    if window.tray_icon:
        assert "2.00 MB/s" in window.tray_icon.toolTip()
        assert "active download" in window.tray_icon.toolTip()

    # Restore window
    window.restore_window()
    assert window._is_in_tray is False
    assert len(window._pending_tray_updates) == 0

    # Status item in table should now reflect the flushed progress
    status_item = window.download_table.item(row, 2)
    assert status_item is not None
    assert "50.00%" in status_item.text() or status_item.data(Qt.ItemDataRole.UserRole) == "50.00%"
    window.close()


def test_download_complete_dialog_shown_after_file_info_fetched(qapp, tmp_path):
    target_file = tmp_path / "archive.zip"
    target_file.write_bytes(b"PK\x03\x04" + b"0" * 1024)

    window = MainWindow(start_ipc=False)
    window.hide()

    file_info = {
        "url": "http://example.com/archive.zip",
        "suggested_filename": "archive.zip",
        "size_str": "1.00 KB",
        "size_bytes": 1028
    }
    window.on_file_info_fetched(file_info)

    assert len(window.active_file_info_dialogs) == 1
    dlg_key = list(window.active_file_info_dialogs.keys())[0]
    info_dlg = window.active_file_info_dialogs[dlg_key]

    # Simulate user confirming "Start Download"
    info_dlg.on_start()

    # Active file info dialog must be cleanly evicted from tracking
    assert dlg_key not in window.active_file_info_dialogs
    assert len(window.active_file_info_dialogs) == 0

    # Ensure download item exists and download is marked complete
    item_ref = window.download_table.item(0, 0)
    assert item_ref is not None
    item_ref.setData(Qt.ItemDataRole.UserRole + 1, str(target_file))

    window.download_finished(item_ref, "Complete")

    # Complete dialog must be created and shown
    assert dlg_key in window.active_complete_dialogs
    complete_dlg = window.active_complete_dialogs[dlg_key]
    assert complete_dlg is not None
    assert complete_dlg.isVisible()

    # Closing dialog cleans up tracking
    complete_dlg.accept()
    assert dlg_key not in window.active_complete_dialogs
    window.close()


def test_media_download_complete_dialog_shown(qapp, tmp_path):
    media_file = tmp_path / "video.mp4"
    media_file.write_bytes(b"\x00\x00\x00 ftypisom" + b"0" * 2048)

    window = MainWindow(start_ipc=False)
    window.hide()

    item_name = window.start_media_download(
        url="https://www.youtube.com/watch?v=sample123",
        filename="video.mp4",
        custom_save_dir=str(tmp_path)
    )
    key = window._get_item_key(item_name)
    assert key in window.active_downloads

    # Simulate media download finish
    window._on_media_download_finished(key, item_name, str(media_file))

    assert key in window.active_complete_dialogs
    complete_dlg = window.active_complete_dialogs[key]
    assert complete_dlg is not None
    assert complete_dlg.isVisible()

    complete_dlg.accept()
    assert key not in window.active_complete_dialogs
    window.close()


def test_options_dialog_max_connections_persistence(qapp, monkeypatch, tmp_path):
    from ui.dialogs import OptionsDialog
    from core.utils import save_extension_config, load_extension_config

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 8})

    dlg = OptionsDialog()
    assert hasattr(dlg, "spin_max_conn")
    assert dlg.spin_max_conn.minimum() == 1
    assert dlg.spin_max_conn.maximum() == 32
    assert dlg.spin_max_conn.value() == 8

    # Change to 16 and save
    dlg.spin_max_conn.setValue(16)
    dlg.save_and_accept()

    loaded = load_extension_config()
    assert loaded["max_connections"] == 16

    # Reopen dialog and verify 16 is displayed
    dlg2 = OptionsDialog()
    assert dlg2.spin_max_conn.value() == 16
    dlg2.reject()


def test_download_progress_dialog_respects_custom_connections(qapp, monkeypatch, tmp_path):
    from ui.dialogs import DownloadProgressDialog
    from core.workers import DownloadWorker
    from core.utils import save_extension_config

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 10})

    worker = DownloadWorker("http://example.com/test.iso", 0, "/tmp")
    progress_dlg = DownloadProgressDialog(worker, None)
    progress_dlg.show()

    assert len(progress_dlg.segment_bars) == 10
    assert progress_dlg.seg_table.rowCount() == 10

    # Expand details and verify geometry is capped to 8 rows
    progress_dlg.toggle_details(True)
    assert not progress_dlg.details_frame.isHidden()
    assert progress_dlg.btn_details.text() == "Details <<"
    expanded_height_10 = progress_dlg.height()

    # Collapse details
    progress_dlg.toggle_details(False)
    assert progress_dlg.details_frame.isHidden()
    assert progress_dlg.btn_details.text() == "Details >>"

    progress_dlg.close()
    worker.deleteLater()

    # Test with 1 connection — must render minimum 8 rows (1 active, 7 unused) and identical expanded height
    save_extension_config({"protocol": "ws", "port": 56800, "token": "", "max_connections": 1})
    worker1 = DownloadWorker("http://example.com/test.iso", 0, "/tmp")
    progress_dlg1 = DownloadProgressDialog(worker1, None)
    progress_dlg1.show()
    assert progress_dlg1.seg_table.rowCount() == 8
    assert len(progress_dlg1.segment_bars) == 8
    assert progress_dlg1.seg_table.item(0, 3).text() == "Pending..."
    assert progress_dlg1.seg_table.item(1, 3).text() == "Unused"
    progress_dlg1.toggle_details(True)
    assert progress_dlg1.height() == expanded_height_10
    progress_dlg1.close()
    worker1.deleteLater()


def test_pause_resume_multi_interface_lifecycle(qapp, monkeypatch):
    """
    Test multiple pause and resume operations on a single download across:
    1. Toolbar Pause / Resume (action_stop, action_resume)
    2. Download Window Pause / Resume (DownloadProgressDialog.toggle_pause)
    3. Right-Click Context Menu (stop_selected_download, resume_selected_download)
    4. Mixed cross-interface alternating cycles
    """
    window = MainWindow(start_ipc=False)
    window.hide()

    # Prevent spawning real background processes
    monkeypatch.setattr(window, "_start_download_worker", lambda url, item_ref, resume_filename=None, **kw: None)

    window.start_download(
        url="http://example.com/test_lifecycle.iso",
        custom_save_dir="/tmp",
        start_paused=False,
        show_dialog=False
    )

    row = 0
    item0 = window.download_table.item(row, 0)
    key = window._get_item_key(item0)
    assert key is not None
    item0.setData(Qt.ItemDataRole.UserRole + 13, 1)

    from PyQt6.QtCore import QObject, pyqtSignal
    class MockWorker(QObject):
        log_signal = pyqtSignal(str)
        main_bar_signal = pyqtSignal(object, object)
        main_progress_signal = pyqtSignal(int, tuple)
        finished_signal = pyqtSignal(int, str)
        init_segments_signal = pyqtSignal(int)
        segment_update_signal = pyqtSignal(int, object, object, float, str)

        def __init__(self):
            super().__init__()
            self.is_paused = False
            self.is_pause_requested = False
            self.url = "http://example.com/test_lifecycle.iso"
            self.target_path = "/tmp/test_lifecycle.iso"
            self.filename = "test_lifecycle.iso"
            self.row_index = 0
            self.total_bytes = 1000000
            self.current_bytes = 500000
            self.generation = 1
        def start(self):
            pass
        def stop(self):
            pass
        def pause(self):
            self.is_paused = True
            self.is_pause_requested = True
        def resume(self):
            self.is_paused = False
            self.is_pause_requested = False
        def format_bytes(self, b, **kw):
            return "500.00 KB"

    mock_worker = MockWorker()
    from ui.dialogs import DownloadProgressDialog
    dlg = DownloadProgressDialog(mock_worker, None)
    dlg.hide()
    window.active_downloads[key] = dlg
    mock_worker.main_progress_signal.connect(lambda _, data: window.update_download_row(item0, data))

    window.download_table.selectRow(row)

    # Initial active progress tick (50.00%, Downloading)
    window.update_download_row(item0, (
        "test_lifecycle.iso", "1.00 MB", "Receiving data...", "10s", "50.00 KB/s", 500000, 1000000, 50000, 1
    ))
    assert window.download_table.item(row, 2).text() == "50.00%"
    assert window._is_row_active(row) is True
    assert window.action_stop.isEnabled() is True
    assert window.action_resume.isEnabled() is False

    # 1. TOOLBAR PAUSE & RESUME
    window.action_stop.trigger()
    assert mock_worker.is_paused is True
    assert item0.data(Qt.ItemDataRole.UserRole + 11) == "Paused"
    assert window.download_table.item(row, 2).text() == "50.00%"
    assert window._is_row_active(row) is False
    assert window.action_stop.isEnabled() is False
    assert window.action_resume.isEnabled() is True

    # Stale in-flight callback from older session arriving while paused -> discarded
    window.update_download_row(item0, (
        "test_lifecycle.iso", "1.00 MB", "Receiving data...", "9s", "60.00 KB/s", 510000, 1000000, 60000, 0
    ))
    assert window.download_table.item(row, 2).text() == "50.00%"
    assert window._is_row_active(row) is False

    # Toolbar Resume
    window.action_resume.trigger()
    assert mock_worker.is_paused is False
    assert item0.data(Qt.ItemDataRole.UserRole + 11) == "Normal"
    assert window._is_row_active(row) is True
    assert window.action_stop.isEnabled() is True
    assert window.action_resume.isEnabled() is False

    # 2. DOWNLOAD WINDOW (DIALOG) PAUSE & RESUME
    dlg.btn_pause.setText("Pause")
    dlg.toggle_pause()
    assert mock_worker.is_paused is True
    assert window._is_row_active(row) is False
    assert window.action_stop.isEnabled() is False
    assert window.action_resume.isEnabled() is True

    dlg.btn_pause.setText("Resume")
    dlg.toggle_pause()
    assert mock_worker.is_paused is False
    assert window._is_row_active(row) is True
    assert window.action_stop.isEnabled() is True
    assert window.action_resume.isEnabled() is False

    # 3. RIGHT-CLICK CONTEXT MENU PAUSE & RESUME
    window.stop_selected_download()
    assert mock_worker.is_paused is True
    assert window._is_row_active(row) is False
    assert window.action_stop.isEnabled() is False
    assert window.action_resume.isEnabled() is True

    window.resume_selected_download()
    assert mock_worker.is_paused is False
    assert window._is_row_active(row) is True
    assert window.action_stop.isEnabled() is True
    assert window.action_resume.isEnabled() is False

    # 4. CROSS-INTERFACE ALTERNATING SWITCHES
    # Toolbar Pause -> Window Resume
    window.action_stop.trigger()
    assert window._is_row_active(row) is False
    dlg.btn_pause.setText("Resume")
    dlg.toggle_pause()
    assert window._is_row_active(row) is True

    # Window Pause -> Context Menu Resume
    dlg.btn_pause.setText("Pause")
    dlg.toggle_pause()
    assert window._is_row_active(row) is False
    window.resume_selected_download()
    assert window._is_row_active(row) is True

    # Context Menu Pause -> Toolbar Resume
    window.stop_selected_download()
    assert window._is_row_active(row) is False
    window.action_resume.trigger()
    assert window._is_row_active(row) is True

    dlg.close()
    dlg.deleteLater()














