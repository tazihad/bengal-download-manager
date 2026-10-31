# Plan: Use "Pending" status while media file-info popup awaits user action

## Goal
Change the status-column text shown in the main table when a file is clicked from the browser, the DownloadFileInfoDialog popup appears, and the item waits for the user to confirm/cancel — currently mislabeled `"Paused"` (implies it was running then stopped). Replace with `"Pending"` (awaiting user action), consistent with existing usage at `main_window.py:5786`.

## Affected location
- `src/ui/main_window.py:7601` — `self._set_status_text(row, "Paused")` inside `start_media_download` when `show_file_info` is True (popup open). Change text to `"Pending"`.

## Related references (review, not necessarily change)
- `src/ui/main_window.py:7619` — dialog-reject handler `self._handle_download_dialog_rejected(None, dialog_id)` already passes `None, dialog_id`; on cancel the row currently lingers. Decide whether a cancelled popup should remove the row or mark it `"Cancelled"` (out of scope for this text-only change; flagged as open question).
- `src/ui/main_window.py:6360-6379` — `_get_display_state` CANONICAL_STATUS / user-intent states are `Complete`, `Paused`, `Cancelled`, `Normal`. `"Pending"` isn't a user-intent state, so a pending row falls through to engine-status interpretation at line 6444 (no worker attached yet) — acceptable.
- `src/ui/main_window.py:5213` — active-count logic already includes `"Pending"` as startable — no breakage.

## Decision (recommended)
Status text: `"Pending"`
- One word, non-technical, user-meaningful.
- Already in codebase vocabulary (`main_window.py:5786`, `:4363`, `:4637`).
- Semantics: awaiting action/decision — exactly the popup-waiting state.

## Files to change
1. `src/ui/main_window.py` line 7601: `"Paused"` → `"Pending"` (single `_set_status_text` call).

## Validation
- `uv run python -m py_compile src/ui/main_window.py` — compiles cleanly.
- Manual: when a browser-clicked media file opens the file-info popup, the main-table row status shows `Pending` instead of `Paused` until the user confirms or cancels the dialog.

## Risks / open questions
- On dialog cancel, the row stays `Pending` (reject handler only pops `active_file_info_dialogs` tracking). Consider removing the row or marking `Cancelled` on reject — marked out of scope; raise as follow-up.
- i18n: status strings are not wrapped in `self.tr()` at this call site; keep consistent with existing (no `tr()`) to avoid scope creep.