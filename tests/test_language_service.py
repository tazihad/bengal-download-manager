"""
Unit tests for Language & Localization Service and Options Dialog integration.
"""

import os
import json
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLocale

from core.services.language_service import (
    SUPPORTED_LANGUAGES,
    get_available_languages,
    get_language_code,
    get_language_display,
    normalize_language_code,
    get_current_language_code,
    get_current_language_display,
    apply_language,
)
from core.utils import get_config_dir
from ui.dialogs.options import OptionsDialog


def test_supported_languages_list():
    langs = get_available_languages()
    assert len(langs) >= 70
    assert "System Default" in langs
    assert "English" in langs
    assert "Bengali - বাংলা" in langs
    assert "French - Français" in langs
    assert "German - Deutsch" in langs
    assert "Spanish - Español" in langs


def test_code_display_resolution():
    assert get_language_code("System Default") == "system"
    assert get_language_code("English") == "en"
    assert get_language_code("Bengali - বাংলা") == "bn"
    assert get_language_code("French - Français") == "fr"
    assert get_language_code("German - Deutsch") == "de"
    assert get_language_code("Spanish - Español") == "es"
    assert get_language_code("unknown_language_xyz") == "system"
    assert get_language_code("") == "system"
    assert get_language_code(None) == "system"

    assert get_language_display("system") == "System Default"
    assert get_language_display("en") == "English"
    assert get_language_display("bn") == "Bengali - বাংলা"
    assert get_language_display("fr") == "French - Français"
    assert get_language_display("de") == "German - Deutsch"
    assert get_language_display("es") == "Spanish - Español"
    assert get_language_display("invalid") == "System Default"
    assert get_language_display("") == "System Default"
    assert get_language_display(None) == "System Default"


def test_normalize_language_code():
    assert normalize_language_code("bn") == "bn"
    assert normalize_language_code("Bengali - বাংলা") == "bn"
    assert normalize_language_code("EN") == "en"
    assert normalize_language_code("") == "system"
    assert normalize_language_code(None) == "system"


def test_apply_language_execution(qapp):
    # Test applying English
    res_en = apply_language(qapp, "en")
    assert res_en is True
    assert QLocale().language() == QLocale.Language.English

    # Test applying Bengali
    apply_language(qapp, "bn")
    assert QLocale().language() == QLocale.Language.Bengali

    # Test applying System Default
    apply_language(qapp, "system")


def test_options_dialog_language_integration(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Pre-save language in settings
    cfg_dir = get_config_dir()
    os.makedirs(cfg_dir, exist_ok=True)
    with open(os.path.join(cfg_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"language": "bn", "ui_scale": "100%"}, f)

    class DummyMainWindow:
        def __init__(self):
            self.settings = {"language": "bn", "ui_scale": "100%"}

        def save_settings(self):
            pass

        def apply_appearance_setting(self, *args):
            pass

    dummy_win = DummyMainWindow()
    dlg = OptionsDialog(dummy_win)

    # Check that combo_language exists on General tab and is scrollable/compact
    assert hasattr(dlg, "combo_language")
    assert dlg.combo_language.count() > 70
    assert dlg.combo_language.maxVisibleItems() == 10
    assert dlg.combo_language.currentText() == "Bengali - বাংলা"
    assert dlg.get_language() == "bn"

    # Change to French and verify get_language
    idx_fr = dlg.combo_language.findText("French - Français")
    assert idx_fr != -1
    dlg.combo_language.setCurrentIndex(idx_fr)
    assert dlg.get_language() == "fr"

    dlg.close()
    dlg.deleteLater()


def test_json_catalog_and_tr(qapp):
    from core.services.language_service import tr, JsonCatalogTranslator
    # Apply Bengali language catalog
    res = apply_language(qapp, "bn")
    assert res is True
    assert tr("&Tasks") == "টাস্ক"
    assert tr("Add URL") == "URL যোগ করুন"
    assert tr("File Name") == "ফাইলের নাম"
    assert tr("NonExistentString12345") == "NonExistentString12345"

    # Font should be adapted
    font = qapp.font()
    assert font.pointSize() == 10


def test_main_window_retranslate_ui(qapp):
    from ui.main_window import MainWindow
    apply_language(qapp, "en")
    win = MainWindow()
    assert win.action_add_url.text() == "Add URL"
    assert win.download_table.horizontalHeaderItem(0).text() == "File Name"

    # Dynamically switch to Bengali
    apply_language(qapp, "bn")
    win.retranslate_ui()
    assert win.action_add_url.text() == "URL যোগ করুন"
    assert win.download_table.horizontalHeaderItem(0).text() == "ফাইলের নাম"

    # Switch back to English
    apply_language(qapp, "en")
    win.retranslate_ui()
    assert win.action_add_url.text() == "Add URL"
    assert win.download_table.horizontalHeaderItem(0).text() == "File Name"

    win.deleteLater()
    qapp.processEvents()
