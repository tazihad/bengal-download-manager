# Plan: Build .deb packages via OBS (Debian 13) and Launchpad PPA (Ubuntu 24.04 & 26.04)

## Goal
Publish Bengal Download Manager as installable `.deb` packages through:
- **openSUSE Build Service (OBS)**: `https://build.opensuse.org/` — target Debian 13 (trixie/sid)
- **Launchpad PPA**: Ubuntu 24.04 LTS (noble) and Ubuntu 26.04 LTS

Both services build from **source packages**, not prebuilt binaries. The plan reuses your existing PyInstaller onefile binary pipeline as the payload inside a native `.deb` source package.

## Context (from codebase)
- Version source of truth: `VERSION` file (`0.3.12`), synced via `scripts/sync_version.py` (AGENTS.md #6)
- Existing builds: Flatpak, Snap, AppImage, PyInstaller onefile (`scripts/build_binary.sh`, `bengal-download-manager.spec`)
- Existing desktop entry: `flatpak/bd.com.zihad.BengalDownloadManager.desktop`
- Existing metainfo: `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml`
- Dependencies: PyQt6 (bundled in binary), aria2c (system package), desktop-file-install dependencies
- No `debian/` directory exists yet

## Design decisions

### D1 — Native .deb source package with bundled binary (recommended)
Create a `debian/` directory at repo root. `debian/rules` runs `scripts/build_binary.sh` to produce the PyInstaller onefile binary, then installs it to `/opt/bengal-download-manager/`, symlinks `/usr/bin/bengal-download-manager`, and installs `.desktop` + metainfo files. `Depends: aria2` only (PyQt6 bundled).
- Pro: single `debian/` tree serves both OBS (as .deb build) and PPA (as source upload)
- Pro: no PyQt6 version drift across Ubuntu/Debian releases
- Con: larger download (~50–100 MB)

### D2 — Version sync
`debian/changelog` version must match `VERSION` file. `scripts/sync_version.py` keeps `VERSION`, `snap/snapcraft.yaml`, `flatpak/metainfo.xml` in sync (AGENTS.md #6). Add `.deb` version to sync list or derive changelog version from `VERSION`.

### D3 — Target matrix
| Service | Distro | Version | Package |
|---------|--------|---------|---------|
| OBS | Debian | 13 (trixie/sid) | .deb |
| Launchpad PPA | Ubuntu | 24.04 LTS (noble) | .deb |
| Launchpad PPA | Ubuntu | 26.04 LTS | .deb |

### D4 — Build flow
1. `scripts/sync_version.py` bumps `VERSION`
2. Update `debian/changelog` to match `VERSION`
3. Build source package: `dpkg-buildpackage -S` (or `debuild -S`)
4. Upload `.changes` to PPA (Launchpad) or submit `.dsc`/SRPM to OBS
5. Services build binary `.deb` for each target distro

## Files to create

### `debian/control`
```
Source: bengal-download-manager
Section: net
Priority: optional
Maintainer: <maintainer-name> <maintainer-email>
Build-Depends: debhelper (>= 12), pyinstaller, python3, python3-pyqt6, aria2
Standards-Version: 4.6.0

Package: bengal-download-manager
Architecture: amd64
Depends: ${shlibs:Depends}, aria2, ${misc:Depends}
Description: High-performance multi-threaded download manager with Aria2 and PyQt6
 Bengal Download Manager is a high-performance, multi-threaded download manager
 built with PyQt6 and Aria2. Features chunked HTTP downloading, Aria2 RPC
 integration, browser extension, and a modern Qt6 UI.
```

### `debian/changelog`
```
bengal-download-manager (<VERSION>) noble; urgency=medium

  * New upstream release

 -- <maintainer-name> <maintainer-email>  <date>
```
(Version derived from `VERSION` file via `scripts/sync_version.py`)

### `debian/rules`
```makefile
#!/usr/bin/make -f
%:
	dh $@

override_dh_auto_build:
	cd $(CURDIR) && scripts/build_binary.sh

override_dh_auto_install:
	dh_auto_install
	install -d debian/bengal-download-manager/opt/bengal-download-manager
	install -m 0755 dist/bengal-download-manager debian/bengal-download-manager/opt/bengal-download-manager/
	install -d debian/bengal-download-manager/usr/bin
	ln -sf /opt/bengal-download-manager/bengal-download-manager debian/bengal-download-manager/usr/bin/bengal-download-manager
	install -d debian/bengal-download-manager/usr/share/applications
	install -m 0644 flatpak/bd.com.zihad.BengalDownloadManager.desktop debian/bengal-download-manager/usr/share/applications/
	install -d debian/bengal-download-manager/usr/share/metainfo
	install -m 0644 flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml debian/bengal-download-manager/usr/share/metainfo/
```

### `debian/compat`
```
12
```

### `debian/source/format`
```
3.0 (native)
```

### Scripts integration
- `scripts/sync_version.py`: add `.deb` version sync (derive `debian/changelog` version from `VERSION`)
- `scripts/build_deb.sh` (optional): local `dpkg-deb` wrapper for testing before upload

## Branch & commit
- Create local branch `feature/debian-packaging`.
- Commit changes locally; do NOT push.
- Open PR against `main` (do not merge).

## Validation
- `dpkg-buildpackage -S` produces a source package (`.dsc`, `.tar.gz`, `.changes`)
- `dpkg-deb -I <binary-deb>` shows correct control fields (Package, Version, Architecture, Depends)
- `dpkg-deb -c <binary-deb>` lists `/opt/bengal-download-manager/`, `/usr/bin/bengal-download-manager`, `.desktop`, metainfo
- Local install test: `dpkg -i <deb>` on Debian 13/Ubuntu 24.04 container; `bengal-download-manager` launches
- `scripts/sync_version.py check` confirms version consistency across `VERSION`, `snap/snapcraft.yaml`, `flatpak/metainfo.xml`, `debian/changelog`

## Risks / open questions
- OBS primarily builds RPMs; building .deb on OBS requires configuring Debian target repos and may need OBS `_service` files or manual .dsc submission. Confirm OBS Debian 13 .deb build support before relying on it.
- PPA only accepts Ubuntu source packages; Debian 13 cannot be built via PPA (use OBS or direct `dpkg-deb` for Debian).
- Maintainer name/email for `debian/control` and `debian/changelog` — use repo contact or set placeholder.
- PyInstaller build inside `debian/rules` requires network access to download dependencies at build time; ensure build environment has network or vendor PyInstaller.
- Confirm architecture: amd64 only, or add arm64 later?
- Debian 13 (trixie/sid) is not yet released — verify target name when building.
