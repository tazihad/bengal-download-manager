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
  * Implemented HWND memoization cache to eliminate focus/activation loops.
  * Wired `QGuiApplication::focusWindowChanged` for automatic dark caption styling on all modal dialogs.
  * Added dynamic style switching: enforces Qt `Fusion` style in Dark Mode (bypassing UxTheme light bitmap bugs) while preserving native `windowsvista` style in Light Mode.
  * Added Windows Dark Mode control overrides (`QHeaderView::section`, `QComboBox`, `QPushButton`, `QGroupBox`, `QScrollBar`) to eliminate white-on-white text and dark groupbox titles.
  * Fixed relative module imports in `build/windows/fixes/theme_fix/__init__.py`.
  * Added safe Windows binary resolver for `aria2` to prevent `OSError: [WinError 193] %1 is not a valid Win32 application` from Linux ELF binaries.
  * Updated standalone patch `build/windows/patches/0001-windows-theming-and-fusion-fixes.patch`.
  * Added toolchain definitions: `toolchain-msvc.cmake` and `toolchain-mingw.cmake`.
* **Linux Build System**:
  * Added GCC and Clang toolchain configurations (`toolchain-gcc.cmake`, `toolchain-clang.cmake`).
  * Integrated custom CMake targets for Standalone Binary, AppImage, Flatpak, and Snap packages.
* **macOS Build Structure**:
  * Reserved `build/macos/` directory structure for future macOS build and codesigning pipelines.
