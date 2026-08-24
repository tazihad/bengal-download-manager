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
      const connText = document.getElementById('conn-text');
      const dot = document.getElementById('dot');
      if (connText && dot && dot.classList.contains('online') && formatted) {
        connText.textContent = `Connected (${formatted})`;
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
async function testConnection(port, token) {
  const connText = document.getElementById('conn-text');
  const dot = document.getElementById('dot');
  const refreshBtn = document.getElementById('refresh-btn');
  const aboutAppVer = document.getElementById('about-app-version');

  if (!connText || !dot || !refreshBtn) return;

  connText.textContent = "Connecting...";
  dot.className = "dot";
  refreshBtn.classList.add('spinning');

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

    // 1. Query Bengal DM app backend to verify app is running and retrieve BDM version
    let bdmData = null;
    try {
      const bdmResp = await fetch("http://127.0.0.1:9000/", {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal
      });
      if (bdmResp.ok) {
        bdmData = await bdmResp.json();
      }
    } catch {
      try {
        const bdmResp = await fetch("http://localhost:9000/", {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          signal: controller.signal
        });
        if (bdmResp.ok) {
          bdmData = await bdmResp.json();
        }
      } catch {}
    }

    // 2. Query Aria2 RPC
    const url = `http://127.0.0.1:${port}/jsonrpc`;
    const params = token ? [`token:${token}`] : [];
    const payload = { jsonrpc: "2.0", id: "settings-check", method: "aria2.getVersion", params: params };

    let ariaResponse;
    try {
      ariaResponse = await fetch(url, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    } catch {
      ariaResponse = await fetch(`http://localhost:${port}/jsonrpc`, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
    }

    clearTimeout(timeoutId);

    const ariaData = await ariaResponse.json();

    if (ariaData && ariaData.result && ariaData.result.version) {
      dot.className = "dot online";

      let versionStr = (bdmData && bdmData.version) ? bdmData.version : "";
      if (versionStr) {
        chrome.storage.local.set({ bdmVersion: versionStr });
      } else {
        const cached = await new Promise(r => chrome.storage.local.get({ bdmVersion: "" }, r));
        versionStr = cached.bdmVersion || "";
      }

      const formattedVersion = formatAppVersion(versionStr);
      connText.textContent = formattedVersion ? `Connected (${formattedVersion})` : "Connected";
      if (aboutAppVer) {
        aboutAppVer.textContent = formattedVersion || "Connected (Active)";
      }
      chrome.runtime.sendMessage({ action: "update_connection_status", online: true }).catch(() => {});
    } else if (ariaData && ariaData.error) {
      dot.className = "dot offline";
      connText.textContent = "Auth Error";
      if (aboutAppVer) aboutAppVer.textContent = "Authentication Error (Invalid Token)";
      chrome.runtime.sendMessage({ action: "update_connection_status", online: false }).catch(() => {});
    } else {
      throw new Error("Invalid response");
    }
  } catch (error) {
    dot.className = "dot offline";
    connText.textContent = error.name === 'AbortError' ? "Timeout" : "Disconnected";
    if (aboutAppVer) aboutAppVer.textContent = "Disconnected (App Not Running)";
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
  // If user pasted a full URL with protocol and no path or just root path e.g. https://mirror.xeonbd.com/
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

  // 4. Setup Filter Inputs
  setupFilterInput('whitelist-url-input', 'add-whitelist-url', 'whitelist-url-tags', 'whitelistUrls', false);
  setupFilterInput('whitelist-ext-input', 'add-whitelist-ext', 'whitelist-ext-tags', 'whitelistExts', true);
  setupFilterInput('blacklist-url-input', 'add-blacklist-url', 'blacklist-url-tags', 'blacklistUrls', false);
  setupFilterInput('blacklist-ext-input', 'add-blacklist-ext', 'blacklist-ext-tags', 'blacklistExts', true);

  // 5. Load from storage
  const defaults = {
    port: 56800,
    token: "",
    theme: "system",
    bdmVersion: "",
    enableInterception: true,
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

    document.getElementById('port').value = port;
    document.getElementById('token').value = items.token || '';
    if (interceptionCheckbox) {
      interceptionCheckbox.checked = (items.enableInterception !== false);
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

    testConnection(port, items.token || '');
  });

  // 6. Button Listeners
  document.getElementById('refresh-btn').addEventListener('click', () => {
    const port = parseInt(document.getElementById('port').value, 10) || 56800;
    const token = document.getElementById('token').value.trim();
    testConnection(port, token);
  });

  document.getElementById('save').addEventListener('click', () => {
    const port = parseInt(document.getElementById('port').value, 10) || 56800;
    const token = document.getElementById('token').value.trim();
    const selectedRadio = document.querySelector('input[name="theme-radio"]:checked');
    const theme = selectedRadio ? selectedRadio.value : 'system';
    const enableInterception = interceptionCheckbox ? interceptionCheckbox.checked : true;

    const payload = {
      host: "localhost",
      port,
      token,
      theme,
      enableInterception,
      whitelistUrls: filterLists.whitelistUrls,
      whitelistExts: filterLists.whitelistExts,
      blacklistUrls: filterLists.blacklistUrls,
      blacklistExts: filterLists.blacklistExts
    };

    chrome.storage.local.set(payload, () => {
      applyTheme(theme);
      showToast('Settings saved successfully ✓', 'success');
      testConnection(port, token);
    });
  });

  document.getElementById('sync').addEventListener('click', async () => {
    showToast('Syncing configuration...', 'success');

    try {
      const response = await fetch("http://127.0.0.1:9000/", { method: 'GET' });
      if (!response.ok) throw new Error("App not responding");

      const data = await response.json();
      if (data.aria2) {
        const { port, token } = data.aria2;
        document.getElementById('port').value = port;
        document.getElementById('token').value = token || '';

        const selectedRadio = document.querySelector('input[name="theme-radio"]:checked');
        const theme = selectedRadio ? selectedRadio.value : 'system';
        const enableInterception = interceptionCheckbox ? interceptionCheckbox.checked : true;

        const savePayload = {
          host: "localhost",
          port,
          token: token || '',
          theme,
          enableInterception,
          whitelistUrls: filterLists.whitelistUrls,
          whitelistExts: filterLists.whitelistExts,
          blacklistUrls: filterLists.blacklistUrls,
          blacklistExts: filterLists.blacklistExts
        };

        if (data.version) {
          savePayload.bdmVersion = data.version;
          const aboutAppVer = document.getElementById('about-app-version');
          if (aboutAppVer) aboutAppVer.textContent = formatAppVersion(data.version);
        }

        chrome.storage.local.set(savePayload, () => {
          showToast('Synced & Saved ✓', 'success');
          testConnection(port, token || '');
        });
      }
    } catch (err) {
      showToast('Sync Failed (Is Bengal DM running?)', 'error');
    }
  });

  document.getElementById('reset').addEventListener('click', () => {
    const defaults = {
      host: "localhost",
      port: 56800,
      token: "",
      theme: "system",
      enableInterception: true,
      whitelistUrls: [],
      whitelistExts: [],
      blacklistUrls: [],
      blacklistExts: []
    };

    chrome.storage.local.set(defaults, () => {
      document.getElementById('port').value = defaults.port;
      document.getElementById('token').value = defaults.token;
      if (interceptionCheckbox) interceptionCheckbox.checked = true;
      applyTheme(defaults.theme);

      filterLists.whitelistUrls = [];
      filterLists.whitelistExts = [];
      filterLists.blacklistUrls = [];
      filterLists.blacklistExts = [];

      renderTagList('whitelist-url-tags', 'whitelistUrls');
      renderTagList('whitelist-ext-tags', 'whitelistExts');
      renderTagList('blacklist-url-tags', 'blacklistUrls');
      renderTagList('blacklist-ext-tags', 'blacklistExts');

      showToast('Reset to Defaults ✓', 'success');
      testConnection(defaults.port, defaults.token);
    });
  });
});
