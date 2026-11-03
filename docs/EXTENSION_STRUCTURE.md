# Bengal Download Manager — Extension Structure & Build Layout

## Summary

The browser extension lives under `extension/`. It is split into **two builds** from **two separate source trees**:

| Build | Source tree | Purpose | YouTube support |
|---|---|---|---|
| `extension-chromium` | `extension/src/` | Chrome + Firefox (shared codebase) | ✅ Yes |
| `extension-chrome` | `extension/chrome/` | Chrome Web Store (YouTube-stripped) | ❌ No |
| `extension-firefox` | `extension/src/` | Firefox (built from same `src/`) | ✅ Yes |

## Directory layout

```
extension/                                    ← manifest/config hub (NOT built directly)
├── assets/                                   ← canonical shared assets (single source of truth)
├── manifest.json                             ← YouTube-patched master manifest (chrome+firefox)
├── manifest.chromium.json                    ← Chromium-specific manifest copy
├── manifest.firefox.json                     ← Firefox-specific manifest copy
├── switch-manifest.sh                        ← switches root manifest.json between chromium/firefox
├── README.md
└── src/                                      ← shared codebase (Chrome + Firefox)
    ├── background/background.js
    ├── content/content.js
    ├── options/
    ├── popup/
    └── sites/
        ├── facebook/                         ← kept in both builds
        └── youtube/                          ← ONLY in chromium/firefox build
└── chrome/                                   ← Chrome Web Store build (YouTube-stripped)
    ├── assets -> ../assets                   ← symlink to canonical assets
    ├── manifest.json                         ← YouTube-stripped manifest (real file)
    └── src/                                  ← YouTube-stripped source
        ├── background/background.js
        ├── content/content.js                ← has YouTube early-return guard
        ├── options/
        ├── popup/
        └── sites/
            └── facebook/                     ← kept (no youtube/ here)
```

## Why two source trees

1. **Chrome Web Store policy** disallows YouTube-specific code (stream extraction, `youtube.com` content scripts, etc.). The Web Store build (`extension/chrome/`) must be completely free of YouTube references.
2. **Regular Chromium + Firefox builds** need full YouTube support. These share one codebase at `extension/src/`.
3. `extension/chrome/assets` is a **symlink** (`../assets`) so there is one canonical asset copy, not two duplicated ones. Git tracks it as mode `120000`.

## How the build works (`scripts/pack_extension.py`)

```
extension/                 ← root dir used as build input
├── src/                   ← chromium + firefox build input
└── chrome/                ← webstore chrome build input (excluded from chromium/firefox)
```

- `make_crx(ext_dir="extension/src/", target="chrome", exclude_dirs=("chrome",))` → `extension-chromium.crx/zip`
- `build_zip_package(ext_dir="extension/src/", target="firefox", exclude_dirs=("chrome",))` → `extension-firefox.zip/xpi`
- `make_crx(ext_dir="extension/chrome/", target="chrome")` → `extension-chrome.crx/zip`

`exclude_dirs=("chrome",)` prevents the webstore-only subtree from leaking into the chromium/firefox packages.

## Output artifacts (`dist/`)

| Artifact | Source | YouTube |
|---|---|---|
| `extension-chromium.crx` / `.zip` | `extension/src/` | ✅ |
| `extension-firefox.zip` / `.xpi` | `extension/src/` | ✅ |
| `extension-chrome.crx` / `.zip` | `extension/chrome/` | ❌ |

## Key differences between chromium and chrome builds

`chrome` is `chromium` **minus YouTube**, plus these small changes:

- **Manifest**: `chrome/manifest.json` has no YouTube `content_scripts`, no `inject.js`/`direct-inject.js` in `web_accessible_resources`, and adds `theme_icons` (dark/light). `chromium/manifest.json` (root `manifest.json`) keeps YouTube entries.
- **`content.js`**: chrome build has an early-return guard at the top so the floating media widget does not activate on `youtube.com`/`youtu.be`:

  ```js
  if (window.location && /youtube\.com|youtu.be/.test(window.location.hostname)) return;
  ```

  This guard exists **only** in `extension/chrome/src/content/content.js`. The shared `extension/src/content/content.js` does NOT have it (YouTube is supported there).
- **`background.js`**: chrome build removes YouTube imports (`youtube-media.js`, `youtube-direct.js`) and YouTube cookie-sanitizing functions (`sanitizeMediaCookies`, `shouldSendCookiesForDirect`).

## switch-manifest.sh

Runs from `extension/` and copies either `manifest.chromium.json` or `manifest.firefox.json` over root `manifest.json`. Since `extension/chrome/manifest.json` is a separate real file (not symlinked), it is **not** affected by this script — the Web Store build keeps its own stripped manifest.

## Files NOT to touch without care

- `extension/assets/` — canonical assets; `chrome/assets` symlinks to it.
- `scripts/pack_extension.py` — the `exclude_dirs` parameter and output filenames are coupled to this layout.
- `extension/chrome/manifest.json` — intentionally a real file (stripped), not a symlink to root `manifest.json`.
