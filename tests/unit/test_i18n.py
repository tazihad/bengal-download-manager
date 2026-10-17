"""Unit tests for the new i18n tooling and Qt translation backend."""

import os
import tempfile
import pytest
from PyQt6.QtCore import QTranslator, QCoreApplication, Qt


class TestI18nBackend:
    def test_elf_hash_calculation(self):
        import sys
        sys.path.insert(0, os.path.abspath("scripts"))
        from i18n import elf_hash

        # Non-empty strings should produce non-zero 32-bit unsigned hashes
        h1 = elf_hash("Resume")
        h2 = elf_hash("Pause")
        assert h1 > 0
        assert h2 > 0
        assert h1 != h2

        # Empty string produces 1 according to Qt elfHash_finish specification
        assert elf_hash("") == 1

    def test_qm_binary_compilation_and_loading(self, qapp):
        import sys
        sys.path.insert(0, os.path.abspath("scripts"))
        from i18n import compile_ts_data_to_qm

        messages = [
            ("MainWindow", "Resume", "পুনরায় শুরু করুন", ""),
            ("MainWindow", "Pause", "বিরতি", ""),
            ("OptionsDialog", "Language:", "ভাষা:", ""),
            ("MainWindow", "Cancel", "إلغاء", ""),
        ]

        qm_bytes = compile_ts_data_to_qm(messages)
        assert len(qm_bytes) > 16
        # Check Qt QM magic number
        assert qm_bytes[:4] == bytes([0x3C, 0xB8, 0x64, 0x18])

        with tempfile.NamedTemporaryFile(suffix=".qm", delete=False) as f:
            f.write(qm_bytes)
            tmp_qm = f.name

        try:
            trans = QTranslator()
            loaded = trans.load(tmp_qm)
            assert loaded is True, "Failed to load generated .qm binary into QTranslator"

            # Verify translation lookups
            assert trans.translate("MainWindow", "Resume") == "পুনরায় শুরু করুন"
            assert trans.translate("MainWindow", "Pause") == "বিরতি"
            assert trans.translate("OptionsDialog", "Language:") == "ভাষা:"
            assert trans.translate("MainWindow", "Cancel") == "إلغاء"
            # Fallback for untranslated
            assert trans.translate("MainWindow", "Unknown") == ""
        finally:
            if os.path.exists(tmp_qm):
                os.unlink(tmp_qm)

    def test_weblate_config_exists(self):
        assert os.path.exists(".weblate.json")
        import json
        with open(".weblate.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        assert cfg.get("filemask") == "translations/bdm_*.ts"
        assert cfg.get("template") == "translations/bdm_en.ts"
        assert cfg.get("file_format") == "ts"

    def test_master_template_ts_exists_and_valid(self):
        import xml.etree.ElementTree as ET
        ts_path = "translations/bdm_en.ts"
        assert os.path.exists(ts_path)
        tree = ET.parse(ts_path)
        root = tree.getroot()
        assert root.tag == "TS"
        contexts = root.findall("context")
        assert len(contexts) > 0
        total_messages = len(root.findall(".//message"))
        assert total_messages >= 200

    def test_apply_language_with_compiled_qm(self, qapp):
        from core.services.language_service import apply_language, tr

        # Apply English
        assert apply_language(qapp, "en") is True
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight

        # Apply Arabic (RTL) - verify layout stays LTR
        apply_language(qapp, "ar")
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight

        # Apply Persian (RTL) - verify layout stays LTR
        apply_language(qapp, "fa")
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight

        # Revert to English
        apply_language(qapp, "en")
