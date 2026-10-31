// --- CONSTANTS & HELPERS ---
if (typeof importScripts === 'function') {
  importScripts('../sites/youtube/shared/youtube-media.js');
  importScripts('../sites/youtube/background/youtube-direct.js');
}

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
let cachedIpcPort = 56900;

// --- TAB CONTEXT & USER INTERACTION TRACKING ---
function isInternalBrowserUrl(u) {
  if (!u || typeof u !== 'string') return true;
  const s = u.toLowerCase().trim();
  return !s.startsWith('http://') && !s.startsWith('https://') && !s.startsWith('ftp://');
}

function normalizeHost(host) {
  if (!host || typeof host !== 'string') return "";
  let clean = host.toLowerCase().trim();
  clean = clean.replace(/^https?:\/\//, '');
  if (clean.startsWith('*.')) clean = clean.substring(2);
  else if (clean.startsWith('*')) clean = clean.substring(1);
  if (clean.startsWith('www.')) clean = clean.substring(4);
  if (clean.includes(':')) clean = clean.split(':')[0];
  if (clean.includes('/')) clean = clean.split('/')[0];
  return clean;
}

const tabContextMap = new Map(); // tabId -> { url, domain, openerTabId, timestamp }
let lastActiveTabContext = { tabId: null, url: "", domain: "", timestamp: 0 };
let lastUserInteraction = { tabId: null, url: "", domain: "", timestamp: 0 };

function trackTab(tabId, url, openerTabId, isActive) {
  if (!tabId || !url || isInternalBrowserUrl(url)) return;
  const domain = normalizeHost(url);
  const info = { url, domain, openerTabId: openerTabId || null, timestamp: Date.now() };
  tabContextMap.set(tabId, info);
  if (isActive) {
    lastActiveTabContext = { tabId, url, domain, timestamp: Date.now() };
  }
}

// Initial populate of all open tabs
if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.query) {
  chrome.tabs.query({}, (tabs) => {
    for (const t of (tabs || [])) {
      if (t && t.id && t.url) {
        trackTab(t.id, t.url, t.openerTabId, !!t.active);
      }
    }
  });
}

if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
  chrome.storage.local.get(['ipcPort'], (res) => {
    if (res && res.ipcPort) {
      cachedIpcPort = parseInt(res.ipcPort, 10) || 56900;
    }
  });

  if (chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && changes.ipcPort) {
        cachedIpcPort = parseInt(changes.ipcPort.newValue, 10) || 56900;
      }
    });
  }
}

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

// Toolbar icon paths must be absolute extension URLs. The service worker and the options
// page now live in src/ subfolders, so a bare 'assets/...' path resolves relative to
// those folders and setIcon silently fails.
function iconUrl(path) {
  try {
    if (typeof chrome !== 'undefined' && chrome.runtime && typeof chrome.runtime.getURL === 'function') {
      return chrome.runtime.getURL(path);
    }
  } catch {}
  return '/' + path;
}

function getIconPathsForStyle(style, effectiveTheme) {
  let target = style || 'system';
  if (target === 'system') {
    target = (effectiveTheme === 'dark') ? 'light' : 'dark';
  }
  if (target === 'light') {
    return {
      16: iconUrl('assets/icon-light-16.png'),
      32: iconUrl('assets/icon-light-32.png'),
      48: iconUrl('assets/icon-light-48.png'),
      128: iconUrl('assets/icon-light-128.png')
    };
  }
  if (target === 'dark') {
    return {
      16: iconUrl('assets/icon-dark-16.png'),
      32: iconUrl('assets/icon-dark-32.png'),
      48: iconUrl('assets/icon-dark-48.png'),
      128: iconUrl('assets/icon-dark-128.png')
    };
  }
  return {
    16: iconUrl('assets/icon-16.png'),
    32: iconUrl('assets/icon-32.png'),
    48: iconUrl('assets/icon-48.png'),
    128: iconUrl('assets/icon-128.png')
  };
}

function isFirefoxEnv() {
  if (typeof browser !== 'undefined' && browser.runtime && typeof browser.runtime.getBrowserInfo === 'function') {
    return true;
  }
  if (typeof navigator !== 'undefined' && navigator.userAgent && navigator.userAgent.includes('Firefox')) {
    return true;
  }
  return false;
}

let lastAppliedIconKey = null;

function updateChromeActionIcon(effectiveTheme, iconStyle = 'system') {
  if (isFirefoxEnv()) return;
  const action = getActionAPI();
  if (!action || !action.setIcon) return;

  const iconKey = `${iconStyle}_${effectiveTheme}`;
  if (lastAppliedIconKey === iconKey) {
    return;
  }
  lastAppliedIconKey = iconKey;

  const paths = getIconPathsForStyle(iconStyle, effectiveTheme);
  try {
    action.setIcon({ path: paths }).catch((err) => {
      console.warn("Could not set extension toolbar icon (promise):", err);
    });
  } catch (err) {
    console.warn("Could not set extension toolbar icon (sync):", err);
  }
}

async function applyStoredActionIcon() {
  const action = getActionAPI();
  if (!action || !action.setIcon) return;

  chrome.storage.local.get({ actionIcon: 'system', theme: 'system', systemTheme: '' }, async (items) => {
    const iconPref = items.actionIcon || 'system';
    const themePref = items.theme || 'system';

    // In Firefox, if both icon and theme are set to system default, reset icon override to let native manifest theme_icons handle it seamlessly without hover
    if (isFirefoxEnv() && iconPref === 'system' && themePref === 'system') {
      try {
        await action.setIcon({ path: null });
        return;
      } catch (e) {
        console.warn("Could not reset Firefox icon to manifest default:", e);
        // Fallback to explicit paths if path: null fails
      }
    }

    let effectiveTheme;
    if (themePref === 'dark') {
      effectiveTheme = 'dark';
    } else if (themePref === 'light') {
      effectiveTheme = 'light';
    } else {
      // themePref === 'system'
      if (items.systemTheme === 'dark' || items.systemTheme === 'light') {
        effectiveTheme = items.systemTheme;
      } else if (typeof matchMedia !== 'undefined') {
        try {
          effectiveTheme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        } catch {
          effectiveTheme = null;
        }
      } else {
        effectiveTheme = null;
      }
    }

    // If the system theme is still unknown (service workers have no matchMedia and
    // content.js has not reported yet), assume light like 0.10 did so the toolbar icon
    // is still theme-adaptive immediately. content.js corrects it once it reports.
    if (effectiveTheme === null || effectiveTheme === undefined) {
      effectiveTheme = 'light';
    }

    if (!isFirefoxEnv()) {
      updateChromeActionIcon(effectiveTheme, iconPref);
    } else {
      const paths = getIconPathsForStyle(iconPref, effectiveTheme);
      try {
        await action.setIcon({ path: paths });
      } catch (err) {
        console.warn("Could not set extension toolbar icon:", err);
      }
    }
  });
}
applyStoredActionIcon();

// Tab-independent system theme detection (Chrome only). A service worker has no matchMedia,
// and content scripts only see theme changes while a normal web page is open and visible.
// An offscreen document with the MATCH_MEDIA reason stays alive and reports every change.
async function ensureThemeOffscreenDocument() {
  if (isFirefoxEnv()) return;
  if (!chrome.offscreen || typeof chrome.offscreen.createDocument !== 'function') return;
  try {
    if (chrome.runtime.getContexts) {
      const existing = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
      if (existing && existing.length) return;
    }
    await chrome.offscreen.createDocument({
      url: 'src/background/offscreen.html',
      reasons: ['MATCH_MEDIA'],
      justification: 'Detect the system dark/light mode so the toolbar icon always matches it'
    });
  } catch (err) {
    // Already exists or unsupported on this Chrome version; content.js remains the fallback.
  }
}
ensureThemeOffscreenDocument();
chrome.runtime.onStartup.addListener(ensureThemeOffscreenDocument);
chrome.runtime.onInstalled.addListener(ensureThemeOffscreenDocument);

// Re-apply icon on startup and install to handle fresh profiles before content.js reports theme
chrome.runtime.onStartup.addListener(applyStoredActionIcon);
chrome.runtime.onInstalled.addListener(applyStoredActionIcon);

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local') {
    for (const key of ['enableInterception', 'enableMediaSniffing', 'whitelistUrls', 'whitelistExts', 'blacklistUrls', 'blacklistExts']) {
      if (changes[key] !== undefined) {
        cachedFilterRules[key] = changes[key].newValue;
      }
    }
    if (changes.actionIcon || changes.theme || changes.systemTheme) {
      applyStoredActionIcon();
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
  if (!rawInput || typeof rawInput !== 'string') return { hostname: "", normHost: "", pathname: "", raw: "" };
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
    if (pathname.endsWith('/*')) pathname = pathname.slice(0, -2);
    else if (pathname.endsWith('*')) pathname = pathname.slice(0, -1);
    const normHost = normalizeHost(hostname);
    return { hostname, normHost, pathname, hasWildcard, raw: str };
  } catch (e) {
    const rawHost = str.replace(/\/.*$/, '');
    return { hostname: rawHost, normHost: normalizeHost(rawHost), pathname: "", hasWildcard, raw: str };
  }
}

function matchesUrlOrDomain(targetUrl, urlPatterns, ...additionalCandidates) {
  if (!Array.isArray(urlPatterns) || urlPatterns.length === 0) return false;
  
  const targets = [];
  function addCandidate(c) {
    if (!c) return;
    if (Array.isArray(c)) {
      for (const item of c) addCandidate(item);
      return;
    }
    if (typeof c === 'string') {
      const trimmed = c.trim();
      if (trimmed && !isInternalBrowserUrl(trimmed) && !targets.includes(trimmed)) {
        targets.push(trimmed);
      }
    }
  }

  addCandidate(targetUrl);
  for (const cand of additionalCandidates) {
    addCandidate(cand);
  }

  if (targets.length === 0) return false;

  for (const pattern of urlPatterns) {
    if (!pattern || typeof pattern !== 'string') continue;
    const pInfo = parseDomainAndPath(pattern);
    if (!pInfo.hostname && !pInfo.normHost && !pInfo.raw) continue;

    for (const testUrl of targets) {
      const urlLower = testUrl.toLowerCase();
      const tInfo = parseDomainAndPath(urlLower);

      // 1. Direct path/keyword match if pattern specifies specific path or query
      if (pInfo.pathname && (urlLower.includes(pInfo.raw) || (tInfo.pathname && tInfo.pathname.startsWith(pInfo.pathname)))) {
        if (pInfo.normHost && tInfo.normHost) {
          if (tInfo.normHost === pInfo.normHost || tInfo.normHost.endsWith('.' + pInfo.normHost)) {
            return true;
          }
        } else {
          return true;
        }
      }

      // 2. Normalized Hostname comparison (handles www., subdomains, exact match)
      if (pInfo.normHost && tInfo.normHost) {
        const hostMatches = (tInfo.normHost === pInfo.normHost || 
                             tInfo.normHost.endsWith('.' + pInfo.normHost) ||
                             (tInfo.hostname && tInfo.hostname === pInfo.hostname) ||
                             (tInfo.hostname && tInfo.hostname.endsWith('.' + pInfo.hostname)));

        if (hostMatches) {
          if (pInfo.pathname) {
            const cleanTPath = tInfo.pathname.replace(/^\//, '');
            const cleanPPath = pInfo.pathname.replace(/^\//, '');
            if (cleanTPath.startsWith(cleanPPath)) return true;
          } else {
            return true;
          }
        }
      }

      // 3. Fallback substring search for raw pattern if user typed specific domain keyword
      if (pInfo.normHost && urlLower.includes(pInfo.normHost)) {
        return true;
      }
      if (pInfo.raw && pInfo.raw.length > 3 && urlLower.includes(pInfo.raw)) {
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

function shouldInterceptDownloadSync(url, filename, referrer, extraContext = {}) {
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

  // Collect all context URLs associated with this download
  const candidates = [];
  if (referrer) candidates.push(referrer);
  if (extraContext.finalUrl) candidates.push(extraContext.finalUrl);
  if (extraContext.tabUrl) candidates.push(extraContext.tabUrl);

  if (extraContext.tabId && tabContextMap.has(extraContext.tabId)) {
    const tabInfo = tabContextMap.get(extraContext.tabId);
    if (tabInfo && tabInfo.url) {
      candidates.push(tabInfo.url);
      if (tabInfo.openerTabId && tabContextMap.has(tabInfo.openerTabId)) {
        const openerInfo = tabContextMap.get(tabInfo.openerTabId);
        if (openerInfo && openerInfo.url) candidates.push(openerInfo.url);
      }
    }
  }

  // Check last active tab if valid
  if (lastActiveTabContext.url && !isInternalBrowserUrl(lastActiveTabContext.url)) {
    candidates.push(lastActiveTabContext.url);
  }

  // Check recent user click/form interaction within last 25 seconds
  if (lastUserInteraction.url && (Date.now() - lastUserInteraction.timestamp < 25000)) {
    candidates.push(lastUserInteraction.url);
  }

  // 1. Blacklist check - if matched on URL, domain, referrer, active tab, user interaction, or extension: do NOT intercept (leave to browser)
  if (matchesUrlOrDomain(url, rules.blacklistUrls, candidates) || matchesExtension(ext || filename, rules.blacklistExts)) {
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
  if (matchesUrlOrDomain(url, rules.whitelistUrls, candidates)) {
    return true;
  }

  return true;
}

async function shouldInterceptDownload(url, filename, referrer, extraContext = {}) {
  return shouldInterceptDownloadSync(url, filename, referrer, extraContext);
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

// Sanitizes and strips oversized tracking / non-essential tokens from media site cookies (e.g. YouTube)
// to prevent HTTP 413 (Request Entity Too Large) errors when communicating with servers and yt-dlp.
function sanitizeMediaCookies(cookieStr, targetUrl) {
  if (!cookieStr || typeof cookieStr !== "string") return "";
  const isYt = targetUrl && (targetUrl.includes("youtube.com") || targetUrl.includes("youtu.be"));
  if (!isYt) return cookieStr;

  const YT_IGNORE = new Set([
    "_gcl_au", "__Secure-ROLLOUT_TOKEN", "GPS", "OTZ",
    "_ga", "_gid", "1P_JAR"
  ]);

  return cookieStr
    .split(";")
    .map(c => c.trim())
    .filter(c => {
      if (!c || !c.includes("=")) return false;
      const name = c.substring(0, c.indexOf("=")).trim();
      return !YT_IGNORE.has(name);
    })
    .join("; ");
}

// Direct downloads relay a signed stream URL verbatim, so cookies are only forwarded when the
// stream host is the page host or a sibling subdomain. This keeps session cookies away from
// third-party CDNs (e.g. youtube.com cookies must never reach googlevideo.com).
function shouldSendCookiesForDirect(streamUrl, referrerUrl) {
  const hostOf = (value) => {
    try {
      return new URL(value).hostname.toLowerCase().replace(/\.$/, "");
    } catch (e) {
      return "";
    }
  };
  const streamHost = hostOf(streamUrl);
  const refHost = hostOf(referrerUrl);
  if (!streamHost || !refHost) return false;
  if (streamHost === refHost) return true;
  return streamHost.endsWith("." + refHost) || refHost.endsWith("." + streamHost);
}

function formatDirectSize(bytes) {
  const total = Number(bytes) || 0;
  if (total <= 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = total;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index++;
  }
  return `${value.toFixed(index ? 2 : 0)}${units[index]}`;
}

// Ask the desktop to resolve stream URLs (yt-dlp locates them, Aria2 downloads them).
// Adaptive YouTube tiers need both the selected video and its audio track.
async function resolveDirectStreamUrl(pageUrl, cookies, userAgent, referrer, selection = {}) {
  const online = await isBengalDMOnline();
  if (!online) return null;

  const ipcPort = cachedIpcPort || 56900;
  const payload = JSON.stringify({
    url: pageUrl,
    cookies: cookies || "",
    userAgent: userAgent || navigator.userAgent,
    referrer: referrer || "",
    videoItag: selection.videoItag || "",
    audioItag: selection.audioItag || ""
  });

  for (const host of ["127.0.0.1", "localhost"]) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 95000);
      const response = await fetch(`http://${host}:${ipcPort}/resolve-direct`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (!response.ok) continue;
      const data = await response.json();
      if (data && data.success && (data.videoUrl || data.audioUrl || data.resolvedUrl)) return data;
      return null;
    } catch (e) {
      // Try the alternate loopback host
    }
  }
  return null;
}

// yt-dlp-backed SABR fallback with per-(page, itag pair) result cache.
async function resolveSabrWithCache(pageUrl, selection = {}) {
  const cacheKey = `${pageUrl}#${selection.videoItag || ''}#${selection.audioItag || ''}`;
  const now = Date.now();
  const cached = sabrResolveCache.get(cacheKey);
  if (cached && now - cached.ts < SABR_CACHE_TTL_MS) {
    return { videoUrl: cached.videoUrl, audioUrl: cached.audioUrl || '' };
  }
  const resolved = await resolveDirectStreamUrl(pageUrl, '', navigator.userAgent, pageUrl, selection);
  if (resolved && resolved.videoUrl) {
    sabrResolveCache.set(cacheKey, { videoUrl: resolved.videoUrl, audioUrl: resolved.audioUrl || '', ts: now });
    if (sabrResolveCache.size > 200) sabrResolveCache.delete(sabrResolveCache.keys().next().value);
  }
  return resolved;
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
  const primaryPort = cachedIpcPort || 56900;
  const portsToTry = [primaryPort];
  for (const fp of [26900, 26901, 26902]) {
    if (!portsToTry.includes(fp)) portsToTry.push(fp);
  }
  if (!portsToTry.includes(56900)) portsToTry.push(56900);

  for (const port of portsToTry) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1200);
      const response = await fetch(`http://127.0.0.1:${port}/`, {
        method: 'GET',
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (response.ok) {
        online = true;
        try { config = await response.json(); } catch {}
        if (config && config.ipc_port) {
          cachedIpcPort = parseInt(config.ipc_port, 10) || port;
        } else {
          cachedIpcPort = port;
        }
        break;
      }
    } catch {
      // Continue to next port candidate
    }
  }

  if (config) {
    if (config.ipc_port) {
      cachedIpcPort = parseInt(config.ipc_port, 10) || cachedIpcPort;
    }
    cachedSabrCapability = config.sabr === true;
    updateDynamicMediaConfig(config);
    chrome.storage.local.set({
      ipcPort: cachedIpcPort,
      activeIpcPort: cachedIpcPort,
      isIpcFallback: Boolean(config.is_fallback),
      configuredIpcPort: config.configured_ipc_port || 56900
    });
  }

  await updateAppConnectionBadge(online);
  return online;
}

// --- SEND DOWNLOAD TO BENGAL DM ---
async function sendToBengalDM(downloadData) {
  const { url, userAgent, cookies, filename, referrer } = downloadData;
  const ipcPort = cachedIpcPort || 56900;

  const isOnline = await isBengalDMOnline();
  if (!isOnline) {
    console.warn(`Bengal DM application is not running on port ${ipcPort}.`);
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
    method: downloadData.method || "standard",
    ext: downloadData.ext || "",
    pageExtract: !!downloadData.pageExtract,
    sizeBytes: downloadData.sizeBytes || 0,
    sizeStr: downloadData.sizeStr || "",
    audioUrl: downloadData.audioUrl || "",
    sabr: downloadData.sabr || undefined
  };

  try {
    const response = await fetch(`http://127.0.0.1:${ipcPort}/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    return response.ok;
  } catch (err) {
    try {
      const response = await fetch(`http://localhost:${ipcPort}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      return response.ok;
    } catch (e) {
      console.error(`Failed to send download to Bengal DM on port ${ipcPort}:`, e);
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
const tabDirectFormats = new Map();     // tabId -> Array of { url, title, mime, quality, bitrate, format, audioUrl, ... }
const youtubePlayers = new Map();       // tabId -> { videoId, title, sabrUrl, ustreamerConfig, clientName, clientVersion, formats[] }
const sabrResolveCache = new Map();     // "${pageUrl}#${videoItag}#${audioItag}" -> { videoUrl, audioUrl, ts }
const SABR_CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes (signed URLs expire)
let cachedSabrCapability = false;       // desktop exposes a Deno SABR streaming runtime (GET / config.sabr)

function recordSniffedMedia(tabId, url, contentType, title, sizeBytes = 0) {
  if (!tabId || tabId === -1 || !url) return;
  let list = tabMediaStreams.get(tabId);
  if (!list) {
    list = [];
    tabMediaStreams.set(tabId, list);
  }
  const existing = list.find(item => item.url === url);
  if (existing) {
    if (title && !existing.title) existing.title = title;
    if (contentType && !existing.contentType) existing.contentType = contentType;
    if (sizeBytes && !existing.sizeBytes) existing.sizeBytes = sizeBytes;
    existing.timestamp = Date.now();
  } else {
    list.push({ url, contentType: contentType || "", title: title || "", sizeBytes: sizeBytes || 0, timestamp: Date.now() });
    if (list.length > 30) list.shift();
  }
}

if (chrome.tabs && chrome.tabs.onRemoved) {
  chrome.tabs.onRemoved.addListener((tabId) => {
    tabMediaStreams.delete(tabId);
    setTimeout(() => {
      tabContextMap.delete(tabId);
    }, 15000);
  });
}

// Dynamic media config, synchronized from Bengal DM app (or default fallback)
const POPULAR_MEDIA_HOSTS = [
  'youtube.com', 'youtu.be',
  'facebook.com', 'fb.watch', 'fb.com',
  'instagram.com',
  'tiktok.com',
  'twitter.com', 'x.com',
  'reddit.com',
  'vimeo.com',
  'dailymotion.com',
  'twitch.tv',
  'bilibili.com',
  'soundcloud.com',
  'rumble.com',
  'kick.com',
  'streamable.com',
  'pinterest.com'
];

function isPopularMediaHost(hostname) {
  if (!hostname) return false;
  const host = hostname.toLowerCase();
  return POPULAR_MEDIA_HOSTS.some(h => host === h || host.endsWith('.' + h));
}

const dynamicMediaConfig = {
  mediaTypes: ['application/x-mpegurl', 'application/vnd.apple.mpegurl', 'application/dash+xml', 'video/mp4', 'video/webm', 'video/', 'audio/'],
  mediaExts: ['m3u8', 'mpd', 'mp4', 'webm', 'mkv', 'flv', 'vid', 'm4s', 'ts', 'f4v'],
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
    let cl = 0;
    if (details.responseHeaders) {
      const clH = details.responseHeaders.find(h => (h.name || '').toLowerCase() === 'content-length');
      if (clH) cl = parseInt(clH.value, 10) || 0;
    }
    recordSniffedMedia(details.tabId, details.url, "", tab ? tab.title : "", cl);
    try {
      chrome.tabs.sendMessage(details.tabId, {
        action: "media_stream_detected",
        stream: { url: details.url, title: tab ? tab.title : "", sizeBytes: cl }
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
    if (cachedFilterRules.enableMediaSniffing === false || cachedFilterRules.enableInterception === false || !cachedAppOnline) {
      return;
    }

    const req = pendingMediaRequests.get(details.requestId);
    let reqReferrer = "";
    if (req && req.requestHeaders) {
      const refH = req.requestHeaders.find(h => h.name && h.name.toLowerCase() === 'referer');
      if (refH) reqReferrer = refH.value;
    }

    const bList = cachedFilterRules.blacklistUrls || [];
    if (matchesUrlOrDomain(details.url, bList, reqReferrer || details.initiator || details.documentUrl)) {
      return;
    }
    if (reqReferrer && matchesUrlOrDomain(reqReferrer, bList)) {
      return;
    }
    if (details.initiator && matchesUrlOrDomain(details.initiator, bList)) {
      return;
    }

    let contentType = "";
    let isAttachment = false;
    let contentLength = 0;

    for (const h of (details.responseHeaders || [])) {
      const name = (h.name || '').toLowerCase();
      const val = (h.value || '').toLowerCase();
      if (name === 'content-type') {
        contentType = val;
      } else if (name === 'content-disposition' && (val.includes('attachment') || val.includes('filename='))) {
        isAttachment = true;
      } else if (name === 'content-length') {
        const cl = parseInt(val, 10);
        if (!isNaN(cl) && cl > 0) contentLength = cl;
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

      if (details.tabId && details.tabId !== -1) {
        chrome.tabs.get(details.tabId, (tab) => {
          if (chrome.runtime.lastError || !tab) return;
          if (tab.url && matchesUrlOrDomain(tab.url, cachedFilterRules.blacklistUrls)) {
            return;
          }
          recordSniffedMedia(details.tabId, details.url, contentType, tab.title || "", contentLength);
          try {
            chrome.tabs.sendMessage(details.tabId, {
              action: "media_stream_detected",
              stream: { url: details.url, contentType: contentType, sizeBytes: contentLength }
            }).catch(() => {});
          } catch (e) {}
          postMediaToBengalDM(details, req, tab, contentType);
        });
      } else {
        postMediaToBengalDM(details, req, null, contentType);
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

// 4. Tab title updates & synchronous context tracking
if (chrome.tabs && chrome.tabs.onUpdated) {
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (tab && tab.url) {
      trackTab(tabId, tab.url, tab.openerTabId, !!tab.active);
    }
    if (changeInfo.title && tab && tab.url && cachedAppOnline) {
      try {
        const port = cachedIpcPort || 56900;
        fetch(`http://127.0.0.1:${port}/tab-update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tabId: String(tabId), tabUrl: tab.url, tabTitle: changeInfo.title })
        }).catch(() => {});
      } catch {}
    }
  });
}

// 5. Active tab context updates & close media popup dropdown when switching tabs
if (chrome.tabs && chrome.tabs.onActivated) {
  chrome.tabs.onActivated.addListener((activeInfo) => {
    chrome.tabs.get(activeInfo.tabId, (tab) => {
      if (!chrome.runtime.lastError && tab && tab.url) {
        trackTab(tab.id, tab.url, tab.openerTabId, true);
      }
    });
    chrome.tabs.query({}, (tabs) => {
      for (const t of (tabs || [])) {
        if (t.id && t.id !== activeInfo.tabId) {
          chrome.tabs.sendMessage(t.id, { action: "close_dropdown" }).catch(() => {});
        }
      }
    });
  });
}

if (chrome.tabs && chrome.tabs.onCreated) {
  chrome.tabs.onCreated.addListener((tab) => {
    if (tab && tab.id && (tab.url || tab.pendingUrl)) {
      trackTab(tab.id, tab.url || tab.pendingUrl, tab.openerTabId, false);
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
        const extraContext = {
          tabId: details.tabId !== -1 ? details.tabId : null,
          tabUrl: (details.tabId !== -1 && tabContextMap.has(details.tabId)) ? tabContextMap.get(details.tabId).url : ""
        };
        const shouldIntercept = shouldInterceptDownloadSync(details.url, filenameFromHeader, referrer, extraContext);
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

  const isFirefox = isFirefoxEnv();
  const manifest = (chrome.runtime && chrome.runtime.getManifest) ? chrome.runtime.getManifest() : {};
  const hasBlocking = isFirefox && manifest.permissions && Array.isArray(manifest.permissions) && manifest.permissions.includes('webRequestBlocking');
  const extraSpec = hasBlocking ? ["responseHeaders", "blocking"] : ["responseHeaders"];

  try {
    setupListener(extraSpec);
  } catch (err) {
    try {
      setupListener(["responseHeaders"]);
    } catch {}
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

    const referrer = downloadItem.referrer || "";
    const extraContext = {
      finalUrl: downloadItem.finalUrl || ""
    };
    const shouldIntercept = shouldInterceptDownloadSync(downloadItem.url, downloadItem.filename, referrer, extraContext);
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

    const referrer = downloadItem.referrer || "";
    const extraContext = {
      finalUrl: downloadItem.finalUrl || ""
    };
    // Check Whitelist & Blacklist rules
    const shouldIntercept = shouldInterceptDownloadSync(downloadItem.url, downloadItem.filename, referrer, extraContext);
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
  chrome.storage.local.get(['port', 'enableInterception', 'theme', 'actionIcon'], (items) => {
    if (!items.port || items.port === 6800 || items.port === 50001 || items.port === 6801) {
      chrome.storage.local.set({ port: 56800 });
    }
    if (items.enableInterception === undefined) {
      chrome.storage.local.set({ enableInterception: true });
    }
    if (!items.theme) {
      chrome.storage.local.set({ theme: "system" });
    }
    if (!items.actionIcon) {
      chrome.storage.local.set({ actionIcon: "system" });
    }
    applyStoredActionIcon();
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
          cookies: sanitizeMediaCookies(cookieString, cleanTargetUrl),
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
        // Fallback check (XDM style): If user right-clicked a page or link that is an HTML landing,
        // but this tab has sniffed media streams, send the sniffed media stream!
        const tabStreams = (tab && tab.id) ? (tabMediaStreams.get(tab.id) || []) : [];
        if (tabStreams.length > 0) {
          const masterStream = tabStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
          const playlistStream = tabStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
          const directStream = tabStreams.slice().reverse().find(s => /\.(mp4|webm|vid)(\?|$)/i.test(s.url) || (s.contentType && s.contentType.includes('video/')));
          const best = masterStream || playlistStream || directStream || tabStreams[tabStreams.length - 1];
          if (best && best.url) {
            markRecentlySent(best.url);
            const success = await sendToBengalDM({
              url: best.url,
              userAgent: navigator.userAgent,
              cookies: sanitizeMediaCookies(cookieString, best.url),
              referrer: targetUrl,
              title: (tab && tab.title) ? tab.title : "",
              filename: (tab && tab.title) ? tab.title : "",
              isMedia: true
            });
            if (success) {
              notifyUser("Bengal DM", "Media stream sent to Bengal DM!");
            } else {
              notifyUser("Bengal DM Error", "Could not send to Bengal DM. Is the application running?");
            }
            return;
          }
        }
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
  if (request && request.action === "system_theme_report") {
    // Saving systemTheme triggers storage.onChanged -> applyStoredActionIcon, which also
    // respects the user's explicit theme/icon choices.
    if (request.effectiveTheme === 'dark' || request.effectiveTheme === 'light') {
      chrome.storage.local.get({ systemTheme: '' }, (items) => {
        if (items.systemTheme !== request.effectiveTheme) {
          chrome.storage.local.set({ systemTheme: request.effectiveTheme });
        }
      });
    }
    sendResponse({ status: "ok" });
    return false;
  }
  if (request.action === "user_page_interaction") {
    const tabId = sender && sender.tab ? sender.tab.id : null;
    const url = request.url || (sender && sender.tab ? sender.tab.url : "");
    if (url && !isInternalBrowserUrl(url)) {
      lastUserInteraction = {
        tabId: tabId,
        url: url,
        domain: normalizeHost(url),
        timestamp: Date.now()
      };
      if (tabId) {
        trackTab(tabId, url, sender && sender.tab ? sender.tab.openerTabId : null, true);
      }
    }
    sendResponse({ received: true });
    return true;
  }

  if (request.action === "send_to_bengal") {
    (async () => {
      const tabUrl = (sender && sender.tab) ? sender.tab.url : null;
      const refUrl = request.referrer || tabUrl;
      const rules = cachedFilterRules;
      const bList = rules.blacklistUrls || [];

      if (rules.enableInterception === false ||
          matchesUrlOrDomain(request.url, bList, refUrl, tabUrl) ||
          (tabUrl && matchesUrlOrDomain(tabUrl, bList)) ||
          (refUrl && matchesUrlOrDomain(refUrl, bList))) {
        sendResponse({ success: false, bypassed: true });
        return;
      }

      const cookieString = await getCookiesForUrl(request.url, sender && sender.tab ? sender.tab.cookieStoreId : undefined);

      if (!request.resolveDirect && !request.pageExtract && isRecentlySent(request.url)) {
        sendResponse({ success: true, duplicate: true });
        return;
      }

      if (request.isMedia || isMediaUrl(request.url)) {
        // Direct method: the URL is an already-muxed stream captured from the page,
        // or a page URL the desktop resolves into one (ciphered/SABR-only players).
        // Either way the URL is relayed verbatim - no sanitizeMediaUrl, no tabMediaStreams
        // rewrite, because the signed query string must reach Aria2 untouched.
        if (request.method === "direct") {
          let directUrl = "";
          let directExt = request.ext || "";
          let directSizeBytes = Number(request.sizeBytes) || 0;
          let directSizeStr = request.sizeStr || "";
          let directReferrer = request.referrer || refUrl || request.url;
          let resolveKey = "";

          if (request.resolveDirect) {
            let pageUrl = "";
            try {
              const parsed = new URL(request.url);
              if (parsed.protocol === "http:" || parsed.protocol === "https:") {
                pageUrl = request.url;
              }
            } catch (e) {}
            if (!pageUrl) {
              sendResponse({ success: false, error: "invalid_direct_url" });
              return;
            }

            resolveKey = `${pageUrl}#direct`;
            if (isRecentlySent(resolveKey)) {
              sendResponse({ success: true, duplicate: true });
              return;
            }
            directReferrer = request.referrer || refUrl || pageUrl;
            const resolved = await resolveDirectStreamUrl(
              pageUrl,
              cookieString,
              navigator.userAgent,
              directReferrer
            );
            if (!resolved) {
              sendResponse({ success: false, error: "resolve_failed" });
              return;
            }
            directUrl = resolved.resolvedUrl;
            if (!directExt) directExt = resolved.ext || "";
            if (!directSizeBytes) directSizeBytes = Number(resolved.sizeBytes) || 0;
            if (!directSizeStr && directSizeBytes > 0) directSizeStr = formatDirectSize(directSizeBytes);
          } else {
            try {
              const parsed = new URL(request.url);
              if (parsed.protocol === "http:" || parsed.protocol === "https:") {
                directUrl = request.url;
              }
            } catch (e) {}
          }

          if (!directUrl) {
            sendResponse({ success: false, error: "invalid_direct_url" });
            return;
          }

          // Resolution-select Direct tiers reuse the page URL, so dedupe per quality
          // instead of per URL (otherwise only one resolution could ever be queued).
          const dedupeKey = resolveKey || (request.pageExtract
            ? `${directUrl}#direct:${request.quality || ''}`
            : directUrl);

          if (isRecentlySent(dedupeKey)) {
            sendResponse({ success: true, duplicate: true });
            return;
          }

          markRecentlySent(dedupeKey);
          const success = await sendToBengalDM({
            url: directUrl,
            userAgent: navigator.userAgent,
            cookies: shouldSendCookiesForDirect(directUrl, directReferrer) ? cookieString : "",
            referrer: directReferrer,
            title: request.title || "",
            filename: request.filename || request.title || "",
            quality: request.quality || "",
            isMedia: true,
            method: "direct",
            pageExtract: !!request.pageExtract,
            sizeBytes: directSizeBytes,
            sizeStr: directSizeStr,
            ext: directExt
          });
          sendResponse({ success, resolvedUrl: directUrl });
          return;
        }

        let cleanUrl = isMediaUrl(request.url) ? sanitizeMediaUrl(request.url) : request.url;

        // Fallback: If cleanUrl points to an external domain (NOT a popular platform)
        // and does NOT look like a direct streaming media file (e.g. it's an HTML page or iframe embed),
        // check if tabMediaStreams has sniffed the real video stream for this tab.
        try {
          const parsedUrl = new URL(cleanUrl);
          const host = parsedUrl.hostname.toLowerCase();
          const isPopular = isPopularMediaHost(host);
          const isDirectStream = isStreamingMedia(cleanUrl) || /\.(m3u8|mpd|mp4|webm|mkv|flv|vid|m4s)(\?|$)/i.test(parsedUrl.pathname);

          if (!isPopular && !isDirectStream) {
            let tabId = (sender && sender.tab) ? sender.tab.id : null;
            if (!tabId && chrome.tabs && chrome.tabs.query) {
              try {
                const [actTab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (actTab) tabId = actTab.id;
              } catch (e) {}
            }
            if (tabId) {
              const streams = tabMediaStreams.get(tabId) || [];
              if (streams.length > 0) {
                const masterStream = streams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
                const playlistStream = streams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
                const directStream = streams.slice().reverse().find(s => /\.(mp4|webm|vid)(\?|$)/i.test(s.url) || (s.contentType && s.contentType.includes('video/')));
                const best = masterStream || playlistStream || directStream || streams[streams.length - 1];
                if (best && best.url) {
                  if (!request.referrer) {
                    request.referrer = cleanUrl;
                  }
                  cleanUrl = best.url;
                }
              }
            }
          }
        } catch (e) {}

        markRecentlySent(cleanUrl);
        const success = await sendToBengalDM({
          url: cleanUrl,
          userAgent: navigator.userAgent,
          cookies: sanitizeMediaCookies(cookieString, cleanUrl),
          referrer: request.referrer || request.url,
          filename: request.filename || request.title || "",
          title: request.title || "",
          quality: request.quality || "",
          isMedia: true,
          sizeBytes: request.sizeBytes || 0,
          sizeStr: request.sizeStr || "",
          ext: request.ext || ""
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

  if (request.action === "report_system_theme" && request.systemTheme) {
    chrome.storage.local.get({ systemTheme: '' }, (items) => {
      if (items.systemTheme !== request.systemTheme) {
        chrome.storage.local.set({ systemTheme: request.systemTheme }, () => {
          applyStoredActionIcon();
        });
      }
    });
    sendResponse({ status: "ok" });
    return true;
  }

  if (request.action === "sync_icon_with_theme" && request.effectiveTheme) {
    if (!isFirefoxEnv()) {
      chrome.storage.local.get({ actionIcon: 'system', theme: 'system', systemTheme: '' }, (items) => {
        const iconPref = items.actionIcon || 'system';
        const themePref = items.theme || 'system';
        if (iconPref === 'system') {
          if (items.systemTheme !== request.effectiveTheme) {
            chrome.storage.local.set({ systemTheme: request.effectiveTheme }, () => {
              updateChromeActionIcon(request.effectiveTheme, iconPref);
            });
          } else {
            updateChromeActionIcon(request.effectiveTheme, iconPref);
          }
        }
      });
    }
    sendResponse({ status: "ok" });
    return true;
  }

  if (request.action === "update_connection_status") {
    updateAppConnectionBadge(Boolean(request.online));
    sendResponse({ success: true, online: cachedAppOnline });
    return true;
  }

  if (request.action === "get_connection_status") {
    if (!cachedAppOnline) {
      isBengalDMOnline().then(online => {
        sendResponse({ online: Boolean(online) });
      }).catch(() => {
        sendResponse({ online: false });
      });
      return true;
    }
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
    const tabUrl = (sender && sender.tab) ? sender.tab.url : null;
    const rules = cachedFilterRules;
    if (rules.enableInterception === false || (tabUrl && matchesUrlOrDomain(tabUrl, rules.blacklistUrls))) {
      sendResponse({ streams: [] });
      return true;
    }
    const streams = tabId ? (tabMediaStreams.get(tabId) || []) : [];
    sendResponse({ streams });
    return true;
  }

  if (request.action === "get_media_sizes") {
    (async () => {
      const isOnline = await isBengalDMOnline();
      if (!isOnline) {
        sendResponse({ success: false, offline: true });
        return;
      }

      const ipcPort = cachedIpcPort || 56900;
      const cookieString = await getCookiesForUrl(request.url, sender && sender.tab ? sender.tab.cookieStoreId : undefined);

      const payload = {
        url: request.url,
        referrer: request.referrer || ((sender && sender.tab) ? sender.tab.url : ""),
        userAgent: navigator.userAgent,
        cookies: sanitizeMediaCookies(cookieString, request.url),
        heights: request.heights || [2160, 1440, 1080, 720, 480, 360, 240, 144],
        videoContainer: "auto",
        audioFormat: "auto"
      };

      try {
        let response = await fetch(`http://127.0.0.1:${ipcPort}/media-sizes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!response.ok) {
          response = await fetch(`http://localhost:${ipcPort}/media-sizes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }
        if (response.ok) {
          const data = await response.json();
          sendResponse(data);
          return;
        }
      } catch (e) {
        console.warn("[Bengal DM] get_media_sizes request failed:", e);
      }
      sendResponse({ success: false, error: "Fetch failed" });
    })();
    return true;
  }

  // --- AWESOME DOWNLOADER STYLE: Per-tab direct format cache & download ---
  if (request.action === 'remember' && sender.tab) {
    const tabId = sender.tab.id;
    const items = Array.isArray(request.items) ? request.items : [];
    let list = tabDirectFormats.get(tabId) || [];
    for (const item of items.slice(0, 100)) {
      const url = item.url;
      if (!url || !/^https?:\/\//i.test(url)) continue;
      const existing = list.findIndex(i => i.url === url);
      if (existing >= 0) {
        list[existing] = {...list[existing], ...item};
      } else {
        list.push(item);
      }
    }
    tabDirectFormats.set(tabId, list.slice(-100));
    sendResponse({ok: true});
    return true;
  }

  if (request.action === 'playerResponse' && sender.tab) {
    const page = new URL(sender.url || sender.tab.url || 'https://invalid.local');
    if (!['www.youtube.com','youtube.com','m.youtube.com'].includes(page.hostname)) {
      sendResponse({ok: false, error: 'Invalid player source.'});
      return true;
    }
    const data = globalThis.bdmYouTube?.sanitizePlayer?.(request.data);
    if (data) {
      const previous = youtubePlayers.get(sender.tab.id);
      if (previous && previous.videoId !== data.videoId) {
        globalThis.bdmYouTubeDirect?.clear(sender.tab.id);
      }
      youtubePlayers.set(sender.tab.id, data);
      if (youtubePlayers.size > 50) youtubePlayers.delete(youtubePlayers.keys().next().value);
    }
    sendResponse({ok: true});
    return true;
  }

  if (request.action === 'list' && !sender.tab) {
    const tabId = request.tabId;
    const list = tabId ? (tabDirectFormats.get(tabId) || []) : [];
    sendResponse({ok: true, items: list});
    return true;
  }

  if (request.action === 'listForFrame' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const page = new URL(sender.tab.url || 'https://invalid.local');
      const isYoutube = /(^|\.)youtube\.com$/.test(page.hostname);

      if (isYoutube) {
        const id = page.searchParams.get('v') || /^\/shorts\/([\w-]{11})/.exec(page.pathname)?.[1];
        if (/^[\w-]{11}$/.test(id || '')) {
          try {
            await chrome.tabs.sendMessage(tabId, {action: 'refreshPlayer'});
          } catch {}
          const player = youtubePlayers.get(tabId);
          if (!player || player.videoId !== id) {
            sendResponse({ok: true, items: []});
            return;
          }
          const observed = globalThis.bdmYouTubeDirect?.getObserved(tabId) || [];
          const items = globalThis.bdmYouTube?.choices(player, observed) || [];
          sendResponse({ok: true, items});
          return;
        }
      }

      let items = tabId ? (tabDirectFormats.get(tabId) || []) : [];
      sendResponse({ok: true, items});
    })();
    return true;
  }

  if (request.action === 'download') {
    const tabId = sender.tab?.id ?? request.tabId;
    const item = request.item || {};
    const pageUrl = sender.tab ? sender.tab.url : '';
    let url = item.url;

    // YouTube adaptive/SABR tiers ship separate video-only and audio-only tracks.
    // Fetching one URL through Aria2 would save a silent video, so the desktop keeps
    // the chosen quality, transfers both tracks through Aria2 and muxes them with FFmpeg.
    const needsAudioMerge = item.provider === 'youtube' && (!!item.sabrSelection || !!item.audioUrl);
    if (needsAudioMerge) {
      if (!/^https?:\/\/(?:[^/]*\.)?youtube\.com\//i.test(pageUrl)) {
        sendResponse({ok: false, error: 'Open the video on YouTube, then choose a format.'});
        return true;
      }
    }

    if (!url || !/^https?:\/\//i.test(url)) {
      sendResponse({ok: false, error: 'Only direct HTTP and HTTPS links are supported.'});
      return true;
    }
    if (!needsAudioMerge && (/\.mpd(?:[?#]|$)/i.test(url) || /\.m3u8(?:[?#]|$)/i.test(url) || /\.mpd/i.test(item.mime || ''))) {
      sendResponse({ok: false, error: 'DASH/HLS manifests are unsupported in Alternate mode. Use Default.'});
      return true;
    }
    if (!needsAudioMerge && /\.(m4s|ts|aac)(?:[?#]|$)/i.test(url)) {
      sendResponse({ok: false, error: 'Media fragments are unsupported in Alternate mode.'});
      return true;
    }

    const referer = item.referer || (sender.tab ? sender.tab.url : '') || url;

    (async () => {
      try {
        let finalUrl = url;
        let audioUrl = "";
        let sabrPayload = null;
        if (needsAudioMerge) {
          // If the item already carries direct stream URLs (e.g. googlevideo.com),
          // use them directly — instant, no yt-dlp re-resolution needed.
          // item.streamUrl is the direct video stream URL; item.url may be the
          // YouTube page URL which would trigger a slow yt-dlp re-resolution.
          const directStreamUrl = item.streamUrl || url;
          const isDirectStreamUrl = directStreamUrl && directStreamUrl.startsWith('http') && !/youtube\.com\/(watch|embed|v|live|shorts)\b/i.test(directStreamUrl);
          if (isDirectStreamUrl && item.audioUrl) {
            finalUrl = directStreamUrl;
            audioUrl = item.audioUrl || '';
          } else if (isDirectStreamUrl && item.sabrSelection) {
            // SABR adaptive tier. If the player's own ABR session was captured and the
            // desktop can stream it (Deno + googlevideo), relay the session — instant,
            // no yt-dlp at all. Otherwise cache the yt-dlp resolution per
            // (page, videoItag, audioItag) so repeat clicks on the same quality are instant.
            const selection = item.sabrSelection || {};
            const capture = globalThis.bdmYouTubeDirect?.getCapture(tabId);
            const player = youtubePlayers.get(tabId);
            const hasVideoPick = selection.videoItag !== undefined && selection.videoItag !== null && selection.videoItag !== '';
            // Audio-only (MP3) picks stay on the yt-dlp path: the SABR helper writes MP4
            // audio and the v1 relay performs no audio transcoding.
            if (hasVideoPick && capture && cachedSabrCapability && player?.videoId) {
              sabrPayload = globalThis.bdmYouTube?.sabrSession(player, capture, selection) || null;
            }
            if (sabrPayload) {
              finalUrl = sabrPayload.serverAbrStreamingUrl;
            } else {
              const resolved = await resolveSabrWithCache(pageUrl, selection);
              if (!resolved || !resolved.videoUrl) {
                sendResponse({ok: false, error: 'Failed to resolve YouTube video+audio tracks. Try Default mode.'});
                return true;
              }
              finalUrl = resolved.videoUrl;
              audioUrl = resolved.audioUrl || '';
            }
          } else {
            // Fall back to yt-dlp resolution (slow path) when direct URLs are unavailable.
            const selection = item.sabrSelection || {};
            const resolved = await resolveDirectStreamUrl(
              pageUrl,
              '',
              navigator.userAgent,
              pageUrl,
              selection
            );
            if (!resolved || !resolved.videoUrl) {
              sendResponse({ok: false, error: 'Failed to resolve YouTube video+audio tracks. Try Default mode.'});
              return true;
            }
            finalUrl = resolved.videoUrl;
            audioUrl = resolved.audioUrl || '';
          }
        }
        const success = await sendToBengalDM({
          url: finalUrl,
          userAgent: navigator.userAgent,
          cookies: '',
          referrer: referer,
          title: item.title || '',
          filename: item.filename || (item.title || 'video') + (item.outputFormat ? '.' + item.outputFormat : '.mp4'),
          quality: item.quality || '',
          isMedia: true,
          method: 'direct',
          pageExtract: needsAudioMerge,
          sizeBytes: Number(item.sizeBytes || item.size_bytes || (sabrPayload && sabrPayload.sizeBytes) || 0) || 0,
          sizeStr: item.sizeStr || item.size_str || item.size || '',
          ext: item.outputFormat || item.ext || '',
          audioUrl: audioUrl,
          sabr: sabrPayload || undefined
        });
        sendResponse({ok: success, resolvedUrl: finalUrl});
      } catch (e) {
        sendResponse({ok: false, error: e.message || 'Download failed'});
      }
    })();
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

