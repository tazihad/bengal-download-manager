# Plan: Make YouTube Alternate (Direct) download file info appear instantly

## Problem
When clicking an option from the YouTube Alternate mode dropdown, the log
`[Direct] Resolving stream URLs for https://www.youtube.com/watch?v=...` appears
and the file info dialog takes 5–15s to show. This log is emitted by
`_run_ytdlp_json()` in `src/core/media/direct.py:225`, which invokes yt-dlp as
a subprocess to resolve a YouTube page URL into signed direct stream URLs.

## Root cause
The YouTube `choices()` function (`extension/youtube-media.js:78-136`) returns
dropdown items with:
- `url` = googlevideo.com direct stream URL (for non-SABR items) or SABR URL
- `audioUrl` = separate audio stream URL (non-muxed items) or `undefined` (muxed)
- `provider` = `'youtube'`
- `sabrSelection` = `{videoItag, audioItag}` (SABR items only)

In `extension/background.js` `action: 'download'` handler (line 2212):
```js
const needsAudioMerge = item.provider === 'youtube' && (!!item.sabrSelection || !!item.audioUrl);
```

When `needsAudioMerge` is true, `resolveDirectStreamUrl()` is called → IPC
`/resolve-direct` → yt-dlp → slow.

My earlier fix (commit `cdfb49d`) added a fast-path:
```js
const directStreamUrl = item.streamUrl || url;
const isDirectStreamUrl = directStreamUrl && directStreamUrl.startsWith('http') && !/youtube\.com\/.../i.test(directStreamUrl);
if (isDirectStreamUrl && item.audioUrl) { /* use direct URLs, skip yt-dlp */ }
```

This only helps non-SABR, non-muxed items (where `item.audioUrl` is set). It does
NOT help:
1. **SABR items** — `item.audioUrl` is `undefined`, `item.sabrSelection` is set
   instead. Condition fails → yt-dlp runs.
2. **Muxed non-SABR items** — `item.audioUrl` is `undefined`, but `needsAudioMerge`
   is `false`, so the `if (needsAudioMerge)` block is never entered → already
   instant (no yt-dlp).

SABR items fundamentally require yt-dlp because they need to resolve specific
`videoItag`/`audioItag` from the YouTube page — there is no pre-resolved direct
pair of URLs available without running yt-dlp.

## Decisions

1. **Fix the fast-path condition** (`extension/background.js` line 2243): Change
   `item.audioUrl` to `item.audioUrl || item.sabrSelection` so non-muxed non-SABR
   items AND items that have either audio URL or sabr selection can skip yt-dlp
   when direct stream URLs are available.

   For SABR items specifically: `item.url` is `data.sabrUrl` (a googlevideo.com
   URL). If we send just the SABR URL + `sabrSelection` to the desktop, the
   desktop's `resolve_media_tracks()` still runs yt-dlp to resolve itags. SABR
   items cannot be made fully instant without caching.

2. **Add yt-dlp result caching** (`extension/background.js`): Cache resolved
   SABR stream URLs keyed by `${videoId}#${videoItag}#${audioItag}` so repeated
   clicks on the same quality are instant. Add a TTL (e.g. 10 minutes) so signed
   URLs don't expire.

3. **Keep `_fetch_size_bytes` HEAD-only with 3s timeout** (`src/core/media/direct.py`):
   Already done in earlier commit — ensures non-YouTube direct downloads don't
   block on slow network probes.

## Files affected
- `extension/background.js` — fast-path condition fix + SABR result cache
- `src/core/media/direct.py` — no further changes needed (HEAD-only size fetch already done)

## Validation
- Run `tests/unit/test_direct_media.py` — all must pass
- Verify the log `[Direct] Resolving stream URLs` does NOT appear for non-SABR
  YouTube items when clicking Alternate mode dropdown options
- For SABR items, first click may still be slow (yt-dlp required), subsequent
  clicks on same quality should be instant (cache hit)

## Open questions / risks
- Signed googlevideo.com URLs expire — cache TTL must be short enough to avoid
  expired URL errors but long enough to make repeat clicks instant.
- SABR items with different videoItag/audioItag combinations are different cache
  keys — cache may not hit if user switches qualities.