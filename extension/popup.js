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

// Live storage sync
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && changes.theme) {
    applyTheme(changes.theme.newValue);
  }
});

document.getElementById('options-link').addEventListener('click', (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
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

chrome.storage.local.get({ theme: "system", port: 56800, token: "", bdmVersion: "" }, async (items) => {
  applyTheme(items.theme || "system");

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
