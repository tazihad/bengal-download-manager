// Bengal DM - Facebook DASH capture (MAIN world)
// Facebook sends the full DASH manifest inside GraphQL/HTML payloads. We keep every
// <Representation> (not just the distinct heights) and publish it to the content script,
// so the chooser can list e.g. both 720p bitrates the video actually offers.
// Facebook also preloads the next reels: manifests are bound to the clip the player is
// showing by its length and rendition, not by whichever response arrived last.
(() => {
  const host = location.hostname.toLowerCase();
  const isFacebook = host === 'facebook.com' || host.endsWith('.facebook.com') ||
    host === 'fb.watch' || host.endsWith('.fb.watch') ||
    host === 'fb.com' || host.endsWith('.fb.com');
  if (!isFacebook) return;
  const api = globalThis.bdmFacebook;
  if (!api) return;

  const MAX_BODY = 4 * 1024 * 1024;
  const MAX_ENTRIES = 120;
  const MAX_RECENT = 40;
  const MANIFEST_TTL_MS = 10 * 60 * 1000;
  const PAGE_SCAN_MIN_MS = 15000;
  const PAGE_SCAN_RETRY_MS = 6000;
  const cache = new Map(); // videoFBID -> { manifest, ts }
  const recent = [];       // parsed manifests, newest first; used to match by clip length
  let lastSignature = '';
  let lastUrl = location.href;
  let lastPageScan = 0;

  function manifestKey(manifest) {
    const first = (manifest.video && manifest.video[0]) || (manifest.audio && manifest.audio[0]) || {};
    return `${String(first.url || '').split('?')[0]}|${manifest.duration || 0}`;
  }

  function keepRecent(manifest, ids) {
    const key = manifestKey(manifest);
    const existing = recent.find(entry => entry.key === key);
    if (existing) {
      existing.ts = Date.now();
      for (const id of ids) if (!existing.ids.includes(id)) existing.ids.push(id);
      return;
    }
    recent.unshift({ key, manifest, ids: ids.slice(), ts: Date.now() });
    if (recent.length > MAX_RECENT) recent.pop();
  }

  function pruneCache() {
    while (cache.size > MAX_ENTRIES) {
      let oldestKey = null;
      let oldestTs = Infinity;
      for (const [key, entry] of cache) {
        if (entry.ts < oldestTs) {
          oldestTs = entry.ts;
          oldestKey = key;
        }
      }
      if (oldestKey === null) break;
      cache.delete(oldestKey);
    }
  }

  function remember(xml, ids) {
    if (typeof xml !== 'string' || xml.length < 64) return false;
    const parsed = api.parseManifest(xml);
    if (!parsed) return false;
    const keys = [];
    for (const id of ids || []) {
      if (api.isVideoId(id) && !keys.includes(String(id))) keys.push(String(id));
    }
    for (const key of keys) {
      const entry = cache.get(key);
      const manifest = api.mergeManifest(entry && entry.manifest, parsed);
      if (manifest) cache.set(key, { manifest, ts: Date.now() });
    }
    keepRecent(parsed, keys);
    pruneCache();
    // An unattributed manifest is still useful: report() matches it to the player's clip.
    return true;
  }

  function fresh(entry) {
    return !!entry && Date.now() - entry.ts < MANIFEST_TTL_MS;
  }

  function scanText(text, pageId) {
    if (typeof text !== 'string' || text.length < 64) return false;
    const found = api.manifestsInText(text);
    if (!found.length) return false;
    // A manifest with no id of its own can only borrow the page's id when the page
    // carries exactly one such video; otherwise it has to prove itself by clip length.
    const unnamed = found.filter(item => !item.ids.length);
    let captured = false;
    for (const item of found) {
      const ids = item.ids.slice();
      if (!ids.length && pageId && unnamed.length === 1 && found.length === 1) ids.push(pageId);
      captured = remember(item.xml, ids) || captured;
    }
    if (captured) report(true);
    return captured;
  }

  function readableContentType(type) {
    return /json|javascript|ecmascript|html|text\/plain|xml/i.test(String(type || ''));
  }

  function scanResponse(response) {
    if (!response || !response.ok) return;
    const length = Number(response.headers.get('content-length') || 0);
    if (length > MAX_BODY) return;
    if (!readableContentType(response.headers.get('content-type'))) return;
    response.clone().text().then(text => {
      if (text.length <= MAX_BODY) scanText(text);
    }).catch(() => {});
  }

  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const result = Reflect.apply(originalFetch, this, args);
    try {
      const raw = args[0] instanceof Request ? args[0].url : String(args[0] || '');
      const url = new URL(raw, location.href);
      if (url.origin === location.origin || url.hostname.endsWith('facebook.com')) result.then(scanResponse).catch(() => {});
    } catch {}
    return result;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    try {
      this.__bdmUrl = new URL(String(url || ''), location.href);
    } catch {
      this.__bdmUrl = null;
    }
    return Reflect.apply(originalOpen, this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    const requestUrl = this.__bdmUrl;
    if (requestUrl && (requestUrl.origin === location.origin || requestUrl.hostname.endsWith('facebook.com'))) {
      this.addEventListener('load', function () {
        try {
          const type = this.responseType;
          if (this.status >= 200 && this.status < 300 && (type === '' || type === 'text') && this.responseText && this.responseText.length <= MAX_BODY) {
            scanText(this.responseText);
          }
        } catch {}
      }, { once: true });
    }
    return Reflect.apply(originalSend, this, args);
  };

  function fiberOf(element) {
    for (const key of Object.keys(element || {})) {
      if (key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$')) return element[key];
    }
    return null;
  }

  function inspectVideo(video) {
    const result = { ids: [], manifest: '', hdUrl: '', sdUrl: '', duration: 0, width: 0, height: 0, isHD: false };
    let node = video;
    for (let depth = 0; depth < 20 && node; depth++, node = node.parentElement) {
      let fiber = fiberOf(node);
      for (let level = 0; level < 20 && fiber; level++, fiber = fiber.return) {
        const props = fiber.memoizedProps;
        if (!props || typeof props !== 'object') continue;
        const meta = props.coreVideoPlayerMetaData ||
          (props.videoPlayerConfig && props.videoPlayerConfig.coreVideoPlayerMetaData) ||
          (props.videoData && props.videoData.coreVideoPlayerMetaData);
        if (meta) {
          if (meta.videoFBID && /^\d{5,30}$/.test(String(meta.videoFBID))) result.ids.push(String(meta.videoFBID));
          const manifest = meta.dash_manifest || meta.dashManifest;
          if (!result.manifest && typeof manifest === 'string') result.manifest = manifest;
          result.hdUrl = result.hdUrl || meta.hdSrc || meta.playableUrlQualityHD || meta.playable_url_quality_hd || '';
          result.sdUrl = result.sdUrl || meta.sdSrc || meta.playableUrlQualitySD || meta.playable_url_quality_sd || '';
          if (meta.duration && !result.duration) result.duration = Number(meta.duration) || 0;
          if (meta.dimensions) {
            result.width = result.width || Number(meta.dimensions.width || meta.dimensions.videoWidth) || 0;
            result.height = result.height || Number(meta.dimensions.height || meta.dimensions.videoHeight) || 0;
          }
          result.isHD = result.isHD || !!meta.isHD || !!result.hdUrl;
        }
        if (props.videoFBID && /^\d{5,30}$/.test(String(props.videoFBID))) result.ids.push(String(props.videoFBID));
      }
    }
    return result;
  }

  function visibleVideos() {
    const list = [];
    for (const video of Array.from(document.querySelectorAll('video'))) {
      try {
        const rect = video.getBoundingClientRect();
        if (rect.width >= 80 && rect.height >= 60) list.push(video);
      } catch { list.push(video); }
    }
    return list;
  }

  // Facebook keeps several <video> elements alive (autoplay previews, the next reel).
  // The widget's own marker wins, then the largest playing element - never the first
  // node in the DOM, which is usually a preloaded neighbour.
  function activeVideo() {
    const marked = document.querySelector('video[data-bdm-active="true"]');
    if (marked) return marked;
    const candidates = visibleVideos();
    return candidates.find(v => !v.paused && !v.ended && v.readyState > 0) ||
      candidates[0] ||
      document.querySelector('video');
  }

  function meta(property, attribute = 'content') {
    const node = document.querySelector(`meta[property="${property}"], meta[name="${property}"]`);
    return node ? node.getAttribute(attribute) || '' : '';
  }

  function elementVideoIds(video) {
    // The wrapper around the element is the safest name for the clip: it follows a Reels
    // scroll even when the React props and the address bar still name the first reel.
    const id = api.videoIdFromElement(video);
    if (!api.isVideoId(id)) return [];
    return [String(id)];
  }

  function manifestFor(ids, pageId, target) {
    for (const id of ids) {
      const entry = cache.get(id);
      if (fresh(entry) && api.manifestFits(entry.manifest, target)) return entry.manifest;
    }
    if (pageId) {
      const entry = cache.get(pageId);
      if (fresh(entry) && api.manifestFits(entry.manifest, target)) return entry.manifest;
    }
    return null;
  }

  // Facebook preloads the next reels, so a manifest can arrive before its id is known
  // (or before the page URL changes). Match those leftovers to the clip the player is
  // actually showing instead of discarding them: the widget would then fall back to a
  // single "playing resolution" row.
  function pickEntry(list, target) {
    const manifest = api.pickManifest(list.map(entry => entry.manifest), target);
    if (!manifest) return null;
    return list.find(entry => entry.manifest === manifest) || null;
  }

  // Only accept a preload from a different id when exactly one of them matches the
  // element's length and rendition. Two equally good candidates stay unreported instead
  // of guessing, so another reel's URLs are never offered.
  function pickUniqueEntry(list, target) {
    let best = null, bestScore = 0, ties = 0;
    for (const entry of list) {
      const score = api.manifestScore(entry.manifest, target);
      if (score <= 0) continue;
      if (score > bestScore) {
        best = entry;
        bestScore = score;
        ties = 0;
      } else if (score === bestScore) {
        ties++;
      }
    }
    return ties ? null : best;
  }

  function recoverManifest(ids, pageId, target) {
    const known = new Set(ids.concat(pageId ? [pageId] : []));
    const entries = recent.filter(entry => Date.now() - entry.ts < MANIFEST_TTL_MS);
    const related = entries.filter(entry => !known.size || !entry.ids.length || entry.ids.some(id => known.has(id)));
    let entry = pickEntry(related, target);
    // A scrolled-to reel keeps its own id while the DOM and address bar still name the
    // previous one. Once the element's length is known, duration and rendition can pick
    // that manifest out of the preloads without waiting for an id that never changes.
    if (!entry && Number(target && target.duration) > 0) {
      const disjoint = entries.filter(entry => entry.ids.length && !entry.ids.some(id => known.has(id)));
      entry = pickUniqueEntry(disjoint, target);
    }
    if (!entry) return null;
    for (const id of ids) cache.set(id, { manifest: entry.manifest, ts: Date.now() });
    return { manifest: entry.manifest, id: entry.ids[0] || '' };
  }

  let hasManifestForCurrent = false;
  let lastActiveVideo = null;

  function report(force = false) {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastSignature = '';
      // A fresh URL may be a different reel: re-read its page right away instead of
      // waiting for the page-scan throttle, and re-report even if the numbers repeat.
      lastPageScan = 0;
      lastActiveVideo = null;
    }
    const video = activeVideo();
    // Detect active video change (e.g., Reels scroll) and trigger fresh capture
    if (video !== lastActiveVideo) {
      lastActiveVideo = video;
      lastSignature = '';
      if (video && !force) {
        // Schedule a scan for the new active video
        setTimeout(() => scanPageHtml(), 100);
      }
    }
    const inspected = video ? inspectVideo(video) : { ids: [] };
    // The wrapper around the element is the safest name for the clip (it follows a Reels
    // scroll); the React fiber id is the fallback when the DOM carries none.
    const ids = elementVideoIds(video);
    if (!ids.length && inspected.ids.length && api.isVideoId(inspected.ids[0])) {
      ids.push(String(inspected.ids[0]));
    }
    const pageId = api.videoIdFromUrl(location.href);
    // Bind the element's own manifest to its primary id only: the fiber walk can also see
    // a neighbouring reel's data, and another id here would leak this manifest there.
    if (inspected.manifest) remember(inspected.manifest, ids.slice(0, 1));
    const target = {
      duration: Number(video && video.duration) || Number(inspected.duration) || 0,
      width: Number(video && video.videoWidth) || Number(inspected.width) || 0,
      height: Number(video && video.videoHeight) || Number(inspected.height) || 0
    };
    let manifest = manifestFor(ids, pageId, target);
    // A manifest found under the element's (or the page's) id is identified; one recovered
    // purely by clip length is not, so it must not borrow the page id as its name.
    const identified = !!manifest;
    let recoveredId = '';
    if (!manifest) {
      const recovered = recoverManifest(ids, pageId, target);
      if (recovered) {
        manifest = recovered.manifest;
        recoveredId = recovered.id;
      }
    }
    hasManifestForCurrent = !!manifest;
    const rows = (api.variants(manifest) || []).slice(0, 100);
    const audio = api.audioChoice(manifest);
    const heights = Array.from(new Set(rows.map(row => Number(row.height)).filter(Boolean))).sort((a, b) => b - a);
    const metaWidth = Number(meta('og:video:width')) || 0;
    const metaHeight = Number(meta('og:video:height')) || 0;
    const videoId = recoveredId || ids[0] || (identified ? pageId : '') || '';
    const elementDuration = Number(video && video.duration);
    const data = {
      platform: 'facebook',
      videoId,
      canonicalUrl: videoId ? `https://www.facebook.com/watch/?v=${videoId}` : '',
      title: meta('og:title') || document.title || '',
      // The element is the source of truth for this report: it is what the widget checks
      // the manifest against, and what changes when the viewer scrolls to another reel.
      duration: (isFinite(elementDuration) && elementDuration > 0 ? elementDuration : 0) ||
        inspected.duration || (manifest && manifest.duration) || 0,
      width: Number(video && video.videoWidth) || inspected.width || metaWidth || 0,
      height: Number(video && video.videoHeight) || inspected.height || metaHeight || 0,
      isHD: inspected.isHD || heights.some(height => height >= 720),
      maxHeight: heights[0] || 0,
      resolutions: heights,
      variants: rows,
      audio: audio ? {
        url: audio.url, bitrate: audio.bitrate, quality: audio.quality,
        label: audio.label, mimeType: audio.mimeType, codecs: audio.codecs, ext: audio.ext
      } : null,
      audioUrl: audio ? audio.url : '',
      // og:video belongs to the first document Facebook rendered; after scrolling to the
      // next reel it would download the wrong clip. Only trust the element's own metadata.
      hdUrl: inspected.hdUrl || '',
      sdUrl: inspected.sdUrl || ''
    };
    const signature = JSON.stringify([
      data.videoId, data.duration, data.width, data.height, data.hdUrl,
      rows.map(row => [row.url, row.bandwidth, row.width, row.height]),
      audio && audio.url
    ]);
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    window.postMessage({ type: 'bdm-facebook-media', data }, '*');
  }

  function scanPageHtml() {
    const now = Date.now();
    const minGap = hasManifestForCurrent ? PAGE_SCAN_MIN_MS : PAGE_SCAN_RETRY_MS;
    if (now - lastPageScan < minGap) return;
    lastPageScan = now;
    const pageUrl = location.href;
    const pageId = api.videoIdFromUrl(pageUrl);
    fetch(pageUrl, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(response => (response && response.ok ? response.text() : ''))
      .then(text => {
        // The page may have been navigated while the HTML was in flight.
        if (location.href !== pageUrl) return;
        scanText(text, pageId || '');
      })
      .catch(() => {});
  }

  window.addEventListener('message', event => {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_MEDIA_INFO__') {
      if (!hasManifestForCurrent) scanPageHtml();
      report(true);
    }
  });
  window.addEventListener('popstate', () => setTimeout(() => report(true), 300));
  document.addEventListener('DOMContentLoaded', () => report(true), { once: true });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) report(true);
  });

  setInterval(() => {
    report(false);
    if (!hasManifestForCurrent) scanPageHtml();
  }, 2500);
  setTimeout(() => report(true), 800);
})();
