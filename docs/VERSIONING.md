# Version Management & Single Source of Truth (SSOT) Guide

This document defines the authoritative versioning architecture, release lifecycle, and manual developer procedures for Bengal Download Manager.

---

## 1. Architectural Philosophy: Single Source of Truth (SSOT)

Bengal Download Manager targets multiple distribution channels:
* **Canonical Snap Store**: Snap package built via Snapcraft (`snap/snapcraft.yaml`).
* **Flatpak / Flathub**: Flatpak bundle and AppStream catalog metadata (`flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml`).
* **Python Packaging (PEP 517/518/621)**: Package manifest and dynamic versioning (`pyproject.toml`).
* **In-App Runtime**: Help -> About Dialog, CLI `--version`, and IPC daemon (`src/core/version.py`).
* *(Note: Browser extension in `extension/manifest.json` is versioned independently, e.g. `0.6`).*

### The Canonical File
The root file **`VERSION`** is the single authoritative source of truth for the application version. No other file should be edited manually to change versions.

```
                              ┌─────────────────────────┐
                              │  Canonical SSOT:        │
                              │  `VERSION` (e.g. 0.3.12)│
                              └────────────┬────────────┘
                                           │
                            `uv run python scripts/sync_version.py`
                                           │
          ┌───────────────────┬─────────────┴─────────────────────────┐
          ▼                   ▼                                       ▼
   ┌──────────────┐    ┌──────────────┐                        ┌──────────────┐
   │  snapcraft   │    │   flatpak    │                        │  In-App UI   │
   │    .yaml     │    │ metainfo.xml │                        │ (version.py) │
   └──────────────┘    └──────────────┘                        └──────────────┘
```

All commands below use `uv run python` per project convention (see AGENTS.md).

---

## 2. Command Reference

Run from the repository root:

```bash
# Check all manifests match VERSION (exits non-zero on mismatch)
uv run python scripts/sync_version.py --check

# Set an exact version across all manifests
uv run python scripts/sync_version.py --set 0.3.12-alpha.3

# Auto-bump: patch / minor / major / alpha
uv run python scripts/sync_version.py --bump patch --tag --commit

# Graduate an alpha/prerelease back to stable (strips -alpha.N suffix)
uv run python scripts/sync_version.py --graduate --tag --commit
```

Flags `--tag` and `--commit` are optional and work with `--set`, `--bump`, and `--graduate`.

**Auto consistency check:** Any command that writes a new version (`--set`, `--bump`, `--graduate`) automatically runs `--check` before committing or tagging. If manifests are out of sync, it aborts with an error message — no commit, no tag.

---

## 3. Alpha vs Stable Release Usage

The version string itself determines release type:
* **Stable**: `X.Y.Z` (no suffix), e.g. `0.3.12`
* **Alpha / prerelease**: `X.Y.Z-alpha.N` (with `-alpha.N` suffix), e.g. `0.3.12-alpha.3`

### Release an Alpha

```bash
# Example: current is 0.3.12-alpha.1 -> release 0.3.12-alpha.3
uv run python scripts/sync_version.py --set 0.3.12-alpha.3 --tag --commit
```

This writes `0.3.12-alpha.3` to `VERSION`, `snap/snapcraft.yaml`, `flatpak/metainfo.xml`, `src/core/version.py`, and `src/core/build_info.py`, then creates git tag `v0.3.12-alpha.3` and a commit.

```bash
# Push the alpha branch and tag (do NOT merge to main)
git push origin <branch-name> --tags
```

### Release a Stable Version

```bash
# Example: graduate or set stable 0.3.12
uv run python scripts/sync_version.py --set 0.3.12 --tag --commit

# Or graduate the current alpha to stable
uv run python scripts/sync_version.py --graduate --tag --commit
```

```bash
# Push the stable branch and tag
git push origin <branch-name> --tags
```

### Increment the Next Alpha

When the current version is already an alpha (e.g. `0.3.12-alpha.3`):

```bash
# Advances to 0.3.12-alpha.4 automatically
uv run python scripts/sync_version.py --bump alpha --tag --commit
```

---

## 4. Branch & Merge Rules

* Do all version bumps on a feature/release branch, **not** on `main`.
* Open a PR against `main` but **do not merge** until you are ready to release.
* `main` is updated only when a stable release is graduated and merged.
* Push tags separately: `git push origin <branch-name> --tags`.

---

## 5. Verify Before Committing

Always run the consistency check after setting a version:

```bash
uv run python scripts/sync_version.py --check
# Expect: [✓] All manifests match canonical VERSION: 0.3.12-alpha.3
```

If `--check` reports mismatches, fix them before committing.

---

## 6. How Release Channels React to Your Push

| Channel | Trigger Mechanism |
|---|---|
| **GitHub Releases** | Triggered only when a release tag (e.g. `v0.3.12`) is pushed or manually dispatched via `workflow_dispatch`. Merging PRs or pushing to branches never triggers a release. |
| **Snap Store (snapcraft.io)** | Snapcraft.io's build service reads `version` from `snap/snapcraft.yaml` upon release tag push or build dispatch. |
| **Flatpak / Flathub** | Uses the updated `<release version="..." .../>` in `bd.com.zihad.BengalDownloadManager.metainfo.xml`. |
| **In-App (Help -> About)** | Automatically displays version from `VERSION` and `SNAP_VERSION`. |

---

## 7. Release Lifecycle & CI/CD Pipeline

1. **Pull Requests & Commits (`ci.yml`)**:
   - `uv run python scripts/sync_version.py --check` automatically executes on every commit and PR.
   - If any manifest does not match `VERSION`, CI fails immediately with actionable instructions.
   - Branch merges and pushes run tests and validation, but do not create releases.

2. **Automated Builds & Releases (`release.yml`)**:
   - Pushing release tags (`v*`) or manual `workflow_dispatch` triggers the release workflow.
   - Merging to `main`, `dev`, or any other branch will NOT publish a release.
   - The workflow reads the canonical `VERSION` file, produces all binaries and package formats with that exact version, and creates the GitHub Release.

3. **Snap Store Synchronization**:
   - Because `snap/snapcraft.yaml` is pre-synchronized to the exact version in Git, Canonical's Snapcraft Build Service builds and publishes the exact matching release version to `snapcraft.io/bengal-download-manager` without race conditions or tag guessing.

---

## 8. Guidelines for AI Agents and Contributors

1. **Never edit application version strings manually in individual package manifests**. Always use `scripts/sync_version.py --set <ver>` or `--bump <type>`.
2. **Run `uv run python scripts/sync_version.py --check` before committing** any changes related to versioning or packaging.
3. **Browser extension versioning is independent**: `extension/manifest.json` is decoupled from app version bumps and managed independently.
