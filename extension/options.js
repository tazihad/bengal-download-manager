function applyTheme(theme) {
  if (theme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }
}

async function testConnection(port, token) {
  const connText = document.getElementById('conn-text');
  const dot = document.getElementById('dot');
  const refreshBtn = document.getElementById('refresh-btn');

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
    } catch (e) {
        // Fallback to localhost if 127.0.0.1 fails
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

document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get({ port: 56800, token: "", theme: "system" }, (items) => {
    let port = items.port;
    if (port === 6800 || port === 6801 || port === 50001) {
      port = 56800;
      chrome.storage.local.set({ port: 56800 });
    }
    document.getElementById('port').value = port;
    document.getElementById('token').value = items.token;
    document.getElementById('theme').value = items.theme;
    applyTheme(items.theme);
    testConnection(port, items.token);
  });
});

document.getElementById('sync').addEventListener('click', async () => {
  const statusMsg = document.getElementById('status-msg');
  statusMsg.textContent = 'Syncing...';
  statusMsg.style.color = 'var(--text)';

  try {
    const response = await fetch("http://127.0.0.1:9000/", { method: 'GET' });
    if (!response.ok) throw new Error("App not responding");
    
    const data = await response.json();
    if (data.aria2) {
      const { port, token } = data.aria2;
      document.getElementById('port').value = port;
      document.getElementById('token').value = token;
      
      const theme = document.getElementById('theme').value;
      
      chrome.storage.local.set({ host: "localhost", port, token, theme }, () => {
        statusMsg.textContent = 'Synced & Saved ✓';
        statusMsg.style.color = 'var(--success)';
        setTimeout(() => statusMsg.textContent = '', 2000);
        testConnection(port, token);
      });
    }
  } catch (err) {
    statusMsg.textContent = 'Sync Failed (Is App Running?)';
    statusMsg.style.color = 'var(--error)';
    setTimeout(() => statusMsg.textContent = '', 2000);
  }
});

document.getElementById('reset').addEventListener('click', () => {
  const defaults = { host: "localhost", port: 56800, token: "", theme: "system" };
  chrome.storage.local.set(defaults, () => {
    document.getElementById('port').value = defaults.port;
    document.getElementById('token').value = defaults.token;
    document.getElementById('theme').value = defaults.theme;
    applyTheme(defaults.theme);
    testConnection(defaults.port, defaults.token);
    
    const statusMsg = document.getElementById('status-msg');
    statusMsg.textContent = 'Reset to Defaults ✓';
    statusMsg.style.color = 'var(--success)';
    setTimeout(() => statusMsg.textContent = '', 2000);
  });
});

document.getElementById('refresh-btn').addEventListener('click', () => {
  const port = parseInt(document.getElementById('port').value, 10) || 56800;
  const token = document.getElementById('token').value.trim();
  testConnection(port, token);
});

document.getElementById('save').addEventListener('click', () => {
  const port = parseInt(document.getElementById('port').value, 10) || 56800;
  const token = document.getElementById('token').value.trim();
  const theme = document.getElementById('theme').value;

  chrome.storage.local.set({ host: "localhost", port, token, theme }, () => {
    applyTheme(theme);
    const statusMsg = document.getElementById('status-msg');
    statusMsg.textContent = 'Settings Saved ✓';
    statusMsg.style.color = 'var(--success)';
    setTimeout(() => statusMsg.textContent = '', 2000);
    testConnection(port, token);
  });
});
