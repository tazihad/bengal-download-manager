# Plan: Improve download statuses in main table, progress window, and media downloader

## Goal
Replace multi-word/technical download statuses with single-word, user-meaningful statuses across:
- Main download table status column (column 2)
- Download progress dialog `lbl_main_status`
- Media downloader (YtDlpDownloadWorker) statuses flowing into the main table
- Prevent statuses and all table columns from flickering too rapidly to read

All statuses must be exactly one word, non-technical, and readable.

## Current behavior (findings)
- Workers emit technical statuses: `Connecting to server...`, `Resume GET...`, `Receiving data...`, `Paused`, `Complete`, `Error`, `Cancelled`, plus log lines.
- Media worker emits `Connecting...`, `Downloading`, `Complete`, `Error`, `Cancelled`, `Paused`, `Resuming...` via `main_progress_signal`.
- Progress dialog maps these to `Downloading`/`Connecting...`/`Complete`/`Resuming...`/`Error`/`Paused`/`Cancelled`.
- Main table resolves status via `_get_display_state` → `_apply_download_row_data` → `_set_status_text` (column 2).
- Workers emit progress every ~100–200 ms, causing rapid UI updates and flicker.
- Transfer rate column flickers when yt-dlp outputs "Unknown B/s" (speed regex never matches, so `speed_bps` stays 0.0 → `"--"`).

## Design decisions

### D1 — Canonical one-word status set (single source of truth)
Map every worker status to one of these single-word statuses:

| Worker status | Display status | Meaning |
|---|---|---|
| queued / not started | Queued | waiting to start |
| `Connecting to server...`, `Connecting to Aria2 engine...`, `Connecting...` | Starting | initial connection/start |
| `Resume GET...`, `Resuming...` | Resuming | resuming a paused download |
| `Receiving data...`, `Downloading` | Downloading | actively transferring fragments |
| `Paused` | Paused | user-paused |
| `Complete`, `Prefetch Complete` | Complete | finished |
| `Error`, `Prefetch Error` | Error | failed |
| `Cancelled`, `Prefetch Cancelled`, `removed` | Cancelled | user-cancelled |

Media pipeline additions:

| yt-dlp phase | Display status | Detection point |
|---|---|---|
| command setup / cookies / ffmpeg check | `Preparing` | before process start (worker.py:529-618) |
| video info / metadata extraction | `Analyzing` | after process start, before first download progress line (worker.py:667-840) |
| initial source connection | `Starting` | right when process starts (worker.py:667) |
| fragment download | `Downloading` | stdout parse loop (worker.py:840) |
| format merging | `Merging` | `[Merger|ExtractAudio|VideoRemuxer]` lines (worker.py:739) |
| post-processing | `Processing` | thumbnail embed / ffmpeg post-processing (worker.py:767-773) |
| file move / cleanup | `Finalizing` | `[MoveFiles]` temp→save_dir (worker.py:776-788) |

### D2 — Anti-flicker / minimum dwell
Add a minimum dwell time so rapid transitions are visible:
- `STATUS_DWELL_MS = 300` (reduced from 800 for responsiveness).
- Track last change time per row per column in main table; per dialog instance in progress window.
- Non-terminal status change applied only if `now - last_change >= STATUS_DWELL_MS / 1000.0`.
- Terminal states (`Complete`, `Error`, `Cancelled`) and media transitions (`Merging`, `Processing`, `Finalizing`) apply immediately — never skipped.
- First-ever set is immediate.

### D3 — All-column flicker protection
Apply dwell guard to every table column that receives rapid stdout updates:
- Column 1: Size (`_set_sortable_item(row, 1, ...)`)
- Column 2: Status (existing status dwell guard)
- Column 3: Time left (add dwell guard, same as rate)
- Column 4: Transfer rate (existing rate dwell guard)
- Column 5: Date/last try (add dwell guard)
Skip UI update if value unchanged and within dwell window; still update progress bar internally.

### D4 — Better size status during Preparing
During `Preparing` phase (before `total_bytes` known), `size_fmt` falls back to `"Calculating..."`. Change to `"--"` so size column shows a neutral placeholder instead of a misleading intermediate value while yt-dlp resolves file info.

## Files to change

### 1. `src/ui/main_window.py`
- `_get_display_state` (line ~6344): canonical one-word mapping; add media statuses to recognized/active set.
- `_apply_download_row_data` (line ~6426): add `_rate_dwell` and `_time_dwell` dicts keyed by item key; apply 300ms dwell guard to columns 3 (time left) and 4 (rate); keep existing status dwell guard on column 2.
- `_set_status_text` (line ~3354): update recognized statuses list to canonical set including media statuses.
- Direct `_set_status_text` call sites using multi-word statuses → canonical:
  - `"Resuming..."` → `"Resuming"`
  - `"Downloading..."` → `"Downloading"`
  - `"Starting..."` → `"Starting"`
  - `"Pending..."` → `"Pending"`
  - `f"Retrying ({current_retries + 1}/{max_retries})..."` → `"Retrying"`
- Status-filter references in `update_ui_states`/queue logic: update string comparisons to canonical set.

### 2. `src/ui/dialogs/progress.py`
- `update_stats`, `append_log`, `on_finished`, `toggle_pause`: canonical mapping + `self.tr()`.
- Add dwell-time guard per dialog instance.

### 3. `src/core/media/worker.py`
- Emit granular one-word media statuses via `main_progress_signal` data[2] at pipeline phases (`Preparing`, `Analyzing`, `Starting`, `Downloading`, `Merging`, `Processing`, `Finalizing`).
- Speed flicker fix: keep `speed_bps` as last known good speed; never drop back to `0.0` on unparseable lines; when `speed_match` fails, keep previous `speed_fmt` instead of `"--"`.
- Size fix: during `Preparing` phase, set `size_fmt = "--"` instead of `"Calculating..."`.

## Branch & commit
- Create local branch `feature/download-status-improvement`.
- Commit changes locally; do NOT push.

## Validation
- Run `PYTHONPATH=src uv run pytest tests/` — no regressions.
- All modified files compile cleanly (`py_compile`).
- Manual: statuses are one word; `Starting` replaces `Connecting...`; media pipeline shows `Preparing`→`Analyzing`→`Starting`→`Downloading`→`Merging`/`Processing`→`Finalizing`→`Complete`; Transfer Rate and Time Left columns don't flicker; Size shows `--` during Preparing.

## Risks / open questions
- Dwell must not delay terminal states — mitigated by terminal-state bypass in D2.
- Existing tests assert old status strings; may need updates.
- i18n scope: translate every status-setting call site or only main progress paths.
