# UI Theme Configuration Design Specification

**Date**: 2026-08-07  
**Branch**: `feat/ui-theming`  
**Status**: Approved  

---

## 1. Overview

Add user-configurable theme selection ("Automatic", "Light", "Dark") to Bengal Download Manager. The theme control will reside in the General tab of the Options dialog, placed directly above the "Startup & Integration" section.

---

## 2. Requirements & Behavior

1. **Options Dialog Placement**:
   - Location: `General` tab in `OptionsDialog`.
   - Layout Position: Top of the `General` tab, directly above the `Startup & Integration` group box.
   - Component: `QGroupBox("Theme")` containing a `QComboBox` with options:
     - `Automatic` (Default)
     - `Light`
     - `Dark`
     - `Breeze Light`
     - `Breeze Dark`
   - Tooltip: `"Select application theme mode (Automatic uses system theme)"`.

2. **Kirigami QML View (`OptionsDialog.qml`)**:
   - Add a `ComboBox` with `Kirigami.FormData.label: "Theme:"` and options `["Automatic", "Light", "Dark", "Breeze Light", "Breeze Dark"]`.

3. **Theme Application Logic**:
   - **`Automatic`**: Applies `Qt.ColorScheme.Unknown` to `QGuiApplication.styleHints()`, allowing Qt to follow system OS light/dark mode.
   - **`Light`**: Applies `Qt.ColorScheme.Light` to `QGuiApplication.styleHints()` and applies standard light palette fallback.
   - **`Dark`**: Applies `Qt.ColorScheme.Dark` to `QGuiApplication.styleHints()` and applies standard dark palette fallback.
   - **`Breeze Light`**: Applies `Qt.ColorScheme.Light` and KDE Breeze Light palette (`#eff0f1`, `#fcfcfc`, `#3daee9`).
   - **`Breeze Dark`**: Applies `Qt.ColorScheme.Dark` and KDE Breeze Dark palette (`#2a2e32`, `#232629`, `#3daee9`).
   - **Icon Adaptation**: Calls `ensure_adaptive_icon_theme(app)` immediately whenever the theme choice is changed/applied, keeping dark/light icon sets in sync.

4. **Persistence**:
   - Save key `"theme"` (values: `"Automatic"`, `"Light"`, `"Dark"`) in `settings.json` located in the application configuration directory (`get_config_dir()`).
   - Load `"theme"` setting during main window startup and apply before showing windows.

---

## 3. Implementation Files

- **`src/ui/dialogs/options.py`**:
  - Add `grp_theme` in `setup_general_tab()`.
  - Populate combo box from saved settings (`self.parent().settings.get("theme", "Automatic")`).
  - Update `save_and_accept()` to persist `"theme"` into `parent().settings` and call `parent().apply_theme_setting(...)`.
- **`src/ui/qml/OptionsDialog.qml`**:
  - Add `Theme` combo box.
- **`src/main.py`**:
  - Add `apply_theme_setting(theme_name)` method on `MainWindow` (and helper function `apply_app_theme(theme_name)`).
  - Call `apply_theme_setting()` in `load_settings()` and app initialization.
- **`tests/test_ui.py`**:
  - Add test case `test_options_dialog_theme_selection` verifying dropdown existence, index loading, and setting persistence.

---

## 4. Quality Assurance & Verification

- **Unit Tests**: Run `PYTHONPATH=src venv/bin/pytest -v tests/`.
- **Manual Verification**: Launch PyQt6 GUI mode (`venv/bin/python src/main.py`) to verify dropdown placement above Startup section.
