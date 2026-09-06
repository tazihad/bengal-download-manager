// --- CONSTANTS & HELPERS ---
const DEFAULT_IGNORED_EXTS = [
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
  'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
  'woff', 'woff2', 'eot', 'ttf', 'otf',
  'm3u8', 'mpd', 'ts', 'm4s'
];

const RECOGNIZED_DOWNLOAD_EXTS = [
  'exe', 'msi', 'zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'xz',
  'iso', 'dmg', 'apk', 'deb', 'rpm', 'bin', 'appimage', 'pkg',
  'pdf', 'epub', 'mobi', 'djvu',
  'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v',
  'mp3', 'flac', 'wav', 'ogg', 'm4a', 'aac', 'opus',
  'torrent'
];

function getFileExtension(urlOrFilename) {
  if (!urlOrFilename) return "";
  const clean = urlOrFilename.split('?')[0].split('#')[0];
  const parts = clean.split('/');
  const lastPart = parts.pop() || "";
  const subParts = lastPart.split('.');
  return subParts.length > 1 ? subParts.pop().toLowerCase() : "";
}

// --- WHITELIST & BLACKLIST FILTER RULES ---
let cachedFilterRules = {
  enableInterception: true,
  enableMediaSniffing: true,
  whitelistUrls: [],
  whitelistExts: [],
  blacklistUrls: [],
  blacklistExts: []
};

// --- APP CONNECTION & TOOLBAR ICON BADGE STATE ---
let cachedAppOnline = false;

function getActionAPI() {
  if (typeof chrome !== 'undefined') {
    if (chrome.action) return chrome.action;
    if (chrome.browserAction) return chrome.browserAction;
  }
  if (typeof browser !== 'undefined') {
    if (browser.action) return browser.action;
    if (browser.browserAction) return browser.browserAction;
  }
  return null;
}

function applyDownloadUiOptions(isOnline) {
  if (chrome.downloads && chrome.downloads.setUiOptions) {
    try {
      chrome.downloads.setUiOptions({ enabled: !isOnline }).catch(() => {});
    } catch {}
  }
}

function broadcastConnectionStatus(isOnline) {
  try {
    chrome.tabs.query({}, (tabs) => {
      if (chrome.runtime.lastError || !tabs) return;
      for (const tab of tabs) {
        if (tab && tab.id) {
          chrome.tabs.sendMessage(tab.id, {
            action: "connection_status_changed",
            online: Boolean(isOnline)
          }).catch(() => {});
        }
      }
    });
  } catch {}
}

async function updateAppConnectionBadge(isOnline) {
  const onlineBool = Boolean(isOnline);
  const statusChanged = (cachedAppOnline !== onlineBool);
  cachedAppOnline = onlineBool;
  applyDownloadUiOptions(cachedAppOnline);
  if (statusChanged) {
    broadcastConnectionStatus(cachedAppOnline);
  }
  const action = getActionAPI();
  if (!action) return;

  try {
    if (cachedAppOnline) {
      if (action.setBadgeText) {
        await action.setBadgeText({ text: '' });
      }
      if (action.setTitle) {
        await action.setTitle({ title: 'Bengal DM' });
      }
    } else {
      if (action.setBadgeText) {
        await action.setBadgeText({ text: '!' });
      }
      if (action.setBadgeBackgroundColor) {
        await action.setBadgeBackgroundColor({ color: '#FFB300' });
      }
      if (action.setBadgeTextColor) {
        try { await action.setBadgeTextColor({ color: '#000000' }); } catch {}
      }
      if (action.setTitle) {
        await action.setTitle({ title: 'Bengal DM (App Disconnected)' });
      }
    }
  } catch (e) {
    console.warn("Could not update extension toolbar badge:", e);
  }
}

function refreshFilterRules() {
  chrome.storage.local.get(cachedFilterRules, (items) => {
    cachedFilterRules = { ...cachedFilterRules, ...items };
  });
}
refreshFilterRules();

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local') {
    for (const key of ['enableInterception', 'enableMediaSniffing', 'whitelistUrls', 'whitelistExts', 'blacklistUrls', 'blacklistExts']) {
      if (changes[key] !== undefined) {
        cachedFilterRules[key] = changes[key].newValue;
      }
    }
  }
});

async function getFilterRules() {
  return new Promise((resolve) => {
    chrome.storage.local.get(cachedFilterRules, (items) => {
      cachedFilterRules = { ...cachedFilterRules, ...items };
      resolve(cachedFilterRules);
    });
  });
}

function parseDomainAndPath(rawInput) {
  if (!rawInput || typeof rawInput !== 'string') return { hostname: "", pathname: "", raw: "" };
  let str = rawInput.trim().toLowerCase();
  // Strip wildcard prefix if present e.g. *.example.com -> example.com
  let hasWildcard = false;
  if (str.startsWith('*.')) {
    hasWildcard = true;
    str = str.substring(2);
  } else if (str.startsWith('*')) {
    hasWildcard = true;
    str = str.substring(1);
  }

  // Prepend dummy protocol if missing to parse cleanly via URL parser
  let toParse = str;
  if (!toParse.includes('://')) {
    toParse = 'http://' + toParse;
  }

  try {
    const parsed = new URL(toParse);
    let hostname = parsed.hostname.toLowerCase();
    let pathname = parsed.pathname || "";
    if (pathname === '/') pathname = "";
    return { hostname, pathname, hasWildcard, raw: str };
  } catch (e) {
    return { hostname: str.replace(/\/.*$/, ''), pathname: "", hasWildcard, raw: str };
  }
}

function matchesUrlOrDomain(targetUrl, urlPatterns, referrerUrl) {
  if (!Array.isArray(urlPatterns) || urlPatterns.length === 0) return false;
  
  const targets = [];
  if (targetUrl) targets.push(targetUrl);
  if (referrerUrl && typeof referrerUrl === 'string' && referrerUrl.startsWith('http')) {
    targets.push(referrerUrl);
  }
  if (targets.length === 0) return false;

  for (const pattern of urlPatterns) {
    if (!pattern || typeof pattern !== 'string') continue;
    const pInfo = parseDomainAndPath(pattern);
    if (!pInfo.hostname && !pInfo.raw) continue;

    for (const testUrl of targets) {
      const urlLower = testUrl.toLowerCase();
      const tInfo = parseDomainAndPath(urlLower);

      // Direct substring match if pattern specifies specific path or query
      if (pInfo.pathname && urlLower.includes(pInfo.raw)) {
        return true;
      }

      // Hostname comparison
      if (pInfo.hostname && tInfo.hostname) {
        if (tInfo.hostname === pInfo.hostname) {
          // If pattern also has pathname requirement
          if (pInfo.pathname) {
            if (tInfo.pathname.startsWith(pInfo.pathname)) return true;
          } else {
            return true;
          }
        }
        // Subdomain matching (e.g. sub.mirror.xeonbd.com matches mirror.xeonbd.com or xeonbd.com)
        if (tInfo.hostname.endsWith('.' + pInfo.hostname)) {
          if (pInfo.pathname) {
            if (tInfo.pathname.startsWith(pInfo.pathname)) return true;
          } else {
            return true;
          }
        }
      }

      // Fallback substring search for raw pattern if user typed partial keyword
      if (pInfo.raw && urlLower.includes(pInfo.raw)) {
        return true;
      }
    }
  }
  return false;
}

function matchesExtension(extOrFilename, extList) {
  if (!extOrFilename || !Array.isArray(extList) || extList.length === 0) return false;
  let ext = extOrFilename.toLowerCase();
  if (ext.includes('.') && !ext.startsWith('.')) {
    ext = getFileExtension(ext);
  }
  ext = ext.replace(/^\./, '').trim();
  if (!ext) return false;

  for (const item of extList) {
    const cleanItem = item.toLowerCase().replace(/^\./, '').trim();
    if (cleanItem && ext === cleanItem) return true;
  }
  return false;
}

function isStreamingMedia(url, filename) {
  const u = (url || '').toLowerCase();
  const f = (filename || '').toLowerCase();

  if (u.includes('googlevideo.com') || u.includes('/videoplayback') || u.includes('/seg-') || u.includes('/fragment-') || u.includes('/range/')) {
    return true;
  }
  if (u.includes('.m3u8') || u.includes('.mpd') || u.includes('.ts?') || u.endsWith('.ts') || u.includes('.m4s') || u.includes('/hls/') || u.includes('/hls2/')) {
    return true;
  }
  if (f.includes('.m3u8') || f.includes('.mpd') || f.includes('.ts') || f.includes('.m4s') || f.includes('videoplayback')) {
    return true;
  }

  const extU = getFileExtension(u);
  const extF = getFileExtension(f);
  const streamingExts = ['m3u8', 'mpd', 'ts', 'm4s', 'key'];
  if (streamingExts.includes(extU) || streamingExts.includes(extF)) {
    return true;
  }

  return false;
}

function shouldInterceptDownloadSync(url, filename, referrer) {
  if (!url || isIgnoredServiceUrl(url) || isStreamingMedia(url, filename)) return false;

  // If Bengal DM app is disconnected, do NOT intercept — let browser handle download seamlessly
  if (!cachedAppOnline) {
    return false;
  }

  const rules = cachedFilterRules;
  if (rules.enableInterception === false) {
    return false;
  }

  const ext = getFileExtension(filename || url);

  // 1. Blacklist check - if matched on URL, domain, referrer, or extension: do NOT intercept (leave to browser)
  if (matchesUrlOrDomain(url, rules.blacklistUrls, referrer) || matchesExtension(ext || filename, rules.blacklistExts)) {
    return false;
  }

  // 2. Whitelisted extension - always intercept
  if (matchesExtension(ext || filename, rules.whitelistExts)) {
    return true;
  }

  // 3. Ignored web asset extensions (manifest.json, html, js, css, images) MUST NEVER be intercepted as downloads
  if (ext && DEFAULT_IGNORED_EXTS.includes(ext)) {
    return false;
  }

  // 4. Whitelisted URL/domain - intercept downloadable files on this domain
  if (matchesUrlOrDomain(url, rules.whitelistUrls, referrer)) {
    return true;
  }

  return true;
}

async function shouldInterceptDownload(url, filename, referrer) {
  return shouldInterceptDownloadSync(url, filename, referrer);
}

// --- ENHANCED COOKIE EXTRACTION (cliget method with Firefox storeId & dFPI support) ---
async function getCookiesForUrl(targetUrl, storeId) {
  if (!targetUrl || (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://'))) {
    return "";
  }

  try {
    const query = { url: targetUrl };
    if (storeId) {
      query.storeId = storeId;
    }

    let cookies = [];
    try {
      cookies = await chrome.cookies.getAll(query);
    } catch (e) {
      delete query.storeId;
      try { cookies = await chrome.cookies.getAll(query); } catch (err) {}
    }

    const cookieMap = new Map();
    for (const c of cookies || []) {
      if (c && c.name) {
        cookieMap.set(c.name, c.value || "");
      }
    }

    // Query domain & parent domain cookies for Firefox dFPI Total Cookie Protection
    try {
      const parsed = new URL(targetUrl);
      const hostParts = parsed.hostname.split('.');
      
      const dQuery = { domain: parsed.hostname };
      if (storeId) dQuery.storeId = storeId;
      try {
        const domCookies = await chrome.cookies.getAll(dQuery);
        for (const c of domCookies || []) {
          if (c && c.name && !cookieMap.has(c.name)) {
            cookieMap.set(c.name, c.value || "");
          }
        }
      } catch (e) {}

      if (hostParts.length >= 2) {
        const parentDomain = hostParts.slice(-2).join('.');
        const pQuery = { domain: parentDomain };
        if (storeId) pQuery.storeId = storeId;
        const parentCookies = await chrome.cookies.getAll(pQuery);
        for (const c of parentCookies || []) {
          if (c && c.name && !cookieMap.has(c.name)) {
            cookieMap.set(c.name, c.value || "");
          }
        }
      }
    } catch (e) {}

    const result = [];
    for (const [name, val] of cookieMap.entries()) {
      result.push(`${name}=${val}`);
    }
    return result.join('; ');
  } catch (err) {
    return "";
  }
}

// --- RESOLVE DOWNLOAD TARGET (handles HTML landing pages with meta refresh / direct mirror links) ---
async function resolveDownloadTarget(url, userAgent, cookies) {
  if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
    return { url, isHtmlLanding: false };
  }

  try {
    const headers = {
      'User-Agent': userAgent || navigator.userAgent,
      'Range': 'bytes=0-30720'
    };
    if (cookies) {
      headers['Cookie'] = cookies;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: headers,
      redirect: 'follow'
    });

    const finalUrl = response.url || url;
    const contentType = (response.headers.get('content-type') || '').toLowerCase();

    // If Content-Type is a direct binary file or non-HTML resource
    if (!contentType.includes('text/html') && !contentType.includes('application/xhtml+xml')) {
      return { url: finalUrl, isHtmlLanding: false };
    }

    // For HTML responses, inspect the snippet for meta refresh or target file confirmation forms
    const text = await response.text();

    // 1. Check for Meta Refresh tag (e.g. VideoLAN mirror redirect, SourceForge)
    const metaMatch = text.match(/content=["']?\d+;\s*url=['"]?([^'"]+)/i)
                   || text.match(/url=['"]?([^'"]+)['"]?[^>]*http-equiv/i);
    if (metaMatch && metaMatch[1]) {
      const cleanUrl = metaMatch[1].replace(/['"]$/, '').trim();
      const resolvedTarget = new URL(cleanUrl, finalUrl).href;
      return { url: resolvedTarget, isHtmlLanding: false };
    }

    // 2. Google Drive / Cloud storage download confirmation forms or links
    const formMatch = text.match(/<form[^>]*id=["']download-form["'][^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i)
                   || text.match(/<form[^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i);
    if (formMatch) {
      const formAction = formMatch[1].replace(/&amp;/g, '&');
      const formInner = formMatch[2];

      const inputs = [];
      const inputRegex = /<input[^>]*name=["']([^"']+)["'][^>]*value=["']([^"']*)["']/gi;
      let m;
      while ((m = inputRegex.exec(formInner)) !== null) {
        if (m[1] && m[1] !== 'submit') {
          inputs.push(`${encodeURIComponent(m[1])}=${encodeURIComponent(m[2])}`);
        }
      }

      if (inputs.length > 0) {
        const baseUrl = new URL(formAction, finalUrl).href;
        const confirmUrl = baseUrl + (baseUrl.includes('?') ? '&' : '?') + inputs.join('&');
        return { url: confirmUrl, isHtmlLanding: false };
      }
    }

    const gdriveConfirmMatch = text.match(/id=["']uc-download-link["'][^>]*href=["']([^"']+)["']/i)
                            || text.match(/href=["'](\/uc\?export=download&[^"']+)["']/i)
                            || text.match(/href=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i)
                            || text.match(/action=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i);
    if (gdriveConfirmMatch && gdriveConfirmMatch[1]) {
      const cleanUrl = gdriveConfirmMatch[1].replace(/&amp;/g, '&').trim();
      const resolvedTarget = new URL(cleanUrl, finalUrl).href;
      return { url: resolvedTarget, isHtmlLanding: false };
    }

    // Pure HTML landing page with no extractable redirect/confirmation
    return { url: finalUrl, isHtmlLanding: true };
  } catch (err) {
    console.warn("Could not resolve download target:", err);
    return { url, isHtmlLanding: false };
  }
}

// --- CHECK BENGAL DM APP CONNECTION & SYNC CONFIG ---
async function isBengalDMOnline() {
  let online = false;
  let config = null;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);
    const response = await fetch("http://127.0.0.1:56900/", {
      method: 'GET',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    if (response.ok) {
      online = true;
      try { config = await response.json(); } catch {}
    }
  } catch {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const response = await fetch("http://localhost:56900/", {
        method: 'GET',
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (response.ok) {
        online = true;
        try { config = await response.json(); } catch {}
      }
    } catch {
      online = false;
    }
  }

  if (config) {
    updateDynamicMediaConfig(config);
  }

  await updateAppConnectionBadge(online);
  return online;
}

// --- SEND DOWNLOAD TO BENGAL DM ---
async function sendToBengalDM(downloadData) {
  const { url, userAgent, cookies, filename, referrer } = downloadData;

  const isOnline = await isBengalDMOnline();
  if (!isOnline) {
    console.warn("Bengal DM application is not running on port 56900.");
    return false;
  }

  const payload = {
    url: url,
    userAgent: userAgent || navigator.userAgent,
    cookies: cookies || "",
    filename: filename || downloadData.title || "",
    referrer: referrer || "",
    title: downloadData.title || "",
    quality: downloadData.quality || "",
    isMedia: !!downloadData.isMedia,
    sizeBytes: downloadData.sizeBytes || 0,
    sizeStr: downloadData.sizeStr || ""
  };

  try {
    const response = await fetch("http://127.0.0.1:56900/", {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    return response.ok;
  } catch (err) {
    try {
      const response = await fetch("http://localhost:56900/", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      return response.ok;
    } catch (e) {
      console.error("Failed to send download to Bengal DM:", e);
      return false;
    }
  }
}

// --- NOTIFICATION HELPER ---
function notifyUser(title, message) {
  return;
}

// --- RECENT DOWNLOAD DEDUPLICATION TRACKER ---
const recentDownloads = new Map();

const GENERIC_ENDPOINTS = ['uc', 'download', 'get', 'fetch', 'file', 'files', 'attachment', 'export', 'dl', 'release', 'index.php', 'index.html', 'view'];

function getCanonicalDownloadKey(url, filename) {
  if (filename && filename.trim()) {
    return filename.trim().toLowerCase();
  }
  if (!url) return "";
  const clean = url.split('?')[0].split('#')[0];
  const parts = clean.split('/').filter(p => p && p !== 'http:' && p !== 'https:');
  let last = parts.pop() || "";
  if (GENERIC_ENDPOINTS.includes(last.toLowerCase())) {
    return "";
  }
  if (last.includes('.') && last.split('.').pop().length <= 6) {
    return last.toLowerCase();
  }
  return "";
}

function isRecentlySent(url, filename) {
  if (!url && !filename) return false;
  const now = Date.now();
  for (const [key, time] of recentDownloads.entries()) {
    if (now - time > 10000) {
      recentDownloads.delete(key);
    }
  }

  if (url && recentDownloads.has(url)) return true;
  const key = getCanonicalDownloadKey(url, filename);
  if (key && key.length > 2 && recentDownloads.has(key)) return true;
  return false;
}

function markRecentlySent(url, filename) {
  const now = Date.now();
  if (url) {
    recentDownloads.set(url, now);
  }
  const key = getCanonicalDownloadKey(url, filename);
  if (key && key.length > 2) {
    recentDownloads.set(key, now);
  }
}

const IGNORED_SERVICE_PATTERNS = [
  'logimpressions', '/log/', 'telemetry', 'analytics', 'metrics',
  'httpservice', 'checktriggerstatus', 'bgasy', 'gen_204', '/collect',
  '/async/', 'batchasynctask', '/rpc', 'tracking', 'beacon',
  'manifest.json', 'favicon.ico', 'site.webmanifest'
];

function isIgnoredServiceUrl(url) {
  if (!url || typeof url !== 'string') return true;
  const lower = url.toLowerCase();
  return IGNORED_SERVICE_PATTERNS.some(pattern => lower.includes(pattern));
}

// --- MEDIA STREAM SNIFFER SYSTEM (Store for On-Page Widget & Optional Relay) ---
const pendingMediaRequests = new Map(); // requestId -> { url, method, requestHeaders, tabId, timestamp }
const detectedMediaUrls = new Map();    // url -> timestamp (5-second deduplication)
const tabMediaStreams = new Map();      // tabId -> Array of { url, contentType, title, timestamp }

function recordSniffedMedia(tabId, url, contentType, title) {
  if (!tabId || tabId === -1 || !url) return;
  let list = tabMediaStreams.get(tabId);
  if (!list) {
    list = [];
    tabMediaStreams.set(tabId, list);
  }
  if (!list.some(item => item.url === url)) {
    list.push({ url, contentType: contentType || "", title: title || "", timestamp: Date.now() });
    if (list.length > 30) list.shift();
  }
}

if (chrome.tabs && chrome.tabs.onRemoved) {
  chrome.tabs.onRemoved.addListener((tabId) => {
    tabMediaStreams.delete(tabId);
  });
}

// Dynamic media config, synchronized from Bengal DM app (or default fallback)
const dynamicMediaConfig = {
  mediaTypes: ['application/x-mpegurl', 'application/vnd.apple.mpegurl', 'application/dash+xml', 'video/mp4', 'video/webm'],
  mediaExts: ['m3u8', 'mpd', 'mp4', 'webm', 'mkv', 'flv'],
  matchingHosts: [],
  blockedHosts: ['127.0.0.1', 'localhost', 'googlevideo.com']
};

function updateDynamicMediaConfig(config) {
  if (!config || typeof config !== 'object') return;
  if (Array.isArray(config.mediaTypes)) dynamicMediaConfig.mediaTypes = config.mediaTypes;
  if (Array.isArray(config.mediaExts)) dynamicMediaConfig.mediaExts = config.mediaExts;
  if (Array.isArray(config.requestFileExts)) dynamicMediaConfig.mediaExts = config.requestFileExts;
  if (Array.isArray(config.matchingHosts)) dynamicMediaConfig.matchingHosts = config.matchingHosts;
  if (Array.isArray(config.blockedHosts)) dynamicMediaConfig.blockedHosts = config.blockedHosts;
}

// Check if request matches media criteria (Content-Type, URL extension, or matching hosts)
function isMatchingMediaRequest(url, contentType) {
  if (!url || isIgnoredServiceUrl(url)) return false;

  let u;
  try {
    u = new URL(url);
  } catch {
    return false;
  }

  const hostname = u.hostname.toLowerCase();
  for (const bh of dynamicMediaConfig.blockedHosts) {
    if (hostname.includes(bh)) return false;
  }

  // Filter out thumbnail preview clips and hover loops (e.g. vidthumb.mp4 on sxyprn)
  const lowerUrl = url.toLowerCase();
  const lowerPath = u.pathname.toLowerCase();
  if (
    lowerUrl.includes('vidthumb') ||
    lowerUrl.includes('thumb_preview') ||
    lowerUrl.includes('hover_preview') ||
    lowerUrl.includes('preview_video') ||
    lowerUrl.includes('preview.mp4') ||
    lowerUrl.includes('trailer_preview') ||
    lowerUrl.includes('storyboard') ||
    lowerUrl.includes('_preview.') ||
    lowerPath.includes('/preview/') ||
    lowerPath.includes('/preview_clip/') ||
    lowerPath.includes('/thumbnails/')
  ) {
    return false;
  }

  // 1. Host matching (e.g. googlevideo)
  for (const mh of dynamicMediaConfig.matchingHosts) {
    if (hostname.includes(mh) || url.includes(mh)) return true;
  }

  // 2. Extension matching
  const pathname = u.pathname.toUpperCase();
  for (const ext of dynamicMediaConfig.mediaExts) {
    const upperExt = ext.toUpperCase().replace(/^\./, '');
    if (pathname.endsWith('.' + upperExt) || pathname.endsWith(upperExt)) {
      return true;
    }
  }

  // 3. Content-Type matching
  if (contentType) {
    const ctype = contentType.toLowerCase();
    for (const mt of dynamicMediaConfig.mediaTypes) {
      if (ctype.includes(mt.toLowerCase())) {
        return true;
      }
    }
  }

  return false;
}

// Periodic cleanup of pending requests and detected URLs
setInterval(() => {
  const now = Date.now();
  for (const [reqId, data] of pendingMediaRequests.entries()) {
    if (now - data.timestamp > 30000) {
      pendingMediaRequests.delete(reqId);
    }
  }
  for (const [url, time] of detectedMediaUrls.entries()) {
    if (now - time > 15000) {
      detectedMediaUrls.delete(url);
    }
  }
}, 15000);

// 1. Capture outgoing GET/HEAD headers and session info (non-blocking)
if (chrome.webRequest && chrome.webRequest.onSendHeaders) {
  const handleMediaSendHeaders = (details) => {
    if (!details || !details.url || details.url.startsWith("http://127.0.0.1") || details.url.startsWith("http://localhost")) {
      return;
    }
    if (isIgnoredServiceUrl(details.url)) return;
    if (details.method !== 'GET' && details.method !== 'HEAD') return;

    pendingMediaRequests.set(details.requestId, {
      url: details.url,
      method: details.method,
      requestHeaders: details.requestHeaders || [],
      tabId: details.tabId,
      timestamp: Date.now()
    });
  };

  try {
    chrome.webRequest.onSendHeaders.addListener(
      handleMediaSendHeaders,
      { urls: ["<all_urls>"] },
      ["requestHeaders", "extraHeaders"]
    );
  } catch {
    try {
      chrome.webRequest.onSendHeaders.addListener(
        handleMediaSendHeaders,
        { urls: ["<all_urls>"] },
        ["requestHeaders"]
      );
    } catch (e) {
      console.warn("Could not register onSendHeaders for media sniffer:", e);
    }
  }
}

if (chrome.webRequest && chrome.webRequest.onErrorOccurred) {
  chrome.webRequest.onErrorOccurred.addListener((details) => {
    if (details && details.requestId) {
      pendingMediaRequests.delete(details.requestId);
    }
  }, { urls: ["<all_urls>"] });
}

// 2. Post raw media data to Bengal DM app (app handles stream matching, manifests, and FFmpeg muxing)
async function postMediaToBengalDM(details, req, tab) {
  const cookieString = await getCookiesForUrl(details.url, details.storeId);

  // Clean request headers (remove range and pseudo-headers so app can fetch full stream)
  const rawReqHeaders = (req && req.requestHeaders) ? req.requestHeaders : [];
  const reqHeadersDict = {};
  for (const h of rawReqHeaders) {
    if (!h.name) continue;
    const n = h.name.toLowerCase();
    if (n === 'range' || n === 'cookie' || n.startsWith(':')) continue;
    reqHeadersDict[h.name] = h.value;
  }

  // Clean response headers
  const rawResHeaders = details.responseHeaders || [];
  const resHeadersDict = {};
  for (const h of rawResHeaders) {
    if (!h.name) continue;
    resHeadersDict[h.name] = h.value;
  }

  const data = {
    url: details.url,
    file: tab ? tab.title : null,
    tabUrl: tab ? tab.url : null,
    tabId: details.tabId !== undefined && details.tabId !== -1 ? String(details.tabId) : "-1",
    method: req && req.method ? req.method : "GET",
    userAgent: navigator.userAgent,
    cookies: cookieString,
    requestHeaders: reqHeadersDict,
    responseHeaders: resHeadersDict
  };

  // 1. Record sniffed media for this tab so the on-page floating popup can offer it
  if (details.tabId && details.tabId !== -1) {
    recordSniffedMedia(details.tabId, details.url, "", tab ? tab.title : "");
    try {
      chrome.tabs.sendMessage(details.tabId, {
        action: "media_stream_detected",
        stream: { url: details.url, title: tab ? tab.title : "" }
      }).catch(() => {});
    } catch (e) {}
  }
  return true;
}

// 3. Register non-blocking media stream sniffer listener
if (chrome.webRequest && chrome.webRequest.onHeadersReceived) {
  const handleMediaHeaders = (details) => {
    if (!details || !details.url || details.url.startsWith("http://127.0.0.1") || details.url.startsWith("http://localhost") || isIgnoredServiceUrl(details.url)) {
      return;
    }
    if (cachedFilterRules.enableMediaSniffing === false || !cachedAppOnline) {
      return;
    }

    let contentType = "";
    let isAttachment = false;

    for (const h of (details.responseHeaders || [])) {
      const name = (h.name || '').toLowerCase();
      const val = (h.value || '').toLowerCase();
      if (name === 'content-type') {
        contentType = val;
      } else if (name === 'content-disposition' && (val.includes('attachment') || val.includes('filename='))) {
        isAttachment = true;
      }
    }

    // Attachments are handled by the main file download interceptor
    if (isAttachment) {
      return;
    }

    if (isMatchingMediaRequest(details.url, contentType)) {
      const now = Date.now();
      if (detectedMediaUrls.has(details.url)) {
        return;
      }
      detectedMediaUrls.set(details.url, now);

      const req = pendingMediaRequests.get(details.requestId);

      if (details.tabId && details.tabId !== -1) {
        chrome.tabs.get(details.tabId, (tab) => {
          postMediaToBengalDM(details, req, tab);
        });
      } else {
        postMediaToBengalDM(details, req, null);
      }
    }
  };

  try {
    chrome.webRequest.onHeadersReceived.addListener(
      handleMediaHeaders,
      { urls: ["<all_urls>"] },
      ["responseHeaders", "extraHeaders"]
    );
  } catch {
    try {
      chrome.webRequest.onHeadersReceived.addListener(
        handleMediaHeaders,
        { urls: ["<all_urls>"] },
        ["responseHeaders"]
      );
    } catch (e) {
      console.warn("Could not register media stream sniffer listener:", e);
    }
  }
}

// 4. Tab title updates: notify Bengal DM /tab-update for SPA navigation (e.g. YouTube video change)
if (chrome.tabs && chrome.tabs.onUpdated) {
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.title && tab && tab.url && cachedAppOnline) {
      try {
        fetch("http://127.0.0.1:56900/tab-update", {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tabId: String(tabId), tabUrl: tab.url, tabTitle: changeInfo.title })
        }).catch(() => {});
      } catch {}
    }
  });
}

// --- HTTP REQUEST & RESPONSE MONITORING SYSTEM (IDM Integration Module Style) ---
if (chrome.webRequest && chrome.webRequest.onHeadersReceived) {
  const setupListener = (extraSpec) => {
    chrome.webRequest.onHeadersReceived.addListener(
      (details) => {
        if (!details || !details.url || details.url.startsWith("http://127.0.0.1") || details.url.startsWith("http://localhost") || isIgnoredServiceUrl(details.url)) {
          return;
        }

        // Tonec IDM Pattern: Only HTTP 200 (OK), 206 (Partial Content), and 304 (Not Modified) can be file downloads.
        // Redirects (301, 302, 303, 307, 308) MUST be allowed to proceed so the browser navigates to the target URL!
        // (e.g. datanodes.to returns a 302 redirect from /...part1.rar to /download).
        // Error codes (4xx, 5xx) must also be displayed as web pages, never cancelled as downloads.
        const status = details.statusCode;
        if (status && status !== 200 && status !== 206 && status !== 304) {
          return; // Allow browser to follow redirects or render error pages!
        }

        const headers = details.responseHeaders || [];
        let filenameFromHeader = "";
        let hasAttachmentDirective = false;
        let hasContentDispositionHeader = false;
        let isBinaryContentType = false;
        let isHtmlContentType = false;

        for (const h of headers) {
          const name = (h.name || '').toLowerCase();
          const value = (h.value || '').toLowerCase();

          if (name === 'content-disposition') {
            if (value.includes('attachment')) {
              hasAttachmentDirective = true;
            }
            if (value.includes('attachment') || value.includes('filename=')) {
              hasContentDispositionHeader = true;
            }
            const match = h.value.match(/filename=["']?([^"';]+)["']?/i);
            if (match) filenameFromHeader = match[1];
          }

          if (name === 'content-type') {
            if (value.includes('text/html') || value.includes('application/xhtml+xml')) {
              isHtmlContentType = true;
            }
            if (value.includes('application/x-msdownload') || 
                value.includes('application/x-7z-compressed') || 
                value.includes('application/x-rar-compressed') || 
                value.includes('application/zip') || 
                value.includes('application/octet-stream') ||
                value.includes('application/x-iso9660-image')) {
              if (!value.includes('mpegurl') && !value.includes('dash') && !value.includes('video') && !value.includes('audio')) {
                isBinaryContentType = true;
              }
            }
          }
        }

        const hasContentDispositionAttachment = hasAttachmentDirective || (hasContentDispositionHeader && !isHtmlContentType);

        // Tonec IDM Pattern: If server returns an HTML webpage without an explicit attachment header,
        // NEVER intercept or cancel, regardless of what the URL extension looks like!
        // File hosts (datanodes.to, rapidgator, mediafire) often have URLs ending in .rar or .zip
        // that return HTML landing pages with captchas or countdown timers.
        if (isHtmlContentType && !hasAttachmentDirective) {
          return; // Bypassed to native browser: let user view the page!
        }

        const ext = getFileExtension(filenameFromHeader || details.url);
        const referrer = details.initiator || details.documentUrl || "";

        // Never intercept streaming media chunks / manifests as browser file downloads
        if (isStreamingMedia(details.url, filenameFromHeader)) {
          return;
        }

        // Synchronous blacklist & interception check
        const shouldIntercept = shouldInterceptDownloadSync(details.url, filenameFromHeader, referrer);
        if (!shouldIntercept || !cachedAppOnline) {
          return; // Bypassed to native browser! NEVER cancel or redirect!
        }

        const isExplicitWhitelistedExt = matchesExtension(ext || filenameFromHeader, cachedFilterRules.whitelistExts);
        const isDownloadExt = ext && RECOGNIZED_DOWNLOAD_EXTS.includes(ext);
        const isGoogleDriveExport = details.url.includes("export=download") || details.url.includes("uc-download-link");

        // Only intercept if there is a real download intent
        if (hasContentDispositionAttachment || isBinaryContentType || isDownloadExt || isExplicitWhitelistedExt || isGoogleDriveExport) {
          (async () => {
            const isOnline = await isBengalDMOnline();
            if (!isOnline) return;

            if (isRecentlySent(details.url, filenameFromHeader)) return;

            const cookieString = await getCookiesForUrl(details.url, details.storeId);

            const resolved = await resolveDownloadTarget(details.url, navigator.userAgent, cookieString);
            if (resolved.isHtmlLanding) {
              return;
            }

            if (isRecentlySent(resolved.url, filenameFromHeader)) return;

            markRecentlySent(details.url, filenameFromHeader);
            markRecentlySent(resolved.url, filenameFromHeader);

            await sendToBengalDM({
              url: resolved.url,
              userAgent: navigator.userAgent,
              cookies: cookieString,
              filename: filenameFromHeader,
              referrer: referrer
            });
          })();

          if (extraSpec.includes("blocking") && cachedAppOnline) {
            if (details.type === "main_frame" && details.tabId && details.tabId !== -1) {
              // Tonec IDM Pattern: Close newly opened blank tabs (e.g. target="_blank") created solely for this download
              chrome.tabs.get(details.tabId, (tab) => {
                if (chrome.runtime.lastError || !tab) return;
                if (!tab.url || tab.url === "about:blank" || tab.url === details.url || tab.pendingUrl === details.url) {
                  chrome.tabs.remove(details.tabId, () => {
                    if (chrome.runtime.lastError) {}
                  });
                }
              });
            }
            return { cancel: true };
          }
        }
      },
      { urls: ["<all_urls>"], types: ["main_frame", "sub_frame"] },
      extraSpec
    );
  };

  const manifest = (chrome.runtime && chrome.runtime.getManifest) ? chrome.runtime.getManifest() : {};
  const hasBlocking = manifest.permissions && Array.isArray(manifest.permissions) && manifest.permissions.includes('webRequestBlocking');
  const extraSpec = hasBlocking ? ["responseHeaders", "blocking"] : ["responseHeaders"];

  try {
    setupListener(extraSpec);
  } catch {
    setupListener(["responseHeaders"]);
  }
}

// --- BROWSER DOWNLOAD CANCELLER & TAKEOVER (Zero-Popup, Zero-Animation, Zero-History) ---
const interceptedDownloadIds = new Set();

function eraseDownloadRecord(downloadId) {
  if (!downloadId || !chrome.downloads || !chrome.downloads.erase) return;
  try {
    chrome.downloads.erase({ id: downloadId }, () => {
      if (chrome.runtime && chrome.runtime.lastError) { /* ignore */ }
    });
  } catch {}
}

function cancelAndEraseDownload(downloadId) {
  if (!downloadId || !chrome.downloads) return;
  interceptedDownloadIds.add(downloadId);
  try {
    chrome.downloads.cancel(downloadId, () => {
      eraseDownloadRecord(downloadId);
    });
  } catch {}
  eraseDownloadRecord(downloadId);
  setTimeout(() => eraseDownloadRecord(downloadId), 40);
  setTimeout(() => eraseDownloadRecord(downloadId), 150);
  setTimeout(() => eraseDownloadRecord(downloadId), 500);
}

// 1. Hook onDeterminingFilename (Chrome/Edge): Cancels before download starts and before swing animation triggers
if (chrome.downloads && chrome.downloads.onDeterminingFilename) {
  chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    if (!downloadItem || !downloadItem.url || isIgnoredServiceUrl(downloadItem.url) || isStreamingMedia(downloadItem.url, downloadItem.filename)) {
      if (suggest) try { suggest(); } catch {}
      return;
    }

    const referrer = downloadItem.referrer || downloadItem.finalUrl || "";
    const shouldIntercept = shouldInterceptDownloadSync(downloadItem.url, downloadItem.filename, referrer);
    if (!shouldIntercept || !cachedAppOnline) {
      if (suggest) try { suggest(); } catch {}
      return; // Leave download to native browser!
    }

    // SYNCHRONOUS 0th-TICK CANCELLATION:
    // Aborts in the determining filename phase BEFORE Chromium triggers DownloadStartedAnimation::Show!
    cancelAndEraseDownload(downloadItem.id);
    if (suggest) {
      try { suggest(); } catch {}
    }
  });
}

// 2. Hook onCreated: Initial download instantiation and handover to Bengal DM
if (chrome.downloads && chrome.downloads.onCreated) {
  chrome.downloads.onCreated.addListener((downloadItem) => {
    if (!downloadItem || !downloadItem.url || isIgnoredServiceUrl(downloadItem.url) || isStreamingMedia(downloadItem.url, downloadItem.filename)) return;

    const referrer = downloadItem.referrer || downloadItem.finalUrl || "";
    // Check Whitelist & Blacklist rules
    const shouldIntercept = shouldInterceptDownloadSync(downloadItem.url, downloadItem.filename, referrer);
    if (!shouldIntercept || !cachedAppOnline) {
      return; // Leave download to native browser!
    }

    // Cancel IMMEDIATELY and SYNCHRONOUSLY on 0th tick
    cancelAndEraseDownload(downloadItem.id);

    // Asynchronous payload preparation and dispatch to Bengal DM
    (async () => {
      // Deduplicate if already processed by content script or webRequest
      if (isRecentlySent(downloadItem.url, downloadItem.filename)) return;

      const cookieString = await getCookiesForUrl(downloadItem.url, downloadItem.storeId);
      const resolved = await resolveDownloadTarget(downloadItem.url, navigator.userAgent, cookieString);

      const isCloudOrBrowserFile = downloadItem.url.includes("google.com") || 
                                   downloadItem.url.includes("googleusercontent.com") || 
                                   downloadItem.url.includes("export=download") || 
                                   (downloadItem.filename && downloadItem.filename.length > 0);

      if (resolved.isHtmlLanding && !isCloudOrBrowserFile) {
        return;
      }

      const targetUrl = (resolved.isHtmlLanding && isCloudOrBrowserFile) ? downloadItem.url : resolved.url;
      if (isRecentlySent(targetUrl, downloadItem.filename)) return;

      markRecentlySent(downloadItem.url, downloadItem.filename);
      markRecentlySent(targetUrl, downloadItem.filename);

      await sendToBengalDM({
        url: targetUrl,
        userAgent: navigator.userAgent,
        cookies: cookieString,
        filename: downloadItem.filename || "",
        referrer: referrer
      });
    })();
  });
}

// 3. Hook onChanged: Erase the download from history database the moment state reaches "interrupted"
if (chrome.downloads && chrome.downloads.onChanged) {
  chrome.downloads.onChanged.addListener((delta) => {
    if (!delta || !delta.id) return;
    if (interceptedDownloadIds.has(delta.id) || (delta.state && delta.state.current === "interrupted")) {
      eraseDownloadRecord(delta.id);
      setTimeout(() => eraseDownloadRecord(delta.id), 80);
      setTimeout(() => eraseDownloadRecord(delta.id), 300);
    }
  });
}

// --- POPULAR STREAMING MEDIA DOMAINS (yt-dlp supported) ---
const POPULAR_MEDIA_DOMAINS = [
  "youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "instagram.com",
  "twitter.com", "x.com", "facebook.com", "fb.watch", "reddit.com",
  "twitch.tv", "bilibili.com", "soundcloud.com", "rumble.com",
  "kick.com", "dailymotion.com", "streamable.com", "pinterest.com"
];

function isMediaUrl(url) {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();
    return POPULAR_MEDIA_DOMAINS.some(d => hostname === d || hostname.endsWith('.' + d));
  } catch (e) {
    return false;
  }
}

function sanitizeMediaUrl(url) {
  if (!url) return url;
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();
    if (hostname.includes("youtube.com") || hostname.includes("youtu.be")) {
      if (parsed.searchParams.has("v") || parsed.pathname.includes("/shorts/")) {
        const listVal = parsed.searchParams.get("list");
        if (listVal && (listVal.startsWith("RD") || listVal.startsWith("UL") || listVal.startsWith("PU") || listVal === "WL")) {
          parsed.searchParams.delete("list");
        }
        parsed.searchParams.delete("start_radio");
        parsed.searchParams.delete("pp");
        parsed.searchParams.delete("si");
        parsed.searchParams.delete("feature");
        parsed.searchParams.delete("index");
        return parsed.toString();
      } else if (hostname.includes("youtu.be")) {
        parsed.searchParams.delete("si");
        parsed.searchParams.delete("feature");
        return parsed.toString();
      }
    } else if (hostname.includes("tiktok.com")) {
      for (const k of ["is_fromwebapp", "sender_device", "share_app_id", "share_item_id", "share_link_id"]) {
        parsed.searchParams.delete(k);
      }
      return parsed.toString();
    }
  } catch (e) {}
  return url;
}

// --- INITIALIZATION & CONTEXT MENUS ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(['port', 'enableInterception', 'theme'], (items) => {
    if (!items.port || items.port === 6800 || items.port === 50001 || items.port === 6801) {
      chrome.storage.local.set({ port: 56800 });
    }
    if (items.enableInterception === undefined) {
      chrome.storage.local.set({ enableInterception: true });
    }
    if (!items.theme) {
      chrome.storage.local.set({ theme: "system" });
    }
  });

  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "download-with-bengal",
      title: "Download with Bengal DM",
      contexts: ["link", "image", "video", "audio", "selection", "page"]
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "download-with-bengal") {
    const targetUrl = info.linkUrl || info.srcUrl || info.selectionText || info.pageUrl;
    if (targetUrl && (targetUrl.startsWith("http://") || targetUrl.startsWith("https://"))) {
      const cookieString = await getCookiesForUrl(targetUrl, tab ? tab.cookieStoreId : undefined);

      // Media streams (YouTube, Vimeo, TikTok, etc.) are streaming sites and should be sent directly to Bengal DM!
      if (isMediaUrl(targetUrl)) {
        const cleanTargetUrl = sanitizeMediaUrl(targetUrl);
        markRecentlySent(cleanTargetUrl);
        const success = await sendToBengalDM({
          url: cleanTargetUrl,
          userAgent: navigator.userAgent,
          cookies: cookieString,
          referrer: (tab && tab.url) ? tab.url : cleanTargetUrl
        });

        if (success) {
          notifyUser("Bengal DM", "Media link sent to Bengal DM!");
        } else {
          notifyUser("Bengal DM Error", "Could not send to Bengal DM. Is the application running?");
        }
        return;
      }

      const resolved = await resolveDownloadTarget(targetUrl, navigator.userAgent, cookieString);
      if (resolved.isHtmlLanding) {
        notifyUser("Bengal DM Warning", "The link is a web page, not a direct download file.");
        return;
      }

      markRecentlySent(targetUrl);
      markRecentlySent(resolved.url);

      const success = await sendToBengalDM({
        url: resolved.url,
        userAgent: navigator.userAgent,
        cookies: cookieString,
        referrer: targetUrl
      });

      if (success) {
        notifyUser("Bengal DM", "Download sent to Bengal DM successfully!");
      } else {
        notifyUser("Bengal DM Error", "Could not send download to Bengal DM. Is the app running?");
      }
    }
  }
});

// --- MESSAGE HANDLER ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "send_to_bengal") {
    (async () => {
      const cookieString = await getCookiesForUrl(request.url, sender && sender.tab ? sender.tab.cookieStoreId : undefined);

      if (isRecentlySent(request.url)) {
        sendResponse({ success: true, duplicate: true });
        return;
      }

      if (request.isMedia || isMediaUrl(request.url)) {
        const cleanUrl = isMediaUrl(request.url) ? sanitizeMediaUrl(request.url) : request.url;
        markRecentlySent(cleanUrl);
        const success = await sendToBengalDM({
          url: cleanUrl,
          userAgent: navigator.userAgent,
          cookies: cookieString,
          referrer: request.referrer || request.url,
          filename: request.filename || request.title || "",
          title: request.title || "",
          quality: request.quality || "",
          isMedia: true,
          sizeBytes: request.sizeBytes || 0,
          sizeStr: request.sizeStr || ""
        });
        sendResponse({ success, resolvedUrl: cleanUrl });
        return;
      }

      // Check filters
      const shouldIntercept = await shouldInterceptDownload(request.url, request.filename, request.referrer);
      if (!shouldIntercept) {
        sendResponse({ success: false, bypassed: true });
        return;
      }

      const resolved = await resolveDownloadTarget(request.url, navigator.userAgent, cookieString);
      if (resolved.isHtmlLanding) {
        sendResponse({ success: false, isHtmlLanding: true, url: request.url });
        return;
      }

      if (isRecentlySent(resolved.url)) {
        sendResponse({ success: true, duplicate: true });
        return;
      }

      markRecentlySent(request.url);
      markRecentlySent(resolved.url);

      const success = await sendToBengalDM({
        url: resolved.url,
        userAgent: navigator.userAgent,
        cookies: cookieString,
        referrer: request.referrer || request.url
      });
      sendResponse({ success, resolvedUrl: resolved.url });
    })();
    return true;
  }

  if (request.action === "check_status") {
    (async () => {
      const isOnline = await isBengalDMOnline();
      const rules = await getFilterRules();
      let blacklisted = false;
      let whitelistedUrl = false;
      let whitelistedExt = false;

      if (request.url) {
        const ext = getFileExtension(request.url);
        blacklisted = matchesUrlOrDomain(request.url, rules.blacklistUrls, request.referrer) || matchesExtension(ext, rules.blacklistExts);
        whitelistedUrl = matchesUrlOrDomain(request.url, rules.whitelistUrls, request.referrer);
        whitelistedExt = matchesExtension(ext, rules.whitelistExts);
      }

      sendResponse({
        online: isOnline,
        enableInterception: rules.enableInterception !== false && isOnline,
        blacklisted,
        whitelistedUrl,
        whitelistedExt
      });
    })();
    return true;
  }

  if (request.action === "update_connection_status") {
    updateAppConnectionBadge(Boolean(request.online));
    sendResponse({ success: true, online: cachedAppOnline });
    return true;
  }

  if (request.action === "get_connection_status") {
    sendResponse({ online: cachedAppOnline });
    return true;
  }

  if (request.action === "get_tab_info") {
    sendResponse({
      tabId: sender && sender.tab ? sender.tab.id : null,
      title: sender && sender.tab ? sender.tab.title : "",
      url: sender && sender.tab ? sender.tab.url : ""
    });
    return true;
  }

  if (request.action === "get_sniffed_media") {
    const tabId = (sender && sender.tab) ? sender.tab.id : null;
    const streams = tabId ? (tabMediaStreams.get(tabId) || []) : [];
    sendResponse({ streams });
    return true;
  }
});

// --- PERIODIC CONNECTION POLLING & STARTUP ---
async function checkAndUpdateConnection() {
  const online = await isBengalDMOnline();
  return online;
}

try {
  if (chrome.alarms) {
    chrome.alarms.create("bengal_connection_poll", { periodInMinutes: 0.25 });
    chrome.alarms.onAlarm.addListener((alarm) => {
      if (alarm && alarm.name === "bengal_connection_poll") {
        checkAndUpdateConnection();
      }
    });
  }
} catch (e) {}

if (chrome.runtime && chrome.runtime.onStartup) {
  chrome.runtime.onStartup.addListener(() => {
    checkAndUpdateConnection();
  });
}

// Initial status check
checkAndUpdateConnection();

