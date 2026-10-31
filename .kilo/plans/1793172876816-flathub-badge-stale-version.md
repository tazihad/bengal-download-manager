# Plan: Fix Flathub badge showing stale 0.3.11 version

## Goal
Get the Flathub version badge in `README.md` to show `0.3.12` instead of being stuck on `0.3.11`.

## Findings (investigation complete)

### Confirmed — `.in` template IS in sync (no source change needed)
- `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml.in` has `<release version="0.3.12" ...>` as its **newest** entry (line ~80-90), followed by `0.3.11` at line 82 after a `</release>` close.
- `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml` (generated) also has `0.3.12` as newest.
- No template divergence exists — my earlier reading of line 82 as "newest" was incorrect; `0.3.11` is the **second** entry, not the first.

### Real issue — shields.io badge caching (visible symptom)
- README badge (line 15): `https://img.shields.io/flathub/v/bd.com.zihad.BengalDownloadManager`
- shields.io caches Flathub API responses aggressively (24–48h typical).
- Even if Flathub has published `0.3.12`, the badge can remain stuck on `0.3.11` until cache expiry or force-refresh.
- This is external to the repo; cannot be "fixed" in code, only worked around.

### Unverified — Flathub publication timing
- User states Flathub has `0.3.12`, but this should be confirmed against Flathub's API (`https://flathub.org/api/v2/apps/bd.com.zihad.BengalDownloadManager`) before concluding the badge is merely cached.

## Files to change

### `README.md` (badge force-refresh, optional)
- The badge URL may need a cosmetic change (e.g. different `label` or `color` value) to force shields.io to bypass its cache and re-fetch from Flathub's API.
- Do **not** change the badge to a static version — keep it dynamic so it self-updates going forward.

### No changes to `flatpak/*.metainfo.xml*` — already in sync

## Validation
- Confirm Flathub has published `0.3.12` via `https://flathub.org/api/v2/apps/bd.com.zihad.BengalDownloadManager`.
- Badge URL returns `0.3.12` when fetched directly (force-refresh shields.io cache).
- `uv run python scripts/sync_version.py --check` passes (version manifests consistent — already verified as in sync).

## Risks / open questions
- If Flathub has **not** actually published `0.3.12` yet, the badge will remain on `0.3.11` regardless of any badge URL change — the fix is then to wait for Flathub publication (the local metainfo/template already has `0.3.12` correct).
- shields.io cache expiry is outside repo control; badge may take up to 48h to self-correct even after Flathub publishes.
