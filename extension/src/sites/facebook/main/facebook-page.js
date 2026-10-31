// Bengal DM - Facebook DASH capture (MAIN world)
// Facebook sends the full DASH manifest inside GraphQL/HTML payloads. We keep every
// <Representation> (not just the distinct heights) and publish it to the content script,
// so the chooser can list e.g. both 720p bitrates the video actually offers.
(() => {
  const host = location.hostname.toLowerCase();
  const isFacebook = host === 'facebook.com' || host.endsWith('.facebook.com') ||
    host === 'fb.watch' || host.endsWith('.fb.watch') ||
    host === 'fb.com' || host.endsWith('.fb.com');
  if (!isFacebook) return;
  const api = globalThis.bdmFacebook;
  if (!api) return;

  const MAX_BODY = 4 * 1024 * 1024;
  const MAX_ENTRIES = 30;
  const MANIFEST_TTL_MS = 10 * 60 * 1000;
  const ANONYMOUS_TTL_MS = 45 * 1000;
  const ANONYMOUS_KEY = '__anonymous__';
  const MANIFEST_KEYS = new Set(['dash_manifest', 'dashManifest', 'video_dash_manifest', 'dash_manifest_xml_string']);
  const cache = new Map(); // videoFBID | __anonymous__ -> { manifest, ts }
  let anonymous = null;
  let lastSignature = '';
  let lastUrl = location.href;
  let lastPageScan = 0;

  function remember(xml, ids) {
    if (typeof xml !== 'string' || xml.length < 64) return false;
    const parsed = api.parseManifest(xml);
    if (!parsed) return false;
    const keys = new Set();
    for (const id of ids || []) {
      if (api.isVideoId(id)) keys.add(String(id));
    }
    // An unattributed manifest must never be reused for a video we can name: Facebook
    // preloads the neighbouring reels, so "the last manifest seen" is often another video.
    const isAnonymous = keys.size === 0;
    if (isAnonymous) keys.add(ANONYMOUS_KEY);
    for (const key of keys) {
      const entry = cache.get(key);
      const manifest = api.mergeManifest(entry && entry.manifest, parsed);
      if (!manifest) continue;
      const value = { manifest, ts: Date.now() };
      cache.set(key, value);
      if (key === ANONYMOUS_KEY) anonymous = value;
    }
    while (cache.size > MAX_ENTRIES) {
      const oldest = cache.keys().next().value;
      if (oldest === ANONYMOUS_KEY && cache.size > 1) { cache.delete(oldest); continue; }
      cache.delete(oldest);
      if (oldest === ANONYMOUS_KEY) anonymous = null;
    }
    return true;
  }

  function fresh(entry, maxAge) {
    return !!entry && Date.now() - entry.ts < maxAge;
  }

  function decodeJsonString(raw) {
    try {
      return JSON.parse('"' + raw + '"');
    } catch {
      return '';
    }
  }

  function nearbyIds(text, index) {
    const windowText = text.slice(Math.max(0, index - 3000), index + 3000);
    const ids = [];
    for (const re of [/"videoFBID"\s*:\s*"?(\d{5,30})"?/g, /"video_id"\s*:\s*"?(\d{5,30})"?/g, /"videoId"\s*:\s*"?(\d{5,30})"?/g]) {
      let match;
      while ((match = re.exec(windowText)) !== null) ids.push(match[1]);
    }
    return ids;
  }

  function collectFromJson(value, out, depth = 0, inheritedIds = []) {
    if (!value || typeof value !== 'object' || depth > 12 || out.length > 40) return;
    const ids = inheritedIds.slice();
    for (const key of ['videoFBID', 'video_id', 'videoId']) {
      const id = value[key];
      if (id !== undefined && id !== null && /^\d{5,30}$/.test(String(id))) ids.push(String(id));
    }
    for (const key of Object.keys(value)) {
      const child = value[key];
      if (MANIFEST_KEYS.has(key) && typeof child === 'string' && child.length > 64) {
        out.push({ xml: child, ids });
      } else if (key === 'dash_manifests' && Array.isArray(child)) {
        for (const entry of child) {
          if (entry && typeof entry.manifest_xml === 'string') out.push({ xml: entry.manifest_xml, ids });
        }
      } else if (child && typeof child === 'object') {
        collectFromJson(child, out, depth + 1, ids);
      }
    }
  }

  function scanText(text, extraIds) {
    if (typeof text !== 'string' || text.length < 64) return false;
    if (!/dash_manifest|dashManifest|dash_manifests|video_dash_manifest|dash_manifest_xml_string/i.test(text)) return false;
    const found = [];
    const trimmed = text.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        collectFromJson(JSON.parse(trimmed), found);
      } catch {}
    }
    const manifestRe = /"(dash_manifest|dashManifest|video_dash_manifest|dash_manifest_xml_string)"\s*:\s*"((?:\\.|[^"\\])*)"/g;
    let match;
    while ((match = manifestRe.exec(text)) !== null) {
      const xml = decodeJsonString(match[2]);
      if (xml) found.push({ xml, ids: nearbyIds(text, match.index) });
    }
    const listRe = /"dash_manifests"\s*:\s*(\[[\s\S]*?\])/g;
    while ((match = listRe.exec(text)) !== null) {
      try {
        const list = JSON.parse(match[1]);
        const ids = nearbyIds(text, match.index);
        for (const entry of Array.isArray(list) ? list : []) {
          if (entry && typeof entry.manifest_xml === 'string') found.push({ xml: entry.manifest_xml, ids });
        }
      } catch {}
    }
    if (extraIds && extraIds.length) {
      for (const item of found) item.ids = item.ids.concat(extraIds);
    }
    let captured = false;
    for (const item of found) captured = remember(item.xml, item.ids) || captured;
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
    for (let depth = 0; depth < 15 && node; depth++, node = node.parentElement) {
      let fiber = fiberOf(node);
      for (let level = 0; level < 12 && fiber; level++, fiber = fiber.return) {
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
    const ids = [];
    const add = value => {
      if (!api.isVideoId(value)) return;
      const id = String(value);
      if (!ids.includes(id)) ids.push(id);
    };
    try {
      if (video && video.dataset) { add(video.dataset.videoFbid); add(video.dataset.videoId); }
      if (ids.length) return ids;
      let node = video && video.parentElement;
      for (let depth = 0; depth < 8 && node; depth++, node = node.parentElement) {
        const id = node.getAttribute && (node.getAttribute('data-video-id') || node.getAttribute('data-videoid'));
        // A feed wrapper can carry the id of the first post it contains, so only trust a
        // container that holds this one video.
        if (api.isVideoId(id) && node.querySelectorAll('video').length === 1) add(id);
      }
    } catch {}
    return ids;
  }

  function durationAgrees(manifest, video) {
    const wanted = Number(video && video.duration) || 0;
    const offered = Number(manifest && manifest.duration) || 0;
    if (!wanted || !offered) return true;
    return Math.abs(wanted - offered) <= 3;
  }

  function manifestFor(ids, pageId) {
    for (const id of ids) {
      const entry = cache.get(id);
      if (fresh(entry, MANIFEST_TTL_MS)) return entry.manifest;
    }
    if (!ids.length && pageId) {
      const entry = cache.get(pageId);
      if (fresh(entry, MANIFEST_TTL_MS)) return entry.manifest;
    }
    return null;
  }

  let hasManifestForCurrent = false;

  function report(force = false) {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastSignature = '';
      // An unattributed manifest belongs to whatever video was on the previous URL.
      cache.delete(ANONYMOUS_KEY);
      anonymous = null;
    }
    const video = activeVideo();
    const inspected = video ? inspectVideo(video) : { ids: [] };
    const ids = inspected.ids.slice();
    for (const id of elementVideoIds(video)) if (!ids.includes(id)) ids.push(id);
    const pageId = api.videoIdFromUrl(location.href);
    if (inspected.manifest) remember(inspected.manifest, ids);
    let manifest = manifestFor(ids, pageId);
    if (!manifest && !ids.length && !pageId) {
      const entry = anonymous;
      if (fresh(entry, ANONYMOUS_TTL_MS) && durationAgrees(entry.manifest, video)) manifest = entry.manifest;
    }
    hasManifestForCurrent = !!manifest;
    const rows = (api.variants(manifest) || []).slice(0, 100);
    const audio = api.audioChoice(manifest);
    const heights = Array.from(new Set(rows.map(row => Number(row.height)).filter(Boolean))).sort((a, b) => b - a);
    const metaWidth = Number(meta('og:video:width')) || 0;
    const metaHeight = Number(meta('og:video:height')) || 0;
    const videoId = ids[0] || (manifest ? pageId : '') || '';
    const data = {
      platform: 'facebook',
      videoId,
      canonicalUrl: videoId ? `https://www.facebook.com/watch/?v=${videoId}` : '',
      title: meta('og:title') || document.title || '',
      duration: inspected.duration || (manifest && manifest.duration) || (video && video.duration) || 0,
      width: inspected.width || metaWidth || (video && video.videoWidth) || 0,
      height: inspected.height || metaHeight || (video && video.videoHeight) || 0,
      isHD: inspected.isHD || heights.some(height => height >= 720),
      maxHeight: heights[0] || 0,
      resolutions: heights,
      variants: rows,
      audio: audio ? {
        url: audio.url, bitrate: audio.bitrate, quality: audio.quality,
        label: audio.label, mimeType: audio.mimeType, codecs: audio.codecs, ext: audio.ext
      } : null,
      audioUrl: audio ? audio.url : '',
      hdUrl: inspected.hdUrl || (manifest ? (meta('og:video:secure_url') || meta('og:video') || '') : ''),
      sdUrl: inspected.sdUrl || ''
    };
    const signature = JSON.stringify([
      data.videoId, data.hdUrl, data.width, data.height,
      rows.map(row => [row.url, row.bandwidth, row.width, row.height]),
      audio && audio.url
    ]);
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    window.postMessage({ type: 'bdm-facebook-media', data }, '*');
  }

  function scanPageHtml() {
    if (Date.now() - lastPageScan < 15000) return;
    lastPageScan = Date.now();
    const pageUrl = location.href;
    const pageId = api.videoIdFromUrl(pageUrl);
    fetch(pageUrl, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(response => (response && response.ok ? response.text() : ''))
      .then(text => {
        // The page may have been navigated while the HTML was in flight.
        if (location.href !== pageUrl) return;
        scanText(text, pageId ? [pageId] : []);
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
