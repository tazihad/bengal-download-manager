# Version Management & Single Source of Truth (SSOT) Guide

This document defines the authoritative versioning architecture, release lifecycle, and manual developer procedures for Bengal Download Manager.

---

## 1. Architectural Philosophy: Single Source of Truth (SSOT)

Bengal Download Manager targets multiple distribution channels:
* **Canonical Snap Store**: Snap package built via Snapcraft (`snap/snapcraft.yaml`).
* **Flatpak / Flathub**: Flatpak bundle and AppStream catalog metadata (`flatpak/io.github.tazihad.bengal-download-manager.metainfo.xml`).
* **In-App Runtime**: Help -> About Dialog, CLI `--version`, and IPC daemon (`src/core/version.py`).
* *(Note: Browser extension in `extension/manifest.json` is versioned independently, e.g. `0.4`).*

### The Canonical File
The root file **`VERSION`** is the single authoritative source of truth for the application version. No other file should be edited manually to change versions.

```
                              ┌─────────────────────────┐
                              │  Canonical SSOT:        │
                              │  `VERSION` (e.g. 0.2.25)│
                              └────────────┬────────────┘
                                           │
                           `python3 scripts/sync_version.py`
                                           │
         ┌───────────────────┬─────────────┴─────────────────────────┐
         ▼                   ▼                                       ▼
  ┌──────────────┐    ┌──────────────┐                        ┌──────────────┐
  │  snapcraft   │    │   flatpak    │                        │  In-App UI   │
  │    .yaml     │    │ metainfo.xml │                        │ (version.py) │
  └──────────────┘    └──────────────┘                        └──────────────┘
```

---

## 2. Manual Developer Workflows

The repository provides [`scripts/sync_version.py`](file:///run/media/zihad/data/dev/bengal-download-manager/scripts/sync_version.py) to manage application version manifests atomically.

### Option A: Set an Explicit Version (Recommended)
```bash
# 1. Update VERSION, snapcraft.yaml, metainfo.xml, and runtime
python3 scripts/sync_version.py --set 0.2.25

# 2. Check that all files are 100% in sync
python3 scripts/sync_version.py --check

# 3. Commit and push to GitHub
git commit -am "chore(release): bump version to 0.2.25"
git push origin main
```

---

### Option B: One-Shot Bump + Commit + Git Tag (Atomic Release)
```bash
# Automatically increments patch (e.g., 0.2.24 -> 0.2.25), updates manifests, creates commit & tag
python3 scripts/sync_version.py --bump patch --commit --tag

# Push the release commit and tag together
git push origin main --tags
```

---

### Option C: Create an Alpha / Pre-Release
```bash
# Automatically detects latest release tag in Git and advances to upcoming alpha (e.g. 0.2.26-alpha.1)
python3 scripts/sync_version.py --bump alpha --commit --tag

# Push branch and tag to GitHub
git push origin <branch-name> --tags
```

---

### Option D: If You Prefer Editing Files by Hand in Your Editor
1. **Edit the `VERSION` file**:
   ```bash
   echo "0.2.25" > VERSION
   ```

2. **Sync the other manifest files with one command**:
   ```bash
   python3 scripts/sync_version.py --set $(cat VERSION)
   ```
   *(This automatically writes `0.2.25` to `snap/snapcraft.yaml`, `flatpak/metainfo.xml`, and `src/core/version.py`).*

3. **Verify consistency**:
   ```bash
   python3 scripts/sync_version.py --check
   ```

4. **Commit and Push**:
   ```bash
   git add .
   git commit -m "chore(release): bump version to 0.2.25"
   git push origin main
   ```

---

## 3. How Release Channels React to Your Push

| Channel | What Happens When You Push to `main` |
|---|---|
| **GitHub Releases** | GitHub Actions reads `VERSION`, builds all binaries (`AppImage`, `Flatpak`, `Snap`, `Standalone Binary`, `Extensions`), creates the GitHub release and tags `v0.2.25`. |
| **Snap Store (snapcraft.io)** | Snapcraft.io's build service clones `main`, reads `version: '0.2.25'` directly from `snap/snapcraft.yaml`, builds and publishes `0.2.25` to the Snap Store. |
| **Flatpak / Flathub** | Uses the updated `<release version="0.2.25" .../>` in `io.github.tazihad.bengal-download-manager.metainfo.xml`. |
| **In-App (Help -> About)** | Automatically displays `0.2.25` from `VERSION` and `SNAP_VERSION`. |

---

## 4. Release Lifecycle & CI/CD Pipeline

1. **Pull Requests & Commits (`ci.yml`)**:
   - `python3 scripts/sync_version.py --check` automatically executes on every commit and PR.
   - If any manifest does not match `VERSION`, CI fails immediately with actionable instructions.

2. **Automated Builds & Releases (`release.yml`)**:
   - Pushes to `main` (stable) or `dev` (alpha) trigger the release workflow.
   - The workflow reads the canonical `VERSION` file, produces all binaries and package formats with that exact version, and creates the GitHub Release.

3. **Snap Store Synchronization**:
   - Because `snap/snapcraft.yaml` is pre-synchronized to the exact version in Git, Canonical's Snapcraft Build Service builds and publishes the exact matching release version to `snapcraft.io/bengal-download-manager` without race conditions or tag guessing.

---

## 5. Guidelines for AI Agents and Contributors

1. **Never edit application version strings manually in individual package manifests**. Always use `scripts/sync_version.py --set <ver>` or `--bump <type>`.
2. **Run `python3 scripts/sync_version.py --check` before committing** any changes related to versioning or packaging.
3. **Browser extension versioning is independent**: `extension/manifest.json` is decoupled from app version bumps and managed independently.
