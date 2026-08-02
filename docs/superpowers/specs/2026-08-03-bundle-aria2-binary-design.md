# Technical Design Specification: Embedded aria2c Binary Bundling & Multi-Arch Release

## 1. Executive Summary
This design specification defines the implementation strategy for embedding static `aria2c` binaries into **Bengal Download Manager**. This eliminates the external system dependency (`sudo apt install aria2` or runtime binary downloading) and provides a 100% self-contained, offline experience out of the box. Additionally, it updates the GitHub Actions CI/CD release workflow to compile, test, and release binaries for both `x86_64` and `aarch64` architectures.

## 2. Architecture & Binary Assets

### 2.1 Repository Structure
Pre-compiled static binaries for `aria2c` will be stored under `assets/bin/`:
```
assets/
└── bin/
    ├── x86_64/
    │   └── aria2c
    └── aarch64/
        └── aria2c
```

### 2.2 Arch-Aware Binary Resolution (`src/core/utils.py`)
`find_aria2()` will detect the host platform architecture using `platform.machine()` and prioritize bundled assets:
1. `sys._MEIPASS/assets/bin/<arch>/aria2c` (PyInstaller bundled single-file path)
2. `/app/bin/aria2c` (Flatpak sandbox bin path)
3. `<repo_root>/assets/bin/<arch>/aria2c` (Development / source path)
4. System PATH via `shutil.which("aria2c")`
5. Local data directory (`~/.local/share/bengal-download-manager/bin/aria2c`)
6. Fallback dynamic fetcher in `ensure_aria2()` (for unsupported edge architectures)

## 3. Build & Packaging Integration

### 3.1 PyInstaller Integration
Update PyInstaller configurations to include `assets/bin/` with `--add-data "assets:assets"`. PyInstaller unpacks these binaries to `sys._MEIPASS` at runtime.

### 3.2 Flatpak Integration
Update Flatpak manifest (`flatpak/io.github.tazihad.bengal-download-manager.yml`) and local build script (`scripts/build_and_run_flatpak.sh`):
```bash
cp assets/bin/$ARCH/aria2c $BUILD_DIR/files/bin/aria2c
```

## 4. Multi-Arch CI/CD Release Pipeline (`.github/`)

### 4.1 Release Workflow Updates (`.github/workflows/release.yml`)
- Update `release.yml` with a build matrix:
  - `x86_64` running on `ubuntu-latest`
  - `aarch64` running on `ubuntu-24.04-arm` (or ARM runners)
- Collect build artifacts from both architecture targets.

### 4.2 Release Artifacts
GitHub Releases will publish:
- `bengal-download-manager-<version>-x86_64`
- `bengal-download-manager-<version>-aarch64`
- `bengal-download-manager-<version>-x86_64.AppImage`
- `bengal-download-manager-<version>-aarch64.AppImage`
- `bengal-download-manager-<version>-x86_64.flatpak`
- `bengal-download-manager-<version>-aarch64.flatpak`
- Chrome and Firefox extension packages (`.crx`, `.xpi`)

## 5. Verification & Testing Strategy
1. **Unit Tests**: Test `find_aria2()` architecture resolution across `x86_64` and `aarch64` under mocked environments.
2. **PyInstaller Build Verification**: Ensure PyInstaller binary correctly identifies and executes bundled `aria2c`.
3. **Flatpak Build Verification**: Ensure Flatpak package contains `aria2c` in `/app/bin/aria2c`.
