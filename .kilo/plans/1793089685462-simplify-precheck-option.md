# Plan: Simplify "Pre-check delete files" option label & tooltip

## Goal
Make the pre-check checkbox label in Options → General tab ("Deletion and Confirmations" group) simple, short, and not confusing while keeping its meaning.

## Affected file
`src/ui/dialogs/options.py`
- Line 578: checkbox label
- Line 579-581: tooltip text

## Current text
- Label: `Pre-check "Also delete files from disk (permanently)" in delete dialog`
- Tooltip: `When deleting downloads, automatically check the option to permanently remove downloaded files from disk.`

## Problem
The label is wordy and nested-quote heavy (`"Also delete files from disk (permanently)"`), making it hard to scan at a glance.

## Decision — no quotes
Per user request, remove all quotation marks from both strings.

- Label: `Pre-check delete files from disk permanently`
- Tooltip: `When deleting downloads, permanently remove downloaded files from disk by default.`

Both keep the core meaning (the permanent-deletion option is pre-checked during deletion) but are shorter, flat (no nested quotes), and less confusing. Context ("in delete dialog") is implied by the "Deletion and Confirmations" group the checkbox sits in.

## Translation impact
- All label/tooltip strings are wrapped in `self.tr(...)`, so they're extraction targets.
- After editing, run `uv run python scripts/i18n.py extract` to refresh `translations/bdm_en.ts`, then `uv run python scripts/i18n.py compile` to rebuild `assets/translations/*.qm`.
- Non-English `.ts` catalogs will mark the changed source strings as `unfinished` (fall back to English) until retranslated — acceptable.

## Validation
- Run `uv run python scripts/i18n.py status` to confirm catalog health.
- Run `PYTHONPATH=src uv run python -m pytest tests/unit -q` to confirm no breakage.
- Optionally launch `uv run python src/main.py` and open Options → General to visually confirm the shorter label/tooltip.

## Notes
- Commit on a feature branch; do not merge to main (per prior instruction).
- No AGENTS.md version bump needed (no version change).

## Open decision
Confirm the exact simplified label/tooltip wording before implementing. Recommended above.
