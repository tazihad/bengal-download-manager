# Version Management & Single Source of Truth (SSOT) Guide

This document defines the authoritative versioning architecture and release lifecycle for Bengal Download Manager.

---

## 1. Architectural Philosophy: Single Source of Truth (SSOT)

Bengal Download Manager targets multiple distribution channels:
* **GitHub Releases**: Linux Standalone Executable, AppImage + ZSync, Browser Extensions (.crx, .xpi).
* **Canonical Snap Store**: Snap package built via Snapcraft (`snap/snapcraft.yaml`).
* **Flatpak / Flathub**: Flatpak bundle and AppStream catalog metadata (`flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml`).
* **Browser Extension Stores**: Chrome / Edge / Firefox extensions (`extension/manifest.json`).
* **In-App Runtime**: Help -> About Dialog, CLI `--version`, and IPC daemon (`src/core/version.py`).

### The Canonical File
The root file **`VERSION`** is the single authoritative source of truth for the application version. No other file should be edited manually to change versions.

```
                              ┌─────────────────────────┐
                              │  Canonical SSOT:        │
                              │  `VERSION` (e.g. 0.2.20)│
                              └────────────┬────────────┘
                                           │
                           `python3 scripts/sync_version.py`
                                           │
         ┌───────────────────┬─────────────┴─────────────┬───────────────────┐
         ▼                   ▼                           ▼                   ▼
  ┌──────────────┐    ┌──────────────┐            ┌──────────────┐    ┌──────────────┐
  │  snapcraft   │    │   flatpak    │            │  extension   │    │  In-App UI   │
  │    .yaml     │    │ metainfo.xml │            │manifest.json │    │ (version.py) │
  └──────────────┘    └──────────────┘            └──────────────┘    └──────────────┘
```

---

## 2. The Version Synchronizer CLI (`scripts/sync_version.py`)

A dedicated script [`scripts/sync_version.py`](file:///run/media/zihad/data/dev/bengal-download-manager/scripts/sync_version.py) automates version checks, bumps, manifest updates, and Git tagging.

### Common Commands

#### 1. Check Consistency Across All Manifests
```bash
python3 scripts/sync_version.py --check
```
*Validates that `VERSION`, `snapcraft.yaml`, `metainfo.xml`, `manifest.json`, and runtime files match. Used by CI to prevent accidental mismatches.*

#### 2. Bump Version for a New Release
```bash
# Patch release (e.g., 0.2.20 -> 0.2.21)
python3 scripts/sync_version.py --bump patch

# Minor release (e.g., 0.2.20 -> 0.3.0)
python3 scripts/sync_version.py --bump minor

# Major release (e.g., 0.2.20 -> 1.0.0)
python3 scripts/sync_version.py --bump major

# Alpha / Pre-release (e.g., 0.2.20 -> 0.2.21-alpha.1)
python3 scripts/sync_version.py --bump alpha
```

#### 3. Atomic Bump + Commit + Git Tag
```bash
# Bumps version, updates all manifests, creates git commit and annotated tag vX.Y.Z
python3 scripts/sync_version.py --bump patch --commit --tag

# Push release and tags to GitHub
git push origin HEAD --tags
```

#### 4. Explicit Version Set
```bash
python3 scripts/sync_version.py --set 0.2.20-alpha.1
```

---

## 3. Release Lifecycle & CI/CD Pipeline

1. **Pull Requests & Commits (`ci.yml`)**:
   - `python3 scripts/sync_version.py --check` automatically executes on every commit and PR.
   - If any manifest does not match `VERSION`, CI fails immediately with actionable instructions.

2. **Automated Builds & Releases (`release.yml`)**:
   - Pushes to `main` (stable) or `dev` (alpha) trigger the release workflow.
   - The workflow reads the canonical `VERSION` file, produces all binaries and package formats with that exact version, and creates the GitHub Release.

3. **Snap Store Synchronization**:
   - Because `snap/snapcraft.yaml` is pre-synchronized to the exact version in Git, Canonical's Snapcraft Build Service builds and publishes the exact matching release version to `snapcraft.io/bengal-download-manager` without race conditions or tag guessing.

---

## 4. Guidelines for AI Agents and Contributors

1. **Never edit version strings manually in individual manifest files**. Always use `scripts/sync_version.py --set <ver>` or `--bump <type>`.
2. **Run `python3 scripts/sync_version.py --check` before committing** any changes related to versioning or packaging.
3. **Keep extension manifest versions semver-compliant**: Extension manifests require numeric dot-separated integers (e.g. `0.2.20.1` for `0.2.20-alpha.1`); `scripts/sync_version.py` handles this conversion automatically.
