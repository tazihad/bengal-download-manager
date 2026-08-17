// --- CONSTANTS & HELPERS ---
const DEFAULT_IGNORED_EXTS = [
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
  'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
  'woff', 'woff2', 'eot', 'ttf', 'otf'
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
async function getFilterRules() {
  return new Promise((resolve) => {
    chrome.storage.local.get({
      whitelistUrls: [],
      whitelistExts: [],
      blacklistUrls: [],
      blacklistExts: []
    }, resolve);
  });
}

function matchesUrlOrDomain(url, urlPatterns) {
  if (!url || !Array.isArray(urlPatterns) || urlPatterns.length === 0) return false;
  const urlLower = url.toLowerCase();
  for (const pattern of urlPatterns) {
    const p = pattern.trim().toLowerCase();
    if (!p) continue;
    if (urlLower.includes(p)) return true;
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

async function shouldInterceptDownload(url, filename) {
  if (!url || isIgnoredServiceUrl(url)) return false;

  const ext = getFileExtension(filename || url);
  const rules = await getFilterRules();

  // 1. Blacklist check - if matched, do NOT intercept (leave to browser)
  if (matchesUrlOrDomain(url, rules.blacklistUrls) || matchesExtension(ext || filename, rules.blacklistExts)) {
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
  if (matchesUrlOrDomain(url, rules.whitelistUrls)) {
    return true;
  }

  return true;
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

    // 1. Check for Meta Refresh tag (e.g. VideoLAN mirror redirect)
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

// --- CHECK BENGAL DM APP CONNECTION ---
async function isBengalDMOnline() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);
    const response = await fetch("http://127.0.0.1:9000/", {
      method: 'GET',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const response = await fetch("http://localhost:9000/", {
        method: 'GET',
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      return response.ok;
    } catch {
      return false;
    }
  }
}

// --- SEND DOWNLOAD TO BENGAL DM ---
async function sendToBengalDM(downloadData) {
  const { url, userAgent, cookies, filename, referrer } = downloadData;

  const isOnline = await isBengalDMOnline();
  if (!isOnline) {
    console.warn("Bengal DM application is not running on port 9000.");
    return false;
  }

  const payload = {
    url: url,
    userAgent: userAgent || navigator.userAgent,
    cookies: cookies || "",
    filename: filename || "",
    referrer: referrer || ""
  };

  try {
    const response = await fetch("http://127.0.0.1:9000/", {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    return response.ok;
  } catch (err) {
    try {
      const response = await fetch("http://localhost:9000/", {
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

// --- HTTP REQUEST & RESPONSE MONITORING SYSTEM (IDM Integration Module Style) ---
if (chrome.webRequest && chrome.webRequest.onHeadersReceived) {
  const setupListener = (extraSpec) => {
    chrome.webRequest.onHeadersReceived.addListener(
      (details) => {
        if (!details || !details.url || details.url.startsWith("http://127.0.0.1") || details.url.startsWith("http://localhost") || isIgnoredServiceUrl(details.url)) {
          return;
        }

        const headers = details.responseHeaders || [];
        let filenameFromHeader = "";
        let hasContentDispositionAttachment = false;
        let isBinaryContentType = false;

        for (const h of headers) {
          const name = (h.name || '').toLowerCase();
          const value = (h.value || '').toLowerCase();

          if (name === 'content-disposition' && (value.includes('attachment') || value.includes('filename='))) {
            hasContentDispositionAttachment = true;
            const match = h.value.match(/filename=["']?([^"';]+)["']?/i);
            if (match) filenameFromHeader = match[1];
          }

          if (name === 'content-type') {
            if (value.includes('application/x-msdownload') || 
                value.includes('application/x-7z-compressed') || 
                value.includes('application/x-rar-compressed') || 
                value.includes('application/zip') || 
                value.includes('application/octet-stream') ||
                value.includes('application/x-iso9660-image')) {
              isBinaryContentType = true;
            }
          }
        }

        const ext = getFileExtension(filenameFromHeader || details.url);

        (async () => {
          const rules = await getFilterRules();

          // 1. Blacklist check - never intercept
          if (matchesUrlOrDomain(details.url, rules.blacklistUrls) || matchesExtension(ext || filenameFromHeader, rules.blacklistExts)) {
            return;
          }

          // 2. Default ignored web extensions (manifest.json, html, js, css, web images) MUST NOT be intercepted unless specifically whitelisted
          const isExplicitWhitelistedExt = matchesExtension(ext || filenameFromHeader, rules.whitelistExts);
          if (ext && DEFAULT_IGNORED_EXTS.includes(ext) && !isExplicitWhitelistedExt) {
            return;
          }

          const isDownloadExt = ext && RECOGNIZED_DOWNLOAD_EXTS.includes(ext);
          const isGoogleDriveExport = details.url.includes("export=download") || details.url.includes("uc-download-link");

          // Only intercept if there is a real download intent
          if (hasContentDispositionAttachment || isBinaryContentType || isDownloadExt || isExplicitWhitelistedExt || isGoogleDriveExport) {
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
              referrer: details.initiator || details.documentUrl || ""
            });
          }
        })();

        if (extraSpec.includes("blocking")) {
          // If blocking is supported, we check synchronicity if available
        }
      },
      { urls: ["<all_urls>"], types: ["main_frame", "sub_frame", "other"] },
      extraSpec
    );
  };

  const manifest = (chrome.runtime && chrome.runtime.getManifest) ? chrome.runtime.getManifest() : {};
  const hasBlocking = manifest.permissions && Array.isArray(manifest.permissions) && manifest.permissions.includes('webRequestBlocking');
  const extraSpec = hasBlocking ? ["responseHeaders", "blocking"] : ["responseHeaders"];

  setupListener(extraSpec);
}

// --- BROWSER DOWNLOAD CANCELLER & TAKEOVER (Guarantees zero browser downloads when Bengal DM is running) ---
if (chrome.downloads && chrome.downloads.onCreated) {
  chrome.downloads.onCreated.addListener(async (downloadItem) => {
    if (!downloadItem || !downloadItem.url || isIgnoredServiceUrl(downloadItem.url)) return;

    // Check Whitelist & Blacklist rules
    const shouldIntercept = await shouldInterceptDownload(downloadItem.url, downloadItem.filename);
    if (!shouldIntercept) {
      return; // Leave download to native browser
    }

    // 1. Verify if Bengal DM application is online
    const isOnline = await isBengalDMOnline();
    if (!isOnline) {
      return;
    }

    // 2. Bengal DM is active: cancel and erase browser native download immediately on 0th byte
    try {
      chrome.downloads.cancel(downloadItem.id, () => {
        try { chrome.downloads.erase({ id: downloadItem.id }); } catch (e) {}
      });
      setTimeout(() => {
        try {
          chrome.downloads.cancel(downloadItem.id, () => {
            try { chrome.downloads.erase({ id: downloadItem.id }); } catch (e) {}
          });
        } catch (e) {}
      }, 50);
    } catch (e) {
      try { chrome.downloads.erase({ id: downloadItem.id }); } catch (err) {}
    }

    // 3. Deduplicate if already processed by content script or webRequest
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
      referrer: downloadItem.referrer || ""
    });
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
        markRecentlySent(targetUrl);
        const success = await sendToBengalDM({
          url: targetUrl,
          userAgent: navigator.userAgent,
          cookies: cookieString,
          referrer: (tab && tab.url) ? tab.url : targetUrl
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

      if (isMediaUrl(request.url)) {
        markRecentlySent(request.url);
        const success = await sendToBengalDM({
          url: request.url,
          userAgent: navigator.userAgent,
          cookies: cookieString,
          referrer: request.url
        });
        sendResponse({ success, resolvedUrl: request.url });
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
        referrer: request.url
      });
      sendResponse({ success, resolvedUrl: resolved.url });
    })();
    return true;
  }

  if (request.action === "check_status") {
    (async () => {
      const isOnline = await isBengalDMOnline();
      let blacklisted = false;
      let whitelistedUrl = false;
      let whitelistedExt = false;

      if (request.url) {
        const ext = getFileExtension(request.url);
        const rules = await getFilterRules();
        blacklisted = matchesUrlOrDomain(request.url, rules.blacklistUrls) || matchesExtension(ext, rules.blacklistExts);
        whitelistedUrl = matchesUrlOrDomain(request.url, rules.whitelistUrls);
        whitelistedExt = matchesExtension(ext, rules.whitelistExts);
      }

      sendResponse({ online: isOnline, blacklisted, whitelistedUrl, whitelistedExt });
    })();
    return true;
  }
});
