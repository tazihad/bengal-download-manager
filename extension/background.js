// --- CONSTANTS & HELPERS ---
const DEFAULT_IGNORED_EXTS = [
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
  'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
  'woff', 'woff2', 'eot', 'ttf', 'otf'
];

function getFileExtension(urlOrFilename) {
  if (!urlOrFilename) return "";
  const clean = urlOrFilename.split('?')[0].split('#')[0];
  const parts = clean.split('.');
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
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
  if (chrome.notifications) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'assets/icon-48.png',
      title: title,
      message: message
    });
  }
}

// --- DOWNLOAD INTERCEPTOR (MV3 downloads API) ---
chrome.downloads.onCreated.addListener(async (item) => {
  if (!item || !item.url || item.url.startsWith("blob:") || item.url.startsWith("data:")) {
    return;
  }

  // Check user preference for automatic interception
  const prefs = await chrome.storage.local.get({ enableInterception: true });
  if (!prefs.enableInterception) return;

  const urlExt = getFileExtension(item.url);
  const fileExt = getFileExtension(item.filename);
  const ext = fileExt || urlExt;

  if (ext && DEFAULT_IGNORED_EXTS.includes(ext)) {
    return; // Don't intercept web assets/pages
  }

  // Check if Bengal DM backend is active
  const isOnline = await isBengalDMOnline();
  if (!isOnline) return;

  // Intercept the download
  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
  } catch (e) {
    console.warn("Could not cancel Chrome download:", e);
  }

  // Retrieve cookies for authorization
  let cookieString = "";
  try {
    const cookies = await chrome.cookies.getAll({ url: item.url });
    cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
  } catch (e) {
    console.warn("Could not retrieve cookies:", e);
  }

  const success = await sendToBengalDM({
    url: item.url,
    userAgent: navigator.userAgent,
    cookies: cookieString,
    filename: item.filename,
    referrer: item.referrer
  });

  if (success) {
    notifyUser("Bengal DM Intercepted", `Sent download to Bengal DM:\n${item.filename || item.url}`);
  }
});

// --- INITIALIZATION & CONTEXT MENUS ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(['port', 'enableInterception'], (items) => {
    if (!items.port || items.port === 6800 || items.port === 50001 || items.port === 6801) {
      chrome.storage.local.set({ port: 56800 });
    }
    if (items.enableInterception === undefined) {
      chrome.storage.local.set({ enableInterception: true });
    }
  });

  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "download-with-bengal",
      title: "Download with Bengal DM",
      contexts: ["link", "image", "video", "audio", "selection"]
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "download-with-bengal") {
    const targetUrl = info.linkUrl || info.srcUrl || info.selectionText || info.pageUrl;
    if (targetUrl && (targetUrl.startsWith("http://") || targetUrl.startsWith("https://"))) {
      let cookieString = "";
      try {
        const cookies = await chrome.cookies.getAll({ url: targetUrl });
        cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
      } catch (e) {
        console.warn("Could not get cookies:", e);
      }

      const success = await sendToBengalDM({
        url: targetUrl,
        userAgent: navigator.userAgent,
        cookies: cookieString
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
      let cookieString = "";
      try {
        const cookies = await chrome.cookies.getAll({ url: request.url });
        cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
      } catch (e) {}

      const success = await sendToBengalDM({
        url: request.url,
        userAgent: navigator.userAgent,
        cookies: cookieString
      });
      sendResponse({ success });
    })();
    return true;
  }

  if (request.action === "check_status") {
    (async () => {
      const isOnline = await isBengalDMOnline();
      sendResponse({ online: isOnline });
    })();
    return true;
  }
});

