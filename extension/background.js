// --- HELPER: Send URL to aria2 ---
function sendToAria2(targetUrl) {
  chrome.storage.local.get({ host: "localhost", port: 50001, token: "" }, (items) => {
    const url = `http://${items.host}:${items.port}/jsonrpc`;

    // Build the params array dynamically
    const rpcParams = [];
    if (items.token) {
      rpcParams.push(`token:${items.token}`);
    }
    rpcParams.push([targetUrl]);

    const payload = {
      jsonrpc: "2.0",
      id: "bengal-dm-add",
      method: "aria2.addUri",
      params: rpcParams
    };

    fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
      .then(response => {
        if (!response.ok) throw new Error("Network response was not ok");
        console.log("Sent to Bengal DM successfully:", targetUrl);
      })
      .catch(err => console.error("Bengal DM Connection failed:", err));
  });
}

// --- FEATURE 1: Right-Click Context Menu ---
// Create the menu item when the extension is installed/reloaded
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "download-with-bengal",
    title: "Download with Bengal DM",
    contexts: ["link", "image", "video", "audio", "selection"]
  });
});

// Listen for clicks on the context menu
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "download-with-bengal") {
    // Grab the URL from wherever they right-clicked (a link, media, or highlighted text)
    const targetUrl = info.linkUrl || info.srcUrl || info.selectionText || info.pageUrl;

    if (targetUrl && targetUrl.startsWith("http")) {
      sendToAria2(targetUrl);
    }
  }
});

// --- FEATURE 2: Smart Download Interceptor ---
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!downloadItem.url.startsWith("http")) return;

  // 1. Check if it's an image (MIME type or URL extension)
  const isImageMime = downloadItem.mime && downloadItem.mime.startsWith("image/");
  const isImageExt = downloadItem.url.match(/\.(jpg|jpeg|png|gif|webp|svg|bmp|ico|avif)(\?.*)?$/i);

  // 2. If it's an image, do nothing and let Firefox download it natively
  if (isImageMime || isImageExt) {
    console.log("Image detected. Letting Firefox handle it:", downloadItem.url);
    return;
  }

  // 3. If it's NOT an image, cancel Firefox download and send to aria2
  chrome.downloads.cancel(downloadItem.id, () => {
    sendToAria2(downloadItem.url);
  });
});