function applyTheme(theme) {
  if (theme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }
}

async function testConnection(host, port) {
  const connText = document.getElementById('conn-text');
  const dot = document.getElementById('dot');
  const refreshBtn = document.getElementById('refresh-btn');

  connText.textContent = "Connecting...";
  dot.className = "dot";
  refreshBtn.classList.add('spinning');

  try {
    const url = `http://${host}:${port}/jsonrpc`;
    const payload = { jsonrpc: "2.0", id: "settings-check", method: "aria2.getVersion" };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      if (data.result && data.result.version) {
        dot.className = "dot online";
        connText.textContent = "Connected";
      }
    } else {
      throw new Error("Bad HTTP status");
    }
  } catch (error) {
    dot.className = "dot offline";
    connText.textContent = error.name === 'AbortError' ? "Timeout" : "Disconnected";
  } finally {
    refreshBtn.classList.remove('spinning');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get({ host: "localhost", port: 50001, theme: "system" }, (items) => {
    document.getElementById('host').value = items.host;
    document.getElementById('port').value = items.port;
    document.getElementById('theme').value = items.theme;
    applyTheme(items.theme);
    testConnection(items.host, items.port);
  });
});

document.getElementById('refresh-btn').addEventListener('click', () => {
  const host = document.getElementById('host').value.trim();
  const port = parseInt(document.getElementById('port').value, 10);
  testConnection(host, port);
});

document.getElementById('save').addEventListener('click', () => {
  const host = document.getElementById('host').value.trim();
  const port = parseInt(document.getElementById('port').value, 10);
  const theme = document.getElementById('theme').value;

  chrome.storage.local.set({ host, port, theme }, () => {
    applyTheme(theme);
    const statusMsg = document.getElementById('status-msg');
    statusMsg.textContent = 'Settings Saved ✓';
    statusMsg.style.color = 'var(--success)';
    setTimeout(() => statusMsg.textContent = '', 2000);
    testConnection(host, port);
  });
});