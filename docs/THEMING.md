# Theming & Color Schemes Reference

This document outlines the visual design system, color palettes, and adaptive theming architecture for **Bengal Download Manager**.

---

## 1. System Overview & Theme Adaptability

Bengal Download Manager features a dynamic theming system built on **PyQt6 QWidget** and **KDE Kirigami QML** interfaces. The theme automatically adapts across Light, Dark, and Automatic desktop system environments without hardcoding static foreground/background text colors.

### Theme Modes

| Mode | Description | Palette Backend |
| :--- | :--- | :--- |
| **Automatic** | Follows the host desktop environment's color scheme (GNOME / KDE / XDG Portal). | `app.style().standardPalette()` |
| **Light** | Clean, high-contrast light interface adhering to KDE Breeze Light standards. | `create_light_palette()` |
| **Dark** | Modern dark mode tailored for low-light environments adhering to KDE Breeze Dark standards. | `create_dark_palette()` |

---

## 2. Palette Specifications

### KDE Kirigami / Breeze Light Scheme

| Color Role | Color Code (Hex) | RGB Value | Usage |
| :--- | :--- | :--- | :--- |
| `Window` | `#eff0f1` | `rgb(239, 240, 241)` | Application window & container backgrounds |
| `WindowText` | `#31363b` | `rgb(49, 54, 59)` | Main window body text & headings |
| `Base` | `#fcfcfc` | `rgb(252, 252, 252)` | Content areas, download table cells, input fields |
| `AlternateBase` | `#eff0f1` | `rgb(239, 240, 241)` | Alternating row backgrounds |
| `Highlight` | `#3daee9` | `rgb(61, 174, 233)` | Active selections, badges, progress bars |
| `HighlightedText` | `#ffffff` | `rgb(255, 255, 255)` | Text on active selection highlights |
| `Mid` / `Border` | `#bdc3c7` | `rgb(189, 195, 199)` | Window borders, dividers, card outlines |
| `Link` | `#3daee9` | `rgb(61, 174, 233)` | Clickable URLs and hyperlinks |

### KDE Kirigami / Breeze Dark Scheme

| Color Role | Color Code (Hex) | RGB Value | Usage |
| :--- | :--- | :--- | :--- |
| `Window` | `#2a2e32` | `rgb(42, 46, 50)` | Application window & container backgrounds |
| `WindowText` | `#fcfcfc` | `rgb(252, 252, 252)` | Main window body text & headings |
| `Base` | `#1b1e20` | `rgb(27, 30, 32)` | Content areas, download table cells, input fields |
| `AlternateBase` | `#2a2e32` | `rgb(42, 46, 50)` | Alternating row backgrounds |
| `Highlight` | `#3daee9` | `rgb(61, 174, 233)` | Active selections, badges, progress bars |
| `HighlightedText` | `#ffffff` | `rgb(255, 255, 255)` | Text on active selection highlights |
| `Mid` / `Border` | `#4d5054` | `rgb(77, 80, 84)` | Window borders, dividers, card outlines |
| `Link` | `#3daee9` | `rgb(61, 174, 233)` | Clickable URLs and hyperlinks |

---

## 3. UI Component Stylesheet Rules (QSS)

### Category Sidebar (`QTreeWidget`)
* **Item Hover:** `rgba(61, 174, 233, 0.15)`
* **Item Selection:** Background `#3daee9`, Text `#ffffff`, Font weight 600
* **Branch Render:** `background: transparent; border: none;`

### Global Context Menus (`QMenu`)
* **Container Border:** `1px solid palette(mid)`
* **Selected Item:** Background `#0078d4`, Text `#ffffff`
* **Separator:** `height: 1px; background-color: #707070; margin: 4px 6px;`

### Window & Dialog Shells (`QMainWindow`, `QDialog`)
* **Adaptive Boundary Border:** `border: 1px solid palette(mid);`
* **Header / Footer Separators:** `border-bottom: 1px solid palette(mid);` for `QMenuBar` and `QToolBar`; `border-top: 1px solid palette(mid);` for `QStatusBar`.

---

## 4. Icon Theme Adaptability

The application resolves icon contrast dynamically via `get_themed_icon()`:
1. **Theme Paths Search:** Checks system icon directories (`/app/share/icons`, `/usr/share/icons`, `~/.local/share/icons`).
2. **Dark Variant Fallbacks:** When `is_dark` is detected (`window_color.value() < 128`), icon search automatically prioritizes `-dark` icon theme sets (`breeze-dark`, `ubuntu-mono-dark`, `Adwaita-dark`).
3. **Luminance Inversion:** Pixmaps with luminance `< 120` on dark backgrounds are inverted automatically to ensure crisp visual contrast.

---

## 5. Typography & OpenType Numerics

* **Primary Font:** `Segoe UI` (9pt default).
* **Tabular Numbers (`tnum: 1`):** Enabled globally on `QApplication.setFont()` to ensure fixed-width alignment for file sizes, transfer rates, percentages, and timestamps across tables and cards.
