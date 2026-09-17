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

function normalizeDomain(host) {
  if (!host || typeof host !== 'string') return "";
  let clean = host.toLowerCase().trim();
  clean = clean.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  if (clean.startsWith('*.')) clean = clean.substring(2);
  else if (clean.startsWith('*')) clean = clean.substring(1);
  if (clean.startsWith('www.')) clean = clean.substring(4);
  if (clean.includes(':')) clean = clean.split(':')[0];
  return clean;
}

function isDomainInList(domain, list) {
  if (!domain || !Array.isArray(list) || list.length === 0) return false;
  const target = normalizeDomain(domain);
  if (!target) return false;
  return list.some(item => {
    const p = normalizeDomain(item);
    if (!p) return false;
    return p === target || target.endsWith('.' + p) || p.endsWith('.' + target);
  });
}

let currentDomain = "";
let isGlobalInterceptionEnabled = true;

function updateGlobalToggleUI(enabled) {
  isGlobalInterceptionEnabled = (enabled !== false);
  const toggle = document.getElementById('toggle-global-interception');
  const subtitle = document.getElementById('global-subtitle');
  if (toggle) toggle.checked = isGlobalInterceptionEnabled;
  if (subtitle) {
    subtitle.textContent = isGlobalInterceptionEnabled 
      ? "Active browser-wide" 
      : "Paused browser-wide";
  }

  if (currentDomain) {
    chrome.storage.local.get({ blacklistUrls: [] }, (items) => {
      const bList = Array.isArray(items.blacklistUrls) ? items.blacklistUrls : [];
      const isBlacklisted = isDomainInList(currentDomain, bList);
      updateSiteToggleUI(currentDomain, !isBlacklisted, true);
    });
  }
}

function updateSiteToggleUI(domain, isCaptured, hasValidSite) {
  const toggle = document.getElementById('toggle-site-interception');
  const domainElem = document.getElementById('site-domain');
  const descElem = document.getElementById('site-desc');
  const row = document.getElementById('site-toggle-row');

  if (!hasValidSite || !domain) {
    if (toggle) {
      toggle.checked = false;
      toggle.disabled = true;
    }
    if (domainElem) domainElem.textContent = "No active website";
    if (descElem) descElem.textContent = "Open a website to configure";
    if (row) row.classList.add('disabled');
    return;
  }

  if (domainElem) {
    domainElem.textContent = domain;
  }

  if (!isGlobalInterceptionEnabled) {
    if (row) row.classList.add('disabled');
    if (toggle) {
      toggle.disabled = true;
      toggle.checked = false;
    }
    if (descElem) {
      descElem.textContent = "Paused (global capture is off)";
    }
    return;
  }

  if (row) row.classList.remove('disabled');
  if (toggle) {
    toggle.disabled = false;
    toggle.checked = !!isCaptured; // Checked = Capture active on this site
  }
  if (descElem) {
    descElem.textContent = isCaptured 
      ? "Enabled (captured by Bengal DM)" 
      : "Disabled (handled by browser)";
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
      const isBlacklisted = isDomainInList(currentDomain, bList);
      updateSiteToggleUI(currentDomain, !isBlacklisted, true);
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

document.getElementById('global-toggle-row').addEventListener('click', (e) => {
  if (e.target.closest('.switch')) return;
  const toggle = document.getElementById('toggle-global-interception');
  if (toggle && !toggle.disabled) {
    toggle.checked = !toggle.checked;
    toggle.dispatchEvent(new Event('change'));
  }
});

document.getElementById('toggle-site-interception').addEventListener('change', (e) => {
  const enableForThisSite = e.target.checked;
  if (!currentDomain) return;

  chrome.storage.local.get({ blacklistUrls: [] }, (items) => {
    let list = Array.isArray(items.blacklistUrls) ? [...items.blacklistUrls] : [];
    const target = normalizeDomain(currentDomain);

    if (enableForThisSite) {
      // Remove domain and its subdomains/apex from blacklist so it IS captured
      list = list.filter(item => {
        const p = normalizeDomain(item);
        if (!p) return false;
        return !(p === target || target.endsWith('.' + p) || p.endsWith('.' + target));
      });
    } else {
      // Add normalized domain to blacklist so it is bypassed
      if (!isDomainInList(currentDomain, list)) {
        list.push(target || currentDomain);
      }
    }

    chrome.storage.local.set({ blacklistUrls: list }, () => {
      updateSiteToggleUI(currentDomain, enableForThisSite, true);
    });
  });
});

document.getElementById('site-toggle-row').addEventListener('click', (e) => {
  if (e.target.closest('.switch')) return;
  const toggle = document.getElementById('toggle-site-interception');
  if (toggle && !toggle.disabled) {
    toggle.checked = !toggle.checked;
    toggle.dispatchEvent(new Event('change'));
  }
});

chrome.storage.local.get({
  theme: "system",
  port: 56800,
  ipcPort: 56900,
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
        const isBlacklisted = isDomainInList(domain, bList);
        updateSiteToggleUI(domain, !isBlacklisted, true);
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
  const primaryIpcPort = items.activeIpcPort || parseInt(items.ipcPort, 10) || 56900;
  const ipcPortsToTry = [primaryIpcPort];
  for (const fp of [26900, 26901, 26902]) {
    if (!ipcPortsToTry.includes(fp)) ipcPortsToTry.push(fp);
  }
  if (!ipcPortsToTry.includes(56900)) ipcPortsToTry.push(56900);

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);

    // 1. Ping the Python app on configured or fallback IPC ports
    let bdmData = null;
    for (const tryPort of ipcPortsToTry) {
      try {
        const response = await fetch(`http://127.0.0.1:${tryPort}/`, {
          method: 'GET',
          signal: controller.signal
        });
        if (response.ok) {
          bdmData = await response.json();
          break;
        }
      } catch {
        // Continue to next port
      }
    }

    clearTimeout(timeoutId);

    if (bdmData) {
      // 2. Ping Aria2 to ensure sync
      const ariaOnline = await checkAria2(items.port, items.token);
      if (ariaOnline) {
        dot.className = "dot online";
        let ver = bdmData.version || items.bdmVersion;
        const storageUpdates = {};
        if (bdmData.version) storageUpdates.bdmVersion = bdmData.version;
        if (bdmData.ipc_port) {
          storageUpdates.ipcPort = bdmData.ipc_port;
          storageUpdates.activeIpcPort = bdmData.ipc_port;
          storageUpdates.isIpcFallback = Boolean(bdmData.is_fallback);
        }
        if (Object.keys(storageUpdates).length > 0) {
          chrome.storage.local.set(storageUpdates);
        }
        const formatted = formatAppVersion(ver);
        const fallbackNotice = bdmData.is_fallback ? ` [Port ${bdmData.ipc_port}]` : "";
        statusText.textContent = formatted ? `Bengal DM Running (${formatted})${fallbackNotice}` : `Bengal DM Running${fallbackNotice}`;
        chrome.runtime.sendMessage({ action: "update_connection_status", online: true }).catch(() => {});
      } else {
        dot.className = "dot offline";
        statusText.textContent = items.token ? "Auth Error / Out of Sync" : "Ports Out of Sync";
        chrome.runtime.sendMessage({ action: "update_connection_status", online: false }).catch(() => {});
      }
    } else {
      throw new Error("Invalid Response");
    }
  } catch (error) {
    dot.className = "dot offline";
    statusText.textContent = "App Not Running";
    chrome.runtime.sendMessage({ action: "update_connection_status", online: false }).catch(() => {});
  }
});
