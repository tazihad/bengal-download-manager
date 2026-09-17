// --- THEME MANAGEMENT ---
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

  // Sync radio buttons if DOM is ready
  const radios = document.querySelectorAll('input[name="theme-radio"]');
  radios.forEach(radio => {
    radio.checked = (radio.value === currentTheme);
  });

  const themeSelect = document.getElementById('theme');
  if (themeSelect) {
    themeSelect.value = currentTheme;
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

// Initial theme check as early as possible
chrome.storage.local.get({ theme: 'system' }, (items) => {
  applyTheme(items.theme || 'system');
});

// System theme change listener
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  chrome.storage.local.get({ theme: 'system' }, (items) => {
    if (items.theme === 'system') {
      applyTheme('system');
    }
  });
});

// Real-time storage change listener across tabs/popups
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local') {
    if (changes.theme) {
      applyTheme(changes.theme.newValue);
    }
    if (changes.bdmVersion) {
      const formatted = formatAppVersion(changes.bdmVersion.newValue);
      const connTextIpc = document.getElementById('conn-text-ipc');
      const dotIpc = document.getElementById('dot-ipc');
      if (connTextIpc && dotIpc && dotIpc.classList.contains('online') && formatted) {
        connTextIpc.textContent = `IPC: Connected (${formatted})`;
      }
      const aboutAppVer = document.getElementById('about-app-version');
      if (aboutAppVer && formatted) {
        aboutAppVer.textContent = formatted;
      }
    }
  }
});

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'success') {
  const toast = document.getElementById('status-toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `status-toast visible ${type}`;
  setTimeout(() => {
    toast.className = 'status-toast';
  }, 2500);
}

// --- BENGAL DM & ARIA2 CONNECTION TEST ---
async function testConnection(port, token, ipcPort) {
  const connTextRpc = document.getElementById('conn-text-rpc');
  const dotRpc = document.getElementById('dot-rpc');
  const connTextIpc = document.getElementById('conn-text-ipc');
  const dotIpc = document.getElementById('dot-ipc');
  const refreshBtn = document.getElementById('refresh-btn');
  const aboutAppVer = document.getElementById('about-app-version');

  if (!refreshBtn) return;

  const effectiveIpcPort = ipcPort || parseInt(document.getElementById('ipc-port')?.value, 10) || 56900;
  const ipcPortsToTry = [effectiveIpcPort];
  for (const fp of [26900, 26901, 26902]) {
    if (!ipcPortsToTry.includes(fp)) ipcPortsToTry.push(fp);
  }
  if (!ipcPortsToTry.includes(56900)) ipcPortsToTry.push(56900);

  if (connTextRpc) connTextRpc.textContent = "RPC: Checking...";
  if (dotRpc) dotRpc.className = "dot";
  if (connTextIpc) connTextIpc.textContent = "IPC: Checking...";
  if (dotIpc) dotIpc.className = "dot";
  refreshBtn.classList.add('spinning');

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

    // 1. Query Bengal DM app backend on configured IPC port or fallback ports
    let bdmOnline = false;
    let bdmVersion = "";
    let bdmData = null;
    let boundIpcPort = effectiveIpcPort;

    for (const tryPort of ipcPortsToTry) {
      try {
        const resp = await fetch(`http://127.0.0.1:${tryPort}/`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          signal: controller.signal
        });
        if (resp && resp.ok) {
          bdmData = await resp.json();
          bdmOnline = true;
          bdmVersion = bdmData.version || "";
          boundIpcPort = bdmData.ipc_port || tryPort;
          break;
        }
      } catch {
        // Continue to next candidate port
      }
    }

    const ipcPortInput = document.getElementById('ipc-port');
    const ipcBadge = document.getElementById('ipc-port-status');

    if (bdmOnline) {
      if (dotIpc) dotIpc.className = "dot online";
      const formattedVer = formatAppVersion(bdmVersion);
      const isFallback = Boolean(bdmData && bdmData.is_fallback);

      if (isFallback || boundIpcPort !== effectiveIpcPort) {
        if (connTextIpc) {
          connTextIpc.textContent = `IPC: Connected (${boundIpcPort})`;
          connTextIpc.title = `Connected via backup port ${boundIpcPort} (primary port was occupied)`;
        }
      } else {
        if (connTextIpc) {
          connTextIpc.textContent = formattedVer ? `IPC: Connected (${formattedVer})` : "IPC: Connected";
          connTextIpc.title = `IPC: Connected (Port ${boundIpcPort})`;
        }
      }

      if (aboutAppVer) {
        aboutAppVer.textContent = formattedVer || "Connected (Active)";
      }

      if (ipcPortInput) {
        ipcPortInput.value = boundIpcPort;
      }

      if (ipcBadge) {
        if (isFallback || boundIpcPort !== (bdmData?.configured_ipc_port || 56900)) {
          const origPort = bdmData?.configured_ipc_port || 56900;
          ipcBadge.className = 'port-status-badge visible fallback';
          ipcBadge.textContent = `⚡ Active on backup port ${boundIpcPort} (primary port ${origPort} is occupied by another process)`;
        } else {
          ipcBadge.className = 'port-status-badge visible connected';
          ipcBadge.textContent = `● Active and connected on port ${boundIpcPort}`;
        }
      }

      chrome.storage.local.set({
        ipcPort: boundIpcPort,
        activeIpcPort: boundIpcPort,
        bdmVersion: bdmVersion
      });
    } else {
      if (dotIpc) {
        dotIpc.className = "dot offline";
        dotIpc.title = `Disconnected on port ${effectiveIpcPort}`;
      }
      if (connTextIpc) {
        connTextIpc.textContent = "IPC: Disconnected";
        connTextIpc.title = "Bengal DM application is not running or unreachable";
      }
      if (aboutAppVer) {
        aboutAppVer.textContent = "Disconnected (App Not Running)";
      }
      if (ipcBadge) {
        ipcBadge.className = 'port-status-badge visible disconnected';
        ipcBadge.textContent = `● Disconnected — Bengal DM is not running on port ${effectiveIpcPort} or backup ports`;
      }
    }

    // 2. Query Aria2 RPC
    const url = `http://127.0.0.1:${port}/jsonrpc`;
    const params = token ? [`token:${token}`] : [];
    const payload = { jsonrpc: "2.0", id: "settings-check", method: "aria2.getVersion", params: params };

    let ariaResponse = null;
    try {
      ariaResponse = await fetch(url, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    } catch {
      try {
        ariaResponse = await fetch(`http://localhost:${port}/jsonrpc`, {
          method: 'POST',
          headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: controller.signal
        });
      } catch {}
    }

    clearTimeout(timeoutId);

    let ariaOnline = false;
    if (ariaResponse && ariaResponse.ok) {
      try {
        const ariaData = await ariaResponse.json();
        if (ariaData && ariaData.result && ariaData.result.version) {
          ariaOnline = true;
          if (dotRpc) dotRpc.className = "dot online";
          if (connTextRpc) connTextRpc.textContent = `RPC: Connected (v${ariaData.result.version})`;
        } else if (ariaData && ariaData.error) {
          if (dotRpc) dotRpc.className = "dot offline";
          if (connTextRpc) connTextRpc.textContent = "RPC: Auth Error";
        } else {
          if (dotRpc) dotRpc.className = "dot offline";
          if (connTextRpc) connTextRpc.textContent = "RPC: Invalid Response";
        }
      } catch {
        if (dotRpc) dotRpc.className = "dot offline";
        if (connTextRpc) connTextRpc.textContent = "RPC: Error";
      }
    } else {
      if (dotRpc) dotRpc.className = "dot offline";
      if (connTextRpc) connTextRpc.textContent = "RPC: Disconnected";
    }

    // Notify background script of connection status
    chrome.runtime.sendMessage({
      action: "update_connection_status",
      online: ariaOnline || bdmOnline,
      ariaOnline,
      bdmOnline
    }).catch(() => {});

  } catch (error) {
    if (dotRpc) dotRpc.className = "dot offline";
    if (connTextRpc) connTextRpc.textContent = "RPC: Disconnected";
    if (dotIpc) dotIpc.className = "dot offline";
    if (connTextIpc) connTextIpc.textContent = "IPC: Disconnected";
    const ipcBadge = document.getElementById('ipc-port-status');
    if (ipcBadge) {
      ipcBadge.className = 'port-status-badge visible disconnected';
      ipcBadge.textContent = "● Disconnected — Unable to contact Bengal DM";
    }
    chrome.runtime.sendMessage({ action: "update_connection_status", online: false }).catch(() => {});
  } finally {
    refreshBtn.classList.remove('spinning');
  }
}

// --- WHITELIST & BLACKLIST FILTER TAGS MANAGEMENT ---
const filterLists = {
  whitelistUrls: [],
  whitelistExts: [],
  blacklistUrls: [],
  blacklistExts: []
};

function normalizeUrlOrDomainInput(input) {
  if (!input || typeof input !== 'string') return "";
  let val = input.trim().toLowerCase();
  // If user pasted a full URL with protocol and no path or just root path (e.g. https://example.com/)
  try {
    if (val.startsWith('http://') || val.startsWith('https://')) {
      const parsed = new URL(val);
      if (!parsed.pathname || parsed.pathname === '/') {
        return parsed.hostname;
      }
      return parsed.hostname + parsed.pathname.replace(/\/$/, '');
    }
  } catch (e) {}

  // Strip trailing slash
  val = val.replace(/\/+$/, '');
  return val;
}

function renderTagList(containerId, listKey) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';

  filterLists[listKey].forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'listbox-row';

    const textSpan = document.createElement('span');
    textSpan.className = 'listbox-text';
    textSpan.textContent = item;
    row.appendChild(textSpan);

    const removeBtn = document.createElement('button');
    removeBtn.className = 'listbox-remove';
    removeBtn.innerHTML = '&times;';
    removeBtn.title = 'Remove';
    removeBtn.addEventListener('click', () => {
      filterLists[listKey].splice(index, 1);
      renderTagList(containerId, listKey);
      // Auto-persist filter list updates
      const updatePayload = {};
      updatePayload[listKey] = filterLists[listKey];
      chrome.storage.local.set(updatePayload);
    });

    row.appendChild(removeBtn);
    container.appendChild(row);
  });
}

function setupFilterInput(inputId, buttonId, containerId, listKey, isExtension = false) {
  const input = document.getElementById(inputId);
  const button = document.getElementById(buttonId);

  const addItem = () => {
    let val = input.value.trim();
    if (!val) return;

    if (isExtension) {
      val = val.toLowerCase();
      if (!val.startsWith('.')) {
        val = '.' + val;
      }
    } else {
      val = normalizeUrlOrDomainInput(val);
    }

    if (val && !filterLists[listKey].includes(val)) {
      filterLists[listKey].push(val);
      renderTagList(containerId, listKey);
      // Auto-persist filter item
      const updatePayload = {};
      updatePayload[listKey] = filterLists[listKey];
      chrome.storage.local.set(updatePayload);
    }
    input.value = '';
    input.focus();
  };

  if (button) button.addEventListener('click', addItem);
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addItem();
      }
    });
  }
}

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
  // 1. Sidebar Navigation
  const navItems = document.querySelectorAll('.nav-item');
  const tabPanes = document.querySelectorAll('.tab-pane');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      navItems.forEach(n => n.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      item.classList.add('active');
      const pane = document.getElementById(targetTab);
      if (pane) pane.classList.add('active');
    });
  });

  // 2. Theme Radio Cards (with instant auto-save)
  const themeRadios = document.querySelectorAll('input[name="theme-radio"]');
  themeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      const selectedTheme = radio.value;
      applyTheme(selectedTheme);
      chrome.storage.local.set({ theme: selectedTheme }, () => {
        showToast('Theme updated ✓', 'success');
      });
    });
  });

  // 3. Interception Toggle Listener
  const interceptionCheckbox = document.getElementById('options-enable-interception');
  if (interceptionCheckbox) {
    interceptionCheckbox.addEventListener('change', (e) => {
      chrome.storage.local.set({ enableInterception: e.target.checked }, () => {
        showToast(e.target.checked ? 'Interception enabled ✓' : 'Interception paused ✓', 'success');
      });
    });
  }

  const mediaSniffingCheckbox = document.getElementById('options-enable-media-sniffing');
  if (mediaSniffingCheckbox) {
    mediaSniffingCheckbox.addEventListener('change', (e) => {
      chrome.storage.local.set({ enableMediaSniffing: e.target.checked }, () => {
        showToast(e.target.checked ? 'Media stream capture enabled ✓' : 'Media stream capture paused ✓', 'success');
      });
    });
  }

  const videoPositionSelect = document.getElementById('options-video-panel-position');
  if (videoPositionSelect) {
    videoPositionSelect.addEventListener('change', (e) => {
      chrome.storage.local.set({ videoPanelPosition: e.target.value }, () => {
        showToast('Video panel position updated ✓', 'success');
      });
    });
  }

  // 4. Setup Filter Inputs
  setupFilterInput('whitelist-url-input', 'add-whitelist-url', 'whitelist-url-tags', 'whitelistUrls', false);
  setupFilterInput('whitelist-ext-input', 'add-whitelist-ext', 'whitelist-ext-tags', 'whitelistExts', true);
  setupFilterInput('blacklist-url-input', 'add-blacklist-url', 'blacklist-url-tags', 'blacklistUrls', false);
  setupFilterInput('blacklist-ext-input', 'add-blacklist-ext', 'blacklist-ext-tags', 'blacklistExts', true);

  // 5. Load from storage
  const defaults = {
    port: 56800,
    ipcPort: 56900,
    token: "",
    theme: "system",
    bdmVersion: "",
    enableInterception: true,
    enableMediaSniffing: true,
    videoPanelPosition: "top-right",
    whitelistUrls: [],
    whitelistExts: [],
    blacklistUrls: [],
    blacklistExts: []
  };

  chrome.storage.local.get(defaults, (items) => {
    let port = items.port;
    if (port === 6800 || port === 6801 || port === 50001) {
      port = 56800;
      chrome.storage.local.set({ port: 56800 });
    }

    const ipcPort = parseInt(items.ipcPort, 10) || 56900;
    const ipcPortInput = document.getElementById('ipc-port');
    if (ipcPortInput) ipcPortInput.value = ipcPort;

    document.getElementById('port').value = port;
    document.getElementById('token').value = items.token || '';
    if (interceptionCheckbox) {
      interceptionCheckbox.checked = (items.enableInterception !== false);
    }
    if (mediaSniffingCheckbox) {
      mediaSniffingCheckbox.checked = (items.enableMediaSniffing !== false);
    }
    if (videoPositionSelect) {
      videoPositionSelect.value = items.videoPanelPosition || 'top-right';
    }

    applyTheme(items.theme || 'system');

    if (items.bdmVersion) {
      const formatted = formatAppVersion(items.bdmVersion);
      const aboutAppVer = document.getElementById('about-app-version');
      if (aboutAppVer) aboutAppVer.textContent = formatted;
    }

    const manifest = (chrome.runtime && chrome.runtime.getManifest) ? chrome.runtime.getManifest() : null;
    if (manifest && manifest.version) {
      const extVerElem = document.getElementById('about-ext-version');
      if (extVerElem) extVerElem.textContent = `${manifest.version} (Manifest V${manifest.manifest_version || 3})`;
    }

    filterLists.whitelistUrls = Array.isArray(items.whitelistUrls) ? [...items.whitelistUrls] : [];
    filterLists.whitelistExts = Array.isArray(items.whitelistExts) ? [...items.whitelistExts] : [];
    filterLists.blacklistUrls = Array.isArray(items.blacklistUrls) ? [...items.blacklistUrls] : [];
    filterLists.blacklistExts = Array.isArray(items.blacklistExts) ? [...items.blacklistExts] : [];

    renderTagList('whitelist-url-tags', 'whitelistUrls');
    renderTagList('whitelist-ext-tags', 'whitelistExts');
    renderTagList('blacklist-url-tags', 'blacklistUrls');
    renderTagList('blacklist-ext-tags', 'blacklistExts');

    testConnection(port, items.token || '', ipcPort);
  });

  // 6. Button Listeners
  document.getElementById('refresh-btn').addEventListener('click', () => {
    const port = parseInt(document.getElementById('port').value, 10) || 56800;
    const ipcPort = parseInt(document.getElementById('ipc-port')?.value, 10) || 56900;
    const token = document.getElementById('token').value.trim();
    testConnection(port, token, ipcPort);
  });

  document.getElementById('save').addEventListener('click', () => {
    const port = parseInt(document.getElementById('port').value, 10) || 56800;
    const ipcPort = parseInt(document.getElementById('ipc-port')?.value, 10) || 56900;
    const token = document.getElementById('token').value.trim();
    const selectedRadio = document.querySelector('input[name="theme-radio"]:checked');
    const theme = selectedRadio ? selectedRadio.value : 'system';
    const enableInterception = interceptionCheckbox ? interceptionCheckbox.checked : true;
    const enableMediaSniffing = mediaSniffingCheckbox ? mediaSniffingCheckbox.checked : true;
    const videoPanelPosition = videoPositionSelect ? videoPositionSelect.value : 'top-right';

    const payload = {
      host: "localhost",
      port,
      ipcPort,
      token,
      theme,
      enableInterception,
      enableMediaSniffing,
      videoPanelPosition,
      whitelistUrls: filterLists.whitelistUrls,
      whitelistExts: filterLists.whitelistExts,
      blacklistUrls: filterLists.blacklistUrls,
      blacklistExts: filterLists.blacklistExts
    };

    chrome.storage.local.set(payload, () => {
      applyTheme(theme);
      showToast('Settings saved successfully ✓', 'success');
      testConnection(port, token, ipcPort);
    });
  });

  document.getElementById('sync').addEventListener('click', async () => {
    showToast('Syncing Bengal DM & Aria2 settings...', 'success');

    const enteredIpcPort = parseInt(document.getElementById('ipc-port')?.value, 10) || 56900;
    let response = null;
    const portsToTry = [enteredIpcPort];
    for (const fp of [26900, 26901, 26902]) {
      if (!portsToTry.includes(fp)) portsToTry.push(fp);
    }
    if (!portsToTry.includes(56900)) portsToTry.push(56900);

    for (const testPort of portsToTry) {
      try {
        response = await fetch(`http://127.0.0.1:${testPort}/`, { method: 'GET' });
        if (response && response.ok) break;
      } catch {
        try {
          response = await fetch(`http://localhost:${testPort}/`, { method: 'GET' });
          if (response && response.ok) break;
        } catch {}
      }
    }

    try {
      if (!response || !response.ok) throw new Error("Bengal DM IPC not responding");

      const data = await response.json();
      const savePayload = {};

      if (data.ipc_port) {
        document.getElementById('ipc-port').value = data.ipc_port;
        savePayload.ipcPort = data.ipc_port;
        savePayload.activeIpcPort = data.ipc_port;
      }

      if (data.aria2) {
        const { port, token } = data.aria2;
        document.getElementById('port').value = port;
        document.getElementById('token').value = token || '';
        savePayload.port = port;
        savePayload.token = token || '';
      }

      if (data.version) {
        savePayload.bdmVersion = data.version;
        const aboutAppVer = document.getElementById('about-app-version');
        if (aboutAppVer) aboutAppVer.textContent = formatAppVersion(data.version);
      }

      chrome.storage.local.set(savePayload, () => {
        showToast('Settings Synced from Bengal DM ✓', 'success');
        testConnection(savePayload.port || 56800, savePayload.token || '', savePayload.ipcPort || enteredIpcPort);
      });
    } catch (err) {
      showToast('Sync Failed (Is Bengal DM running?)', 'error');
    }
  });

  document.getElementById('reset').addEventListener('click', () => {
    const defaults = {
      host: "localhost",
      port: 56800,
      ipcPort: 56900,
      token: "",
      theme: "system",
      enableInterception: true,
      enableMediaSniffing: true,
      videoPanelPosition: "top-right",
      whitelistUrls: [],
      whitelistExts: [],
      blacklistUrls: [],
      blacklistExts: []
    };

    chrome.storage.local.set(defaults, () => {
      document.getElementById('port').value = defaults.port;
      const ipcInput = document.getElementById('ipc-port');
      if (ipcInput) ipcInput.value = defaults.ipcPort;
      document.getElementById('token').value = defaults.token;
      if (interceptionCheckbox) interceptionCheckbox.checked = true;
      if (mediaSniffingCheckbox) mediaSniffingCheckbox.checked = true;
      if (videoPositionSelect) videoPositionSelect.value = 'top-right';
      applyTheme(defaults.theme);

      filterLists.whitelistUrls = [];
      filterLists.whitelistExts = [];
      filterLists.blacklistUrls = [];
      filterLists.blacklistExts = [];

      renderTagList('whitelist-url-tags', 'whitelistUrls');
      renderTagList('whitelist-ext-tags', 'whitelistExts');
      renderTagList('blacklist-url-tags', 'blacklistUrls');
      renderTagList('blacklist-ext-tags', 'blacklistExts');

      testConnection(defaults.port, defaults.token, defaults.ipcPort);
      showToast('Defaults restored ✓', 'success');
    });
  });
});
