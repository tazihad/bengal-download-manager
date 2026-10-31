# Plan: Desktop support option in flatpak metainfo XML

## Current state (flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml.in)

### What exists today
- `<supports>` section (lines 34-37) declares supported **input controls**:
  ```xml
  <supports>
    <control>pointing</control>
    <control>keyboard</control>
  </supports>
  ```
- `<launchable type="desktop-id">bd.com.zihad.BengalDownloadManager.desktop</launchable>` (line 259) — ties the AppStream entry to the `.desktop` file.
- `<categories>` Network, FileTransfer (lines 262-265).
- Branding `<color>` entries for light/dark themes (lines 7-10).

### What does NOT exist
- There is **no** AppStream `<desktop-support>` or desktop-environment element in the metainfo XML. AppStream does not have a standard element for declaring "works on GNOME/KDE/etc."
- Valid `<control>` values per AppStream spec: `pointing`, `keyboard`, `touch`, `touchpad`, `gamepad`, `pen`. Only `pointing` and `keyboard` are currently listed.

## Interpretation of "desktop support"

The user's phrase "desktop support" is ambiguous — it could mean:

**A) Input method support** — declare that the app supports `touch` / `touchpad` in `<supports>` (valid AppStream `<control>` values). This is actionable in the metainfo XML.

**B) Desktop environment targeting** — declare the app works on/is intended for GNOME, KDE, etc. This is **not** expressible in AppStream metainfo; it belongs in the `.desktop` file via `OnlyShowIn=` / `NotShowIn=` keys.

**C) Desktop integration features** — system tray, autostart, notifications. Already handled in code and `.desktop` (`X-GNOME-UsesNotifications=true`), not a metainfo declaration.

## Recommended approach

If the goal is to broaden `<supports>`, add `touch` and `touchpad` controls (valid AppStream values), which is useful for convertible/touch devices and is the closest thing to "desktop support" expressible in metainfo XML.

If the goal is desktop-environment targeting, that requires editing `.desktop`, not metainfo XML.

## Validation
- `appstreamcli validate --pedantic --no-net flatpak/...metainfo.xml` must pass (currently passes with only a pedantic CID info).
- `uv run python scripts/sync_version.py --check` must pass.

## Open decision (ask user)
Which interpretation of "desktop support" do you want, and what specific change?

Recommended: **A** — add `<control>touch</control>` and `<control>touchpad</control>` to the `<supports>` section in `metainfo.xml.in` (and regenerate `metainfo.xml`), since that's the only desktop-support-related option expressible in AppStream metainfo. Confirm before implementing.
