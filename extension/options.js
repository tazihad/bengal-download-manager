// --- THEME MANAGEMENT ---
function applyTheme(theme) {
  if (theme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }

  // Sync radio buttons
  const radios = document.querySelectorAll('input[name="theme-radio"]');
  radios.forEach(radio => {
    radio.checked = (radio.value === theme);
  });

  const themeSelect = document.getElementById('theme');
  if (themeSelect) {
    themeSelect.value = theme;
  }
}

// System theme change listener
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  chrome.storage.local.get({ theme: 'system' }, (items) => {
    if (items.theme === 'system') {
      applyTheme('system');
    }
  });
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

// --- ARIA2 CONNECTION TEST ---
async function testConnection(port, token) {
  const connText = document.getElementById('conn-text');
  const dot = document.getElementById('dot');
  const refreshBtn = document.getElementById('refresh-btn');

  if (!connText || !dot || !refreshBtn) return;

  connText.textContent = "Connecting...";
  dot.className = "dot";
  refreshBtn.classList.add('spinning');

  try {
    const url = `http://127.0.0.1:${port}/jsonrpc`;
    const params = token ? [`token:${token}`] : [];
    const payload = { jsonrpc: "2.0", id: "settings-check", method: "aria2.getVersion", params: params };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

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
    if (data.result && data.result.version) {
      dot.className = "dot online";
      connText.textContent = `Connected (v${data.result.version})`;
    } else if (data.error) {
      dot.className = "dot offline";
      connText.textContent = "Auth Error";
    } else {
      throw new Error("Invalid response");
    }
  } catch (error) {
    dot.className = "dot offline";
    connText.textContent = error.name === 'AbortError' ? "Timeout" : "Disconnected";
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

function renderTagList(containerId, listKey) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';

  filterLists[listKey].forEach((item, index) => {
    const chip = document.createElement('div');
    chip.className = 'tag-chip';

    const textSpan = document.createElement('span');
    textSpan.textContent = item;
    chip.appendChild(textSpan);

    const removeBtn = document.createElement('button');
    removeBtn.className = 'tag-remove';
    removeBtn.innerHTML = '&times;';
    removeBtn.title = 'Remove';
    removeBtn.addEventListener('click', () => {
      filterLists[listKey].splice(index, 1);
      renderTagList(containerId, listKey);
    });

    chip.appendChild(removeBtn);
    container.appendChild(chip);
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
    }

    if (!filterLists[listKey].includes(val)) {
      filterLists[listKey].push(val);
      renderTagList(containerId, listKey);
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

  // 2. Theme Radio Cards
  const themeRadios = document.querySelectorAll('input[name="theme-radio"]');
  themeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      applyTheme(radio.value);
    });
  });

  // 3. Setup Filter Inputs
  setupFilterInput('whitelist-url-input', 'add-whitelist-url', 'whitelist-url-tags', 'whitelistUrls', false);
  setupFilterInput('whitelist-ext-input', 'add-whitelist-ext', 'whitelist-ext-tags', 'whitelistExts', true);
  setupFilterInput('blacklist-url-input', 'add-blacklist-url', 'blacklist-url-tags', 'blacklistUrls', false);
  setupFilterInput('blacklist-ext-input', 'add-blacklist-ext', 'blacklist-ext-tags', 'blacklistExts', true);

  // 4. Load from storage
  const defaults = {
    port: 56800,
    token: "",
    theme: "system",
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

    applyTheme(items.theme || 'system');

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

  // 5. Button Listeners
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

    const payload = {
      host: "localhost",
      port,
      token,
      theme,
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

        chrome.storage.local.set({
          host: "localhost",
          port,
          token: token || '',
          theme,
          whitelistUrls: filterLists.whitelistUrls,
          whitelistExts: filterLists.whitelistExts,
          blacklistUrls: filterLists.blacklistUrls,
          blacklistExts: filterLists.blacklistExts
        }, () => {
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
      whitelistUrls: [],
      whitelistExts: [],
      blacklistUrls: [],
      blacklistExts: []
    };

    chrome.storage.local.set(defaults, () => {
      document.getElementById('port').value = defaults.port;
      document.getElementById('token').value = defaults.token;
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
