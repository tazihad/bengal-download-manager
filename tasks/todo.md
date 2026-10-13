# Task List: BDM Multi-Connection Concurrency & Rust Rewrite Completion

## Task 1: Verify & Refine Connection Clamping and Dynamic Chunk Sizing in Tigris
**Description:** Implement dynamic chunk sizing and allow up to 32 connections (configurable up to 64 for power users) in `TigrisEngine` with unit tests.
**Acceptance criteria:**
- [ ] Support connections between 1 and 64 (default 8, recommended max 32)
- [ ] Enforce minimum segment size threshold of 1 MiB to prevent connection thrashing
- [ ] Unit tests for chunk division logic
**Verification:**
- [ ] `cargo test -p tigris`
**Dependencies:** None
**Files likely touched:**
- `crates/tigris/src/engine.rs`
**Estimated scope:** Small (1 file)

## Task 2: CLI Multi-Connection Tuning & Help Consistency
**Description:** Update `apps/bengal-desktop/src/cli.rs` connection flag descriptions and clamp logic to match Tigris 1–64 range.
**Acceptance criteria:**
- [ ] `bdm get -c` and `bdm add -s` options document connections 1–32 (max 64)
- [ ] Clamping accepts up to 64 connections
**Verification:**
- [ ] `cargo check -p bengal-desktop`
**Dependencies:** Task 1
**Files likely touched:**
- `apps/bengal-desktop/src/cli.rs`
**Estimated scope:** Small (1 file)

## Checkpoint: Tigris Concurrency & CLI
- [ ] `cargo test --workspace` passes cleanly

## Task 3: Verify CMake Out-of-Source Build in `build/`
**Description:** Build the workspace using CMake out-of-source workflow in `build/` and verify the executable and `bdm` symlink.
**Acceptance criteria:**
- [ ] `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build` succeeds
- [ ] `build/bin/bengal-download-manager` and `build/bin/bdm` are created
- [ ] `./build/bin/bdm --version` outputs `0.3.0`
**Verification:**
- [ ] `./build/bin/bdm --help` runs successfully
**Dependencies:** Task 2
**Files likely touched:**
- `CMakeLists.txt`
**Estimated scope:** Small (1 file if tweaks needed)

## Task 4: Update Flatpak Manifest for Pure Rust Build (Phase 5)
**Description:** Update `flatpak/bd.com.zihad.BengalDownloadManager.yml` to replace Python/PyQt6/aria2 build steps with pure Rust cargo/cmake build.
**Acceptance criteria:**
- [ ] Manifest removes python3, python3-pyqt6, and aria2 modules
- [ ] Manifest builds pure Rust binary using cmake or cargo
- [ ] Desktop file and metainfo references verified
**Verification:**
- [ ] Validate YAML manifest structure
**Dependencies:** Task 3
**Files likely touched:**
- `flatpak/bd.com.zihad.BengalDownloadManager.yml`
**Estimated scope:** Small (1-2 files)

## Checkpoint: Complete
- [ ] All tests pass, build produces binary and symlink, packaging manifest updated
