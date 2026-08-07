# UI Theme Configuration Implementation Plan

**Date**: 2026-08-07  
**Branch**: `feat/ui-theming`  
**Spec**: [`docs/superpowers/specs/2026-08-07-ui-theming-design.md`](file:///mnt/data/dev/bengal-download-manager/docs/superpowers/specs/2026-08-07-ui-theming-design.md)  

---

## Tasks

### Task 1: Add Theme Group Box in `OptionsDialog` (`src/ui/dialogs/options.py`)
- [ ] In `setup_general_tab()`, create `grp_theme = QGroupBox("Theme")`.
- [ ] Add `combo_theme` with items `["Automatic", "Light", "Dark"]` and tooltip.
- [ ] Place `grp_theme` at index 0 of `layout` in `General` tab (above `Startup & Integration`).
- [ ] Load saved theme from `parent().settings.get("theme", "Automatic")`.
- [ ] In `save_and_accept()`, save selected theme to `parent().settings["theme"]` and notify parent to apply theme.

### Task 2: Add Theme Option to Kirigami QML View (`src/ui/qml/OptionsDialog.qml`)
- [ ] Add Theme `ComboBox` with model `["Automatic", "Light", "Dark"]` before the Startup checkbox in `OptionsDialog.qml`.

### Task 3: Implement Global Application Theme Management (`src/main.py`)
- [ ] Implement `apply_app_theme(theme_name, app=None)` to handle `Automatic`, `Light`, and `Dark` color schemes via `QGuiApplication.styleHints().setColorScheme()`.
- [ ] Add `MainWindow.apply_theme_setting(theme_name)` to trigger palette/icon updates and persist settings.
- [ ] Load `"theme"` setting on application startup in `main()` and `load_settings()`.

### Task 4: Test Suite & Verification (`tests/test_ui.py`)
- [ ] Add `test_options_dialog_theme_selection` unit test.
- [ ] Verify complete test suite execution (`PYTHONPATH=src venv/bin/pytest -v tests/`).
