# Bengal Download Manager — Windows Build & Theming System

This directory contains the complete build orchestration, packaging configuration, and native Windows theming integration for **Bengal Download Manager (BDM)** on Windows 10 and 11.

---

## 1. Architectural Overview 

In Bengal Download Manager, Windows theming operates flawlessly because of three foundational design choices:
1. **Direct Win32 DWM Immersive Dark Mode**: Bengal Download Manager uses the Win32 Desktop Window Manager API (`dwmapi.dll`) with `DwmSetWindowAttribute` (attribute `20` on Windows 10 1903+ / Windows 11, and attribute `19` on early 1809 builds).
2. **Dynamic Focus Hooking**: Bengal Download Manager hooks `QGuiApplication::focusWindowChanged` to guarantee that every modal dialog or lazily instantiated popup automatically receives dark window caption styling upon appearance.
3. **Isolation from UxTheme Engine**: Bengal Download Manager uses Qt Quick/Material with explicit semantic tokens (`ColorPalette.qml`), completely bypassing the legacy `windowsvista` QStyle engine.

### Why BDM Had Theme Mismanagement on Windows:
* **Missing DWM Title Bar Calls**: BDM left Win32 caption bars untouched, causing stark-white title bars even when dark themes (BDM Dark, Dracula, Nord, One Dark) were active.
* **The `windowsvista` Style Conflict**: On Windows, PyQt6 defaults to `windowsvista` QStyle. This style forces Windows UxTheme light bitmap assets for buttons, comboboxes, scrollbars, and spinboxes. When BDM applied dark palettes, text was inverted to light, resulting in white text on white buttons and light scrollbars across dark tables.
* **Hardcoded `#000000` Selection Text**: Global stylesheets hardcoded black text on highlights, making selections unreadable when using dark accents like Windows Blue (`#0078d4`).
* **Broken Auto-Theme Detection**: BDM's "Auto" mode fell back to `app.style().standardPalette()`, which always reports light mode on Windows under `windowsvista`.

### How This Windows Build Fixes It (Without Touching Core App Files):
* **Zero-Touch Modular Architecture**: All core application code in `src/` remains untouched.
* **`windows/theme_fix/windows_theme_fix.py`**:
  * Implements Win32 `DwmSetWindowAttribute(hwnd, 20/19)` with an HWND memoization cache to prevent recursive focus/activation storms.
  * Hooks `QGuiApplication.focusWindowChanged` to theme all dialogs as they open.
  * Detects OS Dark Mode directly via Windows Registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`).
  * Queries modern Windows 10/11 system accent colors via `HKCU\Software\Microsoft\Windows\DWM\AccentColor` (ABGR).
  * Dynamically switches style: enforces `Fusion` in Dark Mode and preserves `windowsvista` in Light Mode.
  * Injects Windows Dark Mode control overrides (`QHeaderView`, `QComboBox`, `QPushButton`, `QGroupBox`, `QScrollBar`).
  * Sanitizes the global stylesheet so `palette(highlighted-text)` is used rather than `#000000`.
  * Protects `find_aria2` and `ensure_aria2` from returning Linux ELF binaries on Windows, preventing `[WinError 193]`.
  * Sets Win32 `AppUserModelID` (`SetCurrentProcessExplicitAppUserModelID`) and resolves native `assets/app_icon.ico` so the Windows taskbar displays the Bengal Download Manager icon instead of Python's.
* **`build/windows/fixes/entrypoint_windows.py`**: Bootstraps the theme and aria2 fixes before launching `src.main.main()`.
* **`build/windows/patches/`**:
  * `0001-windows-theming-and-fusion-fixes.patch`: Comprehensive source patch (theming, DWM, dark controls QSS, aria2 safety).
  * `0002-windows-aria2-binary-fix.patch`: Focused patch resolving the Linux aria2 ELF execution and daemon spawn error on Windows.

---

## 2. Directory Structure

```
build/windows/
├── CMakeLists.txt                # CMake build orchestrator & packaging targets
├── CMakePresets.json             # Presets (windows-release, windows-debug)
├── config/
│   ├── bengal-download-manager.spec  # PyInstaller packaging specification
│   └── installer.iss                 # Inno Setup 6 installer script (modern wizard)
├── fixes/
│   ├── entrypoint_windows.py         # Windows launcher wrapper with theme hooks
│   └── theme_fix/
│       ├── __init__.py               # Python module exports
│       └── windows_theme_fix.py      # DWM, Fusion style, and aria2 safety
├── patches/
│   ├── 0001-windows-theming-and-fusion-fixes.patch  # Complete Windows parity patch
│   └── 0002-windows-aria2-binary-fix.patch          # Focused aria2 WinError 193 fix
├── build-scripts/
│   ├── build_windows.ps1         # PowerShell build & release pipeline
│   └── build_windows.sh          # Bash / Git-Bash / CI build script
└── README-windows.md             # This documentation
```

---

## 3. How to Run in Development Mode with Patches (`python src\main.py`)

You can run Bengal Download Manager directly from Python on Windows without compiling a binary.

### Prerequisites

1. **Python 3.10+** (managed via `uv` or system Python).
2. **Environment & Dependencies**:
   ```powershell
   # Using uv (Recommended):
   uv venv
   .venv\Scripts\activate
   uv pip install -r requirements.txt

   # Or using standard python:
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. **`aria2c.exe`**:
   The app will automatically download `aria2c.exe` to `%LOCALAPPDATA%\bengal-download-manager\bin\aria2c.exe` on first run, or you can place `aria2c.exe` into `bin\aria2c.exe` or `build\windows\bin\aria2c.exe`.

---

### Option A: Direct Run with Patches (Recommended)

If your working branch already has the fixes in `src/`, or after applying the unified patches:

#### 1. Apply Patches (if working from a clean/upstream clone):
```powershell
# From repository root:
git apply build/windows/patches/0001-windows-theming-and-fusion-fixes.patch
git apply build/windows/patches/0002-windows-aria2-binary-fix.patch
```

#### 2. Run with `PYTHONPATH=src`:

**In PowerShell:**
```powershell
$env:PYTHONPATH = "src"
python src\main.py

# Or with uv:
$env:PYTHONPATH = "src"
uv run python src\main.py
```

**In Command Prompt (`cmd.exe`):**
```cmd
set PYTHONPATH=src
python src\main.py
```

**In Git Bash:**
```bash
PYTHONPATH=src python src/main.py
```

---

### Option B: Zero-Modification Launcher (No changes to `src/`)

If you wish to keep `src/` completely clean and unmodified, run through the Windows launcher script. It injects `src` into `sys.path` and hot-patches theming and aria2 binary resolution dynamically in memory:

```powershell
# In PowerShell:
python build\windows\fixes\entrypoint_windows.py

# Or with uv:
uv run python build\windows\fixes\entrypoint_windows.py
```

---

### Option C: Running KDE Kirigami QML Mode on Windows

```powershell
$env:PYTHONPATH = "src"
python src\main.py --kirigami
```

---

### Running Automated Tests on Windows

```powershell
$env:PYTHONPATH = "src"
uv run pytest -v tests/
```

---

### Windows Troubleshooting

* **`ModuleNotFoundError: No module named 'core'`**: Ensure `$env:PYTHONPATH = "src"` is set before running `python src\main.py`.
* **`[WinError 193] %1 is not a valid Win32 application`**: Ensure patch `0002-windows-aria2-binary-fix.patch` is applied or run with `entrypoint_windows.py`. Ensure any Linux ELF binary named `aria2c` in local folders is removed.
* **PowerShell script execution error (`Activate.ps1 cannot be loaded`)**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.

---

## 4. How to Build on Windows

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
python -m pip install -r requirements.txt
python -m pip install --upgrade pip
python -m pip install pyinstaller
```

```powershell
.\build\windows\build-scripts\build_windows.ps1
```
* **Parameters**:
  * `-Version "0.2.46"` : Override version string (defaults to `VERSION` file).
  * `-SkipBuild` : Skip PyInstaller compilation.
  * `-SkipInstaller` : Skip Inno Setup compiler.
  * `-SkipArchive` : Skip portable ZIP packaging.
  * `-SkipBinaries` : Skip downloading `yt-dlp.exe` and `aria2c.exe`.

---

### Method B: Using CMake & CMake Presets
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

## 5. Build Outputs

All artifacts are generated in `dist/`:
1. **Standalone Application Directory**:
   `dist/bengal-download-manager/` (contains `bengal-download-manager.exe` + assets and Qt plugins)
2. **Inno Setup Installer**:
   `dist/windows/BengalSetup-<version>.exe`
3. **Portable ZIP Archive**:
   `dist/windows/bengal-download-manager-<version>-windows-x64.zip`
