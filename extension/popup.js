function applyTheme(theme) {
  const currentTheme = theme || 'system';
  if (currentTheme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme-setting', 'system');
  } else {
    document.documentElement.setAttribute('data-theme', currentTheme);
    document.documentElement.setAttribute('data-theme-setting', currentTheme);
  }
}

function formatAppVersion(ver) {
  if (!ver) return "";
  let clean = String(ver).trim();
  if (!clean.startsWith('v') && !clean.startsWith('V')) {
    clean = 'v' + clean;
  }
  return clean;
}

// Initial theme check
chrome.storage.local.get({ theme: 'system' }, (items) => {
  applyTheme(items.theme || 'system');
});

// System theme listener
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  chrome.storage.local.get({ theme: 'system' }, (items) => {
    if (items.theme === 'system') {
      applyTheme('system');
    }
  });
});

// Live options link
document.addEventListener('DOMContentLoaded', () => {
  const optLink = document.getElementById('options-link');
  if (optLink) {
    optLink.addEventListener('click', (e) => {
      e.preventDefault();
      chrome.runtime.openOptionsPage();
    });
  }
});

async function checkAria2(port, token) {
  const url = `http://127.0.0.1:${port}/jsonrpc`;
  const params = token ? [`token:${token}`] : [];
  const payload = { jsonrpc: "2.0", id: "popup-check", method: "aria2.getVersion", params: params };

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
    let response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    } catch {
      response = await fetch(`http://localhost:${port}/jsonrpc`, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    }
    clearTimeout(timeoutId);
    const data = await response.json();
    return !!(data.result && data.result.version);
  } catch (e) {
    return false;
  }
}

function extractHostname(url) {
  if (!url || typeof url !== 'string') return "";
  if (!url.startsWith('http://') && !url.startsWith('https://')) return "";
  try {
    const parsed = new URL(url);
    return parsed.hostname.toLowerCase();
  } catch (e) {
    return "";
  }
}

let currentDomain = "";

function updateGlobalToggleUI(enabled) {
  const toggle = document.getElementById('toggle-global-interception');
  const subtitle = document.getElementById('global-subtitle');
  if (toggle) toggle.checked = enabled;
  if (subtitle) {
    subtitle.textContent = enabled 
      ? "Automatically intercept browser downloads" 
      : "Interception paused for all websites";
  }
}

function updateSiteToggleUI(domain, isBlacklisted, hasValidSite) {
  const toggle = document.getElementById('toggle-site-interception');
  const subtitle = document.getElementById('site-subtitle');
  const row = document.getElementById('site-toggle-row');

  if (!hasValidSite || !domain) {
    if (toggle) {
      toggle.checked = false;
      toggle.disabled = true;
    }
    if (subtitle) subtitle.textContent = "No active website";
    if (row) row.classList.add('disabled');
    return;
  }

  if (row) row.classList.remove('disabled');
  if (toggle) {
    toggle.disabled = false;
    toggle.checked = !isBlacklisted;
  }
  if (subtitle) {
    subtitle.textContent = isBlacklisted 
      ? `Bypassed on ${domain} (Browser handles downloads)` 
      : `Active on ${domain}`;
  }
}

// Live storage sync
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local') {
    if (changes.theme) {
      applyTheme(changes.theme.newValue);
    }
    if (changes.enableInterception !== undefined) {
      updateGlobalToggleUI(changes.enableInterception.newValue);
    }
    if (changes.blacklistUrls && currentDomain) {
      const bList = Array.isArray(changes.blacklistUrls.newValue) ? changes.blacklistUrls.newValue : [];
      const isBlacklisted = bList.some(p => {
        const clean = p.toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '').trim();
        return clean === currentDomain || currentDomain.endsWith('.' + clean);
      });
      updateSiteToggleUI(currentDomain, isBlacklisted, true);
    }
  }
});

// Setup Toggle Listeners
document.getElementById('toggle-global-interception').addEventListener('change', (e) => {
  const enabled = e.target.checked;
  chrome.storage.local.set({ enableInterception: enabled }, () => {
    updateGlobalToggleUI(enabled);
  });
});

document.getElementById('toggle-site-interception').addEventListener('change', (e) => {
  const catchOnSite = e.target.checked;
  if (!currentDomain) return;

  chrome.storage.local.get({ blacklistUrls: [] }, (items) => {
    let list = Array.isArray(items.blacklistUrls) ? [...items.blacklistUrls] : [];

    if (!catchOnSite) {
      // Add domain to blacklist if not already present
      const alreadyIn = list.some(p => {
        const clean = p.toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '').trim();
        return clean === currentDomain;
      });
      if (!alreadyIn) {
        list.push(currentDomain);
      }
    } else {
      // Remove domain and its variations from blacklist
      list = list.filter(p => {
        const clean = p.toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '').trim();
        return clean !== currentDomain && !currentDomain.endsWith('.' + clean);
      });
    }

    chrome.storage.local.set({ blacklistUrls: list }, () => {
      updateSiteToggleUI(currentDomain, !catchOnSite, true);
    });
  });
});

chrome.storage.local.get({
  theme: "system",
  port: 56800,
  token: "",
  bdmVersion: "",
  enableInterception: true,
  blacklistUrls: []
}, async (items) => {
  applyTheme(items.theme || "system");
  updateGlobalToggleUI(items.enableInterception !== false);

  // Detect active tab domain
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs && tabs.length > 0 && tabs[0].url) {
      const domain = extractHostname(tabs[0].url);
      if (domain) {
        currentDomain = domain;
        const bList = Array.isArray(items.blacklistUrls) ? items.blacklistUrls : [];
        const isBlacklisted = bList.some(p => {
          const clean = p.toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '').trim();
          return clean === domain || domain.endsWith('.' + clean);
        });
        updateSiteToggleUI(domain, isBlacklisted, true);
      } else {
        updateSiteToggleUI("", false, false);
      }
    } else {
      updateSiteToggleUI("", false, false);
    }
  } catch (e) {
    updateSiteToggleUI("", false, false);
  }

  const statusText = document.getElementById('status-text');
  const dot = document.getElementById('dot');

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);

    // 1. Ping the Python app on port 9000
    let bdmData = null;
    try {
      const response = await fetch("http://127.0.0.1:9000/", {
        method: 'GET',
        signal: controller.signal
      });
      if (response.ok) {
        bdmData = await response.json();
      }
    } catch {
      try {
        const response = await fetch("http://localhost:9000/", {
          method: 'GET',
          signal: controller.signal
        });
        if (response.ok) {
          bdmData = await response.json();
        }
      } catch {}
    }

    clearTimeout(timeoutId);

    if (bdmData) {
      // 2. Ping Aria2 to ensure sync
      const ariaOnline = await checkAria2(items.port, items.token);
      if (ariaOnline) {
        dot.className = "dot online";
        let ver = bdmData.version || items.bdmVersion;
        if (bdmData.version) {
          chrome.storage.local.set({ bdmVersion: bdmData.version });
        }
        const formatted = formatAppVersion(ver);
        statusText.textContent = formatted ? `Bengal DM Running (${formatted})` : "Bengal DM Running";
      } else {
        dot.className = "dot offline";
        statusText.textContent = items.token ? "Auth Error / Out of Sync" : "Ports Out of Sync";
      }
    } else {
      throw new Error("Invalid Response");
    }
  } catch (error) {
    dot.className = "dot offline";
    statusText.textContent = "App Not Running";
  }
});
