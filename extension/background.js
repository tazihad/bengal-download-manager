// --- REDIRECT TRACKING ---
// Maps final/redirected URLs to their original requested URLs
const urlMap = new Map();

chrome.webRequest.onBeforeRedirect.addListener((details) => {
  // If we see a redirect, store the map: redirectUrl -> originalUrl
  const original = urlMap.get(details.url) || details.url;
  urlMap.set(details.redirectUrl, original);
  
  // Cleanup old entries after 1 minute
  setTimeout(() => urlMap.delete(details.redirectUrl), 60000);
}, { urls: ["<all_urls>"] });

// --- DEEP INTERCEPTION: Catch downloads before they reach the manager ---
// This prevents the "Cancelled" entry by stopping the request at the header stage
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

  // 1. Check if it's explicitly an attachment
  if (contentDisposition.includes('attachment')) {
    isDownload = true;
  } 
  // 2. Check for binary/installer mime types
  else if (contentType.includes('application/octet-stream') || 
           contentType.includes('application/x-msdos-program') ||
           contentType.includes('application/zip') ||
           contentType.includes('application/x-7z-compressed') ||
           contentType.includes('application/x-rar-compressed') ||
           contentType.includes('application/x-apple-diskimage') ||
           contentType.includes('application/x-debian-package')) {
    isDownload = true;
  }

  if (isDownload) {
    console.log("Deep Intercepted Download:", details.url);
    sendToBengalDM(details.url);
    return { cancel: true };
  }
}, { urls: ["<all_urls>"], types: ["main_frame", "sub_frame"] }, ["blocking", "responseHeaders"]);

// --- HELPER: Send URL to Python App ---
function sendToBengalDM(targetUrl) {
  const originalUrl = urlMap.get(targetUrl) || targetUrl;

  fetch("http://127.0.0.1:9000/", {
    method: 'POST',
    body: originalUrl
  })
    .then(response => {
      if (!response.ok) throw new Error("Network response was not ok");
      console.log("Sent to Bengal DM App successfully:", originalUrl);
    })
    .catch(err => console.error("Bengal DM App Connection failed:", err));
}

// --- FEATURE 1: Right-Click Context Menu ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "download-with-bengal",
    title: "Download with Bengal DM",
    contexts: ["link", "image", "video", "audio", "selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "download-with-bengal") {
    const targetUrl = info.linkUrl || info.srcUrl || info.selectionText || info.pageUrl;
    if (targetUrl && targetUrl.startsWith("http")) {
      sendToBengalDM(targetUrl);
    }
  }
});

// --- FEATURE 2: Smart Download Interceptor (Fallback/Backup) ---
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!downloadItem.url.startsWith("http")) return;

  const isImageMime = downloadItem.mime && downloadItem.mime.startsWith("image/");
  const isImageExt = downloadItem.url.match(/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico|avif)(\?.*)?$/i);
  if (isImageMime || isImageExt) return;

  // TAKE OVER: Cancel and Erase IMMEDIATELY
  queueMicrotask(() => {
    chrome.downloads.cancel(downloadItem.id);
    chrome.downloads.erase({ id: downloadItem.id });
  });

  sendToBengalDM(downloadItem.url);
});

// --- FEATURE 3: Silent Click Interceptor ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "silent_download") {
    console.log("Silent Click Intercepted:", request.url);
    sendToBengalDM(request.url);
  }
});
