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
  const url = `http://localhost:${items.port}/jsonrpc`;
  const params = items.token ? [`token:${items.token}`] : [];
  const payload = { jsonrpc: "2.0", id: "bg-check", method: "aria2.getVersion", params: params };

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    return !!(data.result && data.result.version);
  } catch (e) {
    return false;
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
             contentType.includes('application/x-7z-compressed') ||
             contentType.includes('application/x-rar-compressed') ||
             contentType.includes('application/x-apple-diskimage') ||
             contentType.includes('application/x-debian-package')) {
    isDownload = true;
  }

  if (isDownload) {
    // Only intercept if Aria2 is actually online on the configured port
    // We use a sync-like check here (Async doesn't work in blocking listeners directly)
    // But since onHeadersReceived blocking doesn't support async, we rely on the Downloads API fallback 
    // for out-of-sync cases, OR we just let it go.
    // However, if we CAN'T verify, we better let the browser handle it than potentially lose the download.
    return; 
  }
}, { urls: ["<all_urls>"], types: ["main_frame", "sub_frame"] }, ["blocking", "responseHeaders"]);

// --- HELPER: Send URL to Python App ---
async function sendToBengalDM(targetUrl) {
  // STRICT SYNC CHECK: Verify Aria2 is online before sending
  const online = await isAria2Online();
  if (!online) {
    console.error("Aria2 port mismatch or offline. Aborting takeover.");
    return false;
  }

  const originalUrl = urlMap.get(targetUrl) || targetUrl;
  try {
    const response = await fetch("http://127.0.0.1:9000/", {
      method: 'POST',
      body: originalUrl
    });
    return response.ok;
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

    // Verify SYNC before hijacking
    const online = await isAria2Online();
    if (!online) {
        console.warn("Aria2 out of sync. Allowing browser to handle download.");
        return;
    }

    // Hijack
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
