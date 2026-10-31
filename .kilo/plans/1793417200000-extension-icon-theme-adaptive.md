# Plan: Adaptive extension icon theme (system / light / dark) for Chrome

## Goal
Make the Bengal DM extension toolbar icon adapt to the system theme (light/dark) on Chrome/Chromium, matching Firefox behavior. Currently Chrome only ever shows the appicon (`icon-*.png`) because `manifest.json` / `manifest.chrome.json` do not declare `action.theme_icons`.

## Findings (code comparison: extension/ v0.11 vs /home/zihad/Downloads/extension-chromium-0.10/ v0.10)

### Structural changes (0.10 → 0.11)
- Flat layout → `src/` subdirs (`src/background/`, `src/content/`, `src/popup/`, `src/options/`, `src/sites/youtube/{shared,background,content,main}/`)
- Single `manifest.json` → split into `manifest.json` (base), `manifest.chrome.json`, `manifest.firefox.json` + `switch-manifest.sh`
- New YouTube SABR/direct adapters under `src/sites/youtube/`
- New `tests/` directory with YouTube media/direct test suites
- New light/dark SVG assets: `assets/icon-light.svg`, `assets/icon-dark.svg` (not present in 0.10)
- `manifest.firefox.json` declares `action.theme_icons` (light/dark PNG pairs) + `browser_specific_settings` gecko ID
- `options.html` line 397 still shows stale extension version `0.10` (manifest says `0.11`)

### Icon/theme assets present (both versions)
- `assets/icon-16/32/48/128.png` (colorful appicon)
- `assets/icon-light-16/32/48/128.png`, `assets/icon-dark-16/32/48/128.png` (monochrome pairs)
- `assets/icon-light.svg`, `assets/icon-dark.svg` (0.11 only)

### Runtime icon logic (identical in both versions)
- `background.js`: `getIconPathsForStyle()`, `updateChromeActionIcon()`, `applyStoredActionIcon()` — reads `actionIcon`/`theme`/`systemTheme` from `chrome.storage.local` (default `system`/`system`), calls `chrome.action.setIcon({ path: ... })` at runtime. For Firefox with both prefs `system`, calls `setIcon({ path: null })` to let native manifest `theme_icons` take over.
- `popup.js`: `updatePopupLogo()` — switches popup logo by theme.
- `options.js`/`options.html`: theme-radio (system/light/dark) + icon-radio (system/app/dark/light) cards that write `theme`/`actionIcon` to storage and call `applyActionIcon()`.

### Root cause: why Chrome only shows appicon
1. `manifest.json` and `manifest.chrome.json` declare `icons` + `action.default_icon` with only appicon paths (`icon-*.png`). **No `action.theme_icons` key.**
2. `manifest.firefox.json` DOES declare `theme_icons` with light/dark pairs → Firefox native adaptive theming works immediately.
3. Chrome relies entirely on background.js runtime `setIcon()` calls, which only fire after background.js loads and storage prefs initialize. Before that (first install, reload), the toolbar shows appicon from `action.default_icon`.
4. `theme_icons` is valid in Chrome Manifest V3 (Chrome ≥ ~115) and Firefox, so it can be declared declaratively.

## Plan (implementation tasks)

### Task 1: Add `theme_icons` to Chrome manifests
- Edit `extension/manifest.json` and `extension/manifest.chrome.json`: add `action.theme_icons` array with light/dark PNG pairs for sizes 16/32/48/128, mirroring `manifest.firefox.json` exactly.
- Keep existing `icons` + `action.default_icon` as appicon fallback (unchanged).
- Result: Chrome gets declarative adaptive theming; Firefox unchanged.

### Task 2: Verify pack_extension.py preserves `theme_icons` for Chrome target
- Read `scripts/pack_extension.py` Chrome target block — it strips `background.scripts`, removes `webRequestBlocking`, adds `downloads.ui`. It does NOT touch `icons`, `action.default_icon`, or `theme_icons`.
- Confirm adding `theme_icons` to `manifest.json` survives packing into `dist/bengal-download-manager-chrome.zip` and `.crx`.
- No code change expected unless inspection shows otherwise.

### Task 3: Fix stale extension version in options.html
- Edit `extension/src/options/options.html` line 397: change `0.10 (Manifest V3)` → `0.11 (Manifest V3)` to match `manifest.json` version.

### Task 4: Validate
- Re-run `uv run python scripts/pack_extension.py` to rebuild Chrome + Firefox packages into `dist/`.
- Unzip/inspect the generated `manifest.json` inside the Chrome ZIP to confirm `theme_icons` is present.
- Optionally load the unpacked extension in Chrome/Edge and confirm the toolbar icon swaps with OS theme (light→dark icon on dark theme, dark→light on light theme).

## Files to touch
- `extension/manifest.json` — add `action.theme_icons`
- `extension/manifest.chrome.json` — add `action.theme_icons`
- `extension/src/options/options.html` — fix version string `0.10` → `0.11`
- `scripts/pack_extension.py` — review only (no change expected)

## Out of scope
- Converting PNG icons to SVG in manifest (SVG `theme_icons` support varies; PNG pairs are safest)
- Changing runtime JS logic (already correct in both versions)
- Any desktop app / Aria2 / Flatpak / AppImage changes
