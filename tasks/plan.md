# Implementation Plan: BDM Multi-Connection Concurrency & Rust Rewrite Completion

## Overview
This plan addresses multi-connection segmented concurrency in the new `bdm` CLI and pure Rust Tigris engine, compares it with legacy Aria2/Python capabilities, establishes safe connection limits, and completes the remaining verification, CMake integration, and distro packaging (Phase 4 & Phase 5).

## Architecture Decisions
- **Concurrency Model**: Pure Rust Tokio multi-threaded runtime. Segment workers run concurrently as asynchronous tasks scheduled across all CPU worker threads.
- **Connection Ceiling**: Standard default cap of **32 connections** (matching aria2 and legacy Bengal Download Manager), with a logical ceiling of **64 connections** for gigabit networks and high-throughput servers.
- **Dynamic Chunk Threshold**: Prevent chunk starvation by enforcing a minimum segment size (1 MiB). A 4 MiB file with `-c 32` will logically scale down to 4 connections (1 MiB per segment) rather than opening 32 tiny, inefficient 128 KiB TCP streams.
- **Sparse Pre-Allocation**: Linux `posix_fallocate`, BSD `fcntl(F_PREALLOCATE)` or seek-write, and Windows `SetFileValidData` prevent disk fragmentation during parallel non-overlapping segment writes.

## Task List

### Phase 1: Tigris Concurrency & Connection Limit Verification
- [ ] **Task 1: Verify & Refine Connection Clamping and Dynamic Chunk Sizing in Tigris**
  - **Description**: Ensure `TigrisEngine` allows connections up to 32 (optionally 64) and intelligently computes actual segment count based on file size (minimum 1 MiB chunk threshold).
  - **Acceptance criteria**:
    - `task.num_connections` accepted in range 1–64 (default 8).
    - If file size / connections < 1 MiB, segment count is scaled to `(total_size / 1_048_576).max(1)`.
    - Unit tests added to `crates/tigris/src/engine.rs` verifying chunk calculation logic.
  - **Verification**: `cargo test -p tigris` passes.

- [ ] **Task 2: CLI Multi-Connection Verification (`bdm get` and `bdm add`)**
  - **Description**: Verify `bdm get -c <connections>` and `bdm add -s <connections>` handle connections flags properly, pass them to Tigris, and report segment progress.
  - **Acceptance criteria**:
    - `bdm get --help` and `bdm add --help` show connection limits (1–32 recommended, max 64).
    - Progress reporting accurately aggregates downloaded bytes across all concurrent workers.
  - **Verification**: `cargo check -p bengal-desktop` and CLI help test.

### Checkpoint: Tigris Concurrency
- [ ] Unit tests pass in `tigris` and `bengal-desktop`.

### Phase 2: CMake Out-of-Source Build & Symlink Integration
- [ ] **Task 3: Verify CMake Release Build in `build/`**
  - **Description**: Run clean out-of-source CMake build in `build/` ensuring binaries land in `build/bin/bengal-download-manager` with symlink `build/bin/bdm`.
  - **Acceptance criteria**:
    - CMake generates build tree in `build/`.
    - Build finishes with zero compiler warnings/errors.
    - `build/bin/bdm --version` outputs `0.3.0`.
  - **Verification**: `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build`.

### Checkpoint: Binary Artifacts
- [ ] Binary and symlink exist and execute in `build/bin/`.

### Phase 3: Packaging & Multi-Arch Verification (Phase 5)
- [ ] **Task 4: Update Flatpak Manifest for Pure Rust Build**
  - **Description**: Update `flatpak/bd.com.zihad.BengalDownloadManager.yml` to remove legacy Python/PyQt6/aria2 dependencies and use `cargo` / `cmake` build pipeline.
  - **Acceptance criteria**:
    - Manifest specifies Rust toolchain / cargo build.
    - No external `aria2c` runtime dependency.
    - Metainfo XML and desktop files verified.
  - **Verification**: Validation of manifest syntax.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Remote CDNs block/throttle IP if >32 connections opened | Medium | Default to 8 connections, clamp default UI to 32, allow up to 64 only when explicitly requested by user |
| Small files degraded by too many TLS handshakes | Low | Minimum chunk size threshold (1 MiB per segment) |
| High disk fragmentation from parallel writes | Medium | OS-level sparse pre-allocation (`posix_fallocate`) |

## Open Questions
- Should the GUI preferences dialog expose a slider up to 32 or up to 64 for max connections per download? (Recommended: 32 in standard slider with power-user manual input up to 64).
