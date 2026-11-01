// Bengal DM - Alternate-method YouTube stream observation (background worker)
// Records googlevideo /videoplayback URLs the page's own player fetched successfully,
// so bdmYouTube.choices() can offer those proven direct URLs instead of yt-dlp resolution.
// Also captures the player's SABR ABR session (protobuf requestBody POST) so the desktop
// can stream the selected quality directly. YouTube Alternate path only; the
// Default/standard pipeline never reads this module.
(function (root) {
  const MAX_PER_TAB = 100, MAX_TABS = 50;
  const MAX_ABR_BODY = 262144, MAX_SEEDS = 200;
  const SABR_CAPTURE_TTL_MS = 6 * 60 * 60 * 1000; // sessions age out with the poToken inside
  const api = (typeof globalThis.browser !== 'undefined' && globalThis.browser?.runtime?.id)
    ? globalThis.browser
    : (typeof globalThis.chrome !== 'undefined' ? globalThis.chrome : null);

  const observedByTab = new Map(); // tabId -> Array of raw URLs, newest first
  const sabrSeeds = new Map();     // requestId -> { tabId, url, requestBody (base64) }
  const sabrCaptures = new Map();  // tabId -> { url, requestBody, ts }

  const isPlayable = (mime) => /^(video|audio)\//i.test(String(mime || ''));

  function contentTypeOf(details) {
    const header = (details.responseHeaders || []).find(h => h.name && h.name.toLowerCase() === 'content-type');
    return header ? String(header.value || '') : '';
  }

  function remember(tabId, url) {
    if (!(tabId >= 0) || !url) return;
    let urls = observedByTab.get(tabId);
    if (!urls) {
      urls = [];
      observedByTab.set(tabId, urls);
      if (observedByTab.size > MAX_TABS) observedByTab.delete(observedByTab.keys().next().value);
    }
    if (!urls.includes(url)) {
      urls.unshift(url);
      if (urls.length > MAX_PER_TAB) urls.length = MAX_PER_TAB;
    }
  }

  function bytesToBase64(bytes) {
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  // Core webRequest.onBeforeRequest(['requestBody']) filter for the player's SABR POST.
  function observeAbrRequest(details) {
    if (!details || !(details.tabId >= 0)) return;
    const url = root.bdmYouTube?.sabrUrl(details.url);
    if (!url) return;
    const raw = details.requestBody && details.requestBody.raw;
    if (!Array.isArray(raw) || !raw.length) return;
    let total = 0;
    for (const part of raw) total += (part && part.bytes) ? part.bytes.byteLength : 0;
    if (!total || total > MAX_ABR_BODY) return;
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const part of raw) {
      if (part && part.bytes) { bytes.set(new Uint8Array(part.bytes), offset); offset += part.bytes.byteLength; }
    }
    sabrSeeds.set(details.requestId, { tabId: details.tabId, url, requestBody: bytesToBase64(bytes) });
    if (sabrSeeds.size > MAX_SEEDS) sabrSeeds.delete(sabrSeeds.keys().next().value);
  }

  function rememberCapture(details, sabrUrl) {
    const seed = sabrSeeds.get(details.requestId);
    if (seed && seed.tabId === details.tabId && seed.url === sabrUrl) {
      sabrCaptures.set(details.tabId, { url: sabrUrl, requestBody: seed.requestBody, ts: Date.now() });
      if (sabrCaptures.size > MAX_TABS) sabrCaptures.delete(sabrCaptures.keys().next().value);
    }
    sabrSeeds.delete(details.requestId);
  }

  // Core webRequest.onHeadersReceived filter, kept listener-free for tests.
  function observe(details) {
    if (!details || !(details.tabId >= 0)) return;
    const accepted = details.statusCode === 200 || details.statusCode === 206;
    const sabr = root.bdmYouTube?.sabrUrl(details.url);
    if (sabr) {
      if (accepted) rememberCapture(details, sabr);
      else sabrSeeds.delete(details.requestId);
      return;
    }
    if (!accepted) return;
    if (!isPlayable(contentTypeOf(details))) return;
    remember(details.tabId, root.bdmYouTube?.mediaUrl(details.url) || '');
  }

  function getObserved(tabId) {
    return observedByTab.get(tabId) || [];
  }

  function getCapture(tabId) {
    const capture = sabrCaptures.get(tabId);
    if (!capture) return null;
    if (Date.now() - capture.ts > SABR_CAPTURE_TTL_MS) {
      sabrCaptures.delete(tabId);
      return null;
    }
    return capture;
  }

  function clear(tabId) {
    observedByTab.delete(tabId);
    sabrCaptures.delete(tabId);
    for (const [requestId, seed] of sabrSeeds) {
      if (seed.tabId === tabId) sabrSeeds.delete(requestId);
    }
  }

  if (api?.webRequest?.onHeadersReceived) {
    api.webRequest.onHeadersReceived.addListener(observe, {
      urls: ['*://*.googlevideo.com/videoplayback*']
    }, ['responseHeaders']);
  }
  if (api?.webRequest?.onBeforeRequest) {
    api.webRequest.onBeforeRequest.addListener(observeAbrRequest, {
      urls: ['*://*.googlevideo.com/videoplayback*']
    }, ['requestBody']);
  }
  if (api?.tabs?.onRemoved) {
    api.tabs.onRemoved.addListener(clear);
  }
  if (api?.tabs?.onUpdated) {
    api.tabs.onUpdated.addListener((tabId, change) => {
      if (change && change.status === 'loading') clear(tabId);
    });
  }

  root.bdmYouTubeDirect = { observe, observeAbrRequest, getObserved, getCapture, clear };
  if (typeof module !== 'undefined') module.exports = root.bdmYouTubeDirect;
})(globalThis);
