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
  const MANIFEST_KEYS = new Set(['dash_manifest', 'dashManifest', 'video_dash_manifest', 'dash_manifest_xml_string']);
  const cache = new Map(); // videoFBID | __latest__ -> { manifest, ts }
  let latest = null;
  let lastSignature = '';
  let lastUrl = location.href;
  let lastPageScan = 0;

  function remember(xml, ids) {
    if (typeof xml !== 'string' || xml.length < 64) return false;
    const parsed = api.parseManifest(xml);
    if (!parsed) return false;
    const keys = new Set(['__latest__']);
    for (const id of ids || []) {
      const key = String(id || '').trim();
      if (/^\d{1,30}$/.test(key)) keys.add(key);
    }
    for (const key of keys) {
      const entry = cache.get(key);
      const manifest = api.mergeManifest(entry && entry.manifest, parsed);
      if (!manifest) continue;
      const value = { manifest, ts: Date.now() };
      cache.set(key, value);
      if (key === '__latest__') latest = value;
    }
    while (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value);
    return true;
  }

  function fresh(entry) {
    return !!entry && Date.now() - entry.ts < MANIFEST_TTL_MS;
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

  function scanText(text) {
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

  function activeVideo() {
    return document.querySelector('video[data-bdm-active="true"]') ||
      Array.from(document.querySelectorAll('video')).find(v => !v.paused && !v.ended && v.readyState > 1) ||
      document.querySelector('video');
  }

  function meta(property, attribute = 'content') {
    const node = document.querySelector(`meta[property="${property}"], meta[name="${property}"]`);
    return node ? node.getAttribute(attribute) || '' : '';
  }

  function manifestFor(ids) {
    for (const id of ids) {
      const entry = cache.get(String(id));
      if (fresh(entry)) return entry.manifest;
    }
    return fresh(latest) ? latest.manifest : null;
  }

  function report(force = false) {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastSignature = '';
    }
    const video = activeVideo();
    const inspected = video ? inspectVideo(video) : { ids: [] };
    const ids = inspected.ids.slice();
    const datasetId = video && video.dataset && video.dataset.videoFbid;
    if (datasetId && /^\d{5,30}$/.test(String(datasetId))) ids.push(String(datasetId));
    if (inspected.manifest) remember(inspected.manifest, ids);
    const manifest = manifestFor(ids);
    const rows = (api.variants(manifest) || []).slice(0, 100);
    const audio = api.audioChoice(manifest);
    const heights = Array.from(new Set(rows.map(row => Number(row.height)).filter(Boolean))).sort((a, b) => b - a);
    const metaWidth = Number(meta('og:video:width')) || 0;
    const metaHeight = Number(meta('og:video:height')) || 0;
    const data = {
      platform: 'facebook',
      videoId: ids[0] || '',
      canonicalUrl: ids[0] ? `https://www.facebook.com/watch/?v=${ids[0]}` : '',
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
      hdUrl: inspected.hdUrl || meta('og:video:secure_url') || meta('og:video') || '',
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
    fetch(location.href, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(response => (response && response.ok ? response.text() : ''))
      .then(text => scanText(text))
      .catch(() => {});
  }

  window.addEventListener('message', event => {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_MEDIA_INFO__') {
      if (!fresh(latest)) scanPageHtml();
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
    if (!fresh(latest)) scanPageHtml();
  }, 2500);
  setTimeout(() => report(true), 800);
})();
