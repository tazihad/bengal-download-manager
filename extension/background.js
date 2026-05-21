// --- EXTENSION HELPERS ---
const ignoredExts = [
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
  'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
  'woff', 'woff2', 'eot', 'ttf', 'otf'
];

function getExtension(str) {
  if (!str) return "";
  const parts = str.split('?')[0].split('#')[0].split('.');
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

// --- REDIRECT TRACKING ---
const urlMap = new Map();

chrome.webRequest.onBeforeRedirect.addListener((details) => {
  const original = urlMap.get(details.url) || details.url;
  urlMap.set(details.redirectUrl, original);
  setTimeout(() => urlMap.delete(details.redirectUrl), 60000);
}, { urls: ["<all_urls>"] });

// --- CONNECTION VERIFICATION ---
async function isAria2Online() {
  const items = await chrome.storage.local.get({ port: 56800, token: "" });
  const url = `http://127.0.0.1:${items.port}/jsonrpc`;
  const params = items.token ? [`token:${items.token}`] : [];
  const payload = { jsonrpc: "2.0", id: "bg-check", method: "aria2.getVersion", params: params };

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
      cache: 'no-store'
    });
    
    clearTimeout(timeoutId);
    const data = await response.json();
    return !!(data.result && data.result.version);
  } catch (e) {
    // If 127.0.0.1 fails, try localhost as fallback
    try {
        const response = await fetch(`http://localhost:${items.port}/jsonrpc`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        return !!(data.result && data.result.version);
    } catch {
        return false;
    }
  }
}

// --- DEEP INTERCEPTION ---
chrome.webRequest.onHeadersReceived.addListener((details) => {
  if (details.method !== "GET") return;

  const headers = details.responseHeaders;
  let isDownload = false;
  let contentType = "";
  let contentDisposition = "";

  for (const header of headers) {
    const name = header.name.toLowerCase();
    if (name === 'content-type') contentType = header.value || "";
    if (name === 'content-disposition') contentDisposition = header.value || "";
  }

  contentDisposition = contentDisposition.toLowerCase();
  contentType = contentType.toLowerCase();

  const lowerUrl = details.url.toLowerCase();
  const urlExt = getExtension(lowerUrl);
  const isIgnoredExt = urlExt && ignoredExts.includes(urlExt);

  // 1. If explicit attachment, always download (unless it's an ignored extension)
  if (contentDisposition.includes('attachment')) {
    let cdFilename = "";
    const cdMatch = contentDisposition.match(/filename\*?=["']?(?:UTF-8'')?([^"';]+)["']?/i);
    if (cdMatch && cdMatch[1]) {
        cdFilename = decodeURIComponent(cdMatch[1]);
    }
    
    if (cdFilename) {
        const cdExt = getExtension(cdFilename);
        if (cdExt && !ignoredExts.includes(cdExt)) {
            isDownload = true;
        } else if (!cdExt) {
            // No extension in filename, trust it's a download if it's an attachment
            isDownload = true;
        }
    } else {
        // Attachment with no filename info, trust it
        isDownload = true;
    }
  } 
  
  // 2. If not already flagged, check if it has a target extension (non-ignored)
  if (!isDownload && urlExt && !isIgnoredExt) {
    // Basic safety: don't intercept image/html types unless they were explicit attachments
    if (!contentType.includes('text/html') && !contentType.includes('image/')) {
        isDownload = true;
    }
  }

  if (isDownload) {
    // Asynchronously send to Bengal DM so we don't block the sync return
    chrome.cookies.getAll({ url: details.url }, (cookies) => {
      const cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
      sendToBengalDM(details.url, cookieString);
    });
    
    // CRITICAL: Immediately cancel the browser's request
    // If it's a main frame navigation that was just opened, we'll try to close the tab.
    if (details.type === "main_frame") {
        setTimeout(() => {
            chrome.tabs.get(details.tabId, (tab) => {
                if (chrome.runtime.lastError || !tab) return;
                // Only close if it's a "clean" tab (no title or just the URL)
                // or if it was opened specifically for this download.
                if (!tab.url || tab.url === details.url || tab.url === 'about:blank') {
                    chrome.tabs.remove(details.tabId);
                }
            });
        }, 500);
    }

    return { cancel: true };
  }
}, { urls: ["<all_urls>"], types: ["main_frame", "sub_frame"] }, ["blocking", "responseHeaders"]);

// --- HELPER: Send URL to Python App ---
async function sendToBengalDM(targetUrl, cookies = "") {
  // Try port 9000 check first
  try {
    const response = await fetch("http://127.0.0.1:9000/", { method: 'GET' });
    if (!response.ok) return false;
  } catch {
    // Try localhost if 127.0.0.1 fails
    try {
        await fetch("http://localhost:9000/", { method: 'GET' });
    } catch {
        return false;
    }
  }

  // Then verify Aria2 Sync
  const online = await isAria2Online();
  if (!online) {
    console.warn("Aria2 out of sync or unreachable via 127.0.0.1/localhost");
    return false;
  }

  const originalUrl = urlMap.get(targetUrl) || targetUrl;
  try {
    await fetch("http://127.0.0.1:9000/", {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: originalUrl,
        userAgent: navigator.userAgent,
        cookies: cookies
      })
    });
    return true;
  } catch (err) {
    return false;
  }
}

// --- PORT MIGRATION & INITIALIZATION ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(['port'], (items) => {
    if (!items.port || items.port === 6800 || items.port === 50001 || items.port === 6801) {
      chrome.storage.local.set({ port: 56800 });
    }
  });

  chrome.contextMenus.create({
    id: "download-with-bengal",
    title: "Download with Bengal DM",
    contexts: ["link", "image", "video", "audio", "selection"]
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "download-with-bengal") {
    const targetUrl = info.linkUrl || info.srcUrl || info.selectionText || info.pageUrl;
    if (targetUrl && targetUrl.startsWith("http")) {
      const cookies = await chrome.cookies.getAll({ url: targetUrl });
      const cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
      await sendToBengalDM(targetUrl, cookieString);
    }
  }
});

// --- MESSAGE INTERCEPTOR ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "silent_download" || request.action === "check_link_preflight") {
    // We let the onHeadersReceived listener do the heavy lifting for navigation links.
    // For manual triggers or pre-flight check, we just tell content.js to go ahead
    // and the deep network interceptor will catch it if it's a real file.
    if (request.action === "check_link_preflight") {
        sendResponse({ handledByBengal: false });
    }
    return true; 
  }
});
