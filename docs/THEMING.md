# Bengal Download Manager — Theming & Design System Reference

This document outlines the visual design system, adaptive theming engine, color palettes, and typography architecture for **Bengal Download Manager**.

---

## 1. Design Philosophy & Adaptive Theming

Bengal Download Manager features a dynamic theming system built on **PyQt6 QWidget** and **KDE Kirigami QML** interfaces. The theme automatically adapts across Light, Dark, and Automatic desktop system environments without hardcoding static foreground or background text colors.

### Theme Modes

| Mode | Description | Palette Backend |
| :--- | :--- | :--- |
| **System** | Follows the host desktop environment's color scheme (GNOME, KDE Plasma, XFCE). | `app.style().standardPalette()` |
| **BDM Auto** | Intelligently switches between high-contrast BDM Dark and BDM Light based on OS signals. | Dynamic evaluation via `QStyleHints` |
| **Light Themes** | High-contrast, clean light interfaces adhering to KDE Breeze Light and FreeDesktop HIG. | `create_light_palette()` |
| **Dark Themes** | Low-light, high-legibility dark modes tailored for developer and power user workflows. | `create_dark_palette()` |

---

## 2. Dynamic OS Theme Tracking Architecture

To respond instantly when the user toggles dark or light mode in their desktop environment (e.g. via KDE System Settings, GNOME Control Center, or day/night scheduling):

### 1. Dynamic Detection
In `apply_app_theme`, `sh.setColorScheme(Qt.ColorScheme.Unknown)` is enforced so Qt does not lock out system theme events. System dark mode is evaluated via:
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

### 2. Live Signal Connections
The application attaches listeners to:
- `QGuiApplication.styleHints().colorSchemeChanged`
- `QGuiApplication.paletteChanged`

### 3. Window Event Interception
`MainWindow.changeEvent(self, event)` monitors specific Qt event types to re-render palettes without requiring an application restart:
- `QEvent.Type.ApplicationPaletteChange`
- `QEvent.Type.PaletteChange`
- `QEvent.Type.ThemeChange`
- `QEvent.Type.StyleChange`

---

## 3. Palette Color Roles

### Breeze / BDM Dark Scheme (Default)
| Color Role | Hex Code | RGB | Usage |
| :--- | :--- | :--- | :--- |
| `Window` | `#202326` | `rgb(32, 35, 38)` | Window frame and container backgrounds |
| `WindowText` | `#fcfcfc` | `rgb(252, 252, 252)` | Primary headings and text labels |
| `Base` | `#1b1e20` | `rgb(27, 30, 32)` | Table content, cards, input text boxes |
| `AlternateBase` | `#25282b` | `rgb(37, 40, 43)` | Alternating row backgrounds and hero frames |
| `Highlight` | `#0078d4` | `rgb(0, 120, 212)` | Active selection backgrounds, progress bars |
| `HighlightedText`| `#ffffff` | `rgb(255, 255, 255)` | Text on active selection highlights |
| `Mid` / `Border` | `#3c4043` | `rgb(60, 64, 67)` | Window borders, dividers, frame outlines |

### Breeze / BDM Light Scheme
| Color Role | Hex Code | RGB | Usage |
| :--- | :--- | :--- | :--- |
| `Window` | `#eff0f1` | `rgb(239, 240, 241)` | Window frame and container backgrounds |
| `WindowText` | `#232629` | `rgb(35, 38, 41)` | Primary headings and text labels |
| `Base` | `#ffffff` | `rgb(255, 255, 255)` | Table content, cards, input text boxes |
| `AlternateBase` | `#f5f5f5` | `rgb(245, 245, 245)` | Alternating row backgrounds and hero frames |
| `Highlight` | `#0078d4` | `rgb(0, 120, 212)` | Active selection backgrounds, progress bars |
| `HighlightedText`| `#ffffff` | `rgb(255, 255, 255)` | Text on active selection highlights |
| `Mid` / `Border` | `#c8c8c8` | `rgb(200, 200, 200)` | Window borders, dividers, frame outlines |

---

## 4. Built-in Theme Presets & Accent Colors

BDM includes 21 color themes and 14 vibrant accents:

### Theme Presets
- **Standard**: `System`, `BDM Auto`, `BDM Dark (Default)`, `BDM Light`
- **KDE Breeze**: `Breeze Dark`, `Breeze Light`, `Kirigami Dark`, `Kirigami Light`
- **Developer Palettes**: `Catppuccin`, `Dracula`, `Nord`, `Obsidian Flow`, `One Dark`, `Solarized Dark`, `Solarized Light`, `Twilight`
- **Distro & HIG**: `Ubuntu Dark`, `Ubuntu Light`, `Material You Dark`, `Material You Light`, `IDM Classic`

### Accent Colors
- `BDM Default` (`#0078d4`)
- `Amethyst Violet` (`#9b59b6`)
- `Breeze Blue` (`#3daee9`)
- `Crimson Red` (`#e74c3c`)
- `Dracula Purple` (`#bd93f9`)
- `Emerald Green` (`#2ecc71`)
- `Material Cobalt` (`#3f51b5`)
- `Material Violet` (`#673ab7`)
- `Nord Frost` (`#88c0d0`)
- `Obsidian Purple` (`#8e44ad`)
- `Twilight` (`#e67e22`)
- `Ubuntu Orange` (`#e95420`)
- `Windows Blue` (`#0078d7`)

---

## 5. Vector Icon Engine & Stroke Rendering

Toolbar and action icons in BDM are rendered dynamically using high-DPI vector drawing procedures (`ui/icons.py`):
- **Dynamic Stroke Coloring**: Uses `palette(window-text)` so icons automatically render crisp white strokes on dark themes and dark charcoal strokes on light themes.
- **Explicit Disabled Pixmaps**: Renders disabled action states at `0.35` opacity to prevent Qt style engines (e.g. Breeze under Flatpak) from rendering solid white disabled icons.
- **Hover Glow Effects**: `ToolbarHoverFilter` renders a bold stroke glow when the mouse hovers over an action button.

---

## 6. Typography & OpenType Numerics (`tnum`)

To prevent visual jitter and flickering during rapid download speed fluctuations:
- **Global Font**: Uses system UI typeface (`Segoe UI`, `Noto Sans`, or `Cantarell`) at 9pt default.
- **OpenType Tabular Figures (`tnum: 1`)**: Enabled globally via `QFont.setFeature(QFont.Tag.fromString('tnum'), 1)`. All numbers (file sizes, transfer rates, percentages, elapsed durations, remaining times) render with equal character widths.
