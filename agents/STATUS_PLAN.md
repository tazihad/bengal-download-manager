# Download Progress Status Refactor Plan

## Goal
Replace the single `Connecting...` status with a clear 5-phase one-word model that works for both media and regular downloads.

## Status Model (one word, no ellipsis)

| Status       | When it appears |
|--------------|-----------------|
| **Preparing**  | Window opens / media metadata is being read / download is being set up |
| **Connecting** | Server contact, Aria2 waiting, or media stream is being opened |
| **Downloading**| Data is actively transferring |
| **Finishing**  | Verifying, moving the file, or merging video + audio |
| **Complete**   | Download fully finished |

Existing non-phase states stay: `Paused`, `Resuming`, `Cancelled`, `Error`.

---

## File Changes

### 1. `src/ui/dialogs/progress.py`
- Initialize status label to **Preparing** instead of `Connecting...`.
- Add `_normalize_status(text)` helper that maps all incoming worker/log messages to the five words above.
- Use the helper in:
  - `append_log()` — map `Connecting to server...` / `Connecting to Aria2 engine...` → `Connecting`; `File assembled. Verifying...`, `Finalizing: Moving file...`, `Aria2 download completed successfully.` → `Finishing`.
  - `update_stats()` — map `Receiving data...` / `Downloading...` → `Downloading`, plus the new `Preparing` / `Finishing` states.
  - `update_segment_row()` — normalize segment labels the same way.
  - `on_finished()` — keep completion and error states consistent.
- Keep Pause/Cancel enabled during `Preparing` and `Finishing`.
- Wrap new display words in `self.tr(...)`.

### 2. `src/core/media/worker.py` (yt-dlp media downloads)
- Start each attempt with **Preparing** instead of `Connecting...`.
- When first real media stream destination is detected, emit **Connecting** once.
- When yt-dlp reports merging, remuxing, audio extraction, or file moving — and once after successful process exit — emit **Finishing**.
- Track phase per attempt so retries start cleanly at Preparing.

### 3. `src/core/workers/aria2.py`
- Map Aria2 state `waiting` → **Connecting**, state `active` → **Downloading**.
- During completion iteration (before final move/cleanup), report **Finishing**, then send **Complete** after move succeeds.

### 4. `src/core/workers/download.py`
- Emit explicit **Finishing** status right after `File assembled. Verifying...`, before the final move.

### 5. Main window / storage consistency
Recognize new statuses as active states so pause/resume, double-click, queue activity, and active counts keep working:
- `src/ui/main_window.py` — status lists around existing `Connecting...` checks.
- `src/core/download_store.py` — `active_statuses`.
- `src/ui/delegates/table_delegate.py` — status-label mapping for Preparing/Finishing.

### 6. Localization
- Add new strings: `uv run python scripts/i18n.py extract`
- Compile: `uv run python scripts/i18n.py compile`
- Untranslated languages fall back to English.

### 7. Tests
- Extend `tests/component/test_progress_dialog.py` to verify:
  - Initial status is `Preparing`
  - `Connecting to server...` → `Connecting`
  - `Receiving data...` → `Downloading`
  - `File assembled. Verifying...` → `Finishing`
  - Completion → `Complete`
  - No status contains `...`
- Run: `PYTHONPATH=src uv run pytest -v tests/`

---

## Manual Verification
- Regular HTTP download and Aria2 download: all five phases visible.
- Media download with separate video/audio streams: `Finishing` appears during merge.
- Pause/resume, cancel, and completion still behave correctly.
- Main download list remains consistent and doesn't get stuck in a new phase.

---

## Rollback
If issues arise, revert these four files:
- `src/ui/dialogs/progress.py`
- `src/core/media/worker.py`
- `src/core/workers/aria2.py`
- `src/core/workers/download.py`