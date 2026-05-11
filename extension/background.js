// --- HELPER: Send URL to Python App ---
function sendToBengalDM(targetUrl) {
  // Talk to Python App on port 9000
  fetch("http://127.0.0.1:9000/", {
    method: 'POST',
    body: targetUrl
  })
    .then(response => {
      if (!response.ok) throw new Error("Network response was not ok");
      console.log("Sent to Bengal DM App successfully:", targetUrl);
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

// --- FEATURE 2: Smart Download Interceptor ---
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!downloadItem.url.startsWith("http")) return;

  const isImageMime = downloadItem.mime && downloadItem.mime.startsWith("image/");
  const isImageExt = downloadItem.url.match(/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico|avif)(\?.*)?$/i);

  if (isImageMime || isImageExt) {
    return;
  }

  // 3. Cancel Firefox download, ERASE the trace, and send to Bengal DM
  chrome.downloads.cancel(downloadItem.id, () => {

    // MAGIC LINE: Instantly erase the canceled download so it leaves no trace in Firefox
    chrome.downloads.erase({ id: downloadItem.id });

    sendToBengalDM(downloadItem.url);
  });
});

// --- FEATURE 3: Silent Click Interceptor ---
// Listen for hijacked clicks coming from content.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "silent_download") {
    console.log("Silent Click Intercepted:", request.url);
    sendToBengalDM(request.url);
  }
});