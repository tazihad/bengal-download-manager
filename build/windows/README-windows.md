# Bengal Download Manager — Windows Build & Theming System

This directory contains the complete build orchestration, packaging configuration, and native Windows theming integration for **Bengal Download Manager (BDM)** on Windows 10 and 11.

---

## 1. Architectural Overview & Inspiration from Stellar

In [Stellar Download Manager](https://github.com/ninka6/stellar), Windows theming operates flawlessly because of three foundational design choices:
1. **Direct Win32 DWM Immersive Dark Mode**: Stellar uses the Win32 Desktop Window Manager API (`dwmapi.dll`) with `DwmSetWindowAttribute` (attribute `20` on Windows 10 1903+ / Windows 11, and attribute `19` on early 1809 builds).
2. **Dynamic Focus Hooking**: Stellar hooks `QGuiApplication::focusWindowChanged` to guarantee that every modal dialog or lazily instantiated popup automatically receives dark window caption styling upon appearance.
3. **Isolation from UxTheme Engine**: Stellar uses Qt Quick/Material with explicit semantic tokens (`ColorPalette.qml`), completely bypassing the legacy `windowsvista` QStyle engine.

### Why BDM Had Theme Mismanagement on Windows:
* **Missing DWM Title Bar Calls**: BDM left Win32 caption bars untouched, causing stark-white title bars even when dark themes (BDM Dark, Dracula, Nord, One Dark) were active.
* **The `windowsvista` Style Conflict**: On Windows, PyQt6 defaults to `windowsvista` QStyle. This style forces Windows UxTheme light bitmap assets for buttons, comboboxes, scrollbars, and spinboxes. When BDM applied dark palettes, text was inverted to light, resulting in white text on white buttons and light scrollbars across dark tables.
* **Hardcoded `#000000` Selection Text**: Global stylesheets hardcoded black text on highlights, making selections unreadable when using dark accents like Windows Blue (`#0078d4`).
* **Broken Auto-Theme Detection**: BDM's "Auto" mode fell back to `app.style().standardPalette()`, which always reports light mode on Windows under `windowsvista`.

### How This Windows Build Fixes It (Without Touching Core App Files):
* **Zero-Touch Modular Architecture**: All core application code in `src/` remains untouched.
* **`windows/theme_fix/windows_theme_fix.py`**:
  * Implements Win32 `DwmSetWindowAttribute(hwnd, 20/19)` with an HWND memoization cache to prevent recursive focus/activation storms (Stellar pattern).
  * Hooks `QGuiApplication.focusWindowChanged` to theme all dialogs as they open.
  * Detects OS Dark Mode directly via Windows Registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`).
  * Queries modern Windows 10/11 system accent colors via `HKCU\Software\Microsoft\Windows\DWM\AccentColor` (ABGR).
  * Dynamically enforces Qt's `Fusion` style on Windows so that all widgets (buttons, comboboxes, scrollbars, headers) follow `QPalette` colors.
  * Sanitizes the global stylesheet so `palette(highlighted-text)` is used rather than `#000000`.
* **`windows/entrypoint_windows.py`**: Bootstraps the theme fixes before launching `src.main.main()`.
* **`windows/patches/`**: Contains a clean unified diff patch (`0001-windows-theming-and-fusion-fixes.patch`) if a CI build chooses source-level patching instead of runtime hooks.

---

## 2. Directory Structure

```
windows/
├── CMakeLists.txt                # CMake build orchestrator & packaging targets
├── CMakePresets.json             # Presets (windows-release, windows-debug)
├── bengal-download-manager.spec  # PyInstaller packaging specification
├── installer.iss                 # Inno Setup 6 installer script (modern wizard)
├── entrypoint_windows.py         # Windows launcher wrapper with theme hooks
├── README.md                     # This documentation
├── assets/
│   └── app_icon.ico              # Multi-resolution Windows app icon (16 to 256px)
├── patches/
│   └── 0001-windows-theming-and-fusion-fixes.patch  # Standalone source patch
├── scripts/
│   ├── build_windows.ps1         # PowerShell build & release pipeline
│   └── build_windows.sh          # Bash / Git-Bash / CI build script
└── theme_fix/
    ├── __init__.py               # Python module exports
    └── windows_theme_fix.py      # DWM, Fusion style, and registry integration
```

---

## 3. How to Build on Windows

### Prerequisites
* **Python 3.10+** (managed via `uv` or system Python)
* **PyQt6** (`uv pip install PyQt6`)
* **PyInstaller** (`uv pip install pyinstaller`)
* **Inno Setup 6** (for installer generation, download from [jrsoftware.org](https://jrsoftware.org/isdl.php))
* **7-Zip** (optional, for portable archive creation)

---

### Method A: Using PowerShell (Recommended)
From PowerShell inside the repository root:
```powershell
.\windows\scripts\build_windows.ps1
```
* **Parameters**:
  * `-Version "0.2.46"` : Override version string (defaults to `VERSION` file).
  * `-SkipBuild` : Skip PyInstaller compilation.
  * `-SkipInstaller` : Skip Inno Setup compiler.
  * `-SkipArchive` : Skip portable ZIP packaging.
  * `-SkipBinaries` : Skip downloading `yt-dlp.exe` and `aria2c.exe`.

---

### Method B: Using CMake & CMake Presets (Stellar Style)
```powershell
# 1. Configure the build
cmake --preset windows-release

# 2. Build executable, compile installer, and package ZIP
cmake --build --preset windows-release
```

Specific targets can also be invoked:
```powershell
cmake --build --preset windows-release --target build_windows     # Standalone exe only
cmake --build --preset windows-release --target package_installer # Inno Setup installer
cmake --build --preset windows-release --target package_portable  # Portable ZIP
```

---

### Method C: Using Git-Bash or CI
```bash
bash windows/scripts/build_windows.sh
```

---

## 4. Build Outputs

All artifacts are generated in `dist/`:
1. **Standalone Application Directory**:
   `dist/bengal-download-manager/` (contains `bengal-download-manager.exe` + assets and Qt plugins)
2. **Inno Setup Installer**:
   `dist/windows/BengalSetup-<version>.exe`
3. **Portable ZIP Archive**:
   `dist/windows/bengal-download-manager-<version>-windows-x64.zip`
