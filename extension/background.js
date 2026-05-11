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

  if (contentDisposition.includes('attachment')) {
    isDownload = true;
  } else if (contentType.includes('application/octet-stream') || 
             contentType.includes('application/x-msdos-program') ||
             contentType.includes('application/zip') ||
             contentType.includes('application/x-7z-compressed')) {
    isDownload = true;
  }

  if (isDownload) {
    // Blocking check for sync is not possible here, so we always pass to background tasks
    // background task will verify sync before actually sending to DM
    return; 
  }
}, { urls: ["<all_urls>"], types: ["main_frame", "sub_frame"] }, ["blocking", "responseHeaders"]);

// --- HELPER: Send URL to Python App ---
async function sendToBengalDM(targetUrl) {
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
      body: originalUrl
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
      await sendToBengalDM(targetUrl);
    }
  }
});

// --- FEATURE 2: Smart Download Interceptor ---
chrome.downloads.onCreated.addListener(async (downloadItem) => {
    if (!downloadItem.url.startsWith("http")) return;

    const isImageMime = downloadItem.mime && downloadItem.mime.startsWith("image/");
    const isImageExt = downloadItem.url.match(/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico|avif)(\?.*)?$/i);
    if (isImageMime || isImageExt) return;

    const online = await isAria2Online();
    if (!online) return;

    queueMicrotask(() => {
        chrome.downloads.cancel(downloadItem.id);
        chrome.downloads.erase({ id: downloadItem.id });
    });

    sendToBengalDM(downloadItem.url);
});

// --- FEATURE 3: Silent Click Interceptor ---
chrome.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  if (request.action === "silent_download") {
    await sendToBengalDM(request.url);
  }
});
