"""Unit and integration tests for Table Style switching (Classic vs Modern)."""
import pytest
from PyQt6.QtCore import Qt
from main import MainWindow
from ui.delegates.table_delegate import ModernTableDelegate


def test_table_style_actions_and_switching(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()

    # 1. Verify actions exist in View menu
    assert hasattr(win, "action_table_style_classic")
    assert hasattr(win, "action_table_style_modern")
    assert win.action_table_style_classic.isCheckable()
    assert win.action_table_style_modern.isCheckable()

    # 2. Verify all 7 existing columns in Classic mode are intact
    assert win.download_table.columnCount() == 7
    expected_headers = ["File Name", "Size", "Status", "Time Left", "Transfer Rate", "Last Try", "Date Added"]
    for col, expected in enumerate(expected_headers):
        assert win.download_table.horizontalHeaderItem(col).text() == expected

    # 3. Default style is classic
    assert win.table_style == "classic"
    assert win.action_table_style_classic.isChecked()
    assert not win.action_table_style_modern.isChecked()
    assert win.download_table.verticalHeader().defaultSectionSize() == 26

    # 4. Switch to Modern
    win.set_table_style("modern")
    assert win.table_style == "modern"
    assert win.action_table_style_modern.isChecked()
    assert not win.action_table_style_classic.isChecked()
    assert isinstance(win.download_table.itemDelegate(), ModernTableDelegate)
    assert win.download_table.verticalHeader().defaultSectionSize() == 50

    # 5. Switch back to Classic
    win.set_table_style("classic")
    assert win.table_style == "classic"
    assert win.action_table_style_classic.isChecked()
    assert not win.action_table_style_modern.isChecked()
    assert win.download_table.verticalHeader().defaultSectionSize() == 26

    # Verify column count and headers remained completely unchanged
    assert win.download_table.columnCount() == 7
    for col, expected in enumerate(expected_headers):
        assert win.download_table.horizontalHeaderItem(col).text() == expected


def test_table_style_settings_persistence(qapp, tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "get_config_dir", lambda: str(tmp_path))

    win = MainWindow(start_ipc=False)
    win.hide()

    # Set to modern and save
    win.set_table_style("modern")
    win.save_settings()

    # Reopen MainWindow in new instance with same config dir
    win2 = MainWindow(start_ipc=False)
    win2.hide()

    assert win2.table_style == "modern"
    assert win2.action_table_style_modern.isChecked()
    assert win2.download_table.verticalHeader().defaultSectionSize() == 50


def test_twilight_theme_and_accent(qapp):
    from main import apply_app_theme, normalize_theme_name, normalize_accent_name, ACCENT_COLORS
    from PyQt6.QtGui import QPalette

    assert "Twilight" in ACCENT_COLORS
    assert ACCENT_COLORS["Twilight"] == "#8b5cf6"
    assert normalize_theme_name("Twilight") == "Twilight"
    assert normalize_theme_name("twilight dark") == "Twilight"
    assert normalize_accent_name("twilight") == "Twilight"

    apply_app_theme("Twilight", "Twilight", "BDM Auto (Default)", "App Icon (Default)", qapp)
    pal = qapp.palette()
    assert pal.color(QPalette.ColorRole.Highlight).name().lower() == "#8b5cf6"
    assert pal.color(QPalette.ColorRole.Window).name().lower() == "#181424"
    assert pal.color(QPalette.ColorRole.Base).name().lower() == "#13111c"

