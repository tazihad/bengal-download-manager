# BDM Auto Theme Implementation & Dynamic Palette Tracking

## Overview
BDM Auto dynamically adapts both application color palette and toolbar vector icons to match system light/dark appearance seamlessly across desktop environments (KDE Plasma, GNOME, XFCE) and sandboxed packaging formats (Flatpak, AppImage).

---

## Technical Architecture & Implementation

### 1. Dynamic System Theme Detection
- **`QStyleHints.colorScheme` & System Palette**: In `apply_app_theme`, `sh.setColorScheme(Qt.ColorScheme.Unknown)` is enforced so Qt does not lock out system theme events.
- **Palette Evaluation**: System dark vs. light mode is determined via:
  ```python
  cs = sh.colorScheme()
  if cs == Qt.ColorScheme.Dark:
      is_sys_dark = True
  elif cs == Qt.ColorScheme.Light:
      is_sys_dark = False
  else:
      sys_pal = app.style().standardPalette()
      is_sys_dark = sys_pal.color(QPalette.ColorRole.Window).value() < 128 or sys_pal.color(QPalette.ColorRole.WindowText).value() > 128
  ```
- **Palette Construction**: Based on `is_sys_dark`, BDM applies high-contrast custom dark (`#202326`) or light (`#eff0f1`) palettes while preserving custom accent colors.

---

### 2. Live OS Theme Signal & Event Listeners
To respond instantly when the desktop environment toggles dark/light mode:
1. **Signal Connections**:
   - `QGuiApplication.styleHints().colorSchemeChanged`
   - `QGuiApplication.paletteChanged`
2. **Window Event Handler**: Overrode `MainWindow.changeEvent(self, event)` for event types:
   - `QEvent.Type.ApplicationPaletteChange`
   - `QEvent.Type.PaletteChange`
   - `QEvent.Type.ThemeChange`
   - `QEvent.Type.StyleChange`

---

### 3. Adaptive Toolbar Icons & Text
- **Vector Icons**: `get_monochrome_icon` in `ui/icons.py` generates high-DPI stroke icons using `QPalette.ColorRole.WindowText`.
- **Explicit Disabled Pixmaps**: Renders `disabled_pixmap` at `0.35` opacity transparent canvas for `QIcon.Mode.Disabled` to prevent Qt style engines (e.g. Breeze under KDE Plasma Flatpak) from auto-rendering solid white disabled icons.
- **Adaptive Text Styling**: Replaced hardcoded `#FFFFFF` text color in toolbar CSS with `palette(window-text)` so toolbar text dynamically adapts to dark and light modes.
