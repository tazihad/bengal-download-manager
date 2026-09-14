# Multiplatform Build System Changelog

All notable architectural and configuration changes to the Bengal Download Manager multiplatform build infrastructure will be documented in this file.

## [0.2.46] - 2026-09-14

### Added
* **Multiplatform Build Architecture**:
  * Established modular `build/` layout (`common/`, `windows/`, `linux/`, `macos/`).
  * Added conditional root `build/CMakeLists.txt` and repository `CMakeLists.txt`.
  * Added shared CMake helper modules in `build/common/cmake/modules/`: `VersionHelper.cmake`, `FindPyQt6.cmake`, `PackagingHelper.cmake`.
* **Windows Build & Theming System**:
  * Integrated native Win32 Desktop Window Manager (DWM) Immersive Dark Mode (`DwmSetWindowAttribute` attributes 20 & 19).
  * Implemented HWND memoization cache to eliminate focus/activation loops (Stellar architecture).
  * Wired `QGuiApplication::focusWindowChanged` for automatic dark caption styling on all modal dialogs.
  * Added dynamic enforcement of Qt `Fusion` style on Windows to resolve `windowsvista` UxTheme light bitmap conflicts.
  * Added Windows 10/11 Registry detection for OS dark mode (`AppsUseLightTheme`) and modern accent colors (`HKCU\Software\Microsoft\Windows\DWM\AccentColor`).
  * Added stylesheet sanitizer ensuring `palette(highlighted-text)` is used rather than hardcoded `#000000`.
  * Added PyInstaller specification (`build/windows/config/bengal-download-manager.spec`) and Inno Setup installer script (`build/windows/config/installer.iss`).
  * Added automated PowerShell (`build_windows.ps1`) and Bash (`build_windows.sh`) build pipelines.
  * Added toolchain definitions: `toolchain-msvc.cmake` and `toolchain-mingw.cmake`.
* **Linux Build System**:
  * Added GCC and Clang toolchain configurations (`toolchain-gcc.cmake`, `toolchain-clang.cmake`).
  * Integrated custom CMake targets for Standalone Binary, AppImage, Flatpak, and Snap packages.
* **macOS Build Structure**:
  * Reserved `build/macos/` directory structure for future macOS build and codesigning pipelines.
